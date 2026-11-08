import pytest
from app.rag.research_answer import _partial_notice, _DETAIL_LEFT_OUT

@pytest.mark.parametrize("label", [
    "how to start investing in shares",
    "eligibility and requirements for a student credit card",
    "how to start", "steps to open a share trading account",
    "brokerage account fees to check before buying shares"])
def test_real_single_part_labels(label):
    assert _partial_notice("Explain please", (label,), part_count=1) == _DETAIL_LEFT_OUT["en"]
    assert label in _partial_notice("Explain please", (label,), part_count=2)
