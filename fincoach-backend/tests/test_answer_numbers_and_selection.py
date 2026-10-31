"""Answer stage: the user's own numbers are given, and a weaker rewrite never
replaces a better verified answer. General rules; no topic or wording lists."""
from dataclasses import replace

from datetime import date

import pytest

from app.llm import CoachRequestBudget, LLMResult
from app.rag import research_answer as answer
from app.rag import verifier
from app.rag.grounding import DISCLAIMER
from app.rag.research_coverage import PartCoverage
from app.rag.research_policy import EvidenceAssessment, ResearchDecision
from app.rag.retrieval import RetrievedChunk
from test_kb_nonfinance import _plan, _public

TIP = "Pay yourself first by moving savings out as soon as your allowance arrives."
TRACK = "Track every expense for a month to see where the money goes."
SOURCE = RetrievedChunk(1, "Saving tips", "tips.md", None, 0, f"{TIP} {TRACK}", 0.8)
DECISION = ResearchDecision([SOURCE], EvidenceAssessment(
    "sufficient", supported_sources=(1,), supported_quotes=((1, TIP), (1, TRACK)),
    parts=(PartCoverage("p1", "reported", (1, 2), complete=True),)))


def _check(monkeypatch, sentences, *, question="Help me save RM50", given=None):
    """Run the real local checks; the semantic verifier supports every claim."""
    text = "**Insight**\n" + "\n".join(f"{s} [S1]." for s in sentences) + f"\n\n**Educational guidance**\n{DISCLAIMER}"

    def verify(claims, *args, **kwargs):
        ids = tuple(claim.id for claim in claims)
        return verifier.GroundingVerification(
            {i: "supported" for i in ids}, {i: 1 for i in ids}, requested_scope_covered=True,
            answered_part_ids=("p1",), answered_part_claims=(("p1", ids),))
    monkeypatch.setattr(answer, "verify_grounding_claims", verify)
    return answer.check_research_draft(text, public_question=question, decision=DECISION,
                                       budget=CoachRequestBudget.start(),
                                       given_text=question if given is None else given)


# ---- The user's own numbers -------------------------------------------------------------

def test_reviewer_repro_the_users_own_target_is_not_an_unsupported_number(monkeypatch):
    # Reproduced on live 2026-10-31: "...a specific RM50 savings plan" was
    # rejected because RM50 is the user's number, not the source's.
    checked = _check(monkeypatch, [f"To work towards your RM50 target, {TIP[0].lower()}{TIP[1:-1]}"])
    assert checked.is_valid and "RM50" in checked.approved_text


def test_without_the_question_numbers_the_same_sentence_is_rejected(monkeypatch):
    checked = _check(monkeypatch, [f"To work towards your RM50 target, {TIP[0].lower()}{TIP[1:-1]}"],
                     given="")
    assert not checked.is_valid and checked.error_codes == ("unsupported_number",)


def test_invented_numbers_are_still_rejected(monkeypatch):
    # Reproduced on live: an invented RM4,500 / RM900 example must not pass.
    checked = _check(monkeypatch, [TIP[:-1], "For example, on RM4,500 a month you would move RM900"])
    assert checked.error_codes == ("unsupported_number",)
    assert "RM4,500" not in (checked.approved_text or "") and "RM900" not in (checked.approved_text or "")


def test_a_given_value_in_another_unit_is_not_given(monkeypatch):
    checked = _check(monkeypatch, [f"Save 50% of what remains; {TIP[0].lower()}{TIP[1:-1]}"])
    assert checked.error_codes == ("unsupported_number",)


def test_numbers_come_from_the_plans_original_question(monkeypatch):
    seen = {}

    def check(draft, **kwargs):
        seen["given"] = kwargs["given_text"]
        return answer.ResearchDraftCheck(True, approved_text=draft, diagnostics={})
    monkeypatch.setattr(answer, "check_research_draft", check)
    plan = replace(_plan(_public("saving money", subject_domain="finance")), original_question="Help me save RM50")
    answer.recover_research_answer(plan=plan, decision=DECISION, draft=LLMResult("**Insight**\nx", "test"),
                                   budget=CoachRequestBudget.start(), public_question="How can I save RM50?")
    assert seen["given"] == "Help me save RM50"


# ---- A weaker rewrite never replaces a better verified answer -----------------------------

FIRST = "**Insight**\nThree approved tips."
REWRITE = "**Insight**\nOne approved tip."


