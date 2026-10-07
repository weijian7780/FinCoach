"""Regression family for slanted receipts and summary/payment boundaries."""
import io
import json
from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from app.receipt_ocr import OCRLine, _reconstruct_rows, extract_receipt, parse_receipt, run_paddle_ocr
from app.receipt_vision import merge_corrections, verify_receipt_image


def rows(*texts):
    return [OCRLine(text, .98) for text in texts]


@pytest.mark.parametrize("merchant,address", [
    ("AYAM GEPUK", "Alamesra Shop/Office Phase 1, 88400 Kota"),
    ("BUNGA", "1st Floor, Block M, Lorong Plaza Permai"),
    ("KEDAI MAKAN", "No 12 Jalan Shop Street, 88400 Sabah"),
])
def test_address_cannot_outrank_merchant(merchant, address):
    result = parse_receipt(rows("Number 164", merchant, address, "05-10-2026", "TOTAL 14.00"))
    assert result["merchant"] == merchant


def test_quantity_summary_and_qr_payment_do_not_become_products():
    result = parse_receipt(rows("AYAM GEPUK", "Pak Gendut", "05-10-2026 18:53",
        "Qty Total", "Product", "Ayam Gepuk CRISPY SET A [Random/Pedas/Teh O Ais]",
        "1 RM14.00", "Total QTY", "1", "Amount RM14.00", "QR RM14.00"),
        today=date(2026, 10, 5))
    assert result["totalAmount"] == "14.00"
    assert len(result["items"]) == 1
    assert "CRISPY SET A" in result["items"][0]["description"]
    assert result["items"][0]["amount"] == 14
    assert result["suggestedCategory"] == "Food"


def test_missed_product_does_not_turn_column_heading_into_item():
    result = parse_receipt(rows("AYAM GEPUK", "Qty Total", "Product", "]", "RM14.00",
        "Total QTY", "Amount RM14.00", "QR RM14.00"))
    assert result["items"] == []
    assert result["totalAmount"] == "14.00"


def test_payment_keyword_inside_real_product_name_is_not_excluded():
    result = parse_receipt(rows("RETAIL SHOP", "Item Qty Total", "QR Sticker 3.00",
        "QR RM3.00", "TOTAL 3.00"))
    assert [i["description"] for i in result["items"]] == ["QR Sticker"]


@pytest.mark.parametrize("summary", ["Total QTY", "Total Quantity 1", "Jumlah Qty 1"])
def test_quantity_summary_ends_item_area(summary):
    result = parse_receipt(rows("CAFE", "Item Qty Total", "Coffee 14.00", summary,
        "Amount RM14.00", "QR RM14.00"))
    assert [i["description"] for i in result["items"]] == ["Coffee"]


@pytest.mark.parametrize("text", ["Amount Cake 14.00", "Amount discount 14.00", "QR RM14.00"])
def test_bare_amount_without_receipt_summary_context_is_not_payable(text):
    assert parse_receipt(rows("SHOP", text))["totalAmount"] == ""


def test_two_contextual_amounts_stay_ambiguous():
    result = parse_receipt(rows("CAFE", "Item Qty Total", "Coffee 14.00",
        "Total QTY 1", "Amount RM14.00", "Amount RM24.00", "QR RM14.00"))
    assert result["totalAmount"] == ""
    assert result["parserWarnings"]


@pytest.mark.parametrize("amount_row", ["RM14.00", "1 RM14.00"])
def test_split_summary_amount_preserves_label_and_amount_evidence(amount_row):
    result = parse_receipt(rows("CAFE", "Product Qty Total", "Coffee 14.00",
        "Total QTY", "Amount", amount_row, "QR", "RM14.00"))
    assert result["totalAmount"] == "14.00"
    assert result["fieldEvidence"]["totalAmount"] == ["Amount", amount_row]
    assert len(result["items"]) == 1


def test_sloped_columns_group_by_projected_baseline():
    # The right side is 30 px higher: horizontal grouping pairs adjacent rows.
    raw = [("Bill Number", .98, (100, 100, 240, 120)),
           ("0510-164", .99, (700, 70, 800, 90)),
           ("Order Time", .98, (100, 140, 240, 160)),
           ("05-10-2026 18:53", .99, (700, 110, 800, 130))]
    result = _reconstruct_rows(raw, row_slope=-.05)
    assert [r.text for r in result] == ["Bill Number 0510-164", "Order Time 05-10-2026 18:53"]


def test_polygon_skew_is_estimated_in_the_real_ocr_adapter():
    image = io.BytesIO()
    Image.new("RGB", (1000, 250)).save(image, "JPEG")
    source = [("Bill Number", 100, 100, 140), ("0510-164", 700, 70, 100),
              ("Order Time", 100, 140, 140), ("05-10-2026 18:53", 700, 110, 100)]
    polygons = [[[x, y], [x + w, y - .05*w], [x + w, y + 20 - .05*w], [x, y + 20]]
                for _, x, y, w in source]
    engine = MagicMock()
    engine.predict.return_value = [{"rec_texts": [s[0] for s in source],
        "rec_scores": [.98]*4, "rec_polys": polygons}]
    result = run_paddle_ocr(image.getvalue(), engine)
    assert [r.text for r in result] == ["Bill Number 0510-164", "Order Time 05-10-2026 18:53"]


