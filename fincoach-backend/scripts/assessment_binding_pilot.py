"""Four fixed-public-evidence assessments, with no search, retry or failover.

The input is a checked-in public FAQ snapshot. This isolates response format
and latency from source discovery, without reading user records or secrets.
"""
from dataclasses import asdict
from hashlib import sha256
import argparse
import json
from pathlib import Path
import sys
from time import monotonic
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import llm
from app.llm_provider_session import ProviderSession
from app.rag import research_policy as policy
from app.rag.retrieval import RetrievedChunk
from app.rag.research_source_spans import read_source_spans


def fixed_evidence():
    root = Path(__file__).resolve().parents[1]
    pages = json.loads((root / 'docs/superpowers/plans/2026-10-04-public-source-seed-inspection.json').read_text(encoding='utf-8-sig'))
    url = next(u for u in pages if 'FAQ%20PERMOHONAN' in u)
    anchors = ('Bagaimanakah kaedah permohonan STR 2026',
               'Apakah dokumen yang perlu dikemukakan')
    chunks = []
    for index, anchor in enumerate(anchors):
        span, = read_source_spans(pages[url], anchors=(anchor,))
        if not span.complete:
            raise ValueError('The pilot requires complete fixed FAQ units.')
        chunks.append(RetrievedChunk(-index-1, 'STR 2026 official application FAQ',
            'bantuantunai.hasil.gov.my', None, index, span.content, .8,
            url=url, source_type='web', tier=1, confidence='sufficient',
            published_date='2025-11-27', source_spans=(span,),
            qualification_context=span.heading_context))
    plan = policy.QuestionPlan('Sumbangan Tunai Rahmah', False, True, 'current',
        period='2026', entities=('STR',), required_facts=('application steps', 'required documents'),
        original_question='How do I apply for STR 2026, and what documents do I need?',
        response_language='English', part_tracking=True)
    return plan, chunks


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--live', action='store_true')
    parser.add_argument('--output', required=True)
    parser.add_argument('--continue-after-recorded-connection-error', action='store_true')
    args = parser.parse_args()
    target = Path(args.output)
    if not args.live or target.exists():
        parser.error('Explicit --live and a new output path are required; failed trials are never overwritten.')
    plan, chunks = fixed_evidence()
    # Load provider configuration internally; never export endpoint credentials.
    providers = {p.role: p for p in llm._providers()}
    if not {'primary', 'fallback'} <= providers.keys():
        parser.error('Both configured providers are needed for the four-call pilot.')
    from openai import OpenAI
    report = dict(schema_version=1, question=plan.original_question,
        source_sha256=[sha256(c.content.encode()).hexdigest() for c in chunks],
        public_plan=asdict(plan), public_chunks=[asdict(c) for c in chunks],
        searches=0, private_read_attempts=0, persisted_writes=0, trials=[])
    target.parent.mkdir(parents=True, exist_ok=True)
    if args.continue_after_recorded_connection_error:
        # Preserve the first attempt made on 5 October before discovering the
        # local .env/Compose model difference and blocked report directory.
        # It consumes a pilot attempt and cannot establish the six-binding cap.
        report['trials'].append(dict(role='primary', binding_limit=6,
            model='gemini-3.8-flash', elapsed_seconds=.835, passed=False,
            failure='APIConnectionError', pilot_configuration_matches=False))
    # Fail before spending a provider call when the artifact path is unwritable.
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    for limit in (6, 4):
        for role in ('primary', 'fallback'):
            if any(r['role'] == role and r['binding_limit'] == limit for r in report['trials']):
                continue
            session = ProviderSession()
            budget = llm.CoachRequestBudget.start(provider_session=session)
            row = dict(role=role, binding_limit=limit, model=providers[role].model,
                       timeout_seconds=12 if role == 'primary' else 15)
            started = monotonic()
            def generate(prompt, **kwargs):
                result = llm._generate_with_provider(OpenAI, providers[role], prompt,
                    reasoning_effort=kwargs['reasoning_effort'], timeout_seconds=row['timeout_seconds'],
                    structured=True, response_schema=kwargs['response_schema'],
                    max_tokens=kwargs['max_tokens'], provider_session=session)
                from app.llm_observability import result_metadata
                row.update(content=result.content, completion_tokens=result.completion_tokens,
                           prompt_tokens=result.prompt_tokens, **result_metadata(result))
                return result
            with patch.object(policy, 'COACH_RESEARCH_FACT_BINDING_LIMIT', limit):
                assessment = policy.assess_evidence(plan, chunks, generate=generate,
                    budget=budget, reserve_after_seconds=0)
            row.update(elapsed_seconds=round(monotonic()-started, 3), assessment=asdict(assessment))
            # Require both complete requested parts and locally accepted literal
            # bindings. Later whole-draft scope controls remain a separate gate.
            row['passed'] = (assessment.failure is None and assessment.status == 'sufficient'
                and len(assessment.parts) == 2 and all(p.complete for p in assessment.parts)
                and bool(assessment.fact_bindings) and all(b.scope_known for b in assessment.fact_bindings))
            report['trials'].append(row)
            target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
            print(json.dumps({k: row[k] for k in ('role', 'binding_limit', 'elapsed_seconds', 'passed')}
                | {'failure': assessment.failure}), flush=True)
    report['selected_binding_limit'] = next((limit for limit in (6, 4)
        if all(r['passed'] for r in report['trials'] if r['binding_limit'] == limit)), None)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    return 0 if report['selected_binding_limit'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
