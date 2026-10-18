"""Bounded, fixed-public-input schema diagnostics; no retry or failover.

HTTP acceptance is measured separately from answer validation: a deliberately
small output cap reduces cost and may yield a truncated diagnostic response.
"""
import argparse
import copy
import json
import sys
from dataclasses import replace
from pathlib import Path
from time import monotonic
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import llm
from app.llm_observability import result_metadata
from app.llm_provider_session import ProviderSession
from app.rag import research_policy as policy
from scripts.assessment_binding_pilot import fixed_evidence
from openai import OpenAI


def inline_refs(schema):
    """Resolve local references only; preserve every constraint and field."""
    definitions = schema.get('$defs', {})
    def visit(node):
        if isinstance(node, list):
            return [visit(item) for item in node]
        if not isinstance(node, dict):
            return node
        if '$ref' in node:
            ref = node['$ref']
            if not ref.startswith('#/$defs/'):
                raise ValueError('Only local fixed-schema refs are supported')
            return visit(dict(definitions[ref[len('#/$defs/'):]],
                              **{k: v for k, v in node.items() if k != '$ref'}))
        return {k: visit(v) for k, v in node.items() if k != '$defs'}
    return visit(schema)


def omit_keywords(schema, keys):
    if isinstance(schema, list):
        return [omit_keywords(v, keys) for v in schema]
    if isinstance(schema, dict):
        return {k: omit_keywords(v, keys) for k, v in schema.items() if k not in keys}
    return schema


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('variant', choices=['original', 'inline_refs', 'no_string_bounds',
        'no_min_length', 'no_max_length', 'no_pattern', 'no_defaults', 'basic_schema', 'native_original', 'core_schema',
        'no_string_constraints', 'no_pattern_max_length', 'no_array_bounds', 'no_number_bounds', 'no_additional_properties',
        'no_alternatives_bound', 'no_fact_bindings_bound'])
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    target = root / f'docs/superpowers/plans/2026-10-05-schema-isolation-{args.variant}.json'
    if target.exists():
        raise SystemExit('Do not overwrite or silently repeat paid diagnostics')
    # Capture the exact current public checker prompt without an SDK call.
    captured = {}
    def capture(prompt, **kwargs):
        captured.update(prompt=prompt, schema=kwargs['response_schema'])
        raise RuntimeError('capture_only')
    plan, chunks = fixed_evidence()
    with patch.object(policy, 'COACH_RESEARCH_FACT_BINDING_LIMIT', 4):
        policy.assess_evidence(plan, chunks, generate=capture,
            budget=llm.CoachRequestBudget.start(provider_session=ProviderSession()), reserve_after_seconds=0)
    schema = copy.deepcopy(captured['schema'])
    if args.variant == 'inline_refs':
        schema = inline_refs(schema)
    elif args.variant == 'no_alternatives_bound':
        schema['$defs']['_FactBindingProposal']['properties']['alternatives'].pop('maxItems')
    elif args.variant == 'no_fact_bindings_bound':
        schema['properties']['fact_bindings'].pop('maxItems')
    elif args.variant.startswith('no_'):
        keys = {'no_string_bounds': {'minLength', 'maxLength'}, 'no_min_length': {'minLength'},
                'no_max_length': {'maxLength'}, 'no_pattern': {'pattern'}, 'no_defaults': {'default'},
                'no_string_constraints': {'pattern', 'minLength', 'maxLength'},
                'no_pattern_max_length': {'pattern', 'maxLength'},
                'no_array_bounds': {'minItems', 'maxItems'}, 'no_number_bounds': {'minimum', 'maximum'},
                'no_additional_properties': {'additionalProperties'}}
        schema = omit_keywords(schema, keys[args.variant])
    elif args.variant == 'basic_schema':
        schema = {'type': 'object', 'properties': {'status': {'type': 'string'}}, 'required': ['status']}
    elif args.variant == 'core_schema':
        schema = omit_keywords(inline_refs(schema), {'default', 'pattern', 'minLength',
            'maxLength', 'minimum', 'maximum', 'minItems', 'maxItems', 'title', 'additionalProperties'})
    provider = replace(next(p for p in llm._providers() if p.role == 'primary'),
                       model='gemini-3.5-flash-lite')
    report = {'variant': args.variant, 'model': provider.model, 'calls': 1,
              'private_reads': 0, 'searches': 0, 'schema': schema, 'prompt': captured['prompt'],
              'max_tokens': 256, 'timeout_seconds': 15}
    target.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
    started = monotonic()
    try:
        if args.variant == 'native_original':
            # Same public schema through Google's native endpoint can expose
            # validation details hidden by the OpenAI compatibility adapter.
            import httpx
            from urllib.parse import urlparse
            endpoint = urlparse(provider.base_url)
            if endpoint.hostname != 'generativelanguage.googleapis.com':
                raise ValueError('Native probe requires the official Google endpoint')
            url = f'https://{endpoint.hostname}/v1beta/models/{provider.model}:generateContent'
            response = httpx.post(url, headers={'x-goog-api-key': provider.api_key}, timeout=15,
                json={'contents': [{'role': 'user', 'parts': [{'text': captured['prompt']}]}],
                    'systemInstruction': {'parts': [{'text': llm.SYSTEM_PROMPT}]},
                    'generationConfig': {'responseMimeType': 'application/json',
                        'responseJsonSchema': schema, 'maxOutputTokens': 256,
                        'thinkingConfig': {'thinkingLevel': 'low'}}})
            report.update(http_accepted=response.is_success, http_status=response.status_code,
                response_body=response.text.replace(provider.api_key, '[REDACTED]')[:10000])
        else:
            result = llm._generate_with_provider(OpenAI, provider, captured['prompt'],
                reasoning_effort='low', timeout_seconds=15, max_tokens=256,
                structured=True, response_schema=schema)
            report.update(http_accepted=True, content=result.content, **result_metadata(result))
    except Exception as exc:
        response = getattr(exc, 'response', None)
        body = response.text if response is not None else type(exc).__name__
        for configured in llm._providers():
            if configured.api_key:
                body = body.replace(configured.api_key, '[REDACTED]')
            body = body.replace(configured.base_url, '[ENDPOINT]')
        report.update(http_accepted=False, http_status=getattr(exc, 'status_code', None),
                      error_type=type(exc).__name__, response_body=body[:6000])
        metadata = getattr(exc, 'completion_metadata', None)
        if metadata is not None:
            # The SDK returned a completion; local rejection of truncation is
            # not an HTTP error and must not obscure schema acceptance.
            report.update(http_accepted=True, local_failure=str(exc), **metadata)
    report['elapsed_seconds'] = round(monotonic() - started, 3)
    target.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k not in {'schema', 'prompt', 'content'}}))


if __name__ == '__main__':
    main()
