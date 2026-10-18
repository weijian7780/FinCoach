"""PaddleOCR adapter and deterministic Malaysian receipt parser.

The OCR model is imported lazily so FastAPI can start and unit tests can run
without loading several hundred megabytes of model files.
"""
from __future__ import annotations

import json
import logging
import os
import re
import threading
from statistics import median
from dataclasses import dataclass
from datetime import date, datetime
from functools import lru_cache
from time import perf_counter
from typing import Any
from zoneinfo import ZoneInfo

from app.receipt_category import classify_category

LOGGER = logging.getLogger("uvicorn.error")
_OCR_INFERENCE_LOCK = threading.Lock()


@dataclass(frozen=True)
class OCRLine:
    text: str
    confidence: float | None
    boxes: tuple[tuple[int, int, int, int], ...] = ()


class OCRLines(list[OCRLine]):
    """Rows plus the upright image used by Paddle, without another OCR pass."""

    verification_image: bytes | None = None
    orientation: int | None = None


_AMOUNT = re.compile(r"(?<!\d)(?:RM\s*)?([+-]?\s*\d{1,6}[.,]\d{2})(?!\d)", re.IGNORECASE)
# One separator throughout prevents an adjacent order code, e.g. 33-03/10/2026,
# from being consumed as the bogus date 33-03/10. Calendar checks follow below.
_DATE = re.compile(r"(?<!\d)(\d{4}|\d{1,2})([/.\-])(\d{1,2})\2(\d{4}|\d{1,2})(?!\d)")
# Named dates occur in both orders. Match their shape separately from calendar
# validation so an invalid date can never turn its year/time into a money value.
_MONTH = (r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
          r"Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)")
_DAY_FIRST_DATE = re.compile(r"\b(\d{1,2})[\s/-]+(" + _MONTH + r")[\s,/-]+(\d{2,4})(?!\d)", re.I)
_MONTH_FIRST_DATE = re.compile(r"\b(" + _MONTH + r")[\s/-]+(\d{1,2})[\s,/-]+(\d{2,4})(?!\d)", re.I)
_TIME = re.compile(r"\b\d{1,2}:\d{2}(?::\d{2})?(?:\s*[AP]M)?\b", re.I)
# Grand/payable total words (English + Malay). Used to read the total value.
_TOTAL_WORDS = (
    "grand total", "nett total", "net total", "total amount", "amount due",
    "amount payable", "balance due", "total due", "total payable", "total",
    "jumlah besar", "jumlah keseluruhan", "jumlah perlu dibayar", "jumlah bayar",
    "jumlah bersih", "jumlah", "amaun",
)
# The totals-block boundary: the first line matching one of these ends the
# itemised section — everything from there down is summary/payment, never an item.
# Includes subtotal terms so items stop before the subtotal (English + Malay).
_TOTALS_BOUNDARY = ("subtotal", "sub total", "sub-total", "jumlah kecil") + _TOTAL_WORDS
# Payment/tender/summary tokens that are never products (English + Malay + common
# e-wallets). Drops tender lines that print inside the item area (e.g. a card line
# above the subtotal). Word-boundary matched, so they don't hit inside real names.
_NON_ITEM_WORDS = (
    "subtotal", "total", "jumlah", "amaun", "tax", "gst", "sst", "cukai",
    "service charge", "svc charge", "caj perkhidmatan", "rounding", "pembundaran",
    "cash", "tunai", "change", "baki", "card", "kad", "credit", "debit",
    "visa", "mastercard", "amex", "tender", "bayaran", "balance", "points",
    "reward", "ganjaran", "member", "ahli", "tng", "touch n go", "touchngo",
    "grabpay", "boost", "shopeepay", "duitnow", "ewallet", "e-wallet", "wallet",
)


def _wordset(words: tuple[str, ...]) -> "re.Pattern[str]":
    """Compile a case-insensitive whole-word/phrase matcher for a token set."""
    return re.compile(r"\b(?:" + "|".join(re.escape(word) for word in words) + r")\b", re.I)


_TOTAL_RE = _wordset(_TOTAL_WORDS)
_BOUNDARY_RE = _wordset(_TOTALS_BOUNDARY)
_NON_ITEM_RE = _wordset(_NON_ITEM_WORDS)


def _table_header(text: str) -> bool:
    return not _money_values(_DATE.sub("", text)) and bool(
        # TOTAL QTY is a summary. QTY TOTAL is a valid split column heading.
        (re.search(r"\b(item|product|description|unit price)\b", text, re.I)
         or re.search(r"\b(qty|quantity)\b.*\b(total|amount|price)\b", text, re.I))
        and re.search(r"\b(total|amount|price)\b", text, re.I)
    )


def _summary_boundary(text: str) -> bool:
    return (bool(_BOUNDARY_RE.search(text)) and not _table_header(text)) or bool(
        re.fullmatch(r"\s*amount\s*:?\s*(?:RM\s*)?[+-]?\s*\d+[.,]\d{2}\s*", text, re.I))


