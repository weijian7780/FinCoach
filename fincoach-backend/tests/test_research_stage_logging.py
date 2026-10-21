"""Diagnostics must label calls without recording prompts or changing deadlines."""
import json
from types import SimpleNamespace
from unittest.mock import MagicMock,patch
from app import llm


def test_stage_preserved_in_nested_budget():
    with patch.object(llm,'monotonic',return_value=10),patch.object(llm,'COACH_REQUEST_DEADLINE_SECONDS',120):
        root=llm.CoachRequestBudget(0)
        child=root.for_stage(max_seconds=20,stage_name='answer_generation')
        nested=child.for_stage(max_seconds=100)
        assert nested.stage_name=='answer_generation'
        assert nested.started_at==0
        assert nested.stage_deadline_at==child.stage_deadline_at


def test_finish_reason_and_usage_logged_without_private_payload(caplog):
    provider=llm._Provider('primary','https://provider.example/v1','secret-api-key','gemini-3.5-flash-lite')
    response=SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='A complete answer.'),finish_reason='stop')],
        usage=SimpleNamespace(prompt_tokens=100,completion_tokens=10))
    client=MagicMock(); client.chat.completions.create.return_value=response
    with caplog.at_level('INFO',logger='uvicorn.error'):
        result=llm._generate_with_provider(lambda **kw:client,provider,'private balance RM99999',
            reasoning_effort='high',timeout_seconds=12,stage_name='evidence_assessment')
    events=[json.loads(record.message) for record in caplog.records if 'coach_provider_attempt' in record.message]
    assert events[-1]['stage']=='evidence_assessment'
    assert events[-1]['finish_reason']=='stop'
    assert events[-1]['prompt_tokens']==100 and events[-1]['completion_tokens']==10
    assert events[-1]['timeout_seconds']==12
    assert 'RM99999' not in caplog.text and 'secret-api-key' not in caplog.text
    assert result.content=='A complete answer.'
