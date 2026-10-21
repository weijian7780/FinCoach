"""The public live harness carries real ephemeral conversation context only."""
from unittest.mock import MagicMock, patch
from app.rag import service, research_policy as p
from scripts.coach_follow_up_probe import run_public_conversation, PublicCorpus


def test_ephemeral_history_contains_actual_previous_assistant_context():
    histories=[]
    def interpret(question,history,**kwargs):
        histories.append(list(history))
        return p.QuestionPlan('ICU JPM',False,True,'stable',required_facts=('duties','application'),
            clarification='Which programme?',clarification_facts=('application',),subject_kind='agency')
    with patch('app.supabase_client.get_supabase',return_value=MagicMock()), \
         patch.object(service,'COACH_RESEARCH_POLICY_ENABLED',True), \
         patch.object(service,'interpret_question',side_effect=interpret), \
         patch.object(service,'retrieve',return_value=[]), \
         patch.object(service,'run_research_policy',return_value=p.ResearchDecision([],p.EvidenceAssessment('insufficient'))):
        result=run_public_conversation(['What does ICU JPM do?', 'Which application?'],warmup=False)
    assert len(result['turns'])==2
    prior=[item for item in histories[1] if item['role']=='assistant'][0]
    assert prior['content']==result['turns'][0]['answer']
    assert prior['ui_payload']['research_context']['clarification_facts']==['application']
    assert result['private_reads']==0 and result['persisted_messages']==0


def test_public_corpus_rejects_financial_tables_and_non_public_rpc():
    client=PublicCorpus(MagicMock())
    import pytest
    with pytest.raises(AssertionError):
        client.table('transactions')
    with pytest.raises(AssertionError):
        client.rpc('get_owner_spending',{})