def _qr_payment_row(text: str) -> bool:
    # QR is a payment label here; it can also occur in a genuine product name
    # such as "QR Sticker", which must remain eligible as a purchased item.
    return bool(re.fullmatch(r"\s*qr\s*:?\s*(?:(?:RM\s*)?\d+[.,]\d{2})?\s*", text, re.I))


def _address_line(text: str) -> bool:
    """Address structure outranks a business word embedded in an address."""
    return bool(re.search(r"(?<![#\d])\b\d{5}\s+[A-Za-z]", text) or re.match(
        r"^(?:\d+(?:st|nd|rd|th|at)?\s+floor\b|(?:level|block|lot|unit|no[. :]*)\s*\d|"
        r"jalan\b|lorong\b|street\b|tel(?:ephone)?\b|phone\b)", text, re.I))


def _payable_line(text: str) -> bool:
    """Tax-inclusive payable totals are valid; tax-only and tender rows are not."""
    if not _TOTAL_RE.search(text) or re.search(r"\b(sub[ -]?total|jumlah kecil|cash|tunai|change|baki|tender|quantity|qty|excluding|exclusive|before tax)\b", text, re.I):
        return False
    if re.search(r"\b(tax|gst|sst)\b", text, re.I):
        return bool(re.search(r"\b(inclusive|including|included|incl)\b", text, re.I))
    return True


def _merchant_text(text: str) -> str:
    # Registration numbers identify a legal entity, but are not its display name.
    return re.sub(r"\s*\([\d][\d\sA-Za-z/-]*\)\s*$", "", text.strip())[:120]


def _positive_int_env(name: str, default: int) -> int:
    try:
        value = int(os.environ.get(name, str(default)))
    except ValueError:
        return default
    return value if value > 0 else default


def _float_env(name: str, default: float) -> float:
    try:
        value = float(os.environ.get(name, str(default)))
    except ValueError:
        return default
    return value if 0 <= value <= 1 else default


def _prepare_ocr_image(
    image_bytes: bytes,
    *,
    max_side: int | None = None,
) -> tuple[Any, tuple[int, int]]:
    """Decode an image once and shrink oversized phone photos before OCR."""
    import cv2
    import numpy as np

    from io import BytesIO
    from PIL import Image

    # OpenCV otherwise applies EXIF implicitly. Decode raw pixels and explicitly
    # normalize all EXIF transforms once, retaining encoded dimensions for logs.
    with Image.open(BytesIO(image_bytes)) as header:
        orientation = header.getexif().get(274, 1)
    image = cv2.imdecode(np.frombuffer(image_bytes, dtype=np.uint8),
                         cv2.IMREAD_COLOR | cv2.IMREAD_IGNORE_ORIENTATION)
    if image is None or image.ndim != 3:
        raise ValueError("Receipt image is invalid or unsupported.")

    height, width = image.shape[:2]
    original_size = (width, height)
    if orientation in (2, 4):
        image = cv2.flip(image, 1 if orientation == 2 else 0)
    elif orientation in (3, 6, 8):
        image = cv2.rotate(image, {3: cv2.ROTATE_180, 6: cv2.ROTATE_90_CLOCKWISE,
                                  8: cv2.ROTATE_90_COUNTERCLOCKWISE}[orientation])
    elif orientation in (5, 7):
        image = cv2.transpose(image)
        if orientation == 7:
            image = cv2.flip(image, -1)
    height, width = image.shape[:2]
    limit = max_side or _positive_int_env("PADDLE_OCR_MAX_SIDE", 1600)
    longest_side = max(width, height)
    if longest_side <= limit:
        return image, original_size

    scale = limit / longest_side
    resized_width = max(1, round(width * scale))
    resized_height = max(1, round(height * scale))
    resized = cv2.resize(
        image,
        (resized_width, resized_height),
        interpolation=cv2.INTER_AREA,
    )
    return resized, original_size


def _money_values(text: str) -> list[float]:
    values: list[float] = []
    temporal_spans = [match.span() for pattern in (_DATE, _DAY_FIRST_DATE, _MONTH_FIRST_DATE, _TIME)
                      for match in pattern.finditer(text)]
    for match in _AMOUNT.finditer(text):
        # A comma between year and time is punctuation, not a decimal separator.
        if any(match.start() < end and match.end() > start for start, end in temporal_spans):
            continue
        try:
            values.append(float(re.sub(r"\s+", "", match.group(1)).replace(",", ".")))
        except ValueError:
            continue
    return values


