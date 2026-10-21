"""One public Gemini reproduction and offline replay of saved DeepSeek outputs.

No search, private records, retries, failover, or configuration mutation.
Provider credentials are loaded internally and excluded from the report.
"""
import json
import argparse
import sys
from dataclasses import asdict, replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.assessment_binding_pilot import fixed_evidence
from app import llm
from app.llm_provider_session import ProviderSession
from app.rag import research_policy as policy
from openai import OpenAI
from pydantic import ValidationError


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--without-native-schema', action='store_true')
    parser.add_argument('--without-pattern', action='store_true')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    suffix = 'no-pattern' if args.without_pattern else ('no-native-schema' if args.without_native_schema else 'detail')
    target = root / f'docs/superpowers/plans/2026-10-05-provider-error-diagnosis-{suffix}.json'
    if target.exists():
        raise SystemExit('Existing diagnosis retained; do not silently repeat calls.')
    plan, chunks = fixed_evidence()
    saved = json.loads((root / 'docs/superpowers/plans/2026-10-05-assessment-binding-pilot.json').read_text())
    report = {'private_reads': 0, 'searches': 0, 'live_calls': 0, 'offline_replays': []}
    for trial in saved['trials']:
        if trial['role'] != 'fallback' or 'content' not in trial:
            continue
        payload = json.loads(trial['content'])
        errors = []
        for row in payload['fact_bindings']:
            try:
                policy._FactBindingProposal.model_validate(row)
            except ValidationError as exc:
                errors.extend({'binding': row['binding_id'], 'field': list(e['loc']),
                               'error': e['type'], 'actual_length': len(e['input'])}
                              for e in exc.errors(include_url=False))
        with patch.object(policy, 'COACH_RESEARCH_FACT_BINDING_LIMIT', trial['binding_limit']):
            replay = policy.assess_evidence(plan, chunks,
                generate=lambda *a, **kw: SimpleNamespace(content=trial['content']),
                budget=llm.CoachRequestBudget.start(provider_session=ProviderSession()),
                reserve_after_seconds=0)
        report['offline_replays'].append({'binding_limit': trial['binding_limit'],
            'finish_reason': trial['finish_reason'], 'schema_errors': errors,
            'current_assessment': asdict(replay)})
    # Test exactly the Compose primary model, rather than the local .env alias.
    provider = replace(next(p for p in llm._providers() if p.role == 'primary'), model='gemini-3.6-flash')
    report['primary'] = {'model': provider.model}
    # Write permission is checked before spending a live call.
    target.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')

    def generate(prompt, **kwargs):
        report['live_calls'] += 1
        schema = kwargs['response_schema']
        if args.without_pattern:
            def remove_pattern(value):
                if isinstance(value, dict):
                    return {k: remove_pattern(v) for k, v in value.items() if k != 'pattern'}
                if isinstance(value, list):
                    return [remove_pattern(v) for v in value]
                return value
            schema = remove_pattern(schema)
        try:
            result = llm._generate_with_provider(OpenAI, provider, prompt,
                reasoning_effort=kwargs['reasoning_effort'], timeout_seconds=12,
                structured=True, response_schema=None if args.without_native_schema else schema,
                max_tokens=kwargs['max_tokens'])
            report['primary'].update(content=result.content, finish_reason=getattr(result, 'finish_reason', None))
            return result
        except Exception as exc:
            # Only retain provider error fields, never request headers or URLs.
            body = getattr(exc, 'body', None)
            error = body.get('error', body) if isinstance(body, dict) else {}
            safe = {k: error[k] for k in ('code', 'status', 'message', 'param', 'type') if k in error}
            serialized = json.dumps(safe, ensure_ascii=False).replace(provider.api_key, '[REDACTED]')
            report['primary'].update(error_type=type(exc).__name__,
                http_status=getattr(exc, 'status_code', None), error=json.loads(serialized))
            # This endpoint may wrap errors in a list rather than an object.
            # Preserve its response body, not the credential-bearing request.
            response = getattr(exc, 'response', None)
            detail = response.text if response is not None else str(body)
            for configured in llm._providers():
                if configured.api_key:
                    detail = detail.replace(configured.api_key, '[REDACTED]')
                detail = detail.replace(configured.base_url, '[ENDPOINT]')
            report['primary']['response_body'] = detail[:6000]
            raise

    with patch.object(policy, 'COACH_RESEARCH_FACT_BINDING_LIMIT', 4):
        assessment = policy.assess_evidence(plan, chunks, generate=generate,
            budget=llm.CoachRequestBudget.start(provider_session=ProviderSession()), reserve_after_seconds=0)
    report['primary']['assessment'] = asdict(assessment)
    target.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False))


if __name__ == '__main__':
    main()
