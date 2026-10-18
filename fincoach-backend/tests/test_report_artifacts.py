"""Exercise the real byte verifier; service mocks cannot prove file integrity."""
from unittest.mock import MagicMock, patch
import pytest
from app.report_artifacts import ReportArtifactInvalid, ReportArtifactVerifier


def fixture():
    data = b'%PDF-1.7\nsynthetic test bytes\n%%EOF'
    storage = MagicMock()
    info = dict(id='object-1', name='owner/coach/attempt.pdf', version='v1',
                size=len(data), content_type='application/pdf', last_modified='2030-01-01T00:00:00Z')
    storage.from_.return_value.info.return_value = info
    storage.from_.return_value.download.return_value = data
    attempt = dict(attempt_id='attempt', storage_path=info['name'])
    return storage, info, attempt


def test_verifies_downloaded_bytes_and_returns_identity_for_atomic_recheck():
    storage, info, attempt = fixture()
    result = ReportArtifactVerifier(storage).verify(user_id='owner', attempt=attempt)
    assert result['object_id'] == info['id'] and result['version'] == 'v1'
    assert result['size'] == info['size']
    storage.from_.return_value.download.assert_called_once_with(info['name'])


@pytest.mark.parametrize('mutation', ['missing', 'empty', 'not_pdf', 'wrong_path', 'wrong_type', 'wrong_size', 'version'])
def test_invalid_or_unreadable_objects_cannot_publish(mutation):
    storage, info, attempt = fixture()
    if mutation == 'missing': storage.from_.return_value.info.side_effect = RuntimeError('404')
    elif mutation == 'empty': storage.from_.return_value.download.return_value = b''
    elif mutation == 'not_pdf': storage.from_.return_value.download.return_value = b'x' * info['size']
    elif mutation == 'wrong_path': attempt['storage_path'] = 'foreign/coach/attempt.pdf'
    elif mutation == 'wrong_type': info['content_type'] = 'application/pdf-invalid'
    elif mutation == 'wrong_size': info['size'] += 1
    elif mutation == 'version': info['version'] = ''
    with pytest.raises(ReportArtifactInvalid):
        ReportArtifactVerifier(storage).verify(user_id='owner', attempt=attempt)


def test_streaming_download_stops_at_the_size_limit():
    from app import report_artifacts as module
    response = MagicMock()
    response.iter_bytes.return_value = iter([b'%PDF-', b'12345', b'never read'])
    stream = MagicMock()
    stream.__enter__.return_value = response
    with patch('httpx.stream', return_value=stream), patch.object(module, 'REPORT_ARTIFACT_MAX_BYTES', 8):
        with pytest.raises(ReportArtifactInvalid):
            module.download_report_bytes('owner/coach/attempt.pdf')
    stream.__exit__.assert_called_once()


def test_slow_first_chunk_cannot_hold_completion_past_the_deadline():
    from app import report_artifacts as module
    from threading import Event
    from time import monotonic
    release = Event()
    response = MagicMock()
    def slow_bytes(**kwargs):
        release.wait(1)
        yield b'%PDF-'
    response.iter_bytes.side_effect = slow_bytes
    stream = MagicMock()
    stream.__enter__.return_value = response
    try:
        started = monotonic()
        with patch('httpx.stream', return_value=stream), patch.object(module, 'REPORT_ARTIFACT_DOWNLOAD_TIMEOUT_SECONDS', 0.02):
            with pytest.raises(ReportArtifactInvalid):
                module.download_report_bytes('owner/coach/attempt.pdf')
        # The completion caller returned before any bytes were released.
        assert not release.is_set()
        assert monotonic() - started < 0.25
    finally:
        release.set()
