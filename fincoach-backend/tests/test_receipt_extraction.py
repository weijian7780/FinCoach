import io
import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from PIL import Image

from app.receipt_extraction import Receipt, extract_with_gemini, normalize_receipt, validate_contract
from app.receipt_ocr import OCRLine, OCRLines, extract_receipt


def payload():
    return dict(merchant="Old Legend Coffee Tea Shd. Bhd.", transactionDate="2026-10-10",
                currency="MYR", totalAmount="14.80", suggestedCategory="Food",
                items=[dict(description="Pork Fillet with Rice", amount="14.80", quantity=1, modifiers=[])],
                breakdown=dict(subtotal="14.80", discount="0.00", tax="0.00", serviceCharge="0.00", rounding="0.00"),
                arithmeticCheckApplicable=True, multipleReceipts=False, warnings=[],
                evidence={k: dict(text=t, status="readable") for k, t in
                          [("merchant", "Old Legend Coffee Tea Shd. Bhd."),
                           ("transactionDate", "10/10/26"), ("totalAmount", "Final Amount(MYR) 14.80")]})


def image():
    out = io.BytesIO()
    Image.new("RGB", (8, 8)).save(out, "PNG")
    return out.getvalue()


@pytest.mark.parametrize("ocr", [[], [OCRLine("TOTAL 99.00", .99)], [OCRLine("Final Amount(MYR) 14.80", .99)]])
def test_gemini_owns_fields_even_when_parser_disagrees(ocr):
    with patch("app.receipt_ocr.run_paddle_ocr", return_value=ocr), patch(
        "app.receipt_extraction.verify_receipt_image", return_value=payload()), patch(
        "app.receipt_ocr.parse_receipt", side_effect=AssertionError("Parser must not run")), patch(
        "app.receipt_ocr.classify_category", side_effect=AssertionError("No second classifier")):
        result = extract_receipt(image())
    assert result["totalAmount"] == "14.80"
    assert result["extractionSource"] == "gemini"
    assert not result["reviewWarnings"]
    assert "ocrVerification" not in result


def test_orientation_image_and_matching_boxes_are_passed_together():
    rows = OCRLines([OCRLine("14.80", .99, ((1, 2, 5, 6),))])
    rows.verification_image, rows.orientation = image(), 90
    with patch("app.receipt_ocr.run_paddle_ocr", return_value=rows), patch(
        "app.receipt_extraction.verify_receipt_image", return_value=payload()) as provider:
        result = extract_receipt(b"original")
    assert provider.call_args.args == (rows.verification_image, rows)
    assert result["imagePreparation"]["documentOrientation"] == 90


def test_ocr_failure_still_reads_image():
    with patch("app.receipt_ocr.run_paddle_ocr", side_effect=RuntimeError()), patch(
        "app.receipt_extraction.verify_receipt_image", return_value=payload()) as provider:
        result = extract_receipt(image())
    assert provider.call_args.args[1] == []
    assert result["totalAmount"] == "14.80"
    assert result["reviewRequired"]


@pytest.mark.parametrize("error", [None, TimeoutError(), ValueError("Bad JSON")])
def test_provider_failure_returns_marked_fallback(error):
    with patch("app.receipt_ocr.run_paddle_ocr", return_value=[OCRLine("TOTAL 8.50", .98)]), patch(
        "app.receipt_extraction.extract_with_gemini", return_value=None, side_effect=error), patch(
        "app.receipt_ocr.classify_category", return_value=("Food", .7, "mock")):
        result = extract_receipt(image())
    assert result["extractionSource"] == "ocr_fallback"
    assert result["reviewRequired"] and result["totalAmount"] == "8.50"


def test_uncertain_fields_never_filled_from_other_sources():
    p = payload()
    p["evidence"]["totalAmount"]["status"] = "uncertain"
    result = normalize_receipt(Receipt.model_validate(p))
    assert result["totalAmount"] == ""
    assert result["reviewRequired"]


def test_decimal_reconciliation_warns_without_replacing_printed_total():
    p = payload()
    p["breakdown"]["rounding"] = "-0.01"
    result = normalize_receipt(Receipt.model_validate(p))
    assert result["totalAmount"] == "14.80"
    assert any("reconcile" in w for w in result["reviewWarnings"])
    p["arithmeticCheckApplicable"] = False
    assert not normalize_receipt(Receipt.model_validate(p))["reviewWarnings"]


def test_bundle_modifiers_and_unpriced_items_do_not_inflate_charges():
    p = payload()
    p["items"] = [dict(description="Ayam Gepuk Bertiga", amount="42.90", quantity=1,
                        modifiers=["Penyet x1", "Crispy x2", "Passion Fruit Lemon Tea x3"]),
                  dict(description="Unpriced standalone drink", amount=None, quantity=1, modifiers=[])]
    result = normalize_receipt(Receipt.model_validate(p))
    assert len(result["items"]) == 1
    assert result["items"][0]["amount"] == 42.90
    assert len(result["items"][0]["modifiers"]) == 3
    assert result["reviewRequired"]


@pytest.mark.parametrize("key,value", [("totalAmount", "NaN"), ("totalAmount", 14.80),
    ("transactionDate", "2026-02-30"), ("suggestedCategory", "Invented")])
