"""Exercise multiple history pages, including tied timestamps, through the repository."""
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import UUID

import pytest
from app.coaching_history import CoachingHistoryRepository


class HistoryQuery:
    def __init__(self, rows):
        self.rows = list(rows)
        self.orders = []
        self.maximum = 30

    def select(self, *_):
        return self

    def eq(self, key, value):
        self.rows = [row for row in self.rows if row[key] == value]
        return self

    def lt(self, key, value):
        self.rows = [row for row in self.rows if row[key] < value]
        return self

    def or_(self, expression):
        # Evaluate the real PostgREST boundary, not an application cursor helper.
        before_time = expression.split('created_at.lt.', 1)[1].split(',', 1)[0]
        before_id = expression.split('id.lt.', 1)[1].rstrip(')')
        self.rows = [row for row in self.rows if
                     (datetime.fromisoformat(row['created_at']), row['id']) <
                     (datetime.fromisoformat(before_time), before_id)]
        return self

    def order(self, key, desc=False):
        self.orders.append((key, desc))
        return self

    def limit(self, maximum):
        self.maximum = maximum
        return self

    def execute(self):
        for key, desc in reversed(self.orders):
            self.rows.sort(key=lambda row: row[key], reverse=desc)
        return SimpleNamespace(data=self.rows[:self.maximum])


def test_history_pagination_never_drops_messages_with_identical_timestamps():
    rows = [dict(id=str(UUID(int=i + 1)), user_id='owner', session_id='session',
                 created_at='2026-10-15T12:00:00+00:00', content=f'message {i}') for i in range(65)]
    rows += [{**rows[0], 'id': str(UUID(int=999)), 'user_id': 'other'}]
    client = MagicMock()
    client.table.side_effect = lambda _: HistoryQuery(rows)
    repository = CoachingHistoryRepository(client, MagicMock(), 'owner')
    repository.require_session = lambda _: {'id': 'session'}
    cursor = None
    received = []
    for _ in range(10):
        page = repository.list_message_page('session', limit=30, before=cursor)
        received.extend(page['messages'])
        cursor = page['next_before']
        if cursor is None:
            break
    assert len(received) == 65
    assert len({row['id'] for row in received}) == 65
    assert all(row['user_id'] == 'owner' for row in received)


@pytest.mark.parametrize('cursor', ['not-a-date', '2026-10-15|not-a-uuid', '2026-10-15T12:00:00|00000000-0000-0000-0000-000000000001'])
def test_history_rejects_invalid_or_timezone_free_cursors(cursor):
    repository = CoachingHistoryRepository(MagicMock(), MagicMock(), 'owner')
    repository.require_session = lambda _: {'id': 'session'}
    with pytest.raises(ValueError, match='cursor'):
        repository.list_message_page('session', before=cursor)
