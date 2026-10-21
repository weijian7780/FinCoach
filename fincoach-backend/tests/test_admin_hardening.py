"""Regression tests for the 2026-10-21 admin audit fixes. No network calls."""
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.admin import routes
from app.admin.routes import administrator, router
from app.auth import AuthenticatedUser

ENABLED = (patch('app.admin.routes.config.ADMIN_PANEL_ENABLED', True), patch('app.admin.routes.config.ACCOUNT_ACCESS_ENFORCED', True))


class UploadBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.app = FastAPI()
        self.app.include_router(router)
        self.client = TestClient(self.app)

    def test_unauthenticated_upload_is_rejected_before_the_body_is_parsed(self):
        with ENABLED[0], ENABLED[1], patch('starlette.requests.Request.form') as form:
            response = self.client.post('/api/admin/uploads', files={'file': ('big.pdf', b'x' * (12 * 1024 * 1024), 'application/pdf')})
        self.assertEqual(response.status_code, 401)
        form.assert_not_called()

    def test_oversized_upload_is_rejected_without_storage(self):
        self.app.dependency_overrides[administrator] = lambda: AuthenticatedUser('admin', 'token')
        with patch('app.admin.routes.get_supabase') as database:
            response = self.client.post('/api/admin/uploads', files={'file': ('big.md', b'x' * (11 * 1024 * 1024), 'text/markdown')})
        self.assertEqual(response.status_code, 413)
        database.assert_not_called()

    def test_valid_upload_is_stored_under_the_administrator(self):
        self.app.dependency_overrides[administrator] = lambda: AuthenticatedUser('admin-id', 'token')
        with patch('app.admin.routes.get_supabase') as database:
            response = self.client.post('/api/admin/uploads', files={'file': ('Guide.md', b'# Guide\nBudget safely.', 'text/markdown')})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['filename'], 'Guide.md')
        path = database.return_value.storage.from_.return_value.upload.call_args.args[0]
        self.assertTrue(path.startswith('admin-id/') and path.endswith('/original.md'))

    def test_extra_form_fields_are_rejected(self):
        self.app.dependency_overrides[administrator] = lambda: AuthenticatedUser('admin', 'token')
        with patch('app.admin.routes.get_supabase') as database:
            response = self.client.post('/api/admin/uploads', data={'extra': 'x'}, files={'file': ('a.md', b'text', 'text/markdown')})
        self.assertEqual(response.status_code, 400)
        database.assert_not_called()


class LoginLimiterTests(unittest.TestCase):
    def setUp(self):
        routes._login_attempts.clear()
        self.app = FastAPI()
        self.app.include_router(router)
        self.client = TestClient(self.app)

    def tearDown(self):
        routes._login_attempts.clear()

    def test_tunnel_client_header_is_trusted_only_from_a_private_peer(self):
        request = lambda peer, header: SimpleNamespace(client=SimpleNamespace(host=peer), headers={'cf-connecting-ip': header})
        self.assertEqual(routes._client_address(request('172.18.0.1', '203.0.113.7')), '203.0.113.7')
        self.assertEqual(routes._client_address(request('8.8.8.8', '203.0.113.7')), '8.8.8.8')
        self.assertEqual(routes._client_address(request('172.18.0.1', 'not-an-ip')), '172.18.0.1')

    def test_only_failed_attempts_count(self):
        body = {'username': 'admin', 'password': 'secret'}
        with ENABLED[0], ENABLED[1], patch('app.admin.routes._sign_in_administrator', return_value={'access_token': 'a', 'refresh_token': 'r'}):
            for _ in range(15):
                self.assertEqual(self.client.post('/api/admin/login', json=body).status_code, 200)
        with ENABLED[0], ENABLED[1], patch('app.admin.routes._sign_in_administrator', side_effect=HTTPException(401, 'Sign-in failed.')):
            codes = [self.client.post('/api/admin/login', json=body).status_code for _ in range(11)]
        self.assertEqual(codes, [401] * 10 + [429])

    def test_one_client_cannot_lock_out_another_tunnel_client(self):
        body = {'username': 'admin', 'password': 'secret'}
        with ENABLED[0], ENABLED[1], patch('app.admin.routes._client_address', return_value='203.0.113.7'), \
                patch('app.admin.routes._sign_in_administrator', side_effect=HTTPException(401, 'Sign-in failed.')):
            for _ in range(10):
                self.client.post('/api/admin/login', json=body)
        with ENABLED[0], ENABLED[1], patch('app.admin.routes._client_address', return_value='198.51.100.9'), \
                patch('app.admin.routes._sign_in_administrator', return_value={'access_token': 'a', 'refresh_token': 'r'}):
            self.assertEqual(self.client.post('/api/admin/login', json=body).status_code, 200)


