"""Offline replay of saved public checker failures; no network or user reads.

This records model verdicts separately from local scope decisions so a transport
failure cannot be confused with evidence rejected by the application itself.
"""
import json
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.rag.grounding import GroundingClaim
from app.rag.research_fact_bindings import EvidenceFactBinding
from app.rag.research_scope import scope_verdict
from app.rag.research_blocks import parse_finished_blocks


def audit():
    directory = Path(__file__).resolve().parents[1] / 'docs/superpowers/plans/evidence-group-live-2026-10-05-policy-v3'
    cases = []
    for name in ('str', 'akpk', 'epf', 'sara'):
        saved = json.loads((directory / f'{name}.json').read_text(encoding='utf-8'))
        bindings = {row['binding_id']: EvidenceFactBinding(**dict(row, alternatives=tuple(row['alternatives'])))
                    for row in saved['public_decision']['assessment']['fact_bindings']}
        replays = []
        for call in saved['verifier_responses']:
            # Inputs and outputs here are retained fixed public diagnostic data.
            claims = json.loads(call['prompt'].split('<claims>\n', 1)[1].split('\n</claims>', 1)[0])
            source_text = call['prompt'].split('<sources>\n', 1)[1].split('\n</sources>', 1)[0]
            segments = re.split(r'(?m)^\[S(\d+)\]\n', source_text)
            references = [segments[i + 1] for i in range(1, len(segments), 2)]
            verdicts = {row['id']: row for row in json.loads(call['content'])['claims']}
            rows = []
            for row in claims:
                item = verdicts[row['id']]
                claim = GroundingClaim(row['id'], row['claim'], tuple(row['cited_sources']))
                bound = tuple(bindings[key] for key in row.get('binding_ids', ()) if key in bindings)
                rows.append(dict(claim_id=claim.id, model_verdict=item['verdict'],
                    local_scope_verdict=scope_verdict(item, claim, references, bindings=bound),
                    unknown_binding_count=sum(not binding.scope_known for binding in bound)))
            replays.append(rows)
        attempts = [stage for stage in saved['stages'] if stage.get('event') == 'coach_provider_attempt']
        cases.append(dict(case=name, complete=saved['complete_answer'], elapsed_ms=saved['elapsed_ms'],
            raw_to_local_scope=replays,
            recovery_attempts=[dict(model=s['model'], outcome=s['outcome'],
                elapsed_ms=s['elapsed_ms'], applied_timeout_seconds=s.get('applied_timeout_seconds'),
                reasoning_mode=s.get('reasoning_mode'), requested_max_tokens=s.get('requested_max_tokens'))
                for s in attempts if s.get('role') == 'fallback' and s.get('stage') == 'generation']))
    gap = json.dumps(dict(part_id='p1', section='Recommended action',
        text='I have not confirmed the application process yet.', binding_ids=[]))
    return dict(cases=cases, gap_record_retained_count=len(parse_finished_blocks(gap,
        allowed_part_ids=('p1',), allowed_binding_ids=('b1',), require_bindings=True)),
        network_calls=0, private_reads=0, production_changes=0)


if __name__ == '__main__':
    print(json.dumps(audit(), indent=2))
