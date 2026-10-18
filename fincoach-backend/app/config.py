"""Central config — everything is read from environment variables (.env)."""
import os
from math import isfinite

from dotenv import load_dotenv

load_dotenv()


def _environment_flag(name: str, default: bool) -> bool:
    """Parse a conservative boolean environment flag."""
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _bounded_setting(name: str, default: float, minimum: float, maximum: float,
                     *, integer: bool = False) -> float | int:
    """Reject configuration that could turn bounded recovery into an open loop."""
    value = float(os.environ.get(name, str(default)))
    if not isfinite(value) or not minimum <= value <= maximum or (integer and not value.is_integer()):
        raise ValueError(f"{name} must be {'an integer' if integer else 'finite'} between {minimum} and {maximum}.")
    return int(value) if integer else value


# ---- Supabase (server-side) ----
# Use the SERVICE ROLE key here. It is secret and must live ONLY on this server,
# never in the mobile app.
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
SUPABASE_PUBLISHABLE_KEY = os.environ.get("SUPABASE_PUBLISHABLE_KEY", "")

# Admin routes remain unavailable until schema and access-control deployment are
# explicitly enabled together. This keeps existing installations compatible.
ADMIN_PANEL_ENABLED = _environment_flag("ADMIN_PANEL_ENABLED", False)
ACCOUNT_ACCESS_ENFORCED = _environment_flag("ACCOUNT_ACCESS_ENFORCED", False)
ADMIN_LOGIN_EMAIL = os.environ.get("ADMIN_LOGIN_EMAIL", "").strip()
ADMIN_STATIC_DIR = os.environ.get("ADMIN_STATIC_DIR", "")

# ---- Embeddings ----
# bge-m3 -> 1024 dimensions. If you change the model, change the SQL vector(N) too.
EMBEDDING_MODEL = os.environ.get("EMBEDDING_MODEL", "BAAI/bge-m3")
EMBEDDING_DIM = 1024

# ---- LLM providers (OpenAI-compatible) ----
# The optional primary provider is attempted first. The existing LLM_* provider
# remains the fallback so deployments without primary settings keep working.
LLM_PRIMARY_BASE_URL = os.environ.get("LLM_PRIMARY_BASE_URL", "")
LLM_PRIMARY_API_KEY = (
    os.environ.get("LLM_PRIMARY_API_KEY", "") or os.environ.get("GROQ_API_KEY", "")
)
LLM_PRIMARY_MODEL = os.environ.get("LLM_PRIMARY_MODEL", "")
LLM_PRIMARY_MAX_TOKENS = int(os.environ.get("LLM_PRIMARY_MAX_TOKENS", "2048"))
LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "")
LLM_API_KEY = os.environ.get("LLM_API_KEY", "")
LLM_MODEL = os.environ.get("LLM_MODEL", "")

# ---- Gemini-first receipt interpretation (image + supporting OCR lines) ----
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_RECEIPT_MODEL = os.environ.get("GEMINI_RECEIPT_MODEL", "gemini-3.5-flash-lite")

# Shared budget for Gemini extraction and at most one contract repair.
# Legacy text cleanup is not part of the active receipt extraction path.
RECEIPT_CLEANUP_TIMEOUT_SECONDS = float(
    # Leave enough time for the initial image verification and one contract
    # repair. Both requests still share this single bounded deadline.
    os.environ.get("RECEIPT_CLEANUP_TIMEOUT_SECONDS", "30")
)

# ---- Receipt category classification (TypeSafe Jev; receipt text only, never the image) ----
# Jev (TypeSafe Choice) is the primary, general category classifier. It is enabled
# automatically when a key is present; the SDK reads TYPESAFE_API_KEY from the env.
TYPESAFE_API_KEY = os.environ.get("TYPESAFE_API_KEY", "")
TYPESAFE_CATEGORY_ENABLED = _environment_flag(
    "TYPESAFE_CATEGORY_ENABLED", bool(TYPESAFE_API_KEY)
)
TYPESAFE_MODEL = os.environ.get("TYPESAFE_MODEL", "")
TYPESAFE_TIMEOUT_SECONDS = float(os.environ.get("TYPESAFE_TIMEOUT_SECONDS", "4"))
# Accept Jev's choice only at/above this confidence; below it we fall back. Tune
# against a labelled receipt set, do not assume this default is optimal.
TYPESAFE_CATEGORY_MIN_CONFIDENCE = float(
    os.environ.get("TYPESAFE_CATEGORY_MIN_CONFIDENCE", "0.6")
)
# BGE-M3 semantic fallback when Jev is unavailable or low-confidence. Off by
# default so unit tests and light deployments never load the ~2 GB embedding
# model just to categorise a receipt; production (embeddings already warm for
# RAG) can turn it on with RECEIPT_CATEGORY_EMBED_FALLBACK=1.
RECEIPT_CATEGORY_EMBED_FALLBACK = _environment_flag(
    "RECEIPT_CATEGORY_EMBED_FALLBACK", False
)

