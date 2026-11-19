"""Fix 1 (2026-11-19): the de-identified search query keeps the user's question.

Sign-off words only end the query in closing position; short numbered names
("Account 3") and year ranges survive. Every privacy case that passed before
the fix must still pass.
"""
import pytest

from app.rag.web_research import build_research_query


@pytest.mark.parametrize(
    ("question", "kept"),
    [
        ("What is the best way to repay PTPTN?", "best way to repay PTPTN"),
        ("Thanks for the help. What is ASB?", "What is ASB"),
        ("Assalamualaikum, salam, how to apply PTPTN", "how to apply PTPTN"),
        ("Salam, apa itu ASB?", "apa itu ASB"),
        ("Is Salam Takaful a good option?", "Salam Takaful"),
        ("EPF Account 3 withdrawal rules", "EPF Account 3 withdrawal rules"),
        ("PTPTN rate 2025-2026", "2025-2026"),
    ],
)
def test_question_text_survives(question, kept):
    assert kept in build_research_query(question)


@pytest.mark.parametrize(
    ("question", "removed"),
    [
        ("How do I repay PTPTN?\n\nRegards,\nAhmad bin Ali\nref 52341", ("Ahmad", "52341")),
        ("What is ASB? Thanks, Siti", ("Siti",)),
        ("Apa itu ASB? Salam, Ahmad", ("Ahmad",)),
        ("PTPTN status ref 2025-2026", ("2025-2026",)),
        ("My account no 12345678 was charged twice, why?", ("12345678",)),
        ("Call me at 012-345 6789 about EPF", ("012", "6789")),
        ("Email me at a.b@example.com about PTPTN", ("example.com",)),
        ("I paid RM1,250.00 for PTPTN", ("1,250",)),
        ("IC 990101-12-5678 PTPTN status", ("990101", "5678")),
    ],
)
def test_private_details_are_still_removed(question, removed):
    query = build_research_query(question)
    for value in removed:
        assert value not in query


def test_privacy_cases_keep_their_topic():
    assert "repay PTPTN" in build_research_query(
        "How do I repay PTPTN?\n\nRegards,\nAhmad bin Ali\nref 52341")
    assert "What is ASB" in build_research_query("What is ASB? Thanks, Siti")
    assert "Apa itu ASB" in build_research_query("Apa itu ASB? Salam, Ahmad")
