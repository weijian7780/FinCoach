"""PaddleOCR adapter and deterministic Malaysian receipt parser.

The OCR model is imported lazily so FastAPI can start and unit tests can run
without loading several hundred megabytes of model files.
"""
from __future__ import annotations

import os
import re
import tempfile
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from typing import Any

from app.receipt_cleanup import enhance_receipt_text


@dataclass(frozen=True)
class OCRLine:
    text: str
    confidence: float


_AMOUNT = re.compile(r"(?<!\d)(?:RM\s*)?(-?\d{1,6}[.,]\d{2})(?!\d)", re.IGNORECASE)
_DATE = re.compile(r"\b(\d{1,4})[/.\-](\d{1,2})[/.\-](\d{1,4})\b")
_TOTAL_WORDS = ("grand total", "amount due", "net total", "total")
_EXCLUDED_ITEM_WORDS = ("total", "subtotal", "tax", "sst", "cash", "change", "rounding", "visa", "mastercard")


def _money_values(text: str) -> list[float]:
    values: list[float] = []
    for match in _AMOUNT.finditer(text):
        try:
            values.append(float(match.group(1).replace(",", ".")))
        except ValueError:
            continue
    return values


def _parse_date(text: str) -> str:
    match = _DATE.search(text)
    if not match:
        return ""
    first, second, third = (int(value) for value in match.groups())
    year, month, day = (first, second, third) if first > 31 else (third, second, first)
    if year < 100:
        year += 2000
    try:
        return datetime(year, month, day).date().isoformat()
    except ValueError:
        return ""


def _merchant(lines: list[OCRLine]) -> tuple[str, float]:
    ignored = ("receipt", "tax invoice", "invoice", "welcome", "thank you")
    for line in lines[:8]:
        text = line.text.strip()
        lowered = text.lower()
        if len(text) >= 3 and not _money_values(text) and not _DATE.search(text) and not any(word in lowered for word in ignored):
            return text[:120], line.confidence
    return "", 0.0


def _category(lines: list[OCRLine]) -> tuple[str, float]:
    content = " ".join(line.text.lower() for line in lines)
    rules = {
        "Transport": ("grab", "petron", "shell", "caltex", "parking", "toll", "bus", "taxi"),
        "Education": ("book", "stationery", "tuition", "university", "college", "school"),
        "Entertainment": ("cinema", "movie", "netflix", "spotify", "game"),
        "Rent": ("rent", "rental", "landlord"),
        "Food": ("food", "restaurant", "cafe", "kopitiam", "makan", "mydin", "lotus", "aeon", "mart", "milo", "bread"),
    }
    for category, keywords in rules.items():
        if any(keyword in content for keyword in keywords):
            return category, 0.7
    return "", 0.0


def parse_receipt(lines: list[OCRLine]) -> dict[str, Any]:
    """Convert OCR lines into editable transaction draft fields."""
    cleaned = [OCRLine(line.text.strip(), round(float(line.confidence), 4)) for line in lines if line.text.strip()]
    merchant, merchant_confidence = _merchant(cleaned)

    transaction_date = ""
    date_confidence = 0.0
    for line in cleaned:
        transaction_date = _parse_date(line.text)
        if transaction_date:
            date_confidence = line.confidence
            break

    total: float | None = None
    total_confidence = 0.0
    for line in reversed(cleaned):
        lowered = line.text.lower()
        values = _money_values(line.text)
        if values and any(word in lowered for word in _TOTAL_WORDS):
            total = values[-1]
            total_confidence = line.confidence
            break
    if total is None:
        candidates = [(value, line.confidence) for line in cleaned for value in _money_values(line.text)]
        if candidates:
            total, total_confidence = max(candidates, key=lambda candidate: candidate[0])

    items: list[dict[str, Any]] = []
    for line in cleaned:
        lowered = line.text.lower()
        values = _money_values(line.text)
        if not values or any(word in lowered for word in _EXCLUDED_ITEM_WORDS):
            continue
        description = _AMOUNT.sub("", line.text).strip(" .:-\t")
        if description and not description.isdigit():
            items.append({
                "description": description[:160],
                "amount": round(values[-1], 2),
                "confidence": round(line.confidence, 4),
            })

    category, category_confidence = _category(cleaned)
    return {
        "merchant": merchant,
        "transactionDate": transaction_date,
        "totalAmount": f"{total:.2f}" if total is not None else "",
        "suggestedCategory": category,
        "items": items,
        "confidence": {
            "merchant": round(merchant_confidence, 4),
            "transactionDate": round(date_confidence, 4),
            "totalAmount": round(total_confidence, 4),
            "category": round(category_confidence, 4),
        },
        "rawLines": [line.text for line in cleaned],
    }


