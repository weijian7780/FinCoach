"""Frozen full-draft category controls; public source artifacts only, no retrieval."""
from __future__ import annotations
from dataclasses import asdict
from hashlib import sha256
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.rag.verifier import verify_grounding_claims, ResearchVerificationContext
from app.rag.grounding import GroundingClaim, DISCLAIMER
from app.rag.research_scope import research_verifier_cap


def freeze(root, output):
    """Freeze actual source bytes and whole eight-claim drafts before live scoring."""
    cases = []
    families = {
        'str': ('str-cold-2-0.json', [
            'You can apply for STR online through its official portal.',
            'The paper application form is BK-01.',
            'The BK-01 application form is free.',
            'You can obtain the paper form from the STR portal.',
            'You can also obtain it at a HASiL Office, Satellite Office or UTC.',
            'Submit the completed paper form with relevant supporting documents to a HASiL Office, Satellite Office or UTC.',
            'For married applicants, provide a copy of the marriage certificate issued by the State Islamic Religious Department or JPN.',
            'For adopted children, provide a copy of the JPN adoption registration certificate.'], [
            'Everyone must provide a copy of the JPN adoption registration certificate.',
            'For biological children, provide a copy of the JPN adoption registration certificate.',
            'Every applicant must provide a spouse death certificate instead of a marriage certificate.']),
        'sara': ('sara.json', [
            'SARA assistance is credited to eligible recipients’ MyKad.',
            'It is used to purchase basic items at selected stores.',
            'SARA is an extension of Sumbangan Tunai Rahmah.',
            'Unused SARA credit can carry over to the following months.',
            'Malaysians aged 18 and above receive a one-off RM100 from 9 February 2026.',
            'STR 2026 recipients verified as Extremely Poor or Poor in eKasih qualify for the stated RM100 or RM200 monthly assistance.',
            'That monthly assistance covers January through December 2026.',
            'No separate SARA application is required; STR application is required to qualify for SARA Bulanan.'], [
            'Only STR recipients verified as Extremely Poor or Poor in eKasih can receive any SARA assistance.',
            'Every Malaysian must register in eKasih and be verified as Extremely Poor or Poor to receive the one-off RM100.',
            'All Malaysians aged 18 and above receive RM200 every month regardless of STR eligibility.'])}
    for family, (name, faithful, mutants) in families.items():
        raw = json.loads((Path(root)/name).read_text(encoding='utf-8'))
        # Classifier-only gold fixtures: exact source windows are supplied whole.
        # This is not a production decision and cannot authorize new service facts.
        sources = [c['content'] for c in raw['public_decision']['chunks']]
        sources.append('\n'.join(raw['validated_quotes']))
        for index, mutation in enumerate([None, *mutants]):
            texts = list(faithful)
            target = 8 if family == 'str' else 6
            if mutation:
                texts[target-1] = mutation
            claims = [GroundingClaim(i+1, text, tuple(range(1,len(sources)+1))) for i,text in enumerate(texts)]
            draft = '**Insight**\n'+' '.join(texts[:4])+'\n\n**Recommended action**\n'+' '.join(texts[4:])+'\n\n**Educational guidance**\n'+DISCLAIMER
            cases.append(dict(id=f'{family}-{index}', family=family, query=raw['query'],
                sources=sources, source_sha256=[sha256(s.encode()).hexdigest() for s in sources],
                draft=draft, claims=[asdict(c) for c in claims], target_claim=target,
                expected='supported' if mutation is None else 'rejected'))
    Path(output).write_text(json.dumps(dict(schema_version=1, cases=cases), ensure_ascii=False, indent=2), encoding='utf-8')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--freeze-from')
    parser.add_argument('--fixture', required=True)
    parser.add_argument('--live', action='store_true')
    parser.add_argument('--output')
    args = parser.parse_args()
    if args.freeze_from:
        if Path(args.fixture).exists():
            parser.error('Frozen fixture already exists; do not overwrite after observing results')
        freeze(args.freeze_from, args.fixture)
        return
    if not args.live or not args.output:
        parser.error('--live and --output required')
    fixture = json.loads(Path(args.fixture).read_text(encoding='utf-8'))
    rows = []
    report = dict(schema_version=1, fixture_sha256=sha256(Path(args.fixture).read_bytes()).hexdigest(),
                  trials=rows, searches=0, persisted_writes=0, private_read_attempts=0)
    for repeat in range(1):
        for case in fixture['cases']:
            claims = [GroundingClaim(**dict(c, cited_indices=tuple(c['cited_indices']))) for c in case['claims']]
            result = verify_grounding_claims(claims, case['sources'], timeout_seconds=8,
                max_tokens=research_verifier_cap(claims, case['sources']),
                research_context=ResearchVerificationContext(case['query'], case['draft'], ()))
            technical = result.error_code is not None
            correct = (result.all_supported if case['expected']=='supported' else
                       not technical and result.verdicts.get(case['target_claim']) in {'misapplied','unsupported','contradicted'})
            rows.append(dict(case=case['id'], repeat=repeat+1, expected=case['expected'],
                correct=correct, technical_failure=technical, verification=asdict(result)))
            report['passed'] = all(r['correct'] for r in rows)
            Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
            print(json.dumps(dict(case=case['id'], repeat=repeat+1, correct=correct, error=result.error_code)), flush=True)


if __name__=='__main__':
    main()
