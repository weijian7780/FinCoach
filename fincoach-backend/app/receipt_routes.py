"""Authenticated receipt extraction API routes."""
from __future__ import annotations

from fastapi import APIRouter, File, Header, HTTPException, UploadFile, status
from starlette.concurrency import run_in_threadpool

from app.auth import require_authenticated_user
from app.receipt_ocr import extract_receipt

router = APIRouter(prefix="/receipts", tags=["receipts"])

MAX_RECEIPT_BYTES = 5 * 1024 * 1024
ALLOWED_RECEIPT_TYPES = {"image/jpeg", "image/png", "image/webp"}


def verify_access_token(authorization: str | None) -> str:
    """Verify the mobile Supabase JWT and return its user ID."""
    return require_authenticated_user(authorization).user_id


@router.post("/extract")
async def extract_receipt_endpoint(
    file: UploadFile = File(...),
    authorization: str | None = Header(default=None),
) -> dict:
    verify_access_token(authorization)
    if file.content_type not in ALLOWED_RECEIPT_TYPES:
        raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail="Use a JPEG, PNG, or WebP image.")
    image_bytes = await file.read(MAX_RECEIPT_BYTES + 1)
    if len(image_bytes) > MAX_RECEIPT_BYTES:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Receipt image must be 5 MB or smaller.")
    if not image_bytes:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Receipt image is empty.")
    try:
        return await run_in_threadpool(extract_receipt, image_bytes)
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="The receipt could not be read.") from exc
