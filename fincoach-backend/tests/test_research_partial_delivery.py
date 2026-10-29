"""A verified explanation is useful without inventing an action or requirement."""
from dataclasses import replace
from unittest.mock import patch
from app.llm import AgentLLMResult, CoachRequestBudget
from app.rag import research_answer as answer
from app.rag.grounding import DISCLAIMER
from app.rag.research_policy import QuestionPlan, ResearchDecision, EvidenceAssessment
from app.rag.retrieval import RetrievedChunk
from app.rag.verifier import GroundingVerification


FACT='The agency coordinates the implementation of government development projects.'


def evidence():
    chunk=RetrievedChunk(1,'Agency duties','official',None,0,FACT,.8,
        source_type='web',url='https://agency.gov.my/duties',tier=1)
    return ResearchDecision([chunk],EvidenceAssessment('partial',('application procedure',),
        supported_sources=(1,),supported_quotes=((1,FACT),)))


def draft(action=None):
    return '**Insight**\n'+FACT+' [S1]\n\n'+(
        '**Recommended action**\n'+action+'\n\n' if action else '')+'**Educational guidance**\n'+DISCLAIMER


def support(claims,*args,**kwargs):
    return GroundingVerification({c.id:'supported' for c in claims},
        {c.id:1 for c in claims if c.cited_indices},
        assessment_supported_ids=tuple(c.id for c in claims if not c.cited_indices))


def test_verified_insight_without_action_is_delivered():
    with patch.object(answer,'verify_grounding_claims',side_effect=support):
        result=answer.check_research_draft(draft(),public_question='What are its duties?',
            decision=evidence(),budget=CoachRequestBudget.start())
    assert result.is_valid
    assert FACT.rstrip('.') in result.approved_text
    assert '**Recommended action**' not in result.approved_text


def test_plain_generated_explanation_gets_layout_without_paid_rewrite():
    plan=QuestionPlan('Agency',False,True,'stable')
    with patch.object(answer,'verify_grounding_claims',side_effect=support), \
         patch.object(answer,'_generate_research_correction') as retry:
        result=answer.recover_research_answer(plan=plan,decision=evidence(),
            draft=AgentLLMResult(FACT+' [S1]', 'primary'),
            budget=CoachRequestBudget.start(),public_question='What are its duties?')
    retry.assert_not_called()
    assert result.result.content.startswith('**Insight**')
    assert result.result.content.endswith(DISCLAIMER)
    assert FACT.rstrip('.') in result.result.content


def test_rejected_action_does_not_erase_independent_insight():
    def verdict(claims,*a,**k):
        good=[c for c in claims if 'grant' not in c.text]
        return GroundingVerification({c.id:'supported' if c in good else 'unsupported' for c in claims},
            {c.id:1 for c in good})
    with patch.object(answer,'verify_grounding_claims',side_effect=verdict):
        result=answer.check_research_draft(draft('Apply for a grant [S1].'),public_question='What does it do?',
            decision=evidence(),budget=CoachRequestBudget.start())
    assert not result.is_valid
    assert result.approved_text and FACT.rstrip('.') in result.approved_text
    assert 'grant' not in result.approved_text
    assert '**Recommended action**' not in result.approved_text


def test_scope_quality_error_does_not_erase_independent_verified_claims():
    def verdict(claims,*a,**k):
        good=[c for c in claims if 'grant' not in c.text]
        return GroundingVerification({c.id:'supported' if c in good else 'unsupported' for c in claims},
            {c.id:1 for c in good}, quality_errors=('incomplete_supported_answer',))
    with patch.object(answer,'verify_grounding_claims',side_effect=verdict):
        result=answer.check_research_draft(draft('Apply for a grant [S1].'),
            public_question='Duties and application?',decision=evidence(),budget=CoachRequestBudget.start())
    assert not result.is_valid
    assert result.approved_text and FACT.rstrip('.') in result.approved_text
    assert 'grant' not in result.approved_text


