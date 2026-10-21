"""Authenticated receipt extraction API routes."""
from __future__ import annotations

import logging
from io import BytesIO

from fastapi import APIRouter, File, Header, HTTPException, UploadFile, status
from PIL import Image, UnidentifiedImageError
from starlette.concurrency import run_in_threadpool

from app.auth import require_authenticated_user
from app.receipt_ocr import extract_receipt

router = APIRouter(prefix="/receipts", tags=["receipts"])

logger = logging.getLogger(__name__)

MAX_RECEIPT_BYTES = 5 * 1024 * 1024
# A phone photo can compress below 5 MB while still expanding to hundreds of
# megabytes. Reject it from header dimensions before OpenCV decodes all pixels.
# 60 MP covers modern high-res phone sensors (Honor 200's 50 MP camera outputs
# ~50.3 MP at full resolution); the OCR path immediately downscales to
# PADDLE_OCR_MAX_SIDE, so the full-size decode is transient. This still blocks
# pathological decompression bombs.
MAX_RECEIPT_PIXELS = 60_000_000
ALLOWED_RECEIPT_TYPES = {"image/jpeg", "image/png", "image/webp"}
EXPECTED_IMAGE_FORMATS = {
    "image/jpeg": "JPEG",
    "image/png": "PNG",
    "image/webp": "WEBP",
}


def verify_access_token(authorization: str | None) -> str:
    """Verify the mobile Supabase JWT and return its user ID."""
    return require_authenticated_user(authorization).user_id


def validate_receipt_image(image_bytes: bytes, content_type: str) -> None:
    """Reject spoofed or malformed images before they reach native OCR code."""
    try:
        with Image.open(BytesIO(image_bytes)) as image:
            if image.format != EXPECTED_IMAGE_FORMATS[content_type]:
                raise HTTPException(
                    status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                    detail="Image content does not match its declared type.",
                )
            width, height = image.size
            logger.info(
                "receipt image received: %dx%d px (%.1f MP), %d bytes",
                width, height, (width * height) / 1_000_000, len(image_bytes),
            )
            if width * height > MAX_RECEIPT_PIXELS:
                logger.warning(
                    "receipt rejected: %dx%d px (%.1f MP) exceeds %.1f MP cap",
                    width, height, (width * height) / 1_000_000,
                    MAX_RECEIPT_PIXELS / 1_000_000,
                )
                raise HTTPException(
                    status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                    detail="Receipt image dimensions are too large.",
                )
            image.verify()
    except HTTPException:
        raise
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Receipt image is invalid or unsupported.",
        ) from exc


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
        raise HTTPException(status_code=status.HTTP_413_CONTENT_TOO_LARGE, detail="Receipt image must be 5 MB or smaller.")
    if not image_bytes:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Receipt image is empty.")
    validate_receipt_image(image_bytes, file.content_type)
    try:
        return await run_in_threadpool(extract_receipt, image_bytes)
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="The receipt could not be read.") from exc
