"""Opt-in fixed public evidence replay. No search, database access or model failover."""
from __future__ import annotations
import argparse
from dataclasses import asdict, fields
from hashlib import sha256
import json
import re
from pathlib import Path
import statistics
import sys
from time import monotonic
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.llm import CoachRequestBudget, _providers, _generate_with_provider
from app.llm_observability import result_metadata
from app.rag.retrieval import RetrievedChunk
from app.rag.research_policy import ResearchDecision, EvidenceAssessment, QuestionPlan
from app.rag.research_coverage import PartCoverage
from app.rag.research_source_spans import SourceSpan
from app.rag.research_fact_bindings import EvidenceFactBinding
from app.rag.prompts import build_research_recovery_prompt, RESEARCH_EXPLANATION_SYSTEM_PROMPT
from app.rag.research_answer import check_research_draft
from app.rag.research_answer import recover_research_answer


def _strict_dataclass(cls, data):
    if not isinstance(data, dict) or set(data) - {f.name for f in fields(cls)}:
        raise ValueError('Unknown or invalid replay fields')
    return cls(**data)


def load_public_decision(path):
    raw = json.loads(Path(path).read_text(encoding='utf-8-sig'))
    query = raw.get('query', '')
    if (not isinstance(query, str) or not re.search(r'\b(STR|Sumbangan Tunai Rahmah|SARA|AKPK|PTPTN|EPF|KWSP)\b', query, re.I)
            or re.search(r'@|\b(my salary|my balance|account number|phone number|password|personal transactions)\b', query, re.I)):
        raise ValueError('Approved public programme question required')
    # Accept the captured public probe shape, then produce a versioned closed bundle.
    if raw.get('schema_version') not in (None, 1):
        raise ValueError('Unknown replay version')
    if raw.get('schema_version') is None:
        # Only the approved captured public fixture may enter the legacy importer.
        approved = Path(__file__).resolve().parents[1] / 'docs/superpowers/plans/2026-10-04-public-source-fourth-failed-first.json'
        if sha256(Path(path).read_bytes()).digest() != sha256(approved.read_bytes()).digest():
            raise ValueError('Unapproved legacy replay')
    if raw.get('private_read_attempts', 0) or raw.get('persisted_writes', 0):
        raise ValueError('Public-only replay required')
    data = raw['public_decision']
    chunks = [_strict_dataclass(RetrievedChunk, dict(chunk,
        source_spans=tuple(_strict_dataclass(SourceSpan, span)
            for span in chunk.get('source_spans', ())))) for chunk in data['chunks']]
    hashes = [sha256(c.content.encode()).hexdigest() for c in chunks]
    if raw.get('schema_version') == 1 and raw.get('source_sha256') != hashes:
        raise ValueError('Replay source hash mismatch')
    if not chunks or len(chunks) > 6 or sum(len(c.content) for c in chunks) > 10800:
        raise ValueError('Evidence bounds exceeded')
    assessment = dict(data['assessment'])
    assessment['parts'] = tuple(_strict_dataclass(PartCoverage, dict(p, support_indices=tuple(p['support_indices']))) for p in assessment.get('parts', ()))
    assessment['supported_quotes'] = tuple(tuple(q) for q in assessment.get('supported_quotes', ()))
    assessment['supported_sources'] = tuple(assessment.get('supported_sources', ()))
    assessment['missing'] = tuple(assessment.get('missing', ()))
    assessment['fact_bindings'] = tuple(_strict_dataclass(EvidenceFactBinding,
        dict(binding, alternatives=tuple(binding.get('alternatives', ()))))
        for binding in assessment.get('fact_bindings', ()))
    assessment = _strict_dataclass(EvidenceAssessment, assessment)
    for index, quote in assessment.supported_quotes:
        if type(index) is not int or not 1 <= index <= len(chunks) or not isinstance(quote, str) or ' '.join(quote.split()) not in ' '.join(chunks[index-1].content.split()):
            raise ValueError('Invalid approved quote or source identity')
    plan_data = dict(raw['public_plans'][0])
    for key in ('entities', 'required_facts'):
        plan_data[key] = tuple(plan_data.get(key, ()))
    plan = _strict_dataclass(QuestionPlan, plan_data)
    if plan.needs_personal:
        raise ValueError('Public-only replay required')
    labels = raw.get('requested_parts', ())
    labels = [p['label'] if isinstance(p, dict) else p for p in labels]
    if not labels:
        labels = list(plan.required_facts)
    decision = ResearchDecision(chunks, assessment, data.get('web_used', False), data.get('failure'),
                                diagnostics={'requested_part_labels': labels})
    return raw['query'], plan, decision


