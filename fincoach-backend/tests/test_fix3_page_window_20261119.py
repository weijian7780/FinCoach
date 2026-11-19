"""Fix 3 (2026-11-19): a long page's section window keeps the body under its heading.

Before the fix, a heading followed by one paragraph longer than the window
limit came back as the bare heading line.
"""
from app.rag.web_research import _complete_page_window

_SENTENCE = ("Cash flow is the movement of money into and out of your accounts over a "
             "period, and tracking it shows whether income covers spending.")


def _page(*headings: str) -> str:
    body = " ".join([_SENTENCE] * 16)
    top = "\n\n".join(headings)
    return (f"# Menu\n\nHome About Contact\n\n{top}\n\n{body}\n\n"
            "# Other topics\n\nUnrelated text about loans and cards.")


def test_long_section_returns_heading_with_its_body():
    page = _page("# What is Cash Flow?")
    assert len(page) > 1800
    window = _complete_page_window(page, "what is cash flow")
    assert "# What is Cash Flow?" in window
    assert _SENTENCE in window
    assert len(window) <= 1800
    assert window in page


def test_stacked_headings_still_reach_the_body():
    page = _page("# Money basics", "## What is Cash Flow?")
    window = _complete_page_window(page, "what is cash flow")
    assert "What is Cash Flow?" in window
    assert _SENTENCE in window
    assert len(window) <= 1800
    assert window in page


def test_window_ends_on_a_full_sentence():
    page = _page("# What is Cash Flow?")
    window = _complete_page_window(page, "what is cash flow")
    assert window.rstrip().endswith("spending.")


def test_short_heading_and_body_page_is_unchanged():
    page = "# What is Cash Flow?\n\n" + _SENTENCE
    assert _complete_page_window(page, "what is cash flow") == page
