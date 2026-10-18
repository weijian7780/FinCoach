"""Repeat terminal-attempt cleanup so late uploads do not remain orphaned."""
import asyncio
import logging
from starlette.concurrency import run_in_threadpool
from app.supabase_client import get_supabase

logger = logging.getLogger('uvicorn.error')


def cleanup_tick(client, cursor=None):
    response = client.rpc('list_abandoned_coach_report_artifacts', {
        'p_after_created': cursor[0] if cursor else None,
        'p_after_id': cursor[1] if cursor else None,
    }).execute()
    if getattr(response, 'error', None):
        raise RuntimeError('Report cleanup query failed')
    rows = response.data
    if not isinstance(rows, list):
        raise RuntimeError('Report cleanup query failed')
    if not rows:
        return None  # Wrap to the beginning on the next minute's scan.
    paths = []
    for row in rows:
        expected = f"{row['user_id']}/coach/{row['attempt_id']}.pdf"
        if row['storage_path'] != expected:
            raise RuntimeError('Invalid report cleanup path')
        paths.append(expected)
    client.storage.from_('financial-reports').remove(paths)
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
