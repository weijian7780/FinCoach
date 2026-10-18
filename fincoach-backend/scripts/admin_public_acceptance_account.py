"""Create/clean up only the disposable account used by the browser acceptance run."""
import json
import secrets
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.supabase_client import get_supabase

manifest = Path(__file__).resolve().parents[2] / 'fincoach-admin/output/playwright/public-acceptance-account.json'
email = 'fincoach-public-qa-20261012-0951@example.invalid'
client = get_supabase()
if sys.argv[1] == 'create':
    if manifest.exists():
        raise RuntimeError('Fixture already recorded; do not create a duplicate.')
    user = client.auth.admin.create_user({'email': email, 'password': secrets.token_urlsafe(32), 'email_confirm': True, 'user_metadata': {'full_name': 'Disposable admin acceptance test'}}).user
    record = {'id': str(user.id), 'email': email}
    manifest.write_text(json.dumps(record), encoding='utf-8')
    print(json.dumps(record))
elif sys.argv[1] == 'delete':
    record = json.loads(manifest.read_text(encoding='utf-8'))
    # Check the server identity before deleting; never infer an ID from a search.
    user = client.auth.admin.get_user_by_id(record['id']).user
    if user.email != email or record['email'] != email:
        raise RuntimeError('Fixture identity mismatch; refusing cleanup.')
    client.auth.admin.delete_user(record['id'])
    record['deleted'] = True
    manifest.write_text(json.dumps(record), encoding='utf-8')
    print('Disposable acceptance account deleted.')
else:
    raise RuntimeError('Expected create or delete.')