def test_invalid_contracts_are_rejected(key, value):
    p = payload(); p[key] = value
    assert validate_contract(p, [])


@pytest.mark.parametrize("change", [{"currency": "USD"}, {"currency": "$"}, {"currency": "SGD"}, {"multipleReceipts": True}])
def test_cannot_silently_save_foreign_money_or_combined_receipts(change):
    p = payload(); p.update(change)
    result = normalize_receipt(Receipt.model_validate(p))
    assert result["totalAmount"] == "" and result["items"] == []
    assert result["reviewRequired"]


@pytest.mark.parametrize("currency", [None, "", "RM", "MYR", "myr"])
def test_unmarked_mixue_receipt_defaults_to_rm_without_losing_amount_or_items(currency):
    p = payload()
    p.update(merchant="MIXUE", currency=currency, totalAmount="3.00", arithmeticCheckApplicable=False)
    p["evidence"]["totalAmount"]["text"] = "Total products 1 3.00"
    p["items"] = [dict(description="Fresh Lemonade", amount="3.00", quantity=1,
                      modifiers=["Normal Ice", "50% Less Sugar"])]
    result = normalize_receipt(Receipt.model_validate(p))
    assert result["currency"] == "MYR"
    assert result["totalAmount"] == "3.00"
    assert result["items"][0]["amount"] == 3
    assert not result["reviewWarnings"]


def response(text, finish="STOP"):
    return SimpleNamespace(text=text, candidates=[SimpleNamespace(finish_reason=finish)], usage_metadata=None)


def test_malformed_json_gets_one_repair_with_same_image():
    with patch("app.receipt_vision.config.GEMINI_API_KEY", "test"), patch("google.genai.Client") as factory:
        generate = factory.return_value.__enter__.return_value.models.generate_content
        generate.side_effect = [response("{bad"), response(json.dumps(payload()))]
        result = extract_with_gemini(image(), [])
    assert result["totalAmount"] == "14.80" and generate.call_count == 2


def test_failed_contract_repair_is_not_accepted():
    with patch("app.receipt_vision.config.GEMINI_API_KEY", "test"), patch("google.genai.Client") as factory:
        generate = factory.return_value.__enter__.return_value.models.generate_content
        generate.return_value = response("{}")
        with pytest.raises(ValueError):
            extract_with_gemini(image(), [])
    assert generate.call_count == 2


def test_truncated_response_is_unusable():
    with patch("app.receipt_vision.config.GEMINI_API_KEY", "test"), patch("google.genai.Client") as factory:
        factory.return_value.__enter__.return_value.models.generate_content.return_value = response("{}", "MAX_TOKENS")
        with pytest.raises(ValueError, match="Incomplete"):
            extract_with_gemini(image(), [])


def test_short_remaining_budget_does_not_send_invalid_repair_deadline():
    with patch("app.receipt_vision.config.GEMINI_API_KEY", "test"), patch(
        "app.receipt_vision.config.RECEIPT_CLEANUP_TIMEOUT_SECONDS", 30), patch(
        "app.receipt_vision.monotonic", side_effect=[0, 0, 21]), patch("google.genai.Client") as factory:
        generate = factory.return_value.__enter__.return_value.models.generate_content
        generate.return_value = response("{}")
        with pytest.raises(ValueError):
            extract_with_gemini(image(), [])
    assert generate.call_count == 1


def test_provider_schema_keeps_types_but_local_limits_are_still_enforced():
    from app.receipt_extraction import provider_schema
    schema = provider_schema()
    assert "maxItems" not in json.dumps(schema)
    assert "totalAmount" in schema["required"]
    p = payload(); p["items"][0]["quantity"] = 0
    assert validate_contract(p, [])
    p = payload(); p["breakdown"]["tax"] = "NaN"
    assert validate_contract(p, [])


@pytest.mark.parametrize("merchant,total,date_text,amounts", [
    ("AYAM GEPUK", "14.00", "2026-10-05", ["14.00"]),
    ("McDonald's Likas Bay KK", "24.50", "2026-10-03", ["17.88", "5.24"]),
    ("DOJO 1 BORNEO", "97.00", "2026-10-02", ["6.90", "12.90", "13.90", "42.90", "14.90"]),
])
def test_receipt_family_contract_preserves_printed_totals_and_line_amounts(merchant, total, date_text, amounts):
    # Labelled contract fixtures, not claims of live image recognition.
    p = payload()
    p.update(merchant=merchant, totalAmount=total, transactionDate=date_text, arithmeticCheckApplicable=False)
    p["evidence"] = {key: dict(text=value, status="readable") for key, value in
                     [("merchant", merchant), ("totalAmount", total), ("transactionDate", date_text)]}
    p["items"] = [dict(description=f"Product {i}", amount=amount, quantity=1, modifiers=[])
                  for i, amount in enumerate(amounts)]
    result = normalize_receipt(Receipt.model_validate(p))
    assert result["totalAmount"] == total
    assert result["transactionDate"] == date_text
    assert [item["amount"] for item in result["items"]] == [float(a) for a in amounts]