def _parse_date(text: str) -> str:
    candidates: list[tuple[bool, bool, int, str]] = []
    for match in _DATE.finditer(text):
        first, _separator, second, third = match.groups()
        year, month, day = ((int(first), int(second), int(third)) if len(first) == 4
                            else (int(third), int(second), int(first)))
        if year < 100:
            year += 2000
        try:
            value = datetime(year, month, day).date().isoformat()
        except ValueError:
            continue
        labelled = bool(re.search(r"\b(date|tarikh)(?:\s*&\s*time)?\s*[:\-]?\s*$",
                                  text[:match.start()], re.I))
        candidates.append((labelled, len(first) == 4 or len(third) == 4,
                           -match.start(), value))
    for pattern in (_DAY_FIRST_DATE, _MONTH_FIRST_DATE):
        for match in pattern.finditer(text):
            first, second, year = match.groups()
            day, month = (first, second) if pattern is _DAY_FIRST_DATE else (second, first)
            for fmt in ("%d %b %Y", "%d %B %Y", "%d %b %y", "%d %B %y"):
                try:
                    value = datetime.strptime(f"{day} {month} {year}", fmt).date().isoformat()
                    labelled = bool(re.search(r"\b(date|tarikh)\s*[:\-]?\s*$", text[:match.start()], re.I))
                    candidates.append((labelled, len(year) == 4, -match.start(), value))
                    break
                except ValueError:
                    pass
    return max(candidates)[3] if candidates else ""


def _merchant(lines: list[OCRLine]) -> tuple[str, float]:
    ignored = ("receipt", "tax invoice", "invoice", "welcome", "thank you", "cashier",
               "customer", "address", "tel:", "date:", "your order", "order number")
    header: list[OCRLine] = []
    for line in lines[:40]:
        if _table_header(line.text) or re.search(r"\b(tax invoice|invoice\s*[#:]|orderkey)\b", line.text, re.I) or _money_values(line.text) or _parse_date(line.text):
            break
        header.append(line)
    aliases = [match.group(1).strip() for line in header
               if (match := re.match(r"(?:licensee of|trading as|t/a|franchise of)\s+(.+)", line.text, re.I))]
    candidates = []
    for index, line in enumerate(header):
        text = line.text.strip()
        lowered = text.lower()
        if (3 <= len(text) <= 120 and not any(word in lowered for word in ignored)
                and not _address_line(text)
                and not re.match(r"^(?:number|bill number|order time)\b", lowered)
                and not re.match(r"^(?:\(|\d+$|level\b|no[. :]\s*\d|jalan\b|street\b|tel(?:ephone)?\b|phone\b|licensee of\b|trading as\b|t/a\b|franchise of\b)", lowered)
                and lowered not in ("paid", "ait", "cash", "original", "copy")):
            business = bool(re.search(r"\b(sdn|bhd|trading|mart|restaurant|restoran|kedai|cafe|gift|store|shop|delights|international|ayam|kopitiam)\b", lowered))
            trade_name = any(alias.casefold() in lowered for alias in aliases)
            candidates.append((3 if trade_name else 2 if business else 1,
                               -index, _merchant_text(text), line.confidence))
    selected = max(candidates, key=lambda candidate: candidate[:2]) if candidates else None
    return (selected[2], selected[3]) if selected else ("", 0.0)


def _category(lines: list[OCRLine]) -> tuple[str, float]:
    content = " ".join(line.text.lower() for line in lines)
    rules = {
        "Transport": ("grab", "petron", "petronas", "shell", "caltex", "parking", "toll", "bus", "taxi"),
        "Education": ("book", "books", "notebook", "textbook", "bookstore", "stationery", "tuition", "university", "college", "school"),
        "Entertainment": ("cinema", "movie", "netflix", "spotify", "game"),
        "Rent": ("rent", "rental", "landlord"),
        "Food": ("food", "restaurant", "restaurants", "cafe", "kopitiam", "makan", "mydin", "lotus", "aeon", "mart", "speedmart", "milo", "bread", "nasi", "roti", "ayam", "coffee", "burger", "rice", "meat", "vege", "vegetable", "chicken", "noodles"),
    }
    for category, keywords in rules.items():
        if _wordset(keywords).search(content):
            return category, 0.7
    return "", 0.0


def _bbox(raw_box: Any) -> tuple[int, int, int, int] | None:
    """Normalise a rec_box [x1,y1,x2,y2] or a 4-point rec_poly to (x1,y1,x2,y2)."""
    try:
        values = list(raw_box)
    except TypeError:
        return None
    if not values:
        return None
    first = values[0]
    if hasattr(first, "__len__") or (
        hasattr(first, "__iter__") and not isinstance(first, (int, float))
    ):
        xs: list[float] = []
        ys: list[float] = []
        for point in values:
            try:
                xs.append(float(point[0]))
                ys.append(float(point[1]))
            except (TypeError, IndexError, ValueError):
                return None
        return int(min(xs)), int(min(ys)), int(max(xs)), int(max(ys))
    try:
        x1, y1, x2, y2 = (float(value) for value in values[:4])
    except (TypeError, ValueError):
        return None
    return int(min(x1, x2)), int(min(y1, y2)), int(max(x1, x2)), int(max(y1, y2))


