"""Run the save-rule regression in an isolated disposable PostgreSQL database."""
import json
from pathlib import Path
import re
import subprocess
import uuid

ROOT = Path(__file__).resolve().parents[3]
BACKEND = ROOT/'fincoach-backend'
CONTAINER = 'fincoach-admin-test'
DATABASE = 'admin_editor_' + uuid.uuid4().hex[:12]
assert re.fullmatch(r'admin_editor_[0-9a-f]{12}', DATABASE)

def docker(*args):
    result = subprocess.run(['docker', *args], capture_output=True, text=True, check=True)
    return result.stdout + result.stderr

def apply(file):
    remote = '/tmp/editor-' + file.name
    docker('cp', str(file), CONTAINER+':'+remote)
    return docker('exec', CONTAINER, 'psql', '-U', 'postgres', '-d', DATABASE,
                  '-v', 'ON_ERROR_STOP=1', '-f', remote)

created = False
try:
    docker('exec', CONTAINER, 'createdb', '-U', 'postgres', DATABASE)
    created = True
    apply(BACKEND/'docs/admin/local-fixture.sql')
    apply(BACKEND/'sql/knowledge.sql')
    apply(ROOT/'fincoach-mobile/supabase/migrations/20261001100105_admin_panel.sql')
    docker('exec', CONTAINER, 'psql', '-U', 'postgres', '-d', DATABASE,
           '-v', 'ON_ERROR_STOP=1', '-c', "update public.account_access set role='admin' where user_id='00000000-0000-0000-0000-000000000001'")
    apply(ROOT/'fincoach-mobile/supabase/migrations/20261020081645_fix_existing_knowledge_editor_validation.sql')
    output = apply(BACKEND/'docs/admin/legacy-editor-regression.sql')
    assert 'Legacy editor regression passed' in output, output
    print(output.strip())
    print(json.dumps({'result':'passed','database':DATABASE,'fixtures_rolled_back':True}))
finally:
    if created:
        # This exact randomly named database was created above for this run.
        docker('exec', CONTAINER, 'dropdb', '-U', 'postgres', DATABASE)
