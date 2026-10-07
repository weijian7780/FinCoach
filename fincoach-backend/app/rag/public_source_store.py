"""Bounded public-page persistence. Never persist user plans or LLM verdicts."""
from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from functools import lru_cache
from hashlib import sha256
import json
from pathlib import Path
import re
from threading import RLock
from uuid import uuid4
from urllib.parse import urlparse
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.rag.research_policy import QuestionPlan

_LOCK = RLock()


@dataclass(frozen=True)
class PublicSourceSpec:
    programme_id: str
    aliases: tuple[str, ...]
    jurisdiction: str
    period: str | None
    urls: tuple[str, ...]


@dataclass(frozen=True)
class PublicSourcePage:
    url: str
    title: str
    content: str
    fetched_at: datetime
    content_sha256: str
    published_date: str | None = None
    declared_period: str | None = None


def canonical_url(url: str) -> str:
    parsed = urlparse(url)
    return parsed._replace(scheme=parsed.scheme.lower(), netloc=parsed.netloc.lower(), fragment="").geturl()


def _safe_page(page: PublicSourcePage) -> bool:
    from app.rag.web_research import is_public_guidance_url, classify_tier
    return (is_public_guidance_url(page.url) and classify_tier(page.url) in {1, 2, 3, 4}
        and 0 < len(page.content) <= 100000 and len(page.title) <= 500
        and page.fetched_at.tzinfo is not None
        and page.content_sha256 == sha256(page.content.encode()).hexdigest()
        and (page.published_date is None or len(page.published_date) <= 100)
        and (page.declared_period is None or bool(re.fullmatch(r"\d{4}", page.declared_period))))


def load_catalog(path: Path) -> tuple[PublicSourceSpec, ...]:
    from app.rag.web_research import is_public_guidance_url, classify_tier
    try:
        raw = json.loads(path.read_text(encoding="utf8"))
        if raw.get("version") != 1:
            return ()
        result = []
        for entry in raw.get("programmes", [])[:32]:
            spec = PublicSourceSpec(entry["programme_id"], tuple(entry["aliases"]), entry["jurisdiction"],
                                    entry.get("period"), tuple(entry["urls"]))
            if (spec.aliases and len(spec.aliases) <= 8 and all(isinstance(a, str) and 2 <= len(a) <= 100 for a in spec.aliases)
                    and spec.urls and len(spec.urls) <= 4 and all(is_public_guidance_url(u)
                        and classify_tier(u) in {1, 2, 3, 4} for u in spec.urls)):
                result.append(spec)
        return tuple(result)
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        return ()


def matching_sources(plan: QuestionPlan, catalog: tuple[PublicSourceSpec, ...]) -> tuple[PublicSourceSpec, ...]:
    text = " ".join((plan.topic, *plan.entities)).casefold()
    year = plan.period or (str(datetime.now(timezone.utc).year) if plan.time_scope == "current" else None)
    matched = tuple(s for s in catalog if s.jurisdiction.casefold() == plan.jurisdiction.casefold()
        and (not year or not s.period or s.period == year)
        and any(re.search(r"(?<!\w)" + re.escape(a.casefold()) + r"(?!\w)", text) for a in s.aliases))[:4]
    result, remaining = [], 4
    for spec in matched:
        if not remaining:
            break
        urls = spec.urls[:remaining]
        result.append(PublicSourceSpec(spec.programme_id, spec.aliases, spec.jurisdiction, spec.period, urls))
        remaining -= len(urls)
    return tuple(result)


class PublicSourceStore:
    def __init__(self, root: Path, *, ttl_seconds: int = 86400, max_pages: int = 64, max_bytes: int = 8388608):
        self.root = Path(root)
        self.ttl_seconds = min(86400, max(0, int(ttl_seconds)))
        self.max_pages = min(64, max(1, int(max_pages)))
        self.max_bytes = min(8388608, max(1, int(max_bytes)))

    def _path(self, url):
        return self.root / (sha256(canonical_url(url).encode()).hexdigest() + ".json")

    def _read(self, path: Path) -> PublicSourcePage | None:
        try:
            if path.is_symlink() or path.stat().st_size > self.max_bytes:
                return None
            raw = json.loads(path.read_text(encoding="utf8"))
            if raw.pop("version", None) != 1:
                return None
            raw["fetched_at"] = datetime.fromisoformat(raw["fetched_at"])
            page = PublicSourcePage(**raw)
            return page if _safe_page(page) and self._path(page.url).name == path.name else None
        except (OSError, ValueError, TypeError, KeyError, AttributeError):
            return None

    def get(self, url: str, *, now: datetime) -> PublicSourcePage | None:
        try:
            page = self._read(self._path(url))
            age = (now - page.fetched_at).total_seconds() if page else -1
            return page if page and 0 <= age < self.ttl_seconds else None
        except (ValueError, TypeError):
            return None

    def put(self, page: PublicSourcePage) -> bool:
        if not _safe_page(page):
            return False
        raw = asdict(page)
        raw.update(version=1, url=canonical_url(page.url), fetched_at=page.fetched_at.isoformat())
        payload = json.dumps(raw, ensure_ascii=False).encode()
        if len(payload) > self.max_bytes or not _LOCK.acquire(timeout=.2):
            return False
        temporary = None
        try:
            self.root.mkdir(parents=True, exist_ok=True)
            target = self._path(page.url)
            if target.is_symlink():
                return False
            temporary = self.root / (uuid4().hex + ".tmp")
            temporary.write_bytes(payload)
            temporary.replace(target)
            files = [p for p in self.root.glob("*.json") if re.fullmatch(r"[a-f0-9]{64}\.json", p.name) and not p.is_symlink()]
            sizes = {p: p.stat().st_size for p in files}
            files.sort(key=lambda p: (self._read(p).fetched_at.timestamp() if self._read(p) else 0, p.name))
            total = sum(sizes.values())
            while len(files) > self.max_pages or total > self.max_bytes:
                oldest = files.pop(0)
                oldest.unlink()
                total -= sizes[oldest]
            return target.exists()
        except OSError:
            return False
        finally:
            if temporary is not None:
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    pass
            _LOCK.release()

    def find(self, plan: QuestionPlan, *, now: datetime) -> tuple[PublicSourcePage, ...]:
        # Discriminative public topic words, never a raw user query on disk.
        procedural = {"application", "apply", "process", "steps", "required", "documents", "document",
                      "eligibility", "criteria", "how", "what", "and", "for", "who", "the", "malaysia"}
        terms = set(re.findall(r"\b\w{3,}\b", plan.topic.casefold())) - procedural
        if not terms:
            return ()
        result = []
        try:
            for path in list(self.root.glob("*.json"))[:64]:
                page = self._read(path)
                if not page or not self.get(page.url, now=now):
                    continue
                words = set(re.findall(r"\b\w{3,}\b", (page.title + " " + page.content[:1000]).casefold()))
                period = plan.period or (str(now.year) if plan.time_scope == "current" else None)
                if terms <= words and (not period or not page.declared_period or page.declared_period == period):
                    result.append(page)
        except OSError:
            return ()
        return tuple(sorted(result, key=lambda p: p.fetched_at, reverse=True)[:4])


@lru_cache(maxsize=1)
def get_public_source_store() -> PublicSourceStore:
    from app.config import COACH_PUBLIC_SOURCE_CACHE_DIR, COACH_PUBLIC_SOURCE_CACHE_TTL_SECONDS
    return PublicSourceStore(Path(COACH_PUBLIC_SOURCE_CACHE_DIR), ttl_seconds=COACH_PUBLIC_SOURCE_CACHE_TTL_SECONDS)