def _reconstruct_rows(
    raw: list[tuple[str, float, tuple[int, int, int, int] | None]],
    *, row_slope: float = 0.0,
) -> list[OCRLine]:
    """Merge PaddleOCR text boxes back into logical rows.

    PaddleOCR returns each detected text box separately, so a two-column receipt
    line ("Vt Pep Mocha" | "4.95") arrives as two boxes. We group boxes whose
    vertical centres are close, order each group left->right, and join the text so
    the parser sees "Vt Pep Mocha 4.95" on one line. Falls back to one line per box
    (original order) when boxes are unavailable (e.g. unit-test fixtures).
    """
    if not raw:
        return []
    if any(box is None for _text, _score, box in raw):
        return [OCRLine(text, score) for text, score, _box in raw]

    heights = sorted(box[3] - box[1] for _t, _s, box in raw if box[3] > box[1])
    median_height = heights[len(heights) // 2] if heights else 0
    # Adjacent receipt lines can be closer than a tall detector box. A tighter
    # centre tolerance avoids merging the date row with the column heading.
    tolerance = max(3.0, 0.35 * median_height)

    def projected_centre(box):
        # Compare columns in the receipt coordinate frame without modifying the
        # image or boxes used by Gemini. A skewed baseline is y = slope*x + b.
        return (box[1] + box[3]) / 2 - row_slope * (box[0] + box[2]) / 2

    ordered = sorted(raw, key=lambda item: (projected_centre(item[2]), item[2][0]))
    rows: list[list[tuple[str, float, tuple[int, int, int, int]]]] = []
    centres: list[float] = []
    for text, score, box in ordered:
        centre = projected_centre(box)
        placed = False
        for index, row_centre in enumerate(centres):
            if abs(centre - row_centre) <= tolerance:
                rows[index].append((text, score, box))
                count = len(rows[index])
                centres[index] = (row_centre * (count - 1) + centre) / count
                placed = True
                break
        if not placed:
            rows.append([(text, score, box)])
            centres.append(centre)

    merged: list[tuple[int, OCRLine]] = []
    for row in rows:
        row.sort(key=lambda item: item[2][0])
        text = " ".join(part[0].strip() for part in row if part[0].strip())
        if not text:
            continue
        confidence = round(float(min(part[1] for part in row)), 4)
        top = min(projected_centre(part[2]) for part in row)
        merged.append((top, OCRLine(text, confidence, tuple(part[2] for part in row))))
    merged.sort(key=lambda item: item[0])
    return [line for _top, line in merged]


def _rounding_matches(delta: int, entries: list[tuple[int, OCRLine]]) -> bool:
    signed = 0
    unsigned = []
    for cents, row in entries:
        match = list(_AMOUNT.finditer(row.text))[-1]
        if match.group(1).lstrip().startswith(("-", "+")):
            signed += cents
        else:
            unsigned.append(abs(cents))
    # A printed sign is authoritative. For one missing sign, the independently
    # printed charge may corroborate either direction; multiple unknown signs
    # remain ambiguous and require review.
    return delta == signed if not unsigned else len(unsigned) == 1 and abs(delta - signed) == unsigned[0]


def _receipt_total(lines: list[OCRLine]) -> tuple[float | None, float | None, list[str], list[str]]:
    """Select printed payable evidence, reconciling payment and rounding in cents.

    Product prices, cash tender and change are never fallback totals. Conflicting
    printed charges are exposed for review rather than resolved by magnitude.
    """
    from decimal import Decimal

    totals: list[tuple[int, int, OCRLine]] = []
    payments: list[tuple[int, OCRLine]] = []
    rounding: list[tuple[int, OCRLine]] = []
    supporting_rows: dict[str, list[OCRLine]] = {}
    terminal = any(re.search(r"\b(cashless|approved|type\s*:?\s*sale|card name)\b", line.text, re.I)
                   for line in lines)
    for index, line in enumerate(lines):
        sources = [line]
        payable_text = line.text
        values = _money_values(line.text)
        quantity_summary = any(re.search(r"\b(?:total|jumlah)\s+(?:qty|quantity)\b", r.text, re.I)
                               for r in lines[:index])
        table_before = any(_table_header(r.text) for r in lines[:index])
        payment_after = any(re.match(r"^\s*(?:qr|cash|tunai|visa|mastercard|duitnow|card)\b", r.text, re.I)
                            for r in lines[index + 1:index + 4])
        amount_label = bool(re.fullmatch(r"\s*amount\s*:?\s*(?:(?:RM\s*)?\d+[.,]\d{2})?\s*", payable_text, re.I))
        contextual_amount = amount_label and (quantity_summary or (table_before and payment_after))
        if not values and (_payable_line(line.text) or contextual_amount):
            # OCR may place a total's amount on the next printed row. Only a
            # standalone amount or a closing parenthetical qualifier can finish
            # this label; never borrow a product price or another summary's value.
            for following in lines[index + 1:index + 4]:
                remainder = _AMOUNT.sub("", following.text).strip(" .:-\t$")
                open_qualifier = payable_text.count("(") > payable_text.count(")")
                closing_qualifier = (open_qualifier and ")" in remainder and
                    bool(re.match(r"^(?:if applicable|incl(?:uding|usive)?\.?|of\b|\d+\s*%\s*(?:SST|GST|tax)\b)", remainder, re.I)))
                # A quantity can share the following summary amount row when
                # fonts/columns are split by OCR. Keep that evidence explicitly.
                summary_quantity = contextual_amount and quantity_summary and bool(re.fullmatch(r"\d+", remainder))
                if remainder and not closing_qualifier and not summary_quantity:
                    break
                sources.append(following)
                payable_text += " " + following.text
                values = _money_values(following.text)
                if values:
                    break
        if not values or _table_header(line.text):
            continue
        value = values[-1]
        cents = int(Decimal(str(value)) * 100)
        if re.search(r"\b(rounding|pembundaran)\b", line.text, re.I):
            rounding.append((cents, line))
            continue
        if cents <= 0:
            continue
        # Some restaurant receipts label the payable total only AMOUNT. Accept
        # that exact label in a summary area, never arbitrary product wording.
        if _payable_line(payable_text) or contextual_amount:
            rank = 2 if re.search(r"\b(grand total|nett? total|total amount|amount (due|payable)|total (due|payable)|jumlah besar|jumlah bersih)\b", payable_text, re.I) else 1
            totals.append((rank, cents, line))
            supporting_rows[line.text] = sources
        # A bare AMOUNT is accepted only in a card-terminal context. A payment
        # row must start with its label, excluding card balance and product names.
        payment_label = re.match(r"^\s*(visa|mastercard|amex|card payment|paid amount|amount paid|amount charged)\b", line.text, re.I)
        terminal_amount = terminal and re.match(r"^\s*amount\s*(?:RM|\d)", line.text, re.I)
        if (payment_label or terminal_amount) and not re.search(r"\b(balance|change|refund|cashback|cash back)\b", line.text, re.I):
            payments.append((cents, line))

    best_rank = max((rank for rank, _, _ in totals), default=0)
    best = [(cents, line) for rank, cents, line in totals if rank == best_rank]
    total_values = {cents for cents, _ in best}
    payment_values = {cents for cents, _ in payments}
    if len(total_values) == 2 and rounding:
        # Some receipts print TOTAL both before and after rounding. Select the
        # later printed total only when the difference matches a rounding row
        # situated between them, and any printed charge agrees with that total.
        later_value, later_line = best[-1]
        earlier_value, earlier_line = best[0]
        between = [(cents, row) for cents, row in rounding
                   if lines.index(earlier_line) < lines.index(row) < lines.index(later_line)]
        if (between and _rounding_matches(later_value - earlier_value, between)
                and (not payment_values or payment_values == {later_value})):
            best = [(cents, row) for cents, row in best if cents == later_value]
            total_values = {later_value}
    if len(total_values) > 1 or len(payment_values) > 1:
        return None, 0.0, ["Printed payable amounts conflict; please confirm the total."], []
    selected = payments or best
    if not selected:
        return None, 0.0, [], []
    if total_values and payment_values and total_values != payment_values:
        delta = next(iter(payment_values)) - next(iter(total_values))
        # A missing OCR minus sign does not authorize inventing text. The final
        # charge is itself printed; rounding magnitude only corroborates it.
        if not rounding or not _rounding_matches(delta, rounding):
            return None, 0.0, ["Payment differs from the receipt total; please confirm it."], []
    cents, line = selected[-1]
    evidence = [source.text for _, record in selected
                for source in supporting_rows.get(record.text, [record])]
    if total_values and payment_values:
        evidence.extend(source.text for _, record in best
                        for source in supporting_rows.get(record.text, [record]))
        if total_values != payment_values:
            evidence.extend(record.text for _, record in rounding)
    scores = [source.confidence for source in supporting_rows.get(line.text, [line])]
    confidence = min(scores) if all(score is not None for score in scores) else None
    return cents / 100, confidence, [], list(dict.fromkeys(evidence))


def parse_receipt(lines: list[OCRLine], *, today: date | None = None) -> dict[str, Any]:
    """Convert OCR lines into editable transaction draft fields."""
    # Vision may correct a collapsed source row into several visible rows. Keep
    # its original score/provenance while parsing each logical row separately.
    cleaned = [OCRLine(text.strip(), round(float(line.confidence), 4) if line.confidence is not None else None, line.boxes)
               for line in lines for text in line.text.splitlines() if text.strip()]
    merchant, merchant_confidence = _merchant(cleaned)

    transaction_date = ""
    date_confidence = 0.0
    local_today = today or datetime.now(ZoneInfo("Asia/Kuala_Lumpur")).date()
    date_candidates = []
    terminal_section = False
    for index, line in enumerate(cleaned):
        if re.search(r"\b(cashless transaction|card number|type\s*:?\s*sale)\b", line.text, re.I):
            terminal_section = True
        if re.search(r"\b(exp(?:iry)?\s*date|valid (until|thru)|date of birth)\b", line.text, re.I):
            continue
        candidate = _parse_date(line.text)
        if candidate and candidate <= local_today.isoformat():
            labelled = bool(re.search(r"\b(date|tarikh)\b", line.text, re.I))
            # The purchase date outranks a repeated card-terminal timestamp.
            rank = (3 if labelled else 2) if not terminal_section else 1
            date_candidates.append((rank, -index, candidate, line))
    date_evidence = []
    if date_candidates:
        selected_date = max(date_candidates, key=lambda candidate: candidate[:2])
        transaction_date, date_line = selected_date[2:]
        date_confidence = date_line.confidence
        date_evidence = [date_line.text]
    total, total_confidence, parser_warnings, total_evidence = _receipt_total(cleaned)
    if date_candidates:
        best_date_rank = max(candidate[0] for candidate in date_candidates)
        if len({candidate[2] for candidate in date_candidates if candidate[0] == best_date_rank}) > 1:
            transaction_date, date_confidence, date_evidence = "", 0.0, []
            parser_warnings.append("Printed purchase dates conflict; please confirm the receipt date.")

    # Items are priced rows ABOVE the totals block. Locating that boundary by
    # position (not a growing word blocklist) generalises across receipts: every
    # summary/payment row (subtotal, total, tax, change, loyalty balance) sits at
    # or below it. A small payment/tender set still drops tender lines that print
    # inside the item area (e.g. a card line above the subtotal).
    boundary = len(cleaned)
    for index, line in enumerate(cleaned):
        if _summary_boundary(line.text):
            boundary = index
            break

    items: list[dict[str, Any]] = []
    in_table = False
    pending_description: list[OCRLine] = []
    for line in cleaned[:boundary]:
        lowered = line.text.lower()
        if _table_header(line.text):
            in_table = True
            pending_description = []
            continue
        if in_table and re.fullmatch(r"\s*(?:product|item|description|qty|quantity|price)\s*", line.text, re.I):
            continue
        values = _money_values(line.text)
        if not values:
            # Explicit unpriced modifier/quantity rows belong to the last priced
            # product; they never become additional paid items or guessed prices.
            if items and re.match(r"^(?:\d+\s+|no\s+|without\s+|add[- ]?on\b)", lowered):
                modifier = re.sub(r"^\d+\s+", "", line.text).strip()
                items[-1].setdefault("modifiers", []).append(modifier)
            elif (items and not in_table and not _NON_ITEM_RE.search(lowered)
                  and not _parse_date(line.text) and re.match(r"^[A-Za-z]", line.text)
                  and not re.search(r"\b(invoice|order|cashier|server|receipt|thank you|tel|phone|date|tarikh)\b", lowered)
                  and not _TIME.search(line.text)):
                # Modifier rows can wrap without a quantity or an explicit table
                # heading. Preserve their wording without inventing extra prices.
                items[-1].setdefault("modifiers", []).append(line.text)
            elif in_table and not _NON_ITEM_RE.search(lowered) and not _parse_date(line.text) and re.search(r"[A-Za-z]", line.text):
                pending_description.append(line)
            continue
        if values[-1] <= 0 or _NON_ITEM_RE.search(lowered) or _qr_payment_row(line.text) or _parse_date(line.text):
            pending_description = []
            continue
        description = _AMOUNT.sub("", line.text).strip(" .:-\t$")
        if pending_description:
            prefix = " ".join(row.text for row in pending_description)
            description = prefix if not description or description.isdigit() else f"{prefix} {description}"
        if description and not description.isdigit():
            source_scores = [row.confidence for row in [*pending_description, line]]
            items.append({
                "description": description[:160],
                "amount": round(values[-1], 2),
                "confidence": round(min(source_scores), 4) if all(score is not None for score in source_scores) else None,
            })
        pending_description = []

    # One watermark with no transaction evidence must remain an empty draft.
    if not transaction_date and total is None and not items:
        merchant, merchant_confidence = "", 0.0
    category_lines = [OCRLine(merchant, merchant_confidence)] + [
        OCRLine(" ".join([item["description"], *item.get("modifiers", [])]), item["confidence"])
        for item in items]
    category, category_confidence = _category(category_lines) if merchant or items else ("", 0.0)
    return {
        "merchant": merchant,
        "transactionDate": transaction_date,
        "totalAmount": f"{total:.2f}" if total is not None else "",
        "suggestedCategory": category,
        "items": items,
        "confidence": {
            "merchant": round(merchant_confidence, 4) if merchant_confidence is not None else None,
            "transactionDate": round(date_confidence, 4) if date_confidence is not None else None,
            "totalAmount": round(total_confidence, 4) if total_confidence is not None else None,
            "category": round(category_confidence, 4),
        },
        "rawLines": [line.text for line in cleaned],
        "parserWarnings": parser_warnings,
        "fieldEvidence": {
            "merchant": [line.text for line in cleaned if _merchant_text(line.text) == merchant],
            "transactionDate": date_evidence,
            "totalAmount": total_evidence,
        },
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
        # Phone cameras commonly produce 12 MP images. A bounded detector input
        # avoids spending ARM CPU time on pixels that do not improve receipt OCR.
        text_det_limit_side_len=_positive_int_env("PADDLE_OCR_MAX_SIDE", 1600),
        text_det_limit_type="max",
        cpu_threads=_positive_int_env("PADDLE_OCR_CPU_THREADS", min(4, os.cpu_count() or 1)),
        # Oracle Ampere uses Paddle's dynamic runner because the prebuilt ARM64
        # wheel can segfault while creating the static AnalysisPredictor.
        engine=os.environ.get("PADDLE_OCR_ENGINE") or None,
        # PaddlePaddle 3.3.x on Windows CPU currently crashes in the oneDNN PIR
        # converter for OCR detection. Standard CPU kernels are slower but stable.
        enable_mkldnn=False,
        # Quarter-turn correction must precede grouping boxes into receipt rows.
        use_doc_orientation_classify=os.environ.get("PADDLE_OCR_DOC_ORIENTATION", "true").lower() not in ("0", "false", "no"),
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

    started = perf_counter()
    image, original_size = _prepare_ocr_image(image_bytes)
    prepared_ms = round((perf_counter() - started) * 1000, 2)
    inference_started = perf_counter()
    with _OCR_INFERENCE_LOCK:
        results = (engine or get_ocr_engine()).predict(image)
        raw: list[tuple[str, float, tuple[int, int, int, int] | None]] = []
        slopes: list[float] = []
        upright_image = None
        orientation = None
        for result in results:
            payload = _result_payload(result)
            # Keep the actual document-preprocessor image. Its coordinates match
            # the recognised boxes, so vision can inspect the same upright rows.
            preprocessing = (result.get("doc_preprocessor_res") if hasattr(result, "get")
                             else payload.get("doc_preprocessor_res")) or {}
            if hasattr(preprocessing, "get"):
                candidate_image = preprocessing.get("output_img")
                if getattr(candidate_image, "ndim", None) == 3:
                    upright_image = candidate_image
                angle = preprocessing.get("angle")
                if angle in (0, 90, 180, 270):
                    orientation = int(angle)
            texts = payload.get("rec_texts", [])
            scores = payload.get("rec_scores", [])
            polygons = payload.get("rec_polys")
            if polygons is not None:
                for polygon in polygons:
                    try:
                        left, right = polygon[0], polygon[1]
                        dx, dy = float(right[0] - left[0]), float(right[1] - left[1])
                        box = _bbox(polygon)
                        if box and dx > 2 * (box[3] - box[1]) and abs(dy / dx) <= .35:
                            slopes.append(dy / dx)
                    except (TypeError, IndexError, ValueError):
                        continue
            boxes = payload.get("rec_boxes", None)
            if boxes is None:
                boxes = payload.get("rec_polys", None)
            has_boxes = boxes is not None and len(boxes) >= len(texts)
            for index, text in enumerate(texts):
                if not str(text).strip():
                    continue
                score = float(scores[index]) if index < len(scores) else 0.0
                box = _bbox(boxes[index]) if has_boxes else None
                raw.append((str(text), score, box))
        # Require several lines to avoid estimating receipt skew from a logo.
        row_slope = median(slopes) if len(slopes) >= 3 else 0.0
        lines = OCRLines(_reconstruct_rows(raw, row_slope=row_slope))
        if upright_image is not None:
            import cv2
            encoded, buffer = cv2.imencode(".jpg", upright_image,
                                           [cv2.IMWRITE_JPEG_QUALITY, 95])
            if encoded:
                lines.verification_image = buffer.tobytes()
        lines.orientation = orientation

    event = {
        "event": "receipt_ocr",
        "input_bytes": len(image_bytes),
        "original_width": original_size[0],
        "original_height": original_size[1],
        "processed_width": int(image.shape[1]),
        "processed_height": int(image.shape[0]),
        "prepare_ms": prepared_ms,
        "inference_ms": round((perf_counter() - inference_started) * 1000, 2),
        "line_count": len(lines),
        "document_orientation": orientation,
    }
    LOGGER.info(json.dumps(event, separators=(",", ":")))
    return lines


def _add_review_status(result: dict[str, Any]) -> dict[str, Any]:
    """Flag fields that need a retake or explicit manual correction."""
    warnings: list[str] = list(result.get("parserWarnings", []))
    # Correcting every source ID is not proof that a collapsed document contains
    # every readable row. Report this independently of provider coverage status.
    if len(result.get("rawLines", [])) <= 5 and any(len(text) > 200 for text in result.get("rawLines", [])):
        warnings.append("Initial OCR merged receipt rows; check the recovered fields or rotate/crop and rescan.")
    records = [{**record, "finalText": text.strip()}
               for record in result.get("ocrVerification", {}).get("lines", [])
               for text in record["finalText"].splitlines() if text.strip()]
    verification = result.get("ocrVerification", {})
    if verification.get("unapplied"):
        warnings.append("Some image-verification decisions were rejected; check the receipt fields and products.")
    if result.get("verificationStatus") == "partial":
        warnings.append("Image verification is partial; some receipt rows remain unresolved.")
    if not result.get("items") and any(_table_header(r["finalText"]) for r in records):
        warnings.append("Product descriptions were not recovered; check the itemised receipt before saving.")
    critical_fields = (
        ("merchant", "Merchant"),
        ("transactionDate", "Receipt date"),
        ("totalAmount", "Total amount"),
    )
    for field, label in critical_fields:
        if not result.get(field):
            warnings.append(f"{label} was not detected.")
            continue
        if field == "merchant":
            sources = [r for r in records if _merchant_text(r["finalText"]) == result[field]]
        elif field == "transactionDate":
            sources = [r for r in records if _parse_date(r["finalText"]) == result[field]]
        else:
            evidence = result.get("fieldEvidence", {}).get(field, [])
            sources = [r for r in records if r["finalText"] in evidence]
        if not sources or any(r["status"] in ("uncertain", "unverified") for r in sources):
            warnings.append(f"{label} has not been visually verified.")
        if field in result.get("changedFields", []):
            warnings.append(f"{label} changed after image verification; please confirm it.")
        if field == "totalAmount" and not sources:
            warnings.append("Payable total is ambiguous; please check it.")
    headings = [r for r in records[:40] if re.search(r"\b(sdn|bhd|trading|mart|restaurant|cafe|gift|store|shop|delights|international)\b", r["finalText"], re.I) and not _money_values(r["finalText"]) and not _parse_date(r["finalText"])]
    if len(headings) > 1:
        warnings.append("Multiple business headings detected; please confirm the merchant.")
    if result.get("verificationStatus") in ("failed", "not_configured"):
        warnings.append("Image verification is unavailable; please check the receipt fields.")
    result["reviewRequired"] = bool(warnings)
    result["reviewWarnings"] = warnings
    return result


def extract_receipt(image_bytes: bytes, engine: Any | None = None) -> dict[str, Any]:
    """Interpret the image with Gemini; use the parser only on provider failure."""
    from app.receipt_extraction import extract_with_gemini

    started = perf_counter()
    ocr_failed = False
    try:
        lines = run_paddle_ocr(image_bytes, engine)
    except Exception:
        # A broken OCR engine must not prevent image-only interpretation.
        lines, ocr_failed = [], True
    image = getattr(lines, "verification_image", None) or image_bytes
    failure = "not_configured"
    try:
        result = extract_with_gemini(image, lines)
    except Exception as exc:
        result, failure = None, "failed"
        LOGGER.warning("receipt extraction provider failure: %s", type(exc).__name__)
    if result is None:
        result = parse_receipt(lines)
        category, confidence, _ = (classify_category(result["merchant"], result["items"])
            if result["merchant"] or result["items"] else ("", 0.0, "unavailable"))
        if category:
            result["suggestedCategory"] = category
            result["confidence"]["category"] = round(confidence, 4)
        warnings = list(result.get("parserWarnings", []))
        warnings.insert(0, "Gemini could not read this receipt. These are OCR fallback results; review all fields before saving.")
        for field, label in (("merchant", "Merchant"), ("transactionDate", "Receipt date"), ("totalAmount", "Total amount")):
            if not result.get(field):
                warnings.append(f"{label} was not detected.")
        result.update(extractionSource="ocr_fallback", verificationStatus=failure,
                      enhancementStatus=failure, reviewRequired=True, reviewWarnings=warnings)
    if ocr_failed:
        result["reviewWarnings"].append("Supporting OCR was unavailable; check the image against the extracted fields.")
        result["reviewRequired"] = True
    result["rawLines"] = [line.text for line in lines]
    result["imagePreparation"] = {"documentOrientation": getattr(lines, "orientation", None)}
    LOGGER.info(json.dumps({"event": "receipt_extraction", "source": result["extractionSource"],
        "elapsed_ms": round((perf_counter() - started) * 1000, 2),
        "review_required": result["reviewRequired"], "ocr_failed": ocr_failed,
        "provider": result.get("extractionMetadata", {})}, separators=(",", ":")))
    return result