def isolated_provider(role):
    matches = [provider for provider in _providers() if provider.role == role]
    if len(matches) != 1:
        raise ValueError('Exactly one configured provider for requested role is required')
    return matches[0]


def summarize(rows):
    success = [r['writer_seconds'] for r in rows if 'writer_seconds' in r and not r.get('writer_error')]
    result = dict(trials=len(rows), writer_successes=len(success),
                  writer_errors=sum(bool(r.get('writer_error')) for r in rows),
                  complete=sum(bool(r.get('complete')) for r in rows),
                  truncated=sum((r.get('finish_reason') or '').upper() in ('LENGTH', 'MAX_TOKENS') for r in rows),
                  censored_timeouts=sum('Timeout' in r.get('writer_error', '') for r in rows))
    if success:
        ordered = sorted(success)
        result.update(latency_median=statistics.median(ordered), latency_p90=ordered[min(len(ordered)-1, int(.9*len(ordered)))])
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--live', action='store_true')
    parser.add_argument('--decision', required=True)
    parser.add_argument('--runs', type=int, default=10)
    parser.add_argument('--role', choices=('primary', 'fallback'), required=True)
    parser.add_argument('--primary-max-tokens', type=int, default=4096)
    parser.add_argument('--output', required=True)
    parser.add_argument('--candidate', action='store_true')
    args = parser.parse_args()
    if not args.live or not 1 <= args.runs <= 10 or args.primary_max_tokens not in (4096, 8192, 32768):
        parser.error('Explicit --live, 1..10 trials and approved cap required')
    query, plan, decision = load_public_decision(args.decision)
    provider = isolated_provider(args.role)
    # Replay the current Markdown writer contract. The retired block-prompt
    # import must not break collection or mislabel a different prompt as live.
    prompt = build_research_recovery_prompt(query, decision)
    system_prompt = RESEARCH_EXPLANATION_SYSTEM_PROMPT
    from openai import OpenAI
    rows = []
    output = dict(schema_version=1, query=query, public_plans=[asdict(plan)],
                  public_decision=asdict(decision), requested_parts=decision.diagnostics['requested_part_labels'],
                  source_sha256=[sha256(c.content.encode()).hexdigest() for c in decision.chunks],
                  decision_sha256=sha256(Path(args.decision).read_bytes()).hexdigest(),
                  prompt=prompt, prompt_sha256=sha256(prompt.encode()).hexdigest(),
                  prompt_fidelity='reconstructed from saved public decision; original prompt unavailable',
                  requested_role=args.role, requested_model=provider.model, trials=rows,
                  candidate=args.candidate,
                  private_read_attempts=0, persisted_writes=0, searches=0, recovery_calls=0)
    if Path(args.output).exists():
        previous = json.loads(Path(args.output).read_text(encoding='utf-8'))
        if any(previous.get(key) != output[key] for key in ('prompt_sha256', 'requested_role', 'requested_model', 'decision_sha256', 'candidate')):
            raise ValueError('Cannot resume a different experiment')
        rows.extend(previous['trials'])
    for index in range(len(rows), args.runs):
        started = monotonic()
        row = dict(trial=index+1, requested_role=args.role, requested_model=provider.model, complete=False)
        budget = CoachRequestBudget.start()
        try:
            result = _generate_with_provider(OpenAI, provider, prompt, reasoning_effort='high',
                timeout_seconds=20 if args.role == 'primary' else 18,
                system_prompt=system_prompt,
                max_tokens=args.primary_max_tokens if args.role == 'primary' else 32768)
            row.update(writer_seconds=monotonic()-started, returned_model=result.model,
                       content=result.content, visible_characters=len(result.content),
                       prompt_tokens=result.prompt_tokens, completion_tokens=result.completion_tokens,
                       **result_metadata(result))
            if args.candidate:
                outcome = recover_research_answer(plan=plan, decision=decision, draft=result,
                                                  budget=budget, public_question=query)
                row.update(outcome=asdict(outcome), complete=outcome.diagnostics['complete'])
                output['recovery_calls'] += int(outcome.recovery_used)
            else:
                checked = check_research_draft(result.content, public_question=query, decision=decision,
                    completion=result, budget=budget.for_stage(max_seconds=8))
                row.update(check=asdict(checked), complete=checked.is_valid and not checked.diagnostics.get('coverage_note_count'))
        except Exception as exc:
            row.update(writer_error=type(exc).__name__, writer_seconds=monotonic()-started)
            row.update(getattr(exc, 'completion_metadata', {}))
        rows.append(row)
        output['summary'] = summarize(rows)
        Path(args.output).write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps(dict(trial=index+1, role=args.role, complete=row['complete'], error=row.get('writer_error'))), flush=True)


if __name__ == '__main__':
    main()