# Fetch a small candidate pool, then pass only close and relevant sources to
# the provider. This prevents overlapping or weak documents from diluting the
# grounded answer while keeping multilingual recall.
RETRIEVE_CANDIDATES = int(os.environ.get("RETRIEVE_CANDIDATES", "5"))
RETRIEVE_K = int(os.environ.get("RETRIEVE_K", "3"))
RETRIEVE_THRESHOLD = float(os.environ.get("RETRIEVE_THRESHOLD", "0.45"))
RETRIEVE_SCORE_MARGIN = float(os.environ.get("RETRIEVE_SCORE_MARGIN", "0.10"))

# ---- Web-research fallback (Tavily) ----
# Used ONLY when corpus retrieval is inadequate for a knowledge-route question.
# Corpus is always tried first. With no API key set, the fallback yields no web
# sources and the answer degrades to "insufficient evidence" rather than erroring.
TAVILY_API_KEY = os.environ.get("TAVILY_API_KEY", "")
WEB_FALLBACK_ENABLED = _environment_flag("WEB_FALLBACK_ENABLED", True)
COACH_RESEARCH_POLICY_ENABLED = _environment_flag("COACH_RESEARCH_POLICY_ENABLED", False)
COACH_PUBLIC_SOURCE_CACHE_ENABLED = _environment_flag("COACH_PUBLIC_SOURCE_CACHE_ENABLED", True)
# Guarded direct fetch of official tier-1/2 pages when Tavily extraction fails
# or is clipped (e.g. hosts that omit their TLS intermediate certificate).
COACH_DIRECT_FETCH_ENABLED = _environment_flag("COACH_DIRECT_FETCH_ENABLED", True)
COACH_PUBLIC_SOURCE_CACHE_DIR = os.environ.get("COACH_PUBLIC_SOURCE_CACHE_DIR", "data/public-source-cache")
COACH_PUBLIC_SOURCE_CACHE_TTL_SECONDS = _bounded_setting("COACH_PUBLIC_SOURCE_CACHE_TTL_SECONDS", 86400, 0, 86400)
COACH_CATEGORY_INTERPRETATION_ENABLED = _environment_flag(
    "COACH_CATEGORY_INTERPRETATION_ENABLED",
    # A category phrase that no exact catalog match resolves is handed to the
    # bounded interpreter ONLY when this is on. Off by default: clear reads stay
    # deterministic and zero-model, and an unfamiliar phrase clarifies rather than
    # silently guessing a filter.
    False,
)
# Behaviour-neutral: when true, run_research_policy emits structured
# "research_decision" logs (corpus vs web evidence, assessment status/missing) to
# diagnose why a stable/definitional query escalated to web. Off in prod.
COACH_RESEARCH_DEBUG = _environment_flag("COACH_RESEARCH_DEBUG", False)
COACH_STRUCTURED_TIMEOUT_SECONDS = _bounded_setting("COACH_STRUCTURED_TIMEOUT_SECONDS", 8, 1, 60)
COACH_RESEARCH_ANSWER_RESERVE_SECONDS = _bounded_setting(
    "COACH_RESEARCH_ANSWER_RESERVE_SECONDS", 30, 1, 60,
)
# Absolute stage bounds for the public-research answer path. They retain ONE
# request clock: research, the initial writer, the single corrective writer and
# the final semantic check all draw down the same deadline, and a small
# finalization margin is reserved before any optional model work starts.
COACH_FINALIZATION_RESERVE_SECONDS = _bounded_setting(
    "COACH_FINALIZATION_RESERVE_SECONDS", 5, 0, 30,
)
COACH_RESEARCH_PHASE_SECONDS = _bounded_setting(
    "COACH_RESEARCH_PHASE_SECONDS", 35, 1, 60,
)
COACH_RESEARCH_WRITER_SECONDS = _bounded_setting(
    "COACH_RESEARCH_WRITER_SECONDS", 35, 5, 60,
)
COACH_RESEARCH_CORRECTION_SECONDS = _bounded_setting(
    "COACH_RESEARCH_CORRECTION_SECONDS", 24, 5, 60,
)
COACH_RESEARCH_MAX_ROUNDS = _bounded_setting("COACH_RESEARCH_MAX_ROUNDS", 3, 1, 3, integer=True)
COACH_RESEARCH_MAX_ASSESSMENT_RETRIES = _bounded_setting(
    "COACH_RESEARCH_MAX_ASSESSMENT_RETRIES", 1, 0, 1, integer=True,
)
# Trigger the web fallback when the best corpus chunk scores below this. Defaults
# to the retrieval threshold, so the fallback fires mainly on an empty corpus hit.
WEB_FALLBACK_SIM_THRESHOLD = float(
    os.environ.get("WEB_FALLBACK_SIM_THRESHOLD", "0.45")
)
WEB_FALLBACK_MAX_RESULTS = int(os.environ.get("WEB_FALLBACK_MAX_RESULTS", "4"))
WEB_FALLBACK_TIMEOUT_SECONDS = float(
    os.environ.get("WEB_FALLBACK_TIMEOUT_SECONDS", "8")
)
COACH_HISTORY_LIMIT = int(os.environ.get("COACH_HISTORY_LIMIT", "6"))
COACH_HISTORY_CHAR_LIMIT = int(
    os.environ.get("COACH_HISTORY_CHAR_LIMIT", "4000")
)
COACH_RATE_LIMIT_MINUTE = int(os.environ.get("COACH_RATE_LIMIT_MINUTE", "6"))
COACH_RATE_LIMIT_DAY = int(os.environ.get("COACH_RATE_LIMIT_DAY", "100"))
COACH_WRITE_ACTIONS_ENABLED = _environment_flag(
    "COACH_WRITE_ACTIONS_ENABLED",
    # Financial records must not be changed merely because a deployment omitted
    # this setting. Operators explicitly opt in only after action flows pass
    # their production acceptance checks.
    False,
)
# Reserved coaching report PDFs. The backend only publishes an artifact after
# downloading the exact stored object; these bounds keep that read small and
# finite. The size cap mirrors the storage bucket's file_size_limit.
REPORT_ARTIFACT_BUCKET = os.environ.get("REPORT_ARTIFACT_BUCKET", "financial-reports")
REPORT_ARTIFACT_MAX_BYTES = int(
    os.environ.get("REPORT_ARTIFACT_MAX_BYTES", "10485760")
)
REPORT_ARTIFACT_DOWNLOAD_TIMEOUT_SECONDS = float(
    os.environ.get("REPORT_ARTIFACT_DOWNLOAD_TIMEOUT_SECONDS", "10")
)
COACH_LLM_CHOICES_ENABLED = _environment_flag(
    "COACH_LLM_CHOICES_ENABLED",
    # LLM-offered tappable choice cards are opt-in. Off by default so a
    # deployment that has not run the end-to-end choice tests renders plain
    # prose. Independent of COACH_ANSWER_VALIDATION.
    False,
)
COACH_PROVIDER_CONSENT_VERSION = os.environ.get(
    "COACH_PROVIDER_CONSENT_VERSION", "openrouter-free-v1"
)
LLM_TIMEOUT_SECONDS = float(os.environ.get("LLM_TIMEOUT_SECONDS", "25"))
COACH_REQUEST_DEADLINE_SECONDS = float(
    os.environ.get("COACH_REQUEST_DEADLINE_SECONDS", "30")
)
LLM_PRIMARY_TIMEOUT_SECONDS = float(
    os.environ.get("LLM_PRIMARY_TIMEOUT_SECONDS", "10")
)
LLM_FALLBACK_TIMEOUT_SECONDS = float(
    os.environ.get("LLM_FALLBACK_TIMEOUT_SECONDS", "18")
)
GROUNDING_VERIFIER_TIMEOUT_SECONDS = float(
    os.environ.get("GROUNDING_VERIFIER_TIMEOUT_SECONDS", "5")
)
GROUNDING_VERIFIER_MAX_TOKENS = int(
    os.environ.get("GROUNDING_VERIFIER_MAX_TOKENS", "256")
)
# Evidence-mode verifier budget. The legacy path keeps 256 (byte-for-byte
# rollback, invariant #9); the evidence path reads real extracted passages, which
# need more room than a snippet, so per-statement assessment uses this larger
# ceiling. Task 7 compares legacy@256 / legacy@1536 / evidence@1536 to prove the
# architecture win is not merely the token bump.
GROUNDING_VERIFIER_EVIDENCE_MAX_TOKENS = int(
    os.environ.get("GROUNDING_VERIFIER_EVIDENCE_MAX_TOKENS", "1536")
)
# Rollback flag (invariant #9): "legacy" behaves exactly as before this work;
# "evidence" enables the statement-level assessment + research pipeline. Defaults
# to legacy so adopting the new path is a deliberate, tested config flip.
COACH_GROUNDING_MODE = os.environ.get("COACH_GROUNDING_MODE", "legacy").strip().lower()
COACH_RATE_LIMIT_RETRY_MAX_SECONDS = float(
    os.environ.get("COACH_RATE_LIMIT_RETRY_MAX_SECONDS", "3")
)
# GPT-OSS uses this completion budget for both hidden reasoning and visible
# coaching text. 1024 can be consumed by high reasoning before any answer is
# returned. NVIDIA's GPT-OSS reasoning examples use 32768, which remains a
# bounded completion ceiling rather than the model's full context window.
LLM_MAX_TOKENS = int(os.environ.get("LLM_MAX_TOKENS", "32768"))
CORS_ORIGINS = [
    origin.strip()
    for origin in os.environ.get("CORS_ORIGINS", "").split(",")
    if origin.strip()
]
