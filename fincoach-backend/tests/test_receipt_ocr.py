import unittest
import weakref
from types import SimpleNamespace
from unittest.mock import Mock, patch

import cv2
import numpy as np

from app import receipt_cleanup
from app.receipt_ocr import (
    OCRLine,
    _prepare_ocr_image,
    extract_receipt,
    get_ocr_engine,
    parse_receipt,
    run_paddle_ocr,
)


def _jpeg_bytes(width: int = 640, height: int = 480) -> bytes:
    image = np.full((height, width, 3), 255, dtype=np.uint8)
    cv2.putText(image, "TOTAL RM 15.70", (20, height // 2), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 0), 2)
    encoded, buffer = cv2.imencode(".jpg", image)
    if not encoded:
        raise RuntimeError("Test image could not be encoded.")
    return buffer.tobytes()


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

    def test_does_not_guess_total_from_unlabelled_amounts(self):
        result = parse_receipt(
            [OCRLine("KEDAI MAKAN", 0.9), OCRLine("NASI AYAM 8.50", 0.85), OCRLine("10.00", 0.8)]
        )
        self.assertEqual(result["totalAmount"], "")
        self.assertEqual(result["suggestedCategory"], "Food")

    def test_returns_editable_empty_fields_instead_of_inventing_values(self):
        result = parse_receipt([OCRLine("THANK YOU", 0.7)])
        self.assertEqual(result["totalAmount"], "")
        self.assertEqual(result["transactionDate"], "")
        self.assertEqual(result["suggestedCategory"], "")


class ReconstructedRowTests(unittest.TestCase):
    def test_merges_description_and_price_boxes_into_one_row(self):
        class Result:
            json = {
                "res": {
                    "rec_texts": ["Vt Pep Mocha", "4.95", "Total", "$4.95"],
                    "rec_scores": [0.98, 0.99, 0.98, 0.99],
                    "rec_boxes": [
                        [40, 300, 200, 330],
                        [400, 302, 470, 330],
                        [40, 460, 120, 488],
                        [400, 462, 470, 488],
                    ],
                }
            }

        class Engine:
            def predict(self, _image):
                return [Result()]

        lines = run_paddle_ocr(_jpeg_bytes(), Engine())
        self.assertEqual(
            [line.text for line in lines],
            ["Vt Pep Mocha 4.95", "Total $4.95"],
        )

    def test_total_and_items_survive_split_starbucks_layout(self):
        lines = [
            OCRLine("STARBUCKS Store #10208", 0.98),
            OCRLine("12/07/2014 06:43 PM", 0.99),
            OCRLine("Vt Pep Mocha 4.95", 0.98),
            OCRLine("Sbux Card 4.95", 0.96),
            OCRLine("Subtotal $4.95", 0.99),
            OCRLine("Total $4.95", 0.99),
            OCRLine("Change Due $0.00", 0.96),
            OCRLine("SBUX Card x3228 New Balance: 37.45", 0.98),
        ]
        result = parse_receipt(lines)
        self.assertEqual(result["merchant"], "STARBUCKS Store #10208")
        self.assertEqual(result["totalAmount"], "4.95")
        self.assertEqual(
            [item["description"] for item in result["items"]], ["Vt Pep Mocha"]
        )
        self.assertEqual(result["transactionDate"], "2014-07-12")


class MultilingualLayoutTests(unittest.TestCase):
    def test_malay_jumlah_is_the_total_not_an_item(self):
        result = parse_receipt([
            OCRLine("KEDAI RUNCIT", 0.95),
            OCRLine("Beras 5kg 25.00", 0.9),
            OCRLine("Gula 3.50", 0.9),
            OCRLine("Jumlah 28.50", 0.95),
        ])
        self.assertEqual(result["totalAmount"], "28.50")
        self.assertEqual(
            [item["description"] for item in result["items"]], ["Beras 5kg", "Gula"]
        )

    def test_excludes_ewallet_and_tender_lines_from_items(self):
        result = parse_receipt([
            OCRLine("99 SPEEDMART", 0.95),
            OCRLine("Air Mineral 2.00", 0.9),
            OCRLine("Roti 3.00", 0.9),
            OCRLine("GrabPay 5.00", 0.9),
            OCRLine("Total 5.00", 0.95),
        ])
        self.assertEqual(result["totalAmount"], "5.00")
        self.assertEqual(
            [item["description"] for item in result["items"]], ["Air Mineral", "Roti"]
        )

    def test_malay_subtotal_and_grand_total_variants(self):
        result = parse_receipt([
            OCRLine("RESTORAN SEDAP", 0.95),
            OCRLine("Nasi 10.00", 0.9),
            OCRLine("Ayam 20.00", 0.9),
            OCRLine("Jumlah Kecil 30.00", 0.95),
            OCRLine("Jumlah Besar 30.00", 0.95),
            OCRLine("Tunai 50.00", 0.9),
            OCRLine("Baki 20.00", 0.9),
        ])
        self.assertEqual(result["totalAmount"], "30.00")
        self.assertEqual(
            [item["description"] for item in result["items"]], ["Nasi", "Ayam"]
        )


class PaddleAdapterTests(unittest.TestCase):
    def test_downscales_large_camera_image_before_cpu_inference(self):
        prepared, original_size = _prepare_ocr_image(
            _jpeg_bytes(width=3024, height=4032),
            max_side=1600,
        )

        self.assertEqual(original_size, (3024, 4032))
        self.assertEqual((prepared.shape[1], prepared.shape[0]), (1200, 1600))

    def test_uses_configured_dynamic_engine_for_arm64(self):
        paddleocr_module = SimpleNamespace(PaddleOCR=Mock(return_value=object()))
        get_ocr_engine.cache_clear()

        try:
            with (
                patch.dict("sys.modules", {"paddleocr": paddleocr_module}),
                patch.dict(
                    "os.environ",
                    {
                        "PADDLE_OCR_ENGINE": "paddle_dynamic",
                        "PADDLE_OCR_MAX_SIDE": "1600",
                        "PADDLE_OCR_CPU_THREADS": "4",
                    },
                    clear=False,
                ),
            ):
                get_ocr_engine()
        finally:
            get_ocr_engine.cache_clear()

        paddleocr_module.PaddleOCR.assert_called_once()
        self.assertEqual(
            paddleocr_module.PaddleOCR.call_args.kwargs["engine"],
            "paddle_dynamic",
        )
        self.assertEqual(
            paddleocr_module.PaddleOCR.call_args.kwargs["text_det_limit_side_len"],
            1600,
        )
        self.assertEqual(
            paddleocr_module.PaddleOCR.call_args.kwargs["text_det_limit_type"],
            "max",
        )
        self.assertEqual(
            paddleocr_module.PaddleOCR.call_args.kwargs["cpu_threads"],
            4,
        )

    def test_normalizes_v3_rec_texts_and_scores(self):
        class Result:
            json = {"res": {"rec_texts": ["SHOP", "TOTAL 4.20"], "rec_scores": [0.9, 0.95]}}

        class Engine:
            def predict(self, image):
                self.image = image
                return [Result()]

        engine = Engine()
        lines = run_paddle_ocr(_jpeg_bytes(), engine)

        self.assertEqual(lines, [OCRLine("SHOP", 0.9), OCRLine("TOTAL 4.20", 0.95)])
        self.assertIsInstance(engine.image, np.ndarray)


class ReceiptEnhancementPipelineTests(unittest.TestCase):
    def run_pipeline(self, payload=None, error=None, confidence=0.96):
        lines = [OCRLine("MYD1N MART", confidence), OCRLine("12 Mar 2018", .94), OCRLine("TOTAL 6O.OO", .98)]
        image = _jpeg_bytes()
        with patch("app.receipt_ocr.run_paddle_ocr", return_value=lines), patch("app.receipt_ocr.verify_receipt_image", return_value=payload, side_effect=error) as verifier, patch("app.receipt_ocr.classify_category", return_value=("Food", .7, "test")):
            result = extract_receipt(image)
        verifier.assert_called_once_with(image, lines)
        return result

    def test_high_confidence_correction_runs_before_parser(self):
        result = self.run_pipeline({"confirmedLineIds": [1], "corrections": [{"lineId": 0, "correctedText": "MYDIN MART"}, {"lineId": 2, "correctedText": "TOTAL 60.00"}]})
        self.assertEqual(result["merchant"], "MYDIN MART")
        self.assertEqual(result["totalAmount"], "60.00")
        self.assertEqual(result["transactionDate"], "2018-03-12")
        self.assertEqual(result["rawLines"][2], "TOTAL 6O.OO")
        self.assertEqual(result["confidence"]["totalAmount"], .98)
        self.assertEqual(result["verificationStatus"], "verified")
        self.assertTrue(result["reviewRequired"])

    def test_failure_and_missing_key_preserve_originals(self):
        for payload, error, status in ((None, None, "not_configured"), (None, TimeoutError(), "failed"), ({"nonsense": True}, None, "failed")):
            result = self.run_pipeline(payload, error)
            self.assertEqual(result["merchant"], "MYD1N MART")
            self.assertEqual(result["verificationStatus"], status)
            self.assertTrue(result["reviewRequired"])

    def test_low_confidence_confirmed_text_is_not_flagged_inaccurate(self):
        result = self.run_pipeline({"confirmedLineIds": [0, 1, 2]}, confidence=.1)
        self.assertNotIn("Merchant has not been visually verified.", result["reviewWarnings"])
        self.assertEqual(result["confidence"]["merchant"], .1)

    def test_missing_critical_fields_still_warn(self):
        result = self.run_pipeline({"confirmedLineIds": [0, 1, 2]})
        self.assertIn("Total amount was not detected.", result["reviewWarnings"])


class ReceiptCleanupTests(unittest.TestCase):
    def test_returns_none_when_no_provider(self):
        with patch.object(receipt_cleanup.llm, "generate_extraction_json", return_value=None):
            self.assertIsNone(receipt_cleanup.enhance_receipt_text("MYDIN\nTOTAL 5.00"))

    def test_returns_none_for_blank_text_without_calling_llm(self):
        with patch.object(receipt_cleanup.llm, "generate_extraction_json") as gen:
            self.assertIsNone(receipt_cleanup.enhance_receipt_text("   "))
        gen.assert_not_called()

    def test_parses_json_and_returns_aliased_fields(self):
        payload = (
            '{"merchant":"MYDIN MART","transactionDate":"2026-07-14",'
            '"totalAmount":15.7,"suggestedCategory":"Food","items":[]}'
        )
        with patch.object(receipt_cleanup.llm, "generate_extraction_json", return_value=payload):
            result = receipt_cleanup.enhance_receipt_text("MYD1N MART\nTOTAL RM 15.70")
        self.assertEqual(result["merchant"], "MYDIN MART")
        self.assertEqual(result["totalAmount"], 15.7)
        self.assertEqual(result["transactionDate"], "2026-07-14")

    def test_returns_none_on_unparseable_reply(self):
        with patch.object(receipt_cleanup.llm, "generate_extraction_json", return_value="sorry, no json"):
            self.assertIsNone(receipt_cleanup.enhance_receipt_text("MYDIN\nTOTAL 5.00"))

    def test_sends_ocr_text_and_receipt_system_prompt(self):
        captured = {}

        def fake(prompt, *, system_prompt, timeout_seconds):
            captured["prompt"] = prompt
            captured["system"] = system_prompt
            return '{"merchant":"X","totalAmount":5.0,"items":[]}'

        with patch.object(receipt_cleanup.llm, "generate_extraction_json", side_effect=fake):
            receipt_cleanup.enhance_receipt_text("MYD1N MART\nTOTAL RM 15.70")
        self.assertEqual(captured["prompt"], "MYD1N MART\nTOTAL RM 15.70")
        self.assertIn("JSON", captured["system"])


if __name__ == "__main__":
    unittest.main()