def _recover(monkeypatch, first, second):
    results = iter([first, second])
    monkeypatch.setattr(answer, "check_research_draft", lambda *a, **k: next(results))
    monkeypatch.setattr(answer, "_generate_research_correction", lambda *a, **k: LLMResult("rewrite", "gemini"))
    plan = _plan(_public("saving money", subject_domain="finance"))
    return answer.recover_research_answer(plan=plan, decision=DECISION, draft=LLMResult("draft", "gemini"),
                                          budget=CoachRequestBudget.start(), public_question="q")


def _salvage(text, approved, parts=("p1",), valid=False):
    return answer.ResearchDraftCheck(valid, () if valid else ("unsupported_number",), text,
                                     {"approved_claim_count": approved, "addressed_part_ids": list(parts)})


def test_reviewer_repro_weaker_rewrite_does_not_replace_the_better_first_answer(monkeypatch):
    # Reproduced on live: first draft 3 approved claims, rewrite 1 -> the user
    # saw a single orphan sentence ("these structured habits").
    outcome = _recover(monkeypatch, _salvage(FIRST, 3), _salvage(REWRITE, 1))
    assert "Three approved tips." in outcome.result.content and "One approved" not in outcome.result.content


def test_rewrite_that_addresses_more_parts_is_kept(monkeypatch):
    outcome = _recover(monkeypatch, _salvage(FIRST, 3, parts=()), _salvage(REWRITE, 1))
    assert "One approved tip." in outcome.result.content


def test_valid_rewrite_is_always_kept(monkeypatch):
    outcome = _recover(monkeypatch, _salvage(FIRST, 3), _salvage(REWRITE, 1, valid=True))
    assert "One approved tip." in outcome.result.content


def test_equal_rewrite_keeps_the_existing_behaviour(monkeypatch):
    outcome = _recover(monkeypatch, _salvage(FIRST, 2), _salvage(REWRITE, 2))
    assert "One approved tip." in outcome.result.content


# ---- Calculations are verified by code, separately from source support ------------------

WEEKLY = "how do I set aside RM30 every week"


@pytest.mark.parametrize("sentence", [
    "Setting aside RM30 × 4 weeks = RM120 a month, so pay yourself first when your allowance arrives",
    "Mengasingkan RM30 x 4 minggu = RM120 sebulan, jadi simpan dahulu sebaik elaun diterima",
    "每周存RM30 × 52 = RM1,560，收到零用钱后先存起来",
    "RM30 × 4 = RM120 a month and RM120 × 12 = RM1,440 a year if you pay yourself first",
])
def test_written_calculation_from_the_users_values_is_verified(monkeypatch, sentence):
    checked = _check(monkeypatch, [sentence], question=WEEKLY)
    assert checked.is_valid, checked.error_codes


@pytest.mark.parametrize("sentence", [
    "Setting aside RM30 × 4 weeks = RM130 a month",          # wrong arithmetic
    "Setting aside RM45 × 4 weeks = RM180 a month",          # operand not given or sourced
    "Setting aside RM30 every week gives about RM1,560 a year",  # result without working
])
def test_unverifiable_calculations_are_still_rejected(monkeypatch, sentence):
    checked = _check(monkeypatch, [sentence, TIP[:-1]], question=WEEKLY)
    assert checked.error_codes == ("unsupported_number",)


def test_rounded_result_matches_only_to_its_shown_precision():
    from app.rag.research_answer import _verified_calculations
    allowed = answer._numeric_values("RM3,000 RM538.33")
    assert _verified_calculations("RM3,000 ÷ RM538.33 ≈ 5.57 months", allowed) == {"months:5.57"}
    assert _verified_calculations("RM3,000 ÷ RM538.33 ≈ 5 months", allowed) == set()


def test_users_numbers_never_override_the_semantic_verdict(monkeypatch):
    # Context is the verifier's call: a sentence attributing the user's value to
    # the source is rejected even though the number itself is permitted.
    text = f"**Insight**\nThe guide recommends saving exactly RM50 from every allowance [S1].\n\n**Educational guidance**\n{DISCLAIMER}"

    def verify(claims, *args, **kwargs):
        ids = tuple(claim.id for claim in claims)
        return verifier.GroundingVerification({i: "unsupported" for i in ids}, {}, requested_scope_covered=False,
                                              answered_part_ids=(), answered_part_claims=())
    monkeypatch.setattr(answer, "verify_grounding_claims", verify)
    checked = answer.check_research_draft(text, public_question="Help me save RM50", decision=DECISION,
                                          budget=CoachRequestBudget.start(), given_text="Help me save RM50")
    assert not checked.is_valid and "RM50" not in (checked.approved_text or "")


# ---- No hard-coded amounts, currencies, units or languages (randomised) ------------------

import random
from decimal import Decimal

