import unittest
import weakref
from types import SimpleNamespace
from unittest.mock import patch

from app import receipt_cleanup
from app.receipt_ocr import OCRLine, extract_receipt, parse_receipt, run_paddle_ocr


class ReceiptParserTests(unittest.TestCase):
    def test_extracts_receipt_fields_and_items(self):
        lines = [
            OCRLine("MYDIN MART", 0.97),
            OCRLine("14/07/2026 14:20", 0.94),
            OCRLine("MILO 12.50", 0.91),
            OCRLine("BREAD 3.20", 0.90),
            OCRLine("TOTAL RM 15.70", 0.99),
        ]

        result = parse_receipt(lines)

        self.assertEqual(result["merchant"], "MYDIN MART")
        self.assertEqual(result["transactionDate"], "2026-07-14")
        self.assertEqual(result["totalAmount"], "15.70")
        self.assertEqual(result["suggestedCategory"], "Food")
        self.assertEqual(
            result["items"],
            [
                {"description": "MILO", "amount": 12.5, "confidence": 0.91},
                {"description": "BREAD", "amount": 3.2, "confidence": 0.9},
            ],
        )

    def test_uses_largest_amount_when_total_label_is_missing(self):
        result = parse_receipt(
            [OCRLine("KEDAI MAKAN", 0.9), OCRLine("NASI AYAM 8.50", 0.85), OCRLine("10.00", 0.8)]
        )
        self.assertEqual(result["totalAmount"], "10.00")
        self.assertEqual(result["suggestedCategory"], "Food")

    def test_returns_editable_empty_fields_instead_of_inventing_values(self):
        result = parse_receipt([OCRLine("THANK YOU", 0.7)])
        self.assertEqual(result["totalAmount"], "")
        self.assertEqual(result["transactionDate"], "")
        self.assertEqual(result["suggestedCategory"], "")


class PaddleAdapterTests(unittest.TestCase):
    def test_normalizes_v3_rec_texts_and_scores(self):
        class Result:
            json = {"res": {"rec_texts": ["SHOP", "TOTAL 4.20"], "rec_scores": [0.9, 0.95]}}

        class Engine:
            def predict(self, _path):
                return [Result()]

        lines = run_paddle_ocr(b"fake-image", Engine())
        self.assertEqual(lines, [OCRLine("SHOP", 0.9), OCRLine("TOTAL 4.20", 0.95)])


class ReceiptEnhancementPipelineTests(unittest.TestCase):
    def test_skips_gemini_when_paddleocr_critical_fields_are_high_confidence(self):
        class Result:
            json = {
                "res": {
                    "rec_texts": ["MYDIN MART", "14/07/2026", "TOTAL RM 15.70"],
                    "rec_scores": [0.97, 0.94, 0.99],
                }
            }

        class Engine:
            def predict(self, _path):
                return [Result()]

        with patch("app.receipt_ocr.enhance_receipt_text") as enhancer:
            result = extract_receipt(b"private-image-bytes", Engine())

        enhancer.assert_not_called()
        self.assertEqual(result["enhancementStatus"], "not_needed")

    def test_sends_only_paddleocr_text_to_enhancer_and_merges_structured_result(self):
        class Result:
            json = {
                "res": {
                    "rec_texts": ["MYD1N MART", "14/07/2026", "TOTAL RM 15.70"],
                    "rec_scores": [0.82, 0.91, 0.96],
                }
            }

        class Engine:
            def predict(self, _path):
                return [Result()]

        enhanced = {
            "merchant": "MYDIN MART",
            "transactionDate": "2026-07-14",
            "totalAmount": 15.70,
            "suggestedCategory": "Food",
            "items": [],
        }
        with patch("app.receipt_ocr.enhance_receipt_text", create=True, return_value=enhanced) as enhancer:
            result = extract_receipt(b"private-image-bytes", Engine())

        enhancer.assert_called_once_with("MYD1N MART\n14/07/2026\nTOTAL RM 15.70")
        self.assertEqual(result["merchant"], "MYDIN MART")
        self.assertEqual(result["totalAmount"], "15.70")
        self.assertEqual(result["enhancementStatus"], "applied")

    def test_falls_back_to_paddleocr_result_when_gemini_fails(self):
        class Result:
            json = {"res": {"rec_texts": ["MYDIN MART", "TOTAL RM 8.50"], "rec_scores": [0.95, 0.96]}}

        class Engine:
            def predict(self, _path):
                return [Result()]

        with patch("app.receipt_ocr.enhance_receipt_text", side_effect=RuntimeError("provider unavailable")):
            try:
                result = extract_receipt(b"private-image-bytes", Engine())
            except RuntimeError as error:
                self.fail(f"Gemini failure escaped the receipt pipeline: {error}")

        self.assertEqual(result["merchant"], "MYDIN MART")
        self.assertEqual(result["totalAmount"], "8.50")
        self.assertEqual(result["enhancementStatus"], "failed")

    def test_flags_missing_critical_fields_for_retake_or_manual_correction(self):
        class Result:
            json = {"res": {"rec_texts": ["THANK YOU"], "rec_scores": [0.61]}}

        class Engine:
            def predict(self, _path):
                return [Result()]

        with patch("app.receipt_ocr.enhance_receipt_text", return_value=None):
            result = extract_receipt(b"private-image-bytes", Engine())

        self.assertIn("reviewRequired", result)
        self.assertTrue(result["reviewRequired"])
        self.assertIn("Merchant was not detected.", result["reviewWarnings"])
        self.assertIn("Receipt date was not detected.", result["reviewWarnings"])
        self.assertIn("Total amount was not detected.", result["reviewWarnings"])

    def test_flags_low_confidence_critical_fields_even_after_text_cleanup(self):
        class Result:
            json = {
                "res": {
                    "rec_texts": ["MYD1N MART", "14/07/2026", "TOTAL RM 15.70"],
                    "rec_scores": [0.62, 0.94, 0.97],
                }
            }

        class Engine:
            def predict(self, _path):
                return [Result()]

        enhanced = {
            "merchant": "MYDIN MART",
            "transactionDate": "2026-07-14",
            "totalAmount": 15.70,
            "suggestedCategory": "Food",
            "items": [],
        }
        with patch("app.receipt_ocr.enhance_receipt_text", return_value=enhanced):
            result = extract_receipt(b"private-image-bytes", Engine())

        self.assertTrue(result["reviewRequired"])
        self.assertIn("Merchant may be inaccurate.", result["reviewWarnings"])


