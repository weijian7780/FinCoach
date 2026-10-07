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
