"""Validate a preserved source checkpoint using an isolated public STR query.

No source restoration, container restart, credentials output, private reads or
conversation persistence occurs here. The snapshot's own public probe enforces
the read/persistence boundary. Keep current files available for later recovery.
"""
import hashlib
import argparse
import json
import os
from pathlib import Path
import sys


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--attempt', type=int, choices=(1, 2), default=1)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    checkpoint = root / 'docs/superpowers/plans/answer-completion-baseline'
    source = checkpoint / 'source'
    manifest = json.loads((checkpoint / 'manifest.json').read_text(encoding='utf-8'))
    for item in manifest['files']:
        path = (source / item['path']).resolve()
        if not path.is_relative_to(source.resolve()):
            raise RuntimeError('Snapshot manifest escapes its source root')
        if hashlib.sha256(path.read_bytes()).hexdigest() != item['sha256']:
            raise RuntimeError('Snapshot hash mismatch: ' + item['path'])
    # Reproduce the recorded Desktop budget/provider choices without printing
    # secrets or overwriting .env. Reserve defaults must fit the older contract.
    os.environ.update(LLM_PRIMARY_MODEL='gemini-3.6-flash',
        COACH_RESEARCH_POLICY_ENABLED='true', COACH_REQUEST_DEADLINE_SECONDS='60',
        LLM_PRIMARY_TIMEOUT_SECONDS='50', LLM_FALLBACK_TIMEOUT_SECONDS='18',
        COACH_RESEARCH_ANSWER_RESERVE_SECONDS='30')
    # Import both the application and probe from the frozen checkpoint, rather
    # than accidentally testing today's service against yesterday's helpers.
    sys.path.insert(0, str(source))
    from scripts.research_recovery_probe import run_public_probe
    import app.rag.service as service
    assert Path(service.__file__).resolve().is_relative_to(source.resolve())
    filename = ('2026-10-05-rollback-baseline-str.json' if args.attempt == 1
        else '2026-10-05-rollback-baseline-str-repeat.json')
    output = root / 'docs/superpowers/plans' / filename
    if output.exists():
        raise RuntimeError('Existing paid result retained; refuse silent rerun')
    result = run_public_probe('how do i apply STR, what document do i need', warmup=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'snapshot_verified_files': len(manifest['files']),
        'complete': result['complete_answer'], 'elapsed_ms': result['elapsed_ms'],
        'model': result['model'], 'answer': result['answer']}, ensure_ascii=True))
    return 0 if result['complete_answer'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