UNIT_WORDS = ["weeks", "minggu", "bulan", "months", "kali", "days", "周", "个月", ""]
OPERATORS = {"×": lambda a, b: a * b, "x": lambda a, b: a * b, "*": lambda a, b: a * b,
             "÷": lambda a, b: a / b, "/": lambda a, b: a / b,
             "+": lambda a, b: a + b, "-": lambda a, b: a - b}


def _money(prefix, value):
    return f"{prefix}{value:,.2f}".replace(".00", "")


@pytest.mark.parametrize("seed", range(200))
def test_any_correct_written_calculation_verifies_and_any_wrong_one_does_not(seed):
    from app.rag.research_answer import _verified_calculations
    rng = random.Random(seed)
    prefix = rng.choice(["RM", "RM ", "$"])         # every currency the shared definition knows
    amount = Decimal(rng.randint(1, 50_000)) / (100 if rng.random() < 0.3 else 1)
    operator = rng.choice(list(OPERATORS))
    if operator in "+-":
        other = Decimal(rng.randint(1, 5_000))
        right = _money(prefix, other)
        result = OPERATORS[operator](amount, other)
    else:
        other = Decimal(rng.randint(2, 60))
        unit = rng.choice(UNIT_WORDS)
        right = f"{other} {unit}".strip()
        result = OPERATORS[operator](amount, other)
    result = result.quantize(Decimal("0.01"))
    if result <= 0:
        return
    sentence = f"{_money(prefix, amount)} {operator} {right} = {_money(prefix, result)}"
    allowed = answer._numeric_values(sentence.split("=")[0])
    if not answer._numeric_values(_money(prefix, result)):
        return  # the shared parser does not treat this currency as a sourced claim
    assert _verified_calculations(sentence, allowed) == answer._numeric_values(_money(prefix, result)), sentence
    wrong = result + Decimal(rng.choice([1, -1])) * Decimal(rng.randint(1, 100))
    if wrong > 0:
        bad = f"{_money(prefix, amount)} {operator} {right} = {_money(prefix, wrong)}"
        assert _verified_calculations(bad, allowed) == set(), bad


@pytest.mark.parametrize("seed", range(50))
def test_any_user_stated_amount_is_given_and_any_other_is_not(monkeypatch, seed):
    rng = random.Random(seed)
    stated, other = rng.sample(range(1, 100_000), 2)
    question = rng.choice(["Help me save RM{v}", "Saya nak simpan RM{v} sebulan", "我想存RM{v}", "how do I set aside RM{v}"])
    question = question.format(v=f"{stated:,}")
    tip = f"{TIP[0].lower()}{TIP[1:-1]}"
    assert _check(monkeypatch, [f"Towards your RM{stated:,} goal, {tip}"], question=question).is_valid
    rejected = _check(monkeypatch, [f"Towards a RM{other:,} goal, {tip}"], question=question)
    assert rejected.error_codes == ("unsupported_number",)


# ---- Approved prompt rules (2026-10-31) ---------------------------------------------------

def test_writer_is_told_to_show_the_working_of_its_calculations():
    from app.rag.prompts import RESEARCH_EXPLANATION_SYSTEM_PROMPT as prompt
    assert "show the working in one line with symbols" in prompt
    assert "never state a calculated figure without its working" in prompt


def test_interpreter_reads_a_personal_target_as_a_savings_calculation():
    from app.rag.request_interpretation import PROMPT
    assert "help reaching a target for themselves" in PROMPT
    assert "or help saving a stated amount" in PROMPT
    assert "how much to save from their own records" not in PROMPT


# ---- Approved 2026-10-31: contribution role; a listed target reads the savings estimate ---

from app.rag import request_interpretation as intent
from app.rag import service as coach_service


def _reading(amount, role, **public_extra):
    public = {"topic": "saving", "subject_domain": "finance", **public_extra}
    if role in ("target", "budget"):
        public.setdefault("stated_amount", amount)
    return {"route": "financial_education", "relation": "new", "public": public,
            "amounts": [{"amount": amount, "role": role}], "response_language": "en"}


def _normalised(payload):
    return intent._normalise_proposal(intent.IntentProposal.model_validate(payload))


@pytest.mark.parametrize("seed", range(40))
def test_any_listed_target_adds_the_savings_estimate_read(seed):
    amount = str(random.Random(seed).randint(1, 100_000))
    proposal = _normalised(_reading(amount, "target"))
    assert proposal.route == "combined" and proposal.read.operation == "predict_savings"
    assert proposal.public.stated_amount == amount and proposal.goal == "plan"
    intent.check_amounts(proposal)
    intent.compile_read(proposal, date(2026, 10, 31))


