"""Two bounded public requests; no retries, failover, search or private reads."""
import json
import argparse
import sys
from dataclasses import asdict, replace
from pathlib import Path
from time import monotonic
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import llm
from app.llm_observability import result_metadata
from app.llm_provider_session import ProviderSession
from app.rag import research_policy as policy
from scripts.assessment_binding_pilot import fixed_evidence
from openai import OpenAI


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output-name', default='2026-10-05-flash-lite-smoke.json',
        choices=['2026-10-05-flash-lite-smoke.json', '2026-10-05-flash-lite-schema-fix-smoke.json',
                 '2026-10-05-flash-lite-group-smoke.json'])
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    target = root / 'docs/superpowers/plans' / args.output_name
    if target.exists():
        raise SystemExit('Retain previous results; no implicit rerun.')
    provider = replace(next(p for p in llm._providers() if p.role == 'primary'),
                       model='gemini-3.5-flash-lite')
    report = {'model': provider.model, 'private_reads': 0, 'searches': 0, 'calls': []}
    target.write_text(json.dumps(report), encoding='utf-8')

    def call(prompt, *, label, schema=None, tokens=128):
        row = {'stage': label, 'timeout_seconds': 15}
        report['calls'].append(row)
        start = monotonic()
        try:
            result = llm._generate_with_provider(OpenAI, provider, prompt,
                reasoning_effort='low', timeout_seconds=15,
                max_tokens=tokens, structured=schema is not None, response_schema=schema)
            row.update(success=True, content=result.content, **result_metadata(result))
            return result
        except Exception as exc:
            response = getattr(exc, 'response', None)
            body = response.text if response is not None else type(exc).__name__
            for configured in llm._providers():
                if configured.api_key:
                    body = body.replace(configured.api_key, '[REDACTED]')
                body = body.replace(configured.base_url, '[ENDPOINT]')
            row.update(success=False, error_type=type(exc).__name__,
                       http_status=getattr(exc, 'status_code', None), response_body=body[:6000])
            raise
        finally:
            row['elapsed_seconds'] = round(monotonic() - start, 3)
            target.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')

    try:
        call('Reply with exactly OK.', label='plain')
    except Exception:
        print(json.dumps(report))
        return 2
    plan, chunks = fixed_evidence()
    def generate(prompt, **kwargs):
        return call(prompt, label='coach_checker', schema=kwargs['response_schema'],
                    tokens=kwargs['max_tokens'])
    limit = 6 if args.output_name == '2026-10-05-flash-lite-group-smoke.json' else 4
    with patch.object(policy, 'COACH_RESEARCH_FACT_BINDING_LIMIT', limit):
        assessment = policy.assess_evidence(plan, chunks, generate=generate,
            budget=llm.CoachRequestBudget.start(provider_session=ProviderSession()), reserve_after_seconds=0)
    report['checker_assessment'] = asdict(assessment)
    target.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