def test_mixed_answer_contains_one_targeted_question():
    question='Which programme or service would you like to apply for?'
    plan=QuestionPlan('Agency',False,True,'stable',required_facts=('duties','application procedure'),
        clarification=question,clarification_facts=('application procedure',))
    with patch.object(answer,'verify_grounding_claims',side_effect=support), \
         patch.object(answer,'_generate_research_correction') as retry:
        result=answer.recover_research_answer(plan=plan,decision=evidence(),draft=AgentLLMResult(draft(),'primary'),
            budget=CoachRequestBudget.start(),public_question='Confirm duties and application')
    assert result.result.content.count(question)==1
    assert FACT.rstrip('.') in result.result.content
    assert result.diagnostics['complete'] is False
    retry.assert_not_called()


def test_verifier_outage_does_not_authorize_draft():
    with patch.object(answer,'verify_grounding_claims',side_effect=TimeoutError):
        result=answer.check_research_draft(draft(),public_question='Duties?',decision=evidence(),budget=CoachRequestBudget.start())
    assert not result.is_valid and result.approved_text is None


def test_no_facts_cannot_be_replaced_by_quotes():
    empty=replace(evidence(),assessment=EvidenceAssessment('insufficient'))
    with patch.object(answer,'_generate_research_correction') as generate:
        result=answer.recover_research_answer(plan=QuestionPlan('agency',False,True,'stable'),decision=empty,
            draft=None,budget=CoachRequestBudget.start(),public_question='Duties?')
    generate.assert_not_called()
    assert FACT not in result.result.content


def test_no_evidence_still_asks_known_ambiguity():
    question='Which programme or service would you like to apply for?'
    plan=QuestionPlan('agency',False,True,'stable',required_facts=('duties','application procedure'),
        clarification=question,clarification_facts=('application procedure',))
    empty=ResearchDecision([],EvidenceAssessment('insufficient'),failure='search_failed')
    result=answer.recover_research_answer(plan=plan,decision=empty,draft=None,
        budget=CoachRequestBudget.start(),public_question='Duties and application?')
    assert question in result.result.content
    assert 'Please try again.' not in result.result.content


def test_untrusted_clarification_cannot_append_source_free_facts():
    plan=QuestionPlan('Agency',False,True,'stable',required_facts=('duties','application procedure'),
        clarification='Everyone is eligible for a grant. Which programme?',
        clarification_facts=('application procedure',))
    with patch.object(answer,'verify_grounding_claims',side_effect=support):
        result=answer.recover_research_answer(plan=plan,decision=evidence(),draft=AgentLLMResult(draft(),'primary'),
            budget=CoachRequestBudget.start(),public_question='Duties and application')
    assert 'Everyone is eligible' not in result.result.content
    assert '?' in result.result.content
    assert result.diagnostics['requested_scope_covered'] is False


def test_clarification_space_is_reserved_before_verifying_draft():
    question='Which programme or service would you like to apply for?'
    plan=QuestionPlan('Agency',False,True,'stable',required_facts=('duties','application procedure'),
        clarification=question,clarification_facts=('application procedure',))
    # A single long complete sentence is otherwise within the 200-word cap,
    # but adding the separately rendered question would exceed that limit.
    text='The agency '+('coordinates '*180)+'development projects.'
    long=draft().replace(FACT,text)
    with patch.object(answer,'verify_grounding_claims',side_effect=support), \
         patch.object(answer,'_generate_research_correction',return_value=AgentLLMResult(draft(),'fallback')) as retry:
        result=answer.recover_research_answer(plan=plan,decision=evidence(),draft=AgentLLMResult(long,'primary'),
            budget=CoachRequestBudget.start(),public_question='Duties and application')
    assert retry.call_count==1
    assert len(result.result.content.replace('**Insight**','').replace('**Educational guidance**','').split())<=200
    assert question in result.result.content
