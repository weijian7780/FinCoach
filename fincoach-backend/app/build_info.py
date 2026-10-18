"""Build identity and runtime fingerprinting for FinCoach backend."""
from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Sensitive keywords: any key containing these substrings is excluded from config fingerprinting.
SECRET_KEYWORDS = (
    "KEY",
    "SECRET",
    "PASSWORD",
    "TOKEN",
    "CREDENTIAL",
    "DATABASE_URL",
    "PRIVATE",
    "AUTH",
    "COOKIE",
    "SESSION",
)

IGNORED_DIRS = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    ".pytest_cache",
    "node_modules",
    "evaluation-results",
    ".deploy-stage",
    "docs",
    "artifacts",
    "dist",
    ".claude",
    ".gemini",
}

IGNORED_EXTENSIONS = {
    ".pyc",
    ".pyo",
    ".pyd",
    ".log",
    ".tmp",
    ".swp",
    ".tar.gz",
    ".zip",
    ".png",
    ".jpg",
    ".jpeg",
    ".ico",
}


def is_secret_key(key: str) -> bool:
    upper = key.upper()
    return any(keyword in upper for keyword in SECRET_KEYWORDS)


def sanitize_public_config(config: dict[str, Any]) -> dict[str, Any]:
    """Retain only non-secret, JSON-serializable configuration items."""
    sanitized: dict[str, Any] = {}
    for k, v in config.items():
        if is_secret_key(k):
            continue
        # Convert non-serializable objects to string or skip
        if isinstance(v, (str, int, float, bool)) or v is None:
            sanitized[k] = v
        elif isinstance(v, (list, tuple)):
            sanitized[k] = list(v)
        elif isinstance(v, dict):
            sanitized[k] = sanitize_public_config(v)
        else:
            sanitized[k] = str(v)
    return sanitized


def get_public_config() -> dict[str, Any]:
    """Extract approved non-secret configuration from app.config."""
    from app import config as app_cfg

    public_keys = [
        "ADMIN_PANEL_ENABLED",
        "ACCOUNT_ACCESS_ENFORCED",
        "EMBEDDING_MODEL",
        "EMBEDDING_DIM",
        "LLM_PRIMARY_MODEL",
        "LLM_PRIMARY_MAX_TOKENS",
        "LLM_MODEL",
        "GEMINI_RECEIPT_MODEL",
        "RECEIPT_CLEANUP_TIMEOUT_SECONDS",
        "TYPESAFE_CATEGORY_ENABLED",
        "TYPESAFE_MODEL",
        "TYPESAFE_TIMEOUT_SECONDS",
        "COACH_REQUEST_DEADLINE_SECONDS",
        "COACH_RESEARCH_POLICY_ENABLED",
        "COACH_STRUCTURED_TIMEOUT_SECONDS",
        "LLM_PRIMARY_TIMEOUT_SECONDS",
        "LLM_FALLBACK_TIMEOUT_SECONDS",
        "COACH_RESEARCH_ANSWER_RESERVE_SECONDS",
        "GROUNDING_VERIFIER_TIMEOUT_SECONDS",
        "CORS_ORIGINS",
    ]
    raw: dict[str, Any] = {}
    for key in public_keys:
        if hasattr(app_cfg, key):
            raw[key] = getattr(app_cfg, key)
    return sanitize_public_config(raw)


def capture_build_info(root: Path, public_config: dict[str, Any]) -> dict[str, str]:
    """Capture runtime build identity, source fingerprint, and public config fingerprint.

    Computed once at application startup. Excludes secrets, .env files, and non-runtime caches.
    """
    root = Path(root).resolve()

    # 1. Config fingerprint
    clean_config = sanitize_public_config(public_config)
    config_json = json.dumps(clean_config, sort_keys=True, separators=(",", ":"))
    config_fingerprint = hashlib.sha256(config_json.encode("utf-8")).hexdigest()

    # 2. Source fingerprint: scan runtime source files
    scanned_files: list[Path] = []

    for item in root.rglob("*"):
        if not item.is_file():
            continue

        rel_parts = item.relative_to(root).parts
        # Check ignored directories
        if any(ignored in rel_parts for ignored in IGNORED_DIRS):
            continue

        # Ignore .env files
        filename = item.name
        if filename.startswith(".env"):
            continue

        # Ignore non-code binary/temp extensions
        if any(filename.endswith(ext) for ext in IGNORED_EXTENSIONS):
            continue

        # Only consider app/, corpus/, and approved root files
        first_part = rel_parts[0]
        if first_part in ("app", "corpus", "sql"):
            scanned_files.append(item)
        elif len(rel_parts) == 1 and item.suffix in (".py", ".txt", ".json"):
            scanned_files.append(item)

    # Sort deterministically by POSIX relative path
    scanned_files.sort(key=lambda p: p.relative_to(root).as_posix())

    hasher = hashlib.sha256()
    for f in scanned_files:
        rel_posix = f.relative_to(root).as_posix()
        file_hash = hashlib.sha256(f.read_bytes()).hexdigest()
        hasher.update(f"{rel_posix}:{file_hash}\n".encode("utf-8"))

    source_fingerprint = hasher.hexdigest()

    # 3. Build ID
    build_hasher = hashlib.sha256()
    build_hasher.update(f"{source_fingerprint}:{config_fingerprint}".encode("utf-8"))
    build_id = build_hasher.hexdigest()[:32]

    return {
        "build_id": build_id,
        "source_fingerprint": source_fingerprint,
        "config_fingerprint": config_fingerprint,
    }
