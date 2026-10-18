"""Run real SQL assertions in the dedicated, disposable admin test container.

Never targets a Supabase URL or reads application secrets. The container must
already exist; a fresh database is created for each run to avoid partial state.
"""
from pathlib import Path
import subprocess
import uuid
import argparse
import tempfile

ROOT = Path(__file__).resolve().parents[3]
BACKEND = ROOT / 'fincoach-backend'
CONTAINER = 'fincoach-admin-test'
DATABASE = 'admin_test_' + uuid.uuid4().hex[:12]


def run(*args):
    subprocess.run(['docker', *args], check=True)


def sql_file(path: Path):
    remote = '/tmp/admin-' + path.name
    run('cp', str(path), f'{CONTAINER}:{remote}')
    run('exec', CONTAINER, 'psql', '-U', 'postgres', '-d', DATABASE,
        '-v', 'ON_ERROR_STOP=1', '-f', remote)


parser = argparse.ArgumentParser()
parser.add_argument('--full-schema', action='store_true')
parser.add_argument('--retrieval-plan', action='store_true')
options = parser.parse_args()
run('exec', CONTAINER, 'createdb', '-U', 'postgres', DATABASE)
# Roles are cluster-wide; the dedicated container supports one test invocation.
if options.full_schema:
    sql_file(BACKEND / 'docs/admin/full-schema-fixture.sql')
    # The pgvector image lacks hosted network, cron and vault extensions. Only
    # their CREATE EXTENSION statements are omitted; FinCoach SQL is unchanged.
    schema = (ROOT / 'fincoach-mobile/supabase/schema.sql').read_text(encoding='utf-8')
    hosted_extensions = ('pg_net', 'pg_cron', 'supabase_vault')
    lines = [line for line in schema.splitlines() if not any(line.lower().startswith('create extension if not exists ' + name + ' ') for name in hosted_extensions)]
    with tempfile.TemporaryDirectory(prefix='fincoach-admin-schema-') as temporary:
        schema_path = Path(temporary) / 'full-schema.sql'
        schema_path.write_text('\n'.join(lines), encoding='utf-8')
        sql_file(schema_path)
    run('exec', CONTAINER, 'psql', '-U', 'postgres', '-d', DATABASE, '-v', 'ON_ERROR_STOP=1', '-c', "insert into auth.users(id,email) values('00000000-0000-0000-0000-000000000001','admin@test.invalid'),('00000000-0000-0000-0000-000000000002','student@test.invalid');")
else:
    sql_file(BACKEND / 'docs/admin/local-fixture.sql')
sql_file(BACKEND / 'sql/knowledge.sql')
run('exec', CONTAINER, 'psql', '-U', 'postgres', '-d', DATABASE, '-v',
    'ON_ERROR_STOP=1', '-c', "insert into public.knowledge_documents(title,content,source,embedding,page_number,chunk_index,content_hash) values('Legacy corpus','Legacy financial content','legacy.md',array_fill(1::real,array[1024])::vector,7,0,'legacy-hash');")
sql_file(ROOT / 'fincoach-mobile/supabase/migrations/20261001100105_admin_panel.sql')
sql_file(BACKEND / ('docs/admin/full-schema-assertions.sql' if options.full_schema else 'docs/admin/local-assertions.sql'))
if options.retrieval_plan:
    # A legacy SQL rerun must fail atomically before replacing the new RPCs.
    guard = subprocess.run(['docker', 'exec', CONTAINER, 'psql', '-U', 'postgres', '-d', DATABASE, '-v', 'ON_ERROR_STOP=1', '-f', '/tmp/admin-knowledge.sql'], capture_output=True, text=True)
    if guard.returncode == 0 or 'Versioned knowledge schema detected' not in guard.stderr:
        raise RuntimeError('Legacy SQL bootstrap guard did not reject the migrated schema.')
    print('Legacy SQL bootstrap correctly rejected the migrated schema.')
    sql_file(BACKEND / 'docs/admin/retrieval-plan-check.sql')
print(f'Passed in isolated database {DATABASE}; no hosted database contacted.')
