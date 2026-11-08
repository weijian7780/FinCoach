"""Bound synchronous research-checker waiting without blocking on worker exit."""
from contextvars import copy_context
from queue import Empty, Queue
from threading import BoundedSemaphore, Thread
from time import monotonic

# An SDK operation cannot be killed safely in Python. Bound orphaned operations;
# caller deadlines do not wait for close(), a response, or worker shutdown.
_slots = BoundedSemaphore(4)
# A stalled writer must not occupy the checker's separate worker capacity.
_writer_slots = BoundedSemaphore(4)
_privacy_slots = BoundedSemaphore(4)
_extraction_slots = BoundedSemaphore(8)


def within_deadline(call, timeout_seconds):
    return _within_deadline(call, timeout_seconds, _slots, 'checker')


def within_writer_deadline(call, timeout_seconds):
    """Bound a pure research writer call even if its SDK timeout is not a wall clock."""
    return _within_deadline(call, timeout_seconds, _writer_slots, 'writer')


def within_privacy_deadline(call, timeout_seconds):
    """A privacy rewrite cannot consume the remaining search allowance."""
    return _within_deadline(call, timeout_seconds, _privacy_slots, 'privacy')


def extract_with_deadline(items, call, timeout_seconds):
    """Run independent URL operations in bounded daemon workers.

    Only the caller merges results into request state. A worker still running
    after the deadline cannot mutate the caller's cache or enqueue more work.
    """
    items = list(items)
    deadline = monotonic() + max(0, timeout_seconds)
    results = {}
    pending = {}
    queue = Queue()
    for index, item in enumerate(items):
        started = monotonic()
        if started >= deadline or not _extraction_slots.acquire(blocking=False):
            results[index] = (False, None, 'deadline' if started >= deadline else 'worker_capacity', 0.0, False)
            continue
        pending[index] = started
        context = copy_context()
        def run(index=index, item=item, started=started, context=context):
            try:
                remaining = deadline - monotonic()
                if remaining <= 0:
                    raise TimeoutError('Extraction deadline reached')
                value = context.run(call, item, remaining)
                queue.put((index, True, value, None, monotonic()))
            except BaseException as exc:
                queue.put((index, False, None, type(exc).__name__, monotonic()))
            finally:
                _extraction_slots.release()
        worker = Thread(target=run, name='research-extraction', daemon=True)
        try:
            worker.start()
        except BaseException:
            pending.pop(index)
            _extraction_slots.release()
            results[index] = (False, None, 'worker_unavailable', 0.0, False)
    while pending:
        remaining = deadline - monotonic()
        if remaining <= 0:
            break
        try:
            index, ok, value, error, finished = queue.get(timeout=remaining)
        except Empty:
            break
        started = pending.pop(index, None)
        if started is None:
            continue
        if finished > deadline:
            results[index] = (False, None, 'deadline', max(0, deadline - started), True)
        else:
            results[index] = (ok, value, error, max(0, finished - started), True)
    for index, started in pending.items():
        results[index] = (False, None, 'deadline', max(0, deadline - started), True)
    return [results[index] for index in range(len(items))]


def _within_deadline(call, timeout_seconds, slots, kind):
    deadline = monotonic() + max(0, timeout_seconds)
    if timeout_seconds <= 0 or not slots.acquire(blocking=False):
        raise TimeoutError(f'Research {kind} deadline or worker capacity reached')
    result = Queue(maxsize=1)
    context = copy_context()

    def run():
        try:
            result.put((True, context.run(call)))
        except BaseException as exc:
            result.put((False, exc))
        finally:
            slots.release()

    worker = Thread(target=run, name=f'research-{kind}', daemon=True)
    try:
        worker.start()
    except BaseException:
        slots.release()
        raise
    try:
        ok, value = result.get(timeout=max(0, deadline - monotonic()))
    except Empty:
        raise TimeoutError(f'Research {kind} wall deadline reached') from None
    if monotonic() > deadline:
        raise TimeoutError(f'Research {kind} wall deadline reached')
    if not ok:
        raise value
    return value
