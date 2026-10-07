"""Hypothetical monthly allocations must not become saved-budget lookups."""
from unittest.mock import MagicMock, patch

import pytest

from app.llm import LLMResult
from app.rag.routing import CoachingRoute, route_coach_message, required_read_agent_tool_name

QUESTION = 'what if i have rm1000 monthly, what was the budget arrangement for that month'


@pytest.mark.parametrize('question', [
    QUESTION,
    'Suppose I have RM1500 monthly, what budget arrangement would work?',
    'If I receive RM900 per month, suggest a budget plan',
    'What would a monthly budget look like if I have RM1200?',
])
def test_hypothetical_arrangement_does_not_read_saved_budget(question):
    assert route_coach_message(question) == CoachingRoute.FINANCIAL_EDUCATION
    assert required_read_agent_tool_name(question) is None


@pytest.mark.parametrize('question', [
    'Show my budget breakdown',
    'How much of my RM1000 budget remains this month?',
    'What was my recorded budget for last month?',
])
def test_saved_budget_queries_remain_personal(question):
    assert route_coach_message(question) == CoachingRoute.PERSONAL_FINANCE


@pytest.mark.parametrize('history', [[], [
    {'id': 'old-user', 'role': 'user', 'content': 'How do I apply for STR?'},
    {'id': 'old-assistant', 'role': 'assistant', 'content': 'I could not retrieve the source details needed for this question.'},
]])
def test_stated_amount_reaches_allocation_without_research_or_personal_reads(history):
    from app.rag import service
    repository = MagicMock(user_id='test-user')
    repository.require_session.return_value = {'id': 'session', 'title': 'Chat'}
    repository.find_user_message.return_value = None
    repository.insert_user_message.return_value = {'id': 'message', 'role': 'user', 'content': QUESTION}
    repository.list_messages.return_value = history
    repository.complete_turn.side_effect = lambda **kwargs: kwargs['assistant_payload']
    result = LLMResult('A proposed allocation.', 'test-model')
    with (patch.object(service, 'COACH_RESEARCH_POLICY_ENABLED', True),
          patch.object(service, 'interpret_question', side_effect=AssertionError('No public policy research')),
          patch.object(service, 'retrieve', side_effect=AssertionError('Use the stated amount')),
          patch.object(service, 'generate_result', return_value=result) as generate,
          patch.object(service, '_ground_educational_answer', return_value=(result, False, False)),
          patch.object(service, 'AgentToolExecutor') as executor):
        reply = service.CoachingService(repository, MagicMock()).send_message('session', 'message', QUESTION)
    assert reply['assistant_message']['content'] == result.content
    executor.return_value.execute.assert_not_called()
    assert generate.call_count == 1
    prompt = generate.call_args.args[0]
    assert '500' in prompt and '300' in prompt and '200' in prompt