@pytest.mark.parametrize("payload", [
    _reading("1500", "budget", framework="allocation"),          # money to split
    _reading("30", "contribution"),                               # saved per period
    _reading("50", "context"),
    {**_reading("3000", "target"), "clarification": "Which laptop?"},
    {**_reading("3000", "target"), "actions": [{"kind": "create_reminder"}], "route": "combined"},
])
def test_other_readings_keep_their_route(payload):
    before = intent.IntentProposal.model_validate(payload)
    after = _normalised(payload)
    assert after.read == before.read


def test_an_existing_records_read_is_kept():
    payload = {**_reading("3000", "target"), "route": "combined",
               "read": {"operation": "get_financial_overview", "category": {"decision": "none"}}, "goal": "advise"}
    assert _normalised(payload).read.operation == "get_financial_overview"


@pytest.mark.parametrize("seed", range(30))
def test_a_contribution_is_never_shown_or_planned_as_a_target(seed):
    amount = str(random.Random(seed).randint(1, 10_000))
    proposal = _normalised(_reading(amount, "contribution"))
    intent.check_amounts(proposal)                     # needs no placement
    assert proposal.read is None and coach_service._listed_target(proposal) is None
    assert coach_service._with_stated_target("answer", proposal) == "answer"


def test_a_contribution_put_in_the_stated_amount_is_rejected_for_repair():
    payload = _reading("30", "contribution", stated_amount="30")
    with pytest.raises(intent.ProposalRejected):
        intent.check_amounts(intent.IntentProposal.model_validate(payload))


def test_interpreter_prompt_defines_the_contribution_role():
    assert "contribution = an amount the user saves or sets aside each period" in intent.PROMPT


@pytest.mark.parametrize("seed", range(30))
def test_a_contribution_copied_into_the_stated_amount_is_accepted_without_it(seed):
    # Live probe: Gemini labelled "RM30 every week" a contribution but also put
    # RM30 in public.stated_amount, so the reading was rejected and the user
    # was asked "price or savings target?". The model's own label decides.
    rng = random.Random(seed)
    amount = str(rng.randint(1, 10_000))
    payload = _reading(amount, "contribution", stated_amount=amount, framework="none")
    payload["goal"] = rng.choice([None, "plan", "advise"])
    proposal = _normalised(payload)
    intent.check_amounts(proposal)
    assert proposal.public.stated_amount is None and proposal.public.framework == "none"
    assert proposal.read is None and coach_service._listed_target(proposal) is None


def test_a_contribution_question_is_answered_in_one_reading():
    from test_kb_reduced_release import _interpret
    payload = _reading("30", "contribution", stated_amount="30")
    result = _interpret("how do I set aside RM30 every week", [], payload)
    assert result.failure is None and len(_interpret.inputs) == 1


def test_only_a_budget_amount_defaults_to_allocation():
    budget = _normalised({**_reading("1500", "budget"), "goal": "plan"})
    assert budget.public.framework == "allocation"
    contribution = _normalised({**_reading("30", "contribution", stated_amount="30"), "goal": "plan"})
    assert contribution.public.framework == "none"


@pytest.mark.parametrize("seed", range(30))
def test_a_contribution_put_on_a_records_read_is_accepted_without_it(seed):
    # Live probe: "Help me save RM50" read as a contribution put RM50 on the
    # savings-estimate read (which takes no amount); the reading was rejected.
    rng = random.Random(seed)
    amount = str(rng.randint(1, 10_000))
    payload = {"route": "personal_finance", "relation": "new", "goal": "plan",
               "read": {"operation": rng.choice(["predict_savings", "get_weekly_savings_plan", "get_savings_goals"]),
                        "category": {"decision": "none"}, "amount": amount},
               "amounts": [{"amount": amount, "role": "contribution"}]}
    proposal = _normalised(payload)
    assert proposal.read.amount is None
    intent.check_amounts(proposal)
    intent.compile_read(proposal, date(2026, 10, 31))


def test_a_transaction_filter_keeps_its_amount():
    payload = {"route": "personal_finance", "relation": "new", "goal": "show",
               "read": {"operation": "search_transactions", "category": {"decision": "none"}, "amount": "50"},
               "amounts": [{"amount": "50", "role": "filter"}]}
    assert _normalised(payload).read.amount == "50"


def test_contribution_is_a_valid_meaning_after_a_repair():
    payload = _normalised(_reading("30", "contribution"))
    assert intent._amount_meaning(payload, "30") == "contribution"


@pytest.mark.parametrize("language", ["en", "ms", "zh", "ta"])
def test_the_amount_question_offers_every_meaning(language):
    text = intent._AMOUNT_MEANING_MESSAGES[language].format(amount="50")
    assert text.count("RM50") == 2  # one meaning names the amount, transactions name it again