def test_single_decision_contract_preserves_uncertain_rows_and_recovers_missing_text():
    source = rows("AYAM GEPUK", "TYPO", "TOTAL 14.00")
    payload = {"decisions": [
        {"lineId": 0, "status": "confirmed", "text": "AYAM GEPUK", "reason": ""},
        {"lineId": 1, "status": "uncertain", "text": "GUESS", "reason": "Unreadable"},
        {"lineId": 2, "status": "confirmed", "text": "TOTAL 14.00", "reason": ""}],
        "missingLines": [{"afterLineId": 1, "text": "Meal 14.00"}]}
    result = merge_corrections(source, payload)
    assert [r["finalText"] for r in result["lines"]] == ["AYAM GEPUK", "TYPO", "Meal 14.00", "TOTAL 14.00"]
    assert result["status"] == "partial"


def test_duplicate_decision_is_rejected_without_choosing_a_winner():
    payload = {"decisions": [
        {"lineId": 0, "status": "confirmed", "text": "SHOP", "reason": ""},
        {"lineId": 0, "status": "corrected", "text": "CAFE", "reason": ""}], "missingLines": []}
    result = merge_corrections(rows("SHOP"), payload)
    assert result["lines"][0]["finalText"] == "SHOP"
    assert result["lines"][0]["status"] == "unverified"
    assert result["unapplied"]


def test_invalid_contract_gets_one_repair_request_and_records_attempts():
    image = io.BytesIO()
    Image.new("RGB", (2, 2)).save(image, "PNG")
    bad = {"decisions": [], "missingLines": []}
    good = {"decisions": [{"lineId": 0, "status": "confirmed", "text": "SHOP", "reason": ""}], "missingLines": []}
    client = MagicMock()
    client.models.generate_content.side_effect = [SimpleNamespace(
        candidates=[SimpleNamespace(finish_reason="STOP")], text=json.dumps(p)) for p in (bad, good)]
    with patch("app.receipt_vision.config.GEMINI_API_KEY", "test-key"), patch("google.genai.Client") as factory:
        factory.return_value.__enter__.return_value = client
        result = verify_receipt_image(image.getvalue(), rows("SHOP"))
    assert result["_attempts"] == 2
    assert client.models.generate_content.call_count == 2


def test_second_invalid_response_is_partial_and_cannot_loop():
    image = io.BytesIO()
    Image.new("RGB", (2, 2)).save(image, "PNG")
    client = MagicMock()
    client.models.generate_content.return_value = SimpleNamespace(
        candidates=[SimpleNamespace(finish_reason="STOP")], text='{"decisions":[],"missingLines":[]}')
    with patch("app.receipt_vision.config.GEMINI_API_KEY", "test-key"), patch("google.genai.Client") as factory:
        factory.return_value.__enter__.return_value = client
        payload = verify_receipt_image(image.getvalue(), rows("SHOP"))
    result = merge_corrections(rows("SHOP"), payload)
    assert result["status"] == "partial"
    assert result["lines"][0]["finalText"] == "SHOP"
    assert result["lines"][0]["status"] == "unverified"
    assert result["unapplied"]
    assert client.models.generate_content.call_count == 2


def test_repair_uses_remaining_deadline_instead_of_resetting_timeout():
    image = io.BytesIO()
    Image.new("RGB", (2, 2)).save(image, "PNG")
    client = MagicMock()
    client.models.generate_content.return_value = SimpleNamespace(
        candidates=[SimpleNamespace(finish_reason="STOP")], text='{"decisions":[],"missingLines":[]}')
    with patch("app.receipt_vision.config.GEMINI_API_KEY", "test-key"), patch(
        "app.receipt_vision.config.RECEIPT_CLEANUP_TIMEOUT_SECONDS", 12), patch(
        "app.receipt_vision.monotonic", side_effect=[0, 0, 3]), patch("google.genai.Client") as factory:
        factory.return_value.__enter__.return_value = client
        payload = verify_receipt_image(image.getvalue(), rows("SHOP"))
    assert client.models.generate_content.call_count == 1
    assert payload["_attempts"] == 1
    assert any("Repair skipped" in e for e in payload["_validationErrors"])
    assert merge_corrections(rows("SHOP"), payload)["status"] == "partial"


def test_request_below_provider_minimum_is_never_sent():
    image = io.BytesIO()
    Image.new("RGB", (2, 2)).save(image, "PNG")
    with patch("app.receipt_vision.config.GEMINI_API_KEY", "test-key"), patch(
        "app.receipt_vision.config.RECEIPT_CLEANUP_TIMEOUT_SECONDS", 5), patch("google.genai.Client") as factory:
        with pytest.raises(TimeoutError, match="10-second minimum"):
            verify_receipt_image(image.getvalue(), rows("SHOP"))
    factory.return_value.__enter__.return_value.models.generate_content.assert_not_called()


def test_partial_items_and_rejected_decisions_always_require_review():
    source = rows("AYAM GEPUK", "05-10-2026", "Qty Total", "Product", "RM14.00",
                  "Total QTY", "Amount RM14.00", "QR RM14.00")
    with patch("app.receipt_ocr.run_paddle_ocr", return_value=source), patch(
        "app.receipt_ocr.verify_receipt_image", return_value={"confirmedLineIds": list(range(len(source))),
            "uncertainLineIds": [3]}), patch("app.receipt_ocr.classify_category", return_value=("Food", .7, "test")):
        result = extract_receipt(b"unused")
    assert result["reviewRequired"]
    assert any("product" in warning.lower() for warning in result["reviewWarnings"])
    assert any("decision" in warning.lower() for warning in result["reviewWarnings"])
