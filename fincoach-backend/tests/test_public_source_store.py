import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from app.rag.public_source_store import PublicSourcePage, PublicSourceSpec, PublicSourceStore, matching_sources
from app.rag.research_policy import QuestionPlan
from app.rag.web_research import is_public_guidance_url

NOW = datetime(2026, 10, 4, 8, tzinfo=timezone.utc)
URL = "https://example.gov.my/guidance.pdf"


def page(url=URL, content="Example benefit 2026 public guidance."):
    return PublicSourcePage(url, "Example benefit", content, NOW,
                            hashlib.sha256(content.encode()).hexdigest(), declared_period="2026")


def test_catalogue_matches_programme_not_substring_or_admin_agency():
    spec = PublicSourceSpec("str", ("STR", "Sumbangan Tunai Rahmah"), "Malaysia", "2026", (URL,))
    p = QuestionPlan("STR application", False, True, "current", entities=("LHDN",))
    assert matching_sources(p, (spec,)) == (spec,)
    assert not matching_sources(replace(p, topic="student strategy", entities=("LHDN",)), (spec,))
    assert not matching_sources(replace(p, period="2023", time_scope="historical"), (spec,))
    assert not matching_sources(replace(p, jurisdiction="Singapore"), (spec,))


def test_page_roundtrip_retains_original_time_and_expires(tmp_path):
    store = PublicSourceStore(tmp_path)
    item = page()
    assert store.put(item)
    assert PublicSourceStore(tmp_path).get(URL, now=NOW + timedelta(hours=23)) == item
    assert store.get(URL, now=NOW + timedelta(hours=24)) is None
    assert store.get(URL, now=NOW - timedelta(minutes=1)) is None


@pytest.mark.parametrize("bad", ["http://localhost/a", "https://127.1/a", "https://0x7f000001/a",
    "https://example.gov.my/login", "https://user:password@example.gov.my/a", "https://example.gov.my/a?id=private",
    "https://example.gov.my/a?token=secret", "file:///tmp/a"])
def test_unsafe_urls_never_enter_store(tmp_path, bad):
    assert not is_public_guidance_url(bad)
    assert not PublicSourceStore(tmp_path).put(page(bad))


def test_bad_hash_oversized_and_unknown_source_are_rejected(tmp_path):
    store = PublicSourceStore(tmp_path)
    assert not store.put(replace(page(), content_sha256="bad"))
    assert not store.put(page(content="x" * 100001))
    assert not store.put(page("https://unclassified-example.net/a"))


def test_corrupt_metadata_is_a_miss(tmp_path):
    store = PublicSourceStore(tmp_path)
    assert store.put(page())
    target = next(tmp_path.glob("*.json"))
    original = target.read_text()
    for content in ["{", json.dumps({"version": 999}), original.replace("2026-10-04T08:00:00+00:00", "wrong")]:
        target.write_text(content)
        assert store.get(URL, now=NOW) is None


def test_store_evicts_by_fetch_time_and_serialized_size(tmp_path):
    store = PublicSourceStore(tmp_path, max_pages=2, max_bytes=2000)
    for i in range(3):
        assert store.put(replace(page(f"https://example.gov.my/{i}"), fetched_at=NOW + timedelta(seconds=i)))
    assert len(list(tmp_path.glob("*.json"))) == 2
    assert store.get("https://example.gov.my/0", now=NOW + timedelta(seconds=4)) is None
    small = PublicSourceStore(tmp_path / "small", max_bytes=500)
    assert not small.put(page(content="x" * 900))


def test_atomic_concurrent_writes_and_disk_failure(tmp_path):
    store = PublicSourceStore(tmp_path)
    with ThreadPoolExecutor(max_workers=4) as pool:
        assert all(pool.map(store.put, [page()] * 12))
    assert store.get(URL, now=NOW) == page()
    assert not list(tmp_path.glob("*.tmp"))
    blocked = tmp_path / "file"
    blocked.write_text("not a directory")
    assert not PublicSourceStore(blocked).put(page())
    assert PublicSourceStore(blocked).get(URL, now=NOW) is None


def test_find_matches_public_subject_only(tmp_path):
    store = PublicSourceStore(tmp_path)
    store.put(page())
    p = QuestionPlan("Example benefit application", False, True, "current")
    assert store.find(p, now=NOW) == (page(),)
    assert not store.find(replace(p, topic="Other benefit"), now=NOW)
    store.put(replace(page(), declared_period="2025"))
    assert not store.find(p, now=NOW)


def test_catalogue_total_url_bound_and_explicit_period():
    specs = tuple(PublicSourceSpec(str(i), ("STR",), "Malaysia", "2026",
        tuple(f"https://example.gov.my/{i}/{j}" for j in range(4))) for i in range(3))
    p = QuestionPlan("STR", False, True, "current")
    assert sum(len(s.urls) for s in matching_sources(p, specs)) == 4


def test_maximum_page_bound_and_byte_eviction(tmp_path):
    store = PublicSourceStore(tmp_path)
    for i in range(65):
        assert store.put(replace(page(f"https://example.gov.my/{i}"), fetched_at=NOW+timedelta(seconds=i)))
    assert len(list(tmp_path.glob("*.json"))) == 64
    small = PublicSourceStore(tmp_path / "bytes", max_bytes=1200)
    for i in range(4):
        small.put(page(f"https://example.gov.my/{i}", content="x" * 350))
    assert sum(p.stat().st_size for p in (tmp_path / "bytes").glob("*.json")) <= 1200
