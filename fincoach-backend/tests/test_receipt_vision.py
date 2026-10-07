import io
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from PIL import Image
from app.receipt_ocr import OCRLine, parse_receipt
from app.receipt_vision import merge_corrections, verify_receipt_image


class CorrectionIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.lines = [OCRLine("SHOP", .98), OCRLine("MILO 2.OO", .99), OCRLine("TOTAL 2.00", .97)]

    def test_partial_conflicts_unknown_ids_and_duplicates_are_local(self):
        result = merge_corrections(self.lines, {"confirmedLineIds": [0, 0, 999],
            "uncertainLineIds": [0], "corrections": [None, {"lineId": 1, "correctedText": "MILO 2.00"}, {"lineId": 1, "correctedText": "MILO 2.00"}]})
        self.assertEqual([r["status"] for r in result["lines"]], ["unverified", "corrected", "unverified"])
        self.assertEqual(result["lines"][1]["originalText"], "MILO 2.OO")
        self.assertEqual(result["lines"][1]["ocrConfidence"], .99)
        self.assertEqual(result["verifiedSourceLines"], 1)
        self.assertEqual(result["status"], "partial")

    def test_missing_rows_insert_before_totals_and_invalid_anchor_is_retained(self):
        result = merge_corrections(self.lines, {"missingLines": [
            {"afterLineId": None, "text": "MYDIN MART"},
            {"afterLineId": 1, "text": "BREAD 3.00"},
            {"afterLineId": 99, "text": "MISPLACED 8.00"}]})
        self.assertEqual([r["finalText"] for r in result["lines"]], ["MYDIN MART", "SHOP", "MILO 2.OO", "BREAD 3.00", "TOTAL 2.00"])
        added = result["lines"][0]
        self.assertIsNone(added["ocrConfidence"])
        self.assertEqual(result["unapplied"][0]["text"], "MISPLACED 8.00")

    def test_empty_ocr_can_recover_text_without_fabricating_confidence(self):
        merged = merge_corrections([], {"missingLines": [{"afterLineId": None, "text": "MYDIN MART"}, {"afterLineId": None, "text": "TOTAL 5.00"}]})
        parsed = parse_receipt([OCRLine(r["finalText"], r["ocrConfidence"]) for r in merged["lines"]])
        self.assertEqual(parsed["totalAmount"], "5.00")
        self.assertIsNone(parsed["confidence"]["totalAmount"])

    def test_unknown_overall_structure_rejected(self):
        with self.assertRaises(ValueError):
            merge_corrections(self.lines, {"merchant": "fake field extraction"})

    def test_named_dates_calendar_validation_and_tender_exclusion(self):
        self.assertEqual(parse_receipt([OCRLine("31 Feb 2018", .9)])["transactionDate"], "")
        parsed = parse_receipt([OCRLine(t, .9) for t in ("MYDIN MART", "12 March 2018", "BREAD 2.00", "SUBTOTAL 2.00", "TOTAL 2.10", "TOTAL CASH 10.00", "CHANGE 7.90")])
        self.assertEqual(parsed["transactionDate"], "2018-03-12")
        self.assertEqual(parsed["totalAmount"], "2.10")
        self.assertEqual(len(parsed["items"]), 1)

    def test_tax_inclusive_payable_amount_is_not_tax_summary(self):
        result = parse_receipt([OCRLine(t, .95) for t in (
            "99 SPEED MART S/B (519537-X)", "BREAD 2.50", "Total Qty: 1 2.36",
            "Total Sales (Excluding GST) 2.36", "Total GST 0.14",
            "Total Sales (Inclusive of GST) 2.50", "TOTAL CASH 5.00", "CHANGE 2.50")])
        self.assertEqual(result["merchant"], "99 SPEED MART S/B")
        self.assertEqual(result["totalAmount"], "2.50")


class VisionRequestTests(unittest.TestCase):
    def test_original_image_and_indexed_text_are_sent_once(self):
        image = io.BytesIO()
        Image.new("RGB", (2, 2)).save(image, format="PNG")
        client = MagicMock()
        client.models.generate_content.return_value = SimpleNamespace(
            candidates=[SimpleNamespace(finish_reason="STOP")], text='{"decisions":[{"lineId":0,"status":"confirmed","text":"SHOP","reason":""}],"missingLines":[]}')
        with patch("app.receipt_vision.config.GEMINI_API_KEY", "test-key"), patch("google.genai.Client") as factory:
            factory.return_value.__enter__.return_value = client
            result = verify_receipt_image(image.getvalue(), [OCRLine("SHOP", .99)])
        self.assertEqual(result["decisions"][0]["lineId"], 0)
        request = client.models.generate_content.call_args.kwargs
        self.assertEqual(request["contents"][0].inline_data.data, image.getvalue())
        self.assertEqual(request["contents"][0].inline_data.mime_type, "image/png")
        self.assertIn('"id": 0', request["contents"][1])
        self.assertEqual(factory.call_args.kwargs["http_options"].retry_options.attempts, 1)
        client.models.generate_content.assert_called_once()

    def test_missing_key_makes_no_request(self):
        with patch("app.receipt_vision.config.GEMINI_API_KEY", ""), patch("google.genai.Client") as client:
            self.assertIsNone(verify_receipt_image(b"unused", []))
        client.assert_not_called()

    def test_truncated_or_undecodable_response_is_rejected(self):
        image = io.BytesIO()
        Image.new("RGB", (2, 2)).save(image, format="PNG")
        for reason, text in (("MAX_TOKENS", '{}'), ("STOP", '{"corrections":')):
            client = MagicMock()
            client.models.generate_content.return_value = SimpleNamespace(candidates=[SimpleNamespace(finish_reason=reason)], text=text)
            with patch("app.receipt_vision.config.GEMINI_API_KEY", "test-key"), patch("google.genai.Client") as factory:
                factory.return_value.__enter__.return_value = client
                with self.assertRaises(ValueError):
                    verify_receipt_image(image.getvalue(), [])
