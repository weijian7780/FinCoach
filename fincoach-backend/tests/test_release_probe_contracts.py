"""Probes must respect the paid-call limit and complete acceptance matrix."""
import json
from types import SimpleNamespace
from unittest.mock import patch


def test_public_gate_includes_akpk_and_epf_failures(tmp_path):
    from scripts import public_source_acceptance as probe
    questions = []
    def run(question, **kwargs):
        questions.append(question)
        return dict(complete_answer='EPF' not in question,
            elapsed_ms=1, part_coverage=[], answer='test', source_reuse={})
    with patch.object(probe, 'run_public_probe', side_effect=run), \
         patch('sys.argv', ['probe', '--output-dir', str(tmp_path)]):
        assert probe.main() == 2
    assert len(questions) == 11
    assert not json.loads((tmp_path/'gate.json').read_text())['automatic_coverage_gate']


def test_verifier_controls_run_once_not_five_times(tmp_path):
    from scripts import answer_applicability_probe as probe
    fixture = tmp_path/'controls.json'
    fixture.write_text(json.dumps(dict(cases=[dict(id=f'c{i}', expected='supported',
        claims=[], sources=['public'], query='public', draft='draft', target_claim=1)
        for i in range(8)])))
    result = SimpleNamespace(error_code=None, all_supported=True, verdicts={})
    with patch.object(probe, 'verify_grounding_claims', return_value=result) as verify, \
         patch.object(probe, 'asdict', return_value={}), \
         patch('sys.argv', ['probe', '--live', '--fixture', str(fixture), '--output', str(tmp_path/'result.json')]):
        probe.main()
    assert verify.call_count == 8


def test_dummy_origin_accepts_only_the_two_fixed_paths():
    from scripts.tunnel_deadline_probe import DELAYS
    assert set(DELAYS.values()) == {120, 122} and len(DELAYS) == 2
