from dataclasses import replace
from datetime import datetime, timezone
from hashlib import sha256


def test_ranked_long_list_preserves_known_incomplete_structural_read():
    from app.rag.research_source_spans import read_source_spans
    text = '## Married applicants\nRequired documents:\n' + '\n'.join(
        '- Document ' + str(i) + ': ' + ('supporting details ' * 10) + '.' for i in range(30))
    p = QuestionPlan('STR', False, True, 'stable', required_facts=('required documents',), part_tracking=True)
    window, = select_part_windows((page(text),), p)
    span, = read_source_spans(text, anchors=(window.content,))
    assert not span.complete
    assert window.source_spans and any(not s.complete for s in window.source_spans)

from app.rag.public_source_store import PublicSourcePage
from app.rag.research_policy import QuestionPlan, _balanced_evidence, _source_key
from app.rag.research_windows import select_part_windows


def page(text, url="https://example.gov.my/guidance.pdf"):
    return PublicSourcePage(url, "Example assistance 2026", text, datetime.now(timezone.utc), sha256(text.encode()).hexdigest())


def test_same_pdf_keeps_application_and_conditional_document_windows():
    raw = ("Example assistance 2026. 1. Q: How do I apply? A: Apply using the official portal. "
           + "Other background. " * 160 + "7. Q: What documents are required? A: Applicants must supply an identity card. "
             "Married applicants must supply a marriage certificate, where applicable. Children need birth certificates. "
           + "Other background. " * 160)
    p = QuestionPlan("Example assistance application and documents", False, True, "current",
                     required_facts=("application steps", "required documents"), part_tracking=True)
    windows = select_part_windows((page(raw),), p)
    merged = _balanced_evidence([], windows)
    assert any("Apply using the official portal" in w.content for w in merged)
    assert any("Married applicants" in w.content for w in merged)
    assert len({_source_key(w) for w in merged}) >= 2
    assert all(w.content in raw and len(w.content) <= 1800 for w in merged)
    assert len({w.url for w in merged}) == 1


def test_identical_windows_deduplicate_and_changed_page_has_new_identity():
    raw = "Example assistance applicants must supply an identity card."
    p = QuestionPlan("Example assistance", False, True, "current", required_facts=("documents", "supporting documents"), part_tracking=True)
    first = select_part_windows((page(raw),), p)
    assert len(first) == 1
    changed = select_part_windows((page(raw + " Additional applicable condition."),), p)
    assert _source_key(first[0]) != _source_key(changed[0])
    assert first[0].checked_at == page(raw).fetched_at.date().isoformat()


def test_window_limits_and_no_invented_document_list():
    raw = "Example assistance. Apply through the public portal."
    p = QuestionPlan("Example assistance", False, True, "current", required_facts=tuple(f"requested part {i}" for i in range(6)), part_tracking=True)
    windows = select_part_windows(tuple(page(raw + str(i), f"https://example.gov.my/{i}") for i in range(4)), p)
    assert len(windows) <= 6 and sum(len(w.content) for w in windows) <= 10800
    assert all("marriage" not in w.content for w in windows)


def test_parts_receive_windows_before_source_alternatives(monkeypatch):
    monkeypatch.setattr("app.rag.web_research._complete_page_window", lambda raw, query, **kw:
                        "documents" if "documents" in query else "application")
    p = QuestionPlan("Example", False, True, "current", required_facts=("application", "documents"), part_tracking=True)
    pages = tuple(page("## Application\napplication\n\n## Documents\ndocuments", f"https://example.gov.my/{i}") for i in range(6))
    windows = select_part_windows(pages, p)
    assert "application" in windows[0].content and "documents" in windows[1].content


def test_captured_str_faq_application_window_includes_channels():
    import json
    from pathlib import Path
    captured = Path(__file__).resolve().parents[1] / "docs/superpowers/plans/2026-10-04-public-source-seed-inspection.json"
    raw = next(text for url, text in json.loads(captured.read_text(encoding="utf8")).items() if "/FAQ/" in url)
    p = QuestionPlan("Sumbangan Tunai Rahmah", False, True, "current", entities=("STR", "LHDN"),
                     required_facts=("Application process for STR",), part_tracking=True)
    windows = select_part_windows((page(raw),), p)
    assert "Permohonan Secara Dalam Talian" in windows[0].content
    assert "Borang Kertas" in windows[0].content
    assert windows[0].source_spans and windows[0].source_spans[0].complete
    assert 'Di manakah saya boleh menghantar' not in windows[0].content


def test_focused_recovery_preserves_original_same_url_sections():
    from app.rag.research_policy import passage_windows
    from app.rag.web_research import WebResearchCache
    raw = "Application instructions. " + "Background. " * 180 + "Documents required: identity card."
    p = QuestionPlan("Example", False, True, "current", required_facts=("application", "documents"), part_tracking=True)
    old = select_part_windows((page(raw),), p)
    cache = WebResearchCache()
    cache.full_pages[old[0].url] = raw
    new = passage_windows(old, {old[0].url: "Documents required: identity card."}, cache)
    merged = _balanced_evidence(old, new)
    assert any("Application instructions" in c.content for c in merged)
    assert any(c.content == "Documents required: identity card." for c in merged)
    assert len({_source_key(c) for c in merged}) == len(merged)


def test_captured_english_application_heading_beats_programme_intro():
    import json
    from pathlib import Path
    captured = Path(__file__).resolve().parents[1] / "docs/superpowers/plans/2026-10-04-public-source-seed-inspection.json"
    raw = json.loads(captured.read_text(encoding="utf8"))["https://sara.gov.my/en/home.html"]
    p = QuestionPlan("SARA", False, True, "current", required_facts=("SARA application process",), part_tracking=True)
    windows = select_part_windows((page(raw, "https://sara.gov.my/en/home.html"),), p)
    assert "STR application is required to qualify for" in windows[0].content
    assert "No application is required" in windows[0].content
