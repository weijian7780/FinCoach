"""Restore only Coach-owned changes after a hash-verified source backup.

Does not touch .env, financial data, database state, receipt/admin code, Git
history, mobile sources or any VPS. Run once; preserve the backup on reruns.
"""
import hashlib
import json
from pathlib import Path
import shutil


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    root = Path(__file__).resolve().parents[1]
    checkpoint = root / 'docs/superpowers/plans/answer-completion-baseline'
    source = checkpoint / 'source'
    backup = root / 'docs/superpowers/plans/pre-rollback-2026-10-05'
    if backup.exists():
        raise RuntimeError('Backup already exists; refuse to overwrite it')
    manifest = json.loads((checkpoint / 'manifest.json').read_text(encoding='utf-8'))
    owned = {'app/config.py', 'app/llm.py', 'app/main.py'}
    targets = [item for item in manifest['files'] if item['path'] in owned
        or item['path'].startswith('app/rag/')]
    # Verify every restoration input before any workspace mutation.
    for item in targets:
        if digest(source / item['path']) != item['sha256']:
            raise RuntimeError('Baseline hash mismatch: ' + item['path'])
    backup.mkdir(parents=True)
    inventory = []
    paths = [p for p in (root / 'app').rglob('*') if p.is_file()
        and p.suffix in {'.py', '.json'} and '__pycache__' not in p.parts]
    paths += [root / name for name in ('docker-compose.yml', 'Dockerfile', 'requirements.txt')]
    for path in paths:
        relative = path.relative_to(root)
        destination = backup / 'source' / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, destination)
        if digest(destination) != digest(path):
            raise RuntimeError('Backup verification failed: ' + str(relative))
        inventory.append({'path': relative.as_posix(), 'sha256': digest(destination)})
    (backup / 'manifest.json').write_text(json.dumps({'files': inventory,
        'baseline': str(checkpoint.relative_to(root)), 'scope': 'Coach source only'}, indent=2), encoding='utf-8')
    changed = []
    for item in targets:
        target = root / item['path']
        if target.exists() and digest(target) == item['sha256']:
            continue
        shutil.copy2(source / item['path'], target)
        if digest(target) != item['sha256']:
            raise RuntimeError('Restore verification failed: ' + item['path'])
        changed.append(item['path'])
    (backup / 'restored-files.json').write_text(json.dumps(changed, indent=2), encoding='utf-8')
    print(json.dumps({'backup_verified_files': len(inventory), 'restored_files': changed}))


if __name__ == '__main__':
    main()
