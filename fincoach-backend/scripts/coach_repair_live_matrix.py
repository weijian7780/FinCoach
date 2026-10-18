"""Run exactly 24 pre-labelled public Coach requests; never retry paid results.

Each conversation uses the existing public-only probe: ephemeral history,
read-only public corpus RPCs, and private tools forbidden. Two subprocesses at
most avoid shared monkeypatch state and bound provider load.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import subprocess
import sys

CASES = [
    ('relevance-compound', 'relevance', ['What is compound interest?', 'Can you give a simple example?'],
     ['Explain the definition', 'Give a relevant example; no unrelated comparison-table or salary-credit advice']),
    ('relevance-emergency', 'relevance', ['What is an emergency fund?', 'Give a simple student example.'],
     ['Explain the purpose', 'Give a student example without product recommendations']),
    ('numbers-annual', 'numerical_accuracy', ['Show RM10000 compounded at 6% annually for 10 years with no deposits.', 'Explain how the RM17908.48 result is calculated.'],
     ['RM17908.48; state annual compounding and assumptions', 'Consistent arithmetic and no invented personal balance']),
    ('numbers-simple', 'numerical_accuracy', ['Give an example of RM1000 growing at 5% annually for two years with no deposits.', 'How much of the final RM1102.50 is interest?'],
     ['RM1102.50 under stated assumptions', 'RM102.50 interest; do not confuse principal and interest']),
    ('qualified-pidm', 'qualifications', ['Does PIDM cover every investment sold by a bank?', 'Explain whether unit trusts and eligible deposits are treated the same.'],
     ['Do not universalize deposit protection', 'Preserve product eligibility qualifications and source support']),
    ('qualified-epf', 'qualifications', ['Can every EPF member withdraw all savings whenever they want?', 'Explain the main qualifications without assuming my age or account eligibility.'],
     ['Reject the universal premise and preserve withdrawal conditions', 'No invented personal eligibility; keep conditions attached to claims']),
    ('language-en', 'language_equivalence', ['Explain compound interest in English.', 'Give a simple annual compounding example in English.'],
     ['English definition', 'English example, correct arithmetic and relevant content']),
    ('language-ms', 'language_equivalence', ['Terangkan faedah kompaun dalam Bahasa Melayu.', 'Beri contoh mudah pengkompaunan tahunan dalam Bahasa Melayu.'],
     ['Malay definition equivalent to English case', 'Malay example, correct arithmetic and relevant content']),
    ('switch-en', 'topic_change', ['What is compound interest?', 'Switch topics: explain PIDM deposit protection in English.'],
     ['Compound-interest definition', 'PIDM answer without compound-interest carry-over']),
    ('switch-ms-en', 'topic_change', ['Apa itu faedah kompaun?', 'New topic: explain credit-card interest in English.'],
     ['Malay definition', 'English credit-card answer; no stale compound-interest request']),
    ('incomplete-fictional', 'incomplete_evidence', ['What are the official eligibility rules for the FinCoach Imaginary Student Grant ZQ-947?', 'If you cannot find an official source, say what remains unknown.'],
     ['No invented grant facts or citations', 'Explicit uncertainty without fabricating eligibility or application steps']),
    ('incomplete-personal', 'incomplete_evidence', ['What exact interest rate will my bank offer me next year?', 'I have not provided a bank or product. What can you safely explain?'],
     ['No invented future or personal rate', 'General qualified explanation; acknowledge unknown bank/product']),
]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--live', action='store_true')
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    if not args.live:
        parser.error('--live is required for bounded billable provider requests')
    if args.output_dir.exists():
        parser.error('Refusing to overwrite an earlier live matrix')
    args.output_dir.mkdir(parents=True)
    manifest = [dict(id=name, family=family, questions=questions, criteria=criteria)
                for name, family, questions, criteria in CASES]
    (args.output_dir/'manifest.json').write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding='utf-8')
    environment = dict(os.environ, COACH_RESEARCH_POLICY_ENABLED='true', COACH_WRITE_ACTIONS_ENABLED='false', PYTHONIOENCODING='utf-8')

    def run(case):
        name, family, questions, _ = case
        output = args.output_dir/f'{name}.json'
        command = [sys.executable, '-X', 'utf8', 'scripts/coach_follow_up_probe.py', '--live', '--output', str(output)]
        for question in questions:
            command += ['--query', question]
        try:
            result = subprocess.run(command, env=environment, capture_output=True, timeout=420)
            (args.output_dir/f'{name}.log').write_bytes(result.stdout+result.stderr)
            return dict(id=name, family=family, exit_code=result.returncode, artifact=output.exists())
        except subprocess.TimeoutExpired:
            return dict(id=name, family=family, error='probe_timeout', artifact=output.exists())

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(run, CASES))
    (args.output_dir/'execution.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
    print(json.dumps(results))
    return int(any(not result['artifact'] for result in results))


if __name__ == '__main__':
    raise SystemExit(main())
