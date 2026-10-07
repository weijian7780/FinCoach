"""Four public end-to-end Coach cases with the Desktop candidate settings.

Use ephemeral repositories/source caches; never load private conversations.
Each result is retained before moving to the next fixed question.
"""
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
# Safe, public deployment values only. Secrets stay in existing configuration.
os.environ.update(LLM_PRIMARY_MODEL='gemini-3.5-flash-lite',
    COACH_RESEARCH_POLICY_ENABLED='true',
    COACH_REQUEST_DEADLINE_SECONDS='120', COACH_STRUCTURED_TIMEOUT_SECONDS='15',
    LLM_PRIMARY_TIMEOUT_SECONDS='110', LLM_FALLBACK_TIMEOUT_SECONDS='24',
    COACH_RESEARCH_ANSWER_RESERVE_SECONDS='75', COACH_FINALIZATION_RESERVE_SECONDS='10',
    COACH_RESEARCH_PHASE_SECONDS='35', COACH_RESEARCH_INTERPRETATION_SECONDS='8',
    COACH_RESEARCH_WRITER_SECONDS='35', COACH_RESEARCH_CORRECTION_SECONDS='24',
    GROUNDING_VERIFIER_TIMEOUT_SECONDS='8', COACH_RESEARCH_FACT_BINDING_LIMIT='6')
from scripts.research_recovery_probe import run_public_probe


def main():
    root = Path(__file__).resolve().parents[1]
    from app.config import COACH_RESEARCH_POLICY_ENABLED
    assert COACH_RESEARCH_POLICY_ENABLED, 'Pilot must exercise the research policy'
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--run-name', default='evidence-group-live-2026-10-05-policy-v3')
    parser.add_argument('--case', choices=('str','akpk','epf','sara'))
    args = parser.parse_args()
    if not args.run_name or Path(args.run_name).name != args.run_name or args.run_name in {'.', '..'}:
        raise SystemExit('Run name must be one directory name')
    directory = root / 'docs/superpowers/plans' / args.run_name
    if directory.exists():
        raise SystemExit('Existing paid results retained; no silent rerun')
    directory.mkdir()
    cases = [
        ('str', 'how do i apply STR, what document do i need'),
        ('akpk', "How do I apply for AKPK's Debt Management Programme, who is eligible, and what documents do I need?"),
        ('epf', 'How do I apply for EPF education withdrawal, who qualifies, and what documents do I need?'),
        ('sara', 'How do I apply for SARA assistance? Explain the eligibility and application process in English.')]
    results = []
    if args.case:
        cases = [case for case in cases if case[0] == args.case]
    for name, question in cases:
        print(json.dumps({'starting': name}), flush=True)
        result = run_public_probe(question, warmup=not results)
        (directory / f'{name}.json').write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding='utf-8')
        results.append(result)
        print(json.dumps({'case': name, 'complete': result['complete_answer'],
            'elapsed_ms': result['elapsed_ms'], 'answer': result['answer'],
            'parts': result['part_coverage']}, ensure_ascii=False), flush=True)
    passed = all(r['complete_answer'] for r in results)
    (directory/'gate.json').write_text(json.dumps({'four_case_gate': passed and len(results) == 4,
        'tested_cases': [name for name, _ in cases], 'tested_case_gate': passed,
        'manual_semantic_review_required': True, 'deploy_authorized_by_results': False}), encoding='utf-8')
    return 0 if passed else 2


if __name__ == '__main__':
    raise SystemExit(main())