@lru_cache(maxsize=1)
def get_ocr_engine() -> Any:
    """Create one reusable English/Latin PaddleOCR v3 pipeline."""
    try:
        from paddleocr import PaddleOCR
    except ImportError as exc:
        raise RuntimeError("PaddleOCR is not installed. Install the backend OCR requirements first.") from exc
    return PaddleOCR(
        # Mobile detection is much smaller and faster on a student laptop CPU,
        # paired with the English mobile recognizer for Malaysian receipts.
        text_detection_model_name=os.environ.get("PADDLE_OCR_DETECTION_MODEL", "PP-OCRv5_mobile_det"),
        text_recognition_model_name=os.environ.get("PADDLE_OCR_RECOGNITION_MODEL", "en_PP-OCRv5_mobile_rec"),
        # PaddlePaddle 3.3.x on Windows CPU currently crashes in the oneDNN PIR
        # converter for OCR detection. Standard CPU kernels are slower but stable.
        enable_mkldnn=False,
        use_doc_orientation_classify=False,
        use_doc_unwarping=False,
        use_textline_orientation=False,
    )


def _result_payload(result: Any) -> dict[str, Any]:
    payload = getattr(result, "json", result)
    if callable(payload):
        payload = payload()
    if isinstance(payload, dict) and isinstance(payload.get("res"), dict):
        return payload["res"]
    return payload if isinstance(payload, dict) else {}


def run_paddle_ocr(image_bytes: bytes, engine: Any | None = None) -> list[OCRLine]:
    """Run PaddleOCR v3 against bytes and normalize its result shape."""
    if not image_bytes:
        raise ValueError("Receipt image is empty.")
    suffix = ".jpg"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as temporary:
        temporary.write(image_bytes)
        temporary_path = temporary.name
    try:
        results = (engine or get_ocr_engine()).predict(temporary_path)
        lines: list[OCRLine] = []
        for result in results:
            payload = _result_payload(result)
            texts = payload.get("rec_texts", [])
            scores = payload.get("rec_scores", [])
            for index, text in enumerate(texts):
                score = float(scores[index]) if index < len(scores) else 0.0
                if str(text).strip():
                    lines.append(OCRLine(str(text), score))
        return lines
    finally:
        try:
            os.unlink(temporary_path)
        except OSError:
            pass


def _add_review_status(result: dict[str, Any]) -> dict[str, Any]:
    """Flag fields that need a retake or explicit manual correction."""
    warnings: list[str] = []
    critical_fields = (
        ("merchant", "Merchant"),
        ("transactionDate", "Receipt date"),
        ("totalAmount", "Total amount"),
    )
    confidence_keys = {
        "merchant": "merchant",
        "transactionDate": "transactionDate",
        "totalAmount": "totalAmount",
    }
    for field, label in critical_fields:
        if not result.get(field):
            warnings.append(f"{label} was not detected.")
            continue
        confidence = float(result.get("confidence", {}).get(confidence_keys[field], 0))
        if confidence < 0.75:
            warnings.append(f"{label} may be inaccurate.")
    result["reviewRequired"] = bool(warnings)
    result["reviewWarnings"] = warnings
    return result


def extract_receipt(image_bytes: bytes, engine: Any | None = None) -> dict[str, Any]:
    lines = run_paddle_ocr(image_bytes, engine)
    result = parse_receipt(lines)
    critical_fields = ("merchant", "transactionDate", "totalAmount")
    confidence = result["confidence"]
    if all(result[field] and confidence[field] >= 0.9 for field in critical_fields):
        result["enhancementStatus"] = "not_needed"
        return _add_review_status(result)

    raw_text = "\n".join(line.text for line in lines)
    try:
        enhanced = enhance_receipt_text(raw_text)
    except Exception:
        result["enhancementStatus"] = "failed"
        return _add_review_status(result)
    if not enhanced:
        result["enhancementStatus"] = "not_configured"
        return _add_review_status(result)

    merchant = str(enhanced.get("merchant") or "").strip()
    transaction_date = str(enhanced.get("transactionDate") or "").strip()
    suggested_category = str(enhanced.get("suggestedCategory") or "").strip()
    total_amount = enhanced.get("totalAmount")
    if merchant:
        result["merchant"] = merchant[:120]
    if transaction_date:
        result["transactionDate"] = transaction_date
    if suggested_category:
        result["suggestedCategory"] = suggested_category
    if isinstance(total_amount, (int, float)) and total_amount > 0:
        result["totalAmount"] = f"{total_amount:.2f}"
    if isinstance(enhanced.get("items"), list):
        result["items"] = enhanced["items"][:20]
    result["enhancementStatus"] = "applied"
    return _add_review_status(result)
