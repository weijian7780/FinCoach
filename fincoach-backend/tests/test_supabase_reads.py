"""Transient network errors must not bypass access checks or replay writes."""
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.auth import AuthenticatedUser, require_authenticated_user
from app.admin.routes import administrator, router
from app.admin.service import admin_rpc, require_administrator
from app.supabase_client import retry_supabase_read


class SupabaseReadRecoveryTests(unittest.TestCase):
    def test_read_recovers_after_one_disconnection(self):
        expected = SimpleNamespace(data=[{'id': 'actual-record'}], count=1)
        operation = MagicMock(side_effect=[httpx.RemoteProtocolError('Server disconnected'), expected])
        self.assertIs(retry_supabase_read(operation), expected)
        self.assertEqual(operation.call_count, 2)

    def test_read_retries_are_bounded(self):
        operation = MagicMock(side_effect=httpx.RemoteProtocolError('Server disconnected'))
        with self.assertRaises(httpx.RemoteProtocolError):
            retry_supabase_read(operation)
        self.assertEqual(operation.call_count, 2)

    def test_non_transport_errors_are_not_retried(self):
        operation = MagicMock(side_effect=RuntimeError('Permission denied'))
        with self.assertRaises(RuntimeError):
            retry_supabase_read(operation)
        operation.assert_called_once()

    def test_admin_permissions_are_checked_again_after_recovery(self):
        client = MagicMock()
        execute = client.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute
        execute.side_effect = [httpx.RemoteProtocolError('Server disconnected'), SimpleNamespace(data={'role': 'student', 'status': 'active'})]
        with patch('app.admin.service.get_supabase', return_value=client), self.assertRaises(HTTPException) as caught:
            require_administrator(AuthenticatedUser('selected-user', 'token'))
        self.assertEqual(caught.exception.status_code, 403)
        self.assertEqual(execute.call_count, 2)

    def test_auth_transport_failure_is_unavailable_not_invalid_credentials(self):
        client = MagicMock()
        client.auth.get_user.side_effect = httpx.RemoteProtocolError('connection-secret')
        with patch('app.auth.get_supabase', return_value=client), self.assertRaises(HTTPException) as caught:
            require_authenticated_user('Bearer token')
        self.assertEqual(caught.exception.status_code, 503)
        self.assertNotIn('secret', caught.exception.detail)
        self.assertEqual(client.auth.get_user.call_count, 2)

    def test_mutating_rpc_is_never_replayed_after_disconnection(self):
        client = MagicMock()
        execute = client.rpc.return_value.execute
        execute.side_effect = httpx.RemoteProtocolError('Server disconnected')
        with patch('app.admin.service.get_supabase', return_value=client), self.assertRaises(HTTPException) as caught:
            admin_rpc('admin_save_knowledge_revision', {'p_actor': 'verified-admin'})
        self.assertEqual(caught.exception.status_code, 503)
        execute.assert_called_once()

    def test_dashboard_outage_returns_json_without_partial_or_fake_counts(self):
        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[administrator] = lambda: AuthenticatedUser('verified-admin', 'token')
        client = MagicMock()
        execute = client.table.return_value.select.return_value.execute
        execute.side_effect = httpx.RemoteProtocolError('connection-secret')
        with patch('app.admin.routes.get_supabase', return_value=client):
            response = TestClient(app).get('/api/admin/dashboard')
        self.assertEqual(response.status_code, 503)
        self.assertIn('temporarily unavailable', response.json()['detail'])
        self.assertNotIn('secret', response.text)
        self.assertNotIn('counts', response.json())
        self.assertEqual(execute.call_count, 2)


if __name__ == '__main__':
    unittest.main()
