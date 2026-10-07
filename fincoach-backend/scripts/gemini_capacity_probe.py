"""Opt-in primary-only replay of the three public Gemini diagnostic cases."""

import argparse
from dataclasses import replace
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from time import perf_counter
from urllib.parse import urlparse

# Supports direct invocation and piping into the already-configured container.
if __file__ != '<stdin>':
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from openai import OpenAI
from app.llm import _providers, _generate_with_provider
from app.rag.research_policy import assess_evidence, QuestionPlan
from app.rag.retrieval import RetrievedChunk


PUBLIC_DIAGNOSTIC_EXCERPTS = [
    'Repayment exemption conditions: 1. Pursuing full-time Bachelor degree studies; 2. Obtained First Class Honors; 3. Complete studies within the stipulated period; 4. Loan does not overlap with another sponsorship; 5. Private institution programmes require full MQA accreditation during the loan period; 6. Apply within 12 months from convocation. This announcement describes an incentive announced on 27 July 2022.',
    'Following the announcement on 27 July 2022, the incentive was extended to borrowers who obtained a First Class Bachelor degree regardless of economic status. Borrowers may apply through the PTPTN official portal. The original special application period was 15 September 2022 to 31 December 2022.',
    'From 1 January 2026, the exemption applies to eligible First Class graduates from public higher education institutions, subject to PTPTN conditions and income category requirements. The university advises borrowers to check the official PTPTN eligibility rules and submit their request through the official application channel.',
]


def safe_error(error, provider):
    """Print HTTP classification only, never headers, credentials or raw repr."""
    body = getattr(error, 'body', None)
    if isinstance(body, list) and body:
        body = body[0]
    if isinstance(body, dict):
        body = body.get('error', body)
    details = {k: str(body[k]).replace(provider.api_key, '[redacted]')[:300]
               for k in ('code', 'status', 'message') if isinstance(body, dict) and k in body}
    return dict(outcome='failed', error_type=type(error).__name__,
                http_status=getattr(error, 'status_code', None), error=details)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live', action='store_true')
    parser.add_argument('--model', required=True)
    parser.add_argument('--timeout', type=float, default=25)
    args = parser.parse_args()
    if not args.live or not 1 <= args.timeout <= 60:
        parser.error('Use --live and a timeout between 1 and 60 seconds.')
    configured = next(p for p in _providers() if p.role == 'primary')
    # Change this process's provider object only. Never write environment/config.
    provider = replace(configured, model=args.model)
    schema = dict(type='object', properties={'ok': {'type': 'boolean'}},
                  required=['ok'], additionalProperties=False)
    rows = []
    for name in ('tiny_plain', 'tiny_structured', 'realistic_checker_public_fixture'):
        started = perf_counter()
        row = dict(test=name, host=urlparse(provider.base_url).hostname,
                   model=provider.model, timeout_seconds=args.timeout,
                   reasoning_effort='low', sdk_retries=0, fallback=False)
        try:
            if name != 'realistic_checker_public_fixture':
                reply = _generate_with_provider(
                    OpenAI, provider, 'Return only the JSON object {"ok":true}.',
                    reasoning_effort='low', timeout_seconds=args.timeout,
                    system_prompt='Follow the requested output exactly.', max_tokens=128,
                    structured=name == 'tiny_structured',
                    response_schema=schema if name == 'tiny_structured' else None)
                row.update(outcome='completed', content=reply.content[:160],
                           prompt_tokens=reply.prompt_tokens, completion_tokens=reply.completion_tokens)
            else:
                # These synthetic public excerpts reproduce the previous probe;
                # they are test data, not independently verified financial advice.
                chunks = [RetrievedChunk(
                    id=-i-1, title='Public diagnostic excerpt', source='public diagnostic',
                    page_number=None, chunk_index=None, content=text, similarity=.8,
                    source_type='web', url='https://www.ptptn.gov.my/' if i < 2 else 'https://university.taylors.edu.my/',
                    tier=1 if i < 2 else 4, confidence='established', checked_at='2026-10-03')
                    for i, text in enumerate(PUBLIC_DIAGNOSTIC_EXCERPTS)]

                def generate(prompt, **kwargs):
                    row['prompt_characters'] = len(prompt)
                    try:
                        reply = _generate_with_provider(
                            OpenAI, provider, prompt, reasoning_effort='low',
                            timeout_seconds=args.timeout, max_tokens=1400,
                            structured=True, response_schema=kwargs.get('response_schema'))
                        row.update(outcome='completed', prompt_tokens=reply.prompt_tokens,
                                   completion_tokens=reply.completion_tokens)
                        return reply
                    except Exception as error:
                        row.update(safe_error(error, provider))
                        raise

                checked = assess_evidence(QuestionPlan(
                    'PTPTN waiver eligibility and application', False, True, 'current',
                    entities=('PTPTN',), required_facts=('eligibility', 'application steps', 'documents'),
                    original_question='How can I apply for a PTPTN waiver?'), chunks, generate=generate)
                row.update(assessment_status=checked.status, assessment_failure=checked.failure,
                           missing=list(checked.missing))
        except Exception as error:
            row.update(safe_error(error, provider))
        row['elapsed_ms'] = round((perf_counter() - started) * 1000, 1)
        rows.append(row)
        print(json.dumps(row), flush=True)
    print(json.dumps(dict(tested_at=datetime.now(timezone.utc).isoformat(), tests=rows,
                          configured_primary_unchanged=configured.model,
                          private_records_sent=False, persisted_writes=0)), flush=True)


if __name__ == '__main__':
    main()
