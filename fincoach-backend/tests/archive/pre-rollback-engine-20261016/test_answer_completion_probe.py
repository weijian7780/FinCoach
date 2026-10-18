from pathlib import Path
from unittest.mock import patch
import pytest
from scripts.answer_completion_probe import load_public_decision, isolated_provider, summarize
from app.llm import _Provider


def test_saved_public_decision_roundtrip(tmp_path):
    from dataclasses import asdict
    import json
    path = Path('docs/superpowers/plans/2026-10-04-public-source-fourth-failed-first.json')
    query, plan, decision = load_public_decision(path)
    output = tmp_path / 'public.json'
    output.write_text(json.dumps(dict(schema_version=1, query=query, public_plans=[asdict(plan)],
        public_decision=asdict(decision), requested_parts=decision.diagnostics['requested_part_labels'],
        source_sha256=[__import__('hashlib').sha256(c.content.encode()).hexdigest() for c in decision.chunks])), encoding='utf-8')
    assert load_public_decision(output)[2] == decision
    raw = json.loads(output.read_text())
    raw['source_sha256'][0] = '0' * 64
    output.write_text(json.dumps(raw))
    with pytest.raises(ValueError, match='hash mismatch'):
        load_public_decision(output)


def test_private_question_rejected(tmp_path):
    import json
    output = tmp_path / 'private.json'
    output.write_text(json.dumps({'query': 'STR my salary and account number'}))
    with pytest.raises(ValueError, match='public programme'):
        load_public_decision(output)


def test_isolated_role_does_not_select_fallback():
    primary = _Provider('primary', 'https://example.test', 'not-a-key', 'primary')
    fallback = _Provider('fallback', 'https://example.test', 'not-a-key', 'fallback')
    with patch('scripts.answer_completion_probe._providers', return_value=[primary, fallback]):
        assert isolated_provider('primary') is primary


def test_summary_includes_censored_failures():
    assert summarize([dict(writer_error='APITimeoutError', writer_seconds=18)])['censored_timeouts'] == 1
