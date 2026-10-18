"""Cleanup is bounded and repeatable; only server-proven terminal paths delete."""
from types import SimpleNamespace
from unittest.mock import MagicMock
import pytest
from app.report_cleanup import cleanup_tick


def test_cleanup_preserves_cursor_and_deletes_only_the_rpc_candidates():
    client = MagicMock()
    client.rpc.return_value.execute.return_value = SimpleNamespace(data=[dict(
        user_id='owner', attempt_id='a1', storage_path='owner/coach/a1.pdf', created_at='2030-01-01T00:00:00Z')])
    assert cleanup_tick(client) == ('2030-01-01T00:00:00Z', 'a1')
    client.storage.from_.return_value.remove.assert_called_once_with(['owner/coach/a1.pdf'])


def test_cleanup_wraps_and_rejects_uncertain_or_nonreserved_paths():
    client = MagicMock()
    client.rpc.return_value.execute.return_value = SimpleNamespace(data=[])
    assert cleanup_tick(client, ('2030-01-01T00:00:00Z', 'a1')) is None
    client.storage.from_.return_value.remove.assert_not_called()
    client.rpc.return_value.execute.return_value = SimpleNamespace(data=[dict(
        user_id='owner', attempt_id='a1', storage_path='owner/manual.pdf', created_at='2030-01-01T00:00:00Z')])
    with pytest.raises(RuntimeError): cleanup_tick(client)
    client.storage.from_.return_value.remove.assert_not_called()
