"""Verify a reserved report PDF before its history row may publish.

The device renders the PDF and uploads it to the immutable path the server
reserved for its attempt. Nothing about that upload is trusted: the backend
loads the attempt, derives the path itself, checks the stored object metadata,
downloads the exact bytes with a bounded timeout and only then lets the
database's completing transaction publish the history row. The database
rechecks the object identity and version under lock, so an object replaced or
rewritten between the download and the completion can never be published.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any, Callable
from urllib.parse import quote
from queue import Queue, Empty
from threading import BoundedSemaphore, Thread, Event

from app.config import (
    REPORT_ARTIFACT_BUCKET,
    REPORT_ARTIFACT_DOWNLOAD_TIMEOUT_SECONDS,
    REPORT_ARTIFACT_MAX_BYTES,
    SUPABASE_SERVICE_ROLE_KEY,
    SUPABASE_URL,
)

# A PDF header may appear anywhere in the first 1024 bytes (ISO 32000-1 7.5.2).
PDF_SIGNATURE_WINDOW_BYTES = 1024
PDF_SIGNATURE = b"%PDF-"
_DOWNLOAD_SLOTS = BoundedSemaphore(2)


class ReportArtifactInvalid(RuntimeError):
    """The reserved object could not be proven to be the rendered PDF."""


class ReportArtifactVerifier:
    """Fail-closed checks over one reserved storage object.

    `storage` is the backend Storage client (service role). The verifier never
    accepts a path from the caller: it derives the reserved path from the
    owner-scoped attempt row and refuses anything else.
    """

    def __init__(
        self,
        storage: Any,
        *,
        bucket: str = REPORT_ARTIFACT_BUCKET,
        max_bytes: int = REPORT_ARTIFACT_MAX_BYTES,
        download: Callable[[str], bytes] | None = None,
    ):
        self.storage = storage
        self.bucket = bucket
        self.max_bytes = max(1, int(max_bytes))
        self.download = download

    @staticmethod
    def _invalid() -> ReportArtifactInvalid:
        return ReportArtifactInvalid(
            "The uploaded report could not be verified."
        )

    def reserved_path(self, user_id: str, attempt: dict) -> str:
        """Derive the one path this attempt may ever publish."""
        attempt_id = attempt.get("attempt_id")
        path = attempt.get("storage_path")
        if not isinstance(attempt_id, str) or not attempt_id:
            raise self._invalid()
        expected = f"{user_id}/coach/{attempt_id}.pdf"
        if not isinstance(path, str) or path != expected:
            raise self._invalid()
        return expected

    def verify(self, *, user_id: str, attempt: dict) -> dict:
        """Return the storage identity payload for the completing transaction."""
        path = self.reserved_path(user_id, attempt)
        info = self._object_info(path)
        if str(info.get("name") or "") != path:
            raise self._invalid()
        size = info.get("size")
        if (
            isinstance(size, bool)
            or not isinstance(size, int)
            or size <= 0
            or size > self.max_bytes
        ):
            raise self._invalid()
        if str(info.get("content_type") or "").split(';', 1)[0].strip().lower() != "application/pdf":
            raise self._invalid()
        object_id = info.get("id")
        version = info.get("version")
        updated_at = info.get("last_modified")
        if not isinstance(object_id, str) or not object_id:
            raise self._invalid()
        if not isinstance(version, str) or not version:
            raise self._invalid()
        if not isinstance(updated_at, str) or not updated_at:
            raise self._invalid()

        content = self._download(path)
        if not content or len(content) > self.max_bytes:
            raise self._invalid()
        # The metadata may understate the object; the bytes must match it too.
        if len(content) != size:
            raise self._invalid()
        if PDF_SIGNATURE not in content[:PDF_SIGNATURE_WINDOW_BYTES]:
            raise self._invalid()
        return {
            "path": path,
            "object_id": object_id,
            "version": version,
            "updated_at": updated_at,
            "size": size,
        }

    def _object_info(self, path: str) -> dict:
        try:
            info = self.storage.from_(self.bucket).info(path)
        except Exception as error:
            raise self._invalid() from error
        if not isinstance(info, dict):
            raise self._invalid()
        return info

    def _download(self, path: str) -> bytes:
        try:
            content = self.download(path) if self.download else self.storage.from_(self.bucket).download(path)
        except Exception as error:
            raise self._invalid() from error
        if not isinstance(content, (bytes, bytearray)):
            raise self._invalid()
        return bytes(content)


@lru_cache(maxsize=1)
def get_report_artifact_storage() -> Any:
    """A service-role Storage client whose reads are bounded by the deadline."""
    from supabase import ClientOptions, create_client

    if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
        raise RuntimeError(
            "Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY in .env "
            "(use the SERVICE ROLE key, not the publishable key)."
        )
    options = ClientOptions(
        storage_client_timeout=REPORT_ARTIFACT_DOWNLOAD_TIMEOUT_SECONDS,
    )
    return create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, options).storage


def default_report_artifact_verifier() -> ReportArtifactVerifier:
    return ReportArtifactVerifier(get_report_artifact_storage(), download=download_report_bytes)


def download_report_bytes(path: str) -> bytes:
    """Bound the CALLER'S wall clock even before the first transport chunk.

    HTTPX read timeouts measure inactivity, not an absolute deadline. At most
    two daemon workers may finish a slow transport read after the caller times
    out; they never publish anything and release their slot on exit.
    """
    if not _DOWNLOAD_SLOTS.acquire(blocking=False):
        raise ReportArtifactInvalid('Report verification is busy. Please retry.')
    cancelled = Event()
    outcome: Queue = Queue(maxsize=1)
    timeout = REPORT_ARTIFACT_DOWNLOAD_TIMEOUT_SECONDS
    def read():
        try:
            result = _stream_report_bytes(path, cancelled, timeout)
        except Exception as error:
            result = error
        finally:
            _DOWNLOAD_SLOTS.release()
        outcome.put(result)
    Thread(target=read, daemon=True, name='report-artifact-read').start()
    try:
        result = outcome.get(timeout=timeout)
    except Empty as error:
        cancelled.set()
        raise ReportArtifactInvalid('The uploaded report could not be verified.') from error
    if isinstance(result, Exception):
        raise result
    return result


def _stream_report_bytes(path: str, cancelled: Event, timeout: float) -> bytes:
    """Bound memory while reading untrusted bytes, even if metadata lies.

    The normal SDK download buffers the whole response before returning. Stream
    this private object with service credentials instead, refusing oversized
    content as soon as it crosses the configured report limit.
    """
    import httpx
    from time import monotonic
    started = monotonic()
    url = f"{SUPABASE_URL.rstrip('/')}/storage/v1/object/authenticated/{REPORT_ARTIFACT_BUCKET}/{quote(path, safe='/')}"
    headers = {'Authorization': f'Bearer {SUPABASE_SERVICE_ROLE_KEY}', 'apikey': SUPABASE_SERVICE_ROLE_KEY}
    with httpx.stream('GET', url, headers=headers, timeout=timeout) as response:
        response.raise_for_status()
        content = bytearray()
        for chunk in response.iter_bytes():
            if (cancelled.is_set() or len(content) + len(chunk) > REPORT_ARTIFACT_MAX_BYTES
                    or monotonic() - started > timeout):
                raise ReportArtifactInvalid('The uploaded report could not be verified.')
            content.extend(chunk)
        return bytes(content)
