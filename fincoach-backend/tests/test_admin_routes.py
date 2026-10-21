"""HTTP permission/validation tests. No privileged client reaches the network."""
import unittest
from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.admin.routes import router, administrator
from app.auth import AuthenticatedUser


class AdminRouteTests(unittest.TestCase):
    def setUp(self):
        self.app = FastAPI()
        self.app.include_router(router)
        self.client = TestClient(self.app)

    def test_audit_resolves_revision_titles_and_missing_records(self):
        from types import SimpleNamespace
        self.app.dependency_overrides[administrator] = lambda: AuthenticatedUser('admin', 'token')
        actor = '11111111-1111-4111-8111-111111111111'
        source = '22222222-2222-4222-8222-222222222222'
        revision = '33333333-3333-4333-8333-333333333333'
        rows = [dict(id=1, actor_id=actor, action='knowledge.draft', target_type='knowledge_source', target_id=source, details={'revision_id': revision}),
                dict(id=2, actor_id=actor, action='knowledge.archive', target_type='knowledge_source', target_id=source, details={'revision_id': None}),
                dict(id=3, actor_id=actor, action='account.suspended', target_type='account', target_id=source, details={'reason': 'Review'})]
        results = [SimpleNamespace(data=rows, count=3),
                   SimpleNamespace(data=[{'user_id': actor, 'email': 'admin@example.test'}]),
                   SimpleNamespace(data=[{'id': source, 'title': 'Current title'}]),
                   SimpleNamespace(data=[{'id': revision, 'source_id': source, 'title': 'Historical title'}])]
        with patch('app.admin.routes.get_supabase'), patch('app.admin.routes.admin_read', side_effect=results):
            response = self.client.get('/api/admin/audit')
        self.assertEqual(response.status_code, 200)
        items = response.json()['items']
        self.assertEqual(items[0]['target_name'], 'Historical title')
        self.assertEqual(items[1]['target_name'], 'Current title')
        self.assertEqual(items[2]['target_name'], 'Account unavailable')
        self.assertEqual(items[0]['actor_name'], 'admin@example.test')
        self.assertEqual(items[2]['details'], {'reason': 'Review'})

    def test_disabled_panel_fails_closed(self):
        with patch('app.admin.routes.config.ADMIN_PANEL_ENABLED', False):
            self.assertEqual(self.client.get('/api/admin/accounts').status_code, 503)

    def test_every_management_route_requires_authentication(self):
        with patch('app.admin.routes.config.ADMIN_PANEL_ENABLED', True), patch('app.admin.routes.config.ACCOUNT_ACCESS_ENFORCED', True):
            for path in ('/me', '/accounts', '/dashboard', '/audit', '/knowledge', '/knowledge/11111111-1111-4111-8111-111111111111/revisions?offset=50'):
                with self.subTest(path=path):
                    self.assertEqual(self.client.get('/api/admin' + path).status_code, 401)

    def test_student_cannot_read_account_list(self):
        client = MagicMock()
        client.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value.data = {'role': 'student', 'status': 'active'}
        with patch('app.admin.routes.config.ADMIN_PANEL_ENABLED', True), patch('app.admin.routes.config.ACCOUNT_ACCESS_ENFORCED', True), patch('app.admin.routes.require_authenticated_user', return_value=AuthenticatedUser('student', 'token')), patch('app.admin.service.get_supabase', return_value=client):
            self.assertEqual(self.client.get('/api/admin/accounts', headers={'Authorization': 'Bearer token'}).status_code, 403)

    def test_invalid_knowledge_body_never_reaches_database(self):
        self.app.dependency_overrides[administrator] = lambda: AuthenticatedUser('admin', 'token')
        with patch('app.admin.routes.admin_rpc') as rpc:
            response = self.client.post('/api/admin/knowledge', json={'title': 'Invalid', 'content': 'Body', 'source_urls': [], 'checked_at': '2999-01-01'})
        self.assertEqual(response.status_code, 422)
        rpc.assert_not_called()

    def test_link_import_requires_authentication(self):
        with patch('app.admin.routes.config.ADMIN_PANEL_ENABLED', True), patch('app.admin.routes.config.ACCOUNT_ACCESS_ENFORCED', True):
            self.assertEqual(self.client.post('/api/admin/imports/link', json={'url': 'https://example.org'}).status_code, 401)

    def test_unsafe_upload_never_reaches_storage(self):
        self.app.dependency_overrides[administrator] = lambda: AuthenticatedUser('admin', 'token')
        with patch('app.admin.routes.get_supabase') as database:
            response = self.client.post('/api/admin/uploads', files={'file': ('unsafe.exe', b'binary', 'application/octet-stream')})
        self.assertEqual(response.status_code, 422)
        database.assert_not_called()

    def test_account_action_forwards_verified_actor_and_expected_state(self):
        self.app.dependency_overrides[administrator] = lambda: AuthenticatedUser('verified-admin', 'token')
        with patch('app.admin.routes.admin_rpc', return_value={'status': 'suspended'}) as rpc:
            response = self.client.patch('/api/admin/accounts/11111111-1111-4111-8111-111111111111', json={'status': 'suspended', 'expected_status': 'active', 'reason': 'Account review'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(rpc.call_args.args[1]['p_actor'], 'verified-admin')
        self.assertEqual(rpc.call_args.args[1]['p_expected'], 'active')


class LiveStatusTests(unittest.TestCase):
    def test_existing_bearer_is_rejected_after_suspension(self):
        from types import SimpleNamespace
        from fastapi import HTTPException
        from app.auth import require_authenticated_user
        client = MagicMock()
        client.auth.get_user.return_value = SimpleNamespace(user=SimpleNamespace(id='student', is_anonymous=False))
        client.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value.data = {'status': 'suspended'}
        with patch('app.config.ACCOUNT_ACCESS_ENFORCED', True), patch('app.auth.get_supabase', return_value=client):
            with self.assertRaises(HTTPException) as caught:
                require_authenticated_user('Bearer still-valid-token')
        self.assertEqual(caught.exception.status_code, 403)

    def test_access_lookup_failure_never_grants_access(self):
        from types import SimpleNamespace
        from fastapi import HTTPException
        from app.auth import require_authenticated_user
        client = MagicMock()
        client.auth.get_user.return_value = SimpleNamespace(user=SimpleNamespace(id='student', is_anonymous=False))
        client.table.side_effect = RuntimeError('connection-secret')
        with patch('app.config.ACCOUNT_ACCESS_ENFORCED', True), patch('app.auth.get_supabase', return_value=client):
            with self.assertRaises(HTTPException) as caught:
                require_authenticated_user('Bearer token')
        self.assertEqual(caught.exception.status_code, 503)
        self.assertNotIn('secret', caught.exception.detail)
