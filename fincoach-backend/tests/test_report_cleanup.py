"""Cleanup respects lease races, bounded work, and existing report references."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock
import pytest
from app.report_cleanup import cleanup_tick

OWNER = '11111111-1111-4111-8111-111111111111'
ATTEMPT = '22222222-2222-4222-8222-222222222222'
NOW = datetime(2026, 10, 21, tzinfo=timezone.utc)


def attempt():
    return dict(user_id=OWNER, attempt_id=ATTEMPT,
                storage_path=f'{OWNER}/coach/{ATTEMPT}.pdf', status='active',
                lease_owner=OWNER, lease_expires_at=(NOW-timedelta(days=2)).isoformat(),
                updated_at=(NOW-timedelta(days=2)).isoformat(),
                created_at='2026-10-01T00:00:00+00:00')


class Query:
    def __init__(self, fixture, table):
        self.fixture, self.table = fixture, table
        self.filters, self.patch, self.maximum = [], None, None

    def select(self, *_): return self
    def order(self, *_): return self
    def eq(self, key, value): self.filters.append(lambda row: row.get(key) == value); return self
    def lte(self, key, value): self.filters.append(lambda row: row[key] <= value); return self
    def is_(self, key, _): self.filters.append(lambda row: row.get(key) is None); return self
    def limit(self, value): self.maximum = value; return self
    def update(self, patch): self.patch = patch; return self

    def execute(self):
        if self.patch and self.fixture.race:
            self.fixture.race(self.fixture.rows[0]); self.fixture.race = None
        rows = self.fixture.rows if self.table == 'report_attempts' else self.fixture.reports
        matches = [row for row in rows if all(check(row) for check in self.filters)]
        if self.maximum is not None: matches = matches[:self.maximum]
        if self.patch:
            self.fixture.updated += len(matches)
            for row in matches: row.update(self.patch)
        return SimpleNamespace(data=deepcopy(matches), error=None)


class Fixture:
    def __init__(self, rows=None, reports=None, race=None):
        self.rows, self.reports, self.race = rows or [], reports or [], race
        self.updated = 0
        self.storage = MagicMock()
        self.storage.from_.return_value.remove.return_value = []

    def table(self, name): return Query(self, name)

    def rpc(self, name, args):
        assert name == 'list_abandoned_coach_report_artifacts'
        rows = [row for row in self.rows if row['status'] in ('cancelled', 'superseded')]
        return SimpleNamespace(execute=lambda: SimpleNamespace(data=deepcopy(rows), error=None))


def test_expired_attempt_is_cancelled_and_its_unreferenced_pdf_is_removed():
    client = Fixture([attempt()])
    assert cleanup_tick(client, now=NOW) == ('2026-10-01T00:00:00+00:00', ATTEMPT)
    assert client.rows[0]['status'] == 'cancelled'
    client.storage.from_.return_value.remove.assert_called_once_with([attempt()['storage_path']])


@pytest.mark.parametrize('change', [
    {'lease_expires_at': (NOW+timedelta(minutes=5)).isoformat()},
    {'status': 'completed'},
    {'updated_at': NOW.isoformat()},
    {'lease_owner': '33333333-3333-4333-8333-333333333333'},
])
def test_cancellation_skips_a_concurrent_renewal_completion_or_owner_change(change):
    client = Fixture([attempt()], race=lambda row: row.update(change))
    cleanup_tick(client, now=NOW)
    assert client.updated == 0
    client.storage.from_.return_value.remove.assert_not_called()


def test_recent_expiry_waits_24_hours_and_tick_is_bounded_to_100():
    recent = attempt(); recent['lease_expires_at'] = (NOW-timedelta(hours=23)).isoformat()
    client = Fixture([recent]); cleanup_tick(client, now=NOW)
    assert client.updated == 0
    client = Fixture([attempt() for _ in range(101)])
    for i, row in enumerate(client.rows):
        row['attempt_id'] = f'{i:08x}-2222-4222-8222-222222222222'
        row['storage_path'] = f"{OWNER}/coach/{row['attempt_id']}.pdf"
    cleanup_tick(client, now=NOW)
    assert client.updated == 100


def test_report_reference_added_after_authorization_prevents_removal():
    row = attempt(); row['status'] = 'cancelled'
    client = Fixture([row], reports=[{'id': 8, 'storage_path': row['storage_path']}])
    cleanup_tick(client, now=NOW)
    client.storage.from_.return_value.remove.assert_not_called()


def test_uncertain_reads_and_failed_removals_are_retryable():
    row = attempt(); row['status'] = 'cancelled'
    client = Fixture([row]); client.storage.from_.return_value.remove.side_effect = RuntimeError('unavailable')
    with pytest.raises(RuntimeError): cleanup_tick(client, now=NOW)
    client.storage.from_.return_value.remove.side_effect = None
    cleanup_tick(client, now=NOW)
    assert client.storage.from_.return_value.remove.call_count == 2
    client.table = MagicMock(return_value=MagicMock())
    with pytest.raises(RuntimeError): cleanup_tick(client, now=NOW)


def test_wrap_and_invalid_reserved_path():
    client = Fixture(); assert cleanup_tick(client, ('old', ATTEMPT), now=NOW) is None
    row = attempt(); row.update(status='cancelled', storage_path=f'{OWNER}/manual.pdf')
    client = Fixture([row])
    with pytest.raises(RuntimeError): cleanup_tick(client, now=NOW)
    client.storage.from_.return_value.remove.assert_not_called()