class GeminiReceiptCleanupTests(unittest.TestCase):
    def test_keeps_gemini_client_alive_until_generation_finishes(self):
        class Models:
            def __init__(self, owner):
                self.owner = owner

            def generate_content(self, **_kwargs):
                if self.owner() is None:
                    raise RuntimeError("Gemini client was closed before generation.")
                return SimpleNamespace(parsed={
                    "merchant": "MYDIN MART",
                    "transactionDate": None,
                    "totalAmount": 15.70,
                    "suggestedCategory": "Food",
                    "items": [],
                })

        class Client:
            @property
            def models(self):
                return Models(weakref.ref(self))

        with (
            patch.object(receipt_cleanup, "GEMINI_API_KEY", "test-key"),
            patch.object(receipt_cleanup, "_gemini_client", side_effect=Client),
        ):
            try:
                result = receipt_cleanup.enhance_receipt_text("MYDIN MART\nTOTAL RM 15.70")
            except RuntimeError as error:
                self.fail(str(error))

        self.assertEqual(result["merchant"], "MYDIN MART")

    def test_response_schema_uses_only_fields_supported_by_gemini_sdk(self):
        from google.genai import _transformers

        try:
            _transformers.t_schema(None, receipt_cleanup.ReceiptCleanupResult)
        except Exception as error:
            self.fail(f"Gemini SDK rejected the receipt response schema: {error}")

    def test_configures_a_short_timeout_for_mobile_scan_fallback(self):
        with (
            patch.object(receipt_cleanup, "GEMINI_API_KEY", "test-key"),
            patch("google.genai.Client") as client_constructor,
        ):
            receipt_cleanup._gemini_client()

        client_constructor.assert_called_once_with(
            api_key="test-key",
            http_options={"timeout": 10_000},
        )

    def test_requests_structured_fields_using_ocr_text_only(self):
        calls = []

        class Models:
            def generate_content(self, **kwargs):
                calls.append(kwargs)
                return SimpleNamespace(parsed={
                    "merchant": "MYDIN MART",
                    "transactionDate": "2026-07-14",
                    "totalAmount": 15.70,
                    "suggestedCategory": "Food",
                    "items": [],
                })

        client = SimpleNamespace(models=Models())
        with (
            patch.object(receipt_cleanup, "GEMINI_API_KEY", "test-key", create=True),
            patch.object(receipt_cleanup, "_gemini_client", return_value=client, create=True),
        ):
            result = receipt_cleanup.enhance_receipt_text("MYD1N MART\nTOTAL RM 15.70")

        self.assertIsNotNone(result)
        self.assertEqual(result["merchant"], "MYDIN MART")
        self.assertEqual(calls[0]["contents"], "MYD1N MART\nTOTAL RM 15.70")
        self.assertEqual(calls[0]["config"]["response_mime_type"], "application/json")
        self.assertIn("response_schema", calls[0]["config"])


if __name__ == "__main__":
    unittest.main()
