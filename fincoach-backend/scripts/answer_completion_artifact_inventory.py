"""Reproduce the historical public artifact membership, never a traffic failure rate."""
from hashlib import sha256
import json
from pathlib import Path
import statistics


def main():
    root = Path(__file__).resolve().parents[1]
    docs = root/'docs/superpowers/plans'
    paths = set(docs.glob('2026-10-04-public-source*.json'))
    for directory in docs.glob('2026-10-04-public-source-acceptance*'):
        if directory.is_dir():
            paths.update(directory.glob('*.json'))
    unique, rows, counts = {}, [], {}
    for path in sorted(paths):
        raw = path.read_bytes()
        digest = sha256(raw).hexdigest()
        data = json.loads(raw.decode('utf-8-sig'))
        row = dict(path=path.relative_to(root).as_posix(), sha256=digest,
                   duplicate_of=unique.get(digest), query=data.get('query'), elapsed_ms=data.get('elapsed_ms'),
                   response_mode=data.get('response_mode'), generation_attempts=data.get('generation_attempts', []),
                   checks=[dict(valid=c.get('valid'), errors=c.get('errors', [])) for c in data.get('answer_checks', [])])
        rows.append(row)
        if digest not in unique:
            unique[digest] = row['path']
            for check in row['checks']:
                for code in check['errors']:
                    counts[code] = counts.get(code, 0)+1
    tokens = [a['completion_tokens'] for r in rows if r['duplicate_of'] is None
              for a in r['generation_attempts'] if type(a.get('completion_tokens')) is int]
    output = dict(collection_rule='Top-level 2026-10-04-public-source*.json plus *.json in dated public-source-acceptance directories; exact-byte SHA256 dedup only',
        limitation='Mixed code/provider versions and selected diagnostic requests. Collection profile only, never production reliability. Same-run nonidentical copies may remain.',
        files=len(rows), unique_files=len(unique), checker_error_counts=counts, artifacts=rows,
        completion_token_distribution=dict(count=len(tokens), minimum=min(tokens) if tokens else None,
            median=statistics.median(tokens) if tokens else None, maximum=max(tokens) if tokens else None))
    (docs/'answer-completion-baseline/artifact-inventory.json').write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(dict(files=len(rows), unique_files=len(unique), checker_error_counts=counts)))


if __name__=='__main__':
    main()
