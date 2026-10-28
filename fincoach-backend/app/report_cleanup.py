"""Repeat terminal-attempt cleanup so late uploads do not remain orphaned."""
import asyncio
import logging
from datetime import datetime, timedelta, timezone
from uuid import UUID
from starlette.concurrency import run_in_threadpool
from app.supabase_client import get_supabase

logger = logging.getLogger('uvicorn.error')


def _rows(response):
    if getattr(response, 'error', None) or not isinstance(response.data, list):
        raise RuntimeError('Report cleanup query failed')
    return response.data


def _reserved_path(row):
    # Do not broaden this worker into an arbitrary Storage orphan scanner.
    owner, attempt = str(UUID(row['user_id'])), str(UUID(row['attempt_id']))
    expected = f'{owner}/coach/{attempt}.pdf'
    if row['storage_path'] != expected:
        raise RuntimeError('Invalid report cleanup path')
    return expected


def cleanup_tick(client, cursor=None, *, now=None):
    instant = now or datetime.now(timezone.utc)
    cutoff = (instant - timedelta(hours=24)).isoformat()
    expired = _rows(client.table('report_attempts')
                    .select('user_id,attempt_id,storage_path,status,lease_owner,lease_expires_at,updated_at')
                    .eq('status', 'active').lte('lease_expires_at', cutoff)
                    .order('lease_expires_at').order('attempt_id').limit(100).execute())
    for row in expired[:100]:
        _reserved_path(row)
        # One conditional UPDATE closes the race with renewal/completion. An
        # empty representation means another operation won; leave it alone.
        query = (client.table('report_attempts')
                 .update({'status': 'cancelled', 'updated_at': instant.isoformat()})
                 .eq('user_id', row['user_id']).eq('attempt_id', row['attempt_id'])
                 .eq('status', 'active').eq('lease_expires_at', row['lease_expires_at'])
                 .eq('updated_at', row['updated_at']))
        query = (query.is_('lease_owner', 'null') if row['lease_owner'] is None
                 else query.eq('lease_owner', row['lease_owner']))
        _rows(query.execute())
    response = client.rpc('list_abandoned_coach_report_artifacts', {
        'p_after_created': cursor[0] if cursor else None,
        'p_after_id': cursor[1] if cursor else None,
    }).execute()
    rows = _rows(response)
    if not rows:
        return None  # Wrap to the beginning on the next minute's scan.
    for row in rows:
        expected = _reserved_path(row)
        # The existing RPC authorizes terminal attempts. Recheck references as
        # late as possible; DB and Storage still cannot share a transaction.
        references = _rows(client.table('reports').select('id')
                           .eq('storage_path', expected).limit(1).execute())
        if references:
            continue
        removed = client.storage.from_('financial-reports').remove([expected])
        if getattr(removed, 'error', None) or (isinstance(removed, dict) and removed.get('error')):
            raise RuntimeError('Report cleanup removal failed')
    last = rows[-1]
    return last['created_at'], last['attempt_id']


async def run_report_cleanup(stop: asyncio.Event) -> None:
    cursor = None
    while not stop.is_set():
        try:
            cursor = await run_in_threadpool(cleanup_tick, get_supabase(), cursor)
        except Exception:
            # Keep the cursor unchanged so a failed deletion is retried.
            logger.warning('fincoach_report_cleanup_unavailable')
        try:
            await asyncio.wait_for(stop.wait(), timeout=60)
        except asyncio.TimeoutError:
            pass