class AuthOutageTests(unittest.TestCase):
    def check(self, error):
        from app.auth import require_authenticated_user
        client = SimpleNamespace(auth=SimpleNamespace(get_user=MagicMock(side_effect=error)))
        with patch('app.auth.get_supabase', return_value=client), self.assertRaises(HTTPException) as caught:
            require_authenticated_user('Bearer token')
        return caught.exception.status_code

    def test_auth_service_failures_are_not_reported_as_sign_out(self):
        from supabase_auth.errors import AuthApiError, AuthRetryableError
        self.assertEqual(self.check(AuthRetryableError('gateway', 502)), 503)
        self.assertEqual(self.check(AuthApiError('server', 500, None)), 503)
        self.assertEqual(self.check(AuthApiError('rate limited', 429, None)), 503)

    def test_invalid_tokens_remain_unauthenticated(self):
        from supabase_auth.errors import AuthApiError
        self.assertEqual(self.check(AuthApiError('bad jwt', 401, None)), 401)
        self.assertEqual(self.check(AuthApiError('forbidden', 403, None)), 401)


class ActionForbiddenTests(unittest.TestCase):
    def test_protected_target_is_a_conflict_not_a_lost_admin_session(self):
        from app.admin.service import admin_rpc
        client = MagicMock()
        client.rpc.return_value.execute.side_effect = RuntimeError('ADMIN_FORBIDDEN')
        with patch('app.admin.service.get_supabase', return_value=client), self.assertRaises(HTTPException) as caught:
            admin_rpc('admin_set_account_status', {})
        self.assertEqual(caught.exception.status_code, 409)


class OrphanUploadSweepTests(unittest.TestCase):
    def test_removes_only_old_unreferenced_originals(self):
        from app.admin.worker import sweep_orphan_uploads
        now = datetime(2026, 10, 21, tzinfo=timezone.utc)
        old = (now - timedelta(days=2)).isoformat().replace('+00:00', 'Z')
        new = (now - timedelta(hours=1)).isoformat().replace('+00:00', 'Z')
        tree = {
            '': [{'name': 'admin'}],
            'admin': [{'name': 'kept'}, {'name': 'orphan'}, {'name': 'recent'}],
            'admin/kept': [{'name': 'original.md', 'created_at': old}],
            'admin/orphan': [{'name': 'original.pdf', 'created_at': old}],
            'admin/recent': [{'name': 'original.txt', 'created_at': new}],
        }
        client = MagicMock()
        client.table.return_value.select.return_value.not_.is_.return_value.execute.return_value.data = [{'file_path': 'admin/kept/original.md'}]
        bucket = client.storage.from_.return_value
        bucket.list.side_effect = lambda path, options: tree.get(path, [])
        self.assertEqual(sweep_orphan_uploads(client, now), 1)
        bucket.remove.assert_called_once_with(['admin/orphan/original.pdf'])

    def test_nothing_removed_when_all_referenced(self):
        from app.admin.worker import sweep_orphan_uploads
        client = MagicMock()
        client.table.return_value.select.return_value.not_.is_.return_value.execute.return_value.data = []
        client.storage.from_.return_value.list.return_value = []
        self.assertEqual(sweep_orphan_uploads(client), 0)
        client.storage.from_.return_value.remove.assert_not_called()


if __name__ == '__main__':
    unittest.main()
