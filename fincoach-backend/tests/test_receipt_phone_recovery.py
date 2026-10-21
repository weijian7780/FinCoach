"""Regression coverage for phone-photo layouts, independent of one merchant."""
import io
import unittest
from datetime import date

from PIL import Image

from app.receipt_ocr import OCRLine, _prepare_ocr_image, parse_receipt
from app.receipt_vision import merge_corrections


def rows(*texts):
    return [OCRLine(text, .98) for text in texts]


class PhoneReceiptParserTests(unittest.TestCase):
    def test_month_first_timestamps_are_dates_and_never_priced_items(self):
        for stamp in ("Oct 04 2026,12:53 PM", "October 04, 2026 12:53 PM",
                      "oct 4 2026, 12:53 PM", "Oct 04 2026.12:53 PM"):
            with self.subTest(stamp=stamp):
                result = parse_receipt(rows("COFFEE SHOP", stamp,
                    "Latte 13.11", "TOTAL 13.90"), today=date(2026, 10, 4))
                self.assertEqual(result["transactionDate"], "2026-10-04")
                self.assertEqual([item["amount"] for item in result["items"]], [13.11])

    def test_invalid_or_future_month_first_timestamps_are_not_products(self):
        for stamp in ("Feb 31 2026,12:53 PM", "Oct 05 2026,12:53 PM"):
            with self.subTest(stamp=stamp):
                result = parse_receipt(rows("COFFEE SHOP", stamp,
                    "Latte 13.11", "TOTAL 13.90"), today=date(2026, 10, 4))
                self.assertEqual(result["transactionDate"], "")
                self.assertEqual([item["amount"] for item in result["items"]], [13.11])

    def test_wrapped_tax_inclusive_total_uses_its_printed_amount(self):
        result = parse_receipt(rows("COFFEE SHOP", "Latte 13.11",
            "SubTotal 13.11", "6% SST,if applicable 0.79", "Rounding Adjustment 0.00",
            "Total(Incl. 6% SST,", "if applicable) 13.90", "maybank payment card 13.90"))
        self.assertEqual(result["totalAmount"], "13.90")
        self.assertIn("Total(Incl. 6% SST,", result["fieldEvidence"]["totalAmount"])
        self.assertIn("if applicable) 13.90", result["fieldEvidence"]["totalAmount"])
        self.assertEqual(len(result["items"]), 1)

    def test_total_label_and_standalone_amount_are_bounded_by_next_summary(self):
        result = parse_receipt(rows("SHOP", "TOTAL", "13.90", "CASH 20.00"))
        self.assertEqual(result["totalAmount"], "13.90")
        for text in ("CASH 20.00", "SST 0.79", "Subtotal 13.11", "Cake 13.90"):
            with self.subTest(text=text):
                result = parse_receipt(rows("SHOP", "TOTAL", text, "20.00"))
                self.assertEqual(result["totalAmount"], "")

    def test_unpriced_wrapped_details_stay_with_the_product(self):
        result = parse_receipt(rows("COFFEE SHOP", "Oct 04 2026,12:53 PM",
            "1 Latte, Regular, Cold, 13.11", "Signature Milk, House Blend,",
            "Normal Sugar", "SubTotal 13.11", "TOTAL 13.90"), today=date(2026, 10, 4))
        self.assertEqual(len(result["items"]), 1)
        self.assertEqual(result["items"][0]["modifiers"],
                         ["Signature Milk, House Blend,", "Normal Sugar"])

    def test_column_heading_does_not_end_products(self):
        result = parse_receipt(rows("KEDAI MAKAN", "QTY ITEM TOTAL",
                                    "1 Nasi 17.88", "1 Taro Pie 5.24",
                                    "Subtotal 23.12", "TOTAL 23.12"))
        self.assertEqual([item["amount"] for item in result["items"]], [17.88, 5.24])

    def test_collapsed_date_and_column_header_still_preserve_products(self):
        result = parse_receipt(rows("KEDAI MAKAN",
            "ORD #59 -CS0 #33-03/10/2026 QTY ITEM 17:16:03 TOTAL",
            "1 Nasi 17.88", "1 Pie 5.24", "Subtotal 23.12", "TOTAL 23.12"))
        self.assertEqual(result["transactionDate"], "2026-10-03")
        self.assertEqual(len(result["items"]), 2)

    def test_column_header_with_dotted_date_is_not_a_monetary_total(self):
        result = parse_receipt(rows("HOTEL EXAMPLE", "DATE 03.10.2026 QTY ITEM TOTAL",
                                    "Breakfast 10.00", "TOTAL 10.00"))
        self.assertEqual(result["merchant"], "HOTEL EXAMPLE")
        self.assertEqual(result["transactionDate"], "2026-10-03")
        self.assertEqual(len(result["items"]), 1)

    def test_purchase_date_outranks_payment_date_across_midnight(self):
        result = parse_receipt(rows("CAFE", "ORDER 02/10/2026 23:59",
            "TOTAL 5.00", "Cashless transaction information",
            "DATE & TIME 03/10/2026 00:01"))
        self.assertEqual(result["transactionDate"], "2026-10-02")

    def test_conflicting_purchase_dates_remain_empty(self):
        result = parse_receipt(rows("CAFE", "DATE 01/10/2026",
                                    "DATE 02/10/2026", "TOTAL 5.00"))
        self.assertEqual(result["transactionDate"], "")
        self.assertTrue(result["parserWarnings"])

    def test_complete_date_survives_adjacent_reference_and_invalid_candidate(self):
        for text in ("CS0 #33-03/10/2026", "31/02/2026 DATE 03/10/2026",
                     "REF 99-08/11/2025 DATE 03/10/2026"):
            with self.subTest(text=text):
                result = parse_receipt(rows("SHOP", text, "TOTAL 5.00"))
                self.assertEqual(result["transactionDate"], "2026-10-03")

    def test_future_and_expiry_dates_do_not_become_purchase_date(self):
        result = parse_receipt(rows("SHOP", "EXP DATE 01/01/2029",
                                    "DATE 03/10/2026", "TOTAL 5.00"),
                               today=date(2026, 10, 3))
        self.assertEqual(result["transactionDate"], "2026-10-03")
        future = parse_receipt(rows("SHOP", "DATE 04/10/2026", "TOTAL 5.00"),
                               today=date(2026, 10, 3))
        self.assertEqual(future["transactionDate"], "")

    def test_rounded_card_charge_is_final_total(self):
        result = parse_receipt(rows("RESTORAN SEDAP", "1 Nasi 17.88",
            "1 Pie 5.24", "Subtotal 23.12", "Eat-In Total (incl Tax) 24.51",
            "Rounding Adjust - 0.01", "Visa 24.50", "TOTAL 6% Service Tax 1.39",
            "Cashless transaction information", "TYPE SALE", "AMOUNT RM 24.50",
            "APPROVED"))
        self.assertEqual(result["totalAmount"], "24.50")
        self.assertEqual(len(result["items"]), 2)

    def test_missing_rounding_sign_is_not_needed_to_read_printed_payment(self):
        result = parse_receipt(rows("CAFE", "Coffee 9.99", "TOTAL 9.99",
                                    "Rounding 0.01", "Mastercard 10.00"))
        self.assertEqual(result["totalAmount"], "10.00")

    def test_two_printed_totals_can_be_reconciled_across_rounding(self):
        for payment in ([], ["Visa 24.50"]):
            with self.subTest(payment=payment):
                result = parse_receipt(rows("CAFE", "Food 23.12", "TOTAL 24.51",
                                            "Rounding - 0.01", "TOTAL 24.50", *payment))
                self.assertEqual(result["totalAmount"], "24.50")

    def test_modifiers_are_preserved_without_extra_charges(self):
        result = parse_receipt(rows("CAFE", "1 Meal 17.88", "1 M Coke",
                                    "NO Ice", "1 No Add-On", "TOTAL 17.88"))
        self.assertEqual(len(result["items"]), 1)
        self.assertEqual(result["items"][0]["modifiers"], ["M Coke", "NO Ice", "No Add-On"])

    def test_wrapped_product_rows_attach_to_the_following_price_row(self):
        result = parse_receipt(rows("CAFE", "Item Qty Total", "SR 1001 Meat + 3 Vege",
            "$7.10 1 $7.10", "SR 1002 Vegetable", "$1.10 1 $1.10",
            "TOTAL 8.20", "Follow us on Facebook"))
        self.assertEqual([item["amount"] for item in result["items"]], [7.1, 1.1])
        self.assertEqual(result["items"][0]["description"], "SR 1001 Meat + 3 Vege")
        self.assertEqual(result["suggestedCategory"], "Food")

    def test_footer_words_do_not_drive_category(self):
        result = parse_receipt(rows("RETAIL SHOP", "USB Cable 5.00", "TOTAL 5.00",
                                    "Follow us on Facebook"))
        self.assertEqual(result["suggestedCategory"], "")

    def test_conflicting_total_and_charge_require_review(self):
        result = parse_receipt(rows("CAFE", "Coffee 10.00", "TOTAL 10.00",
                                    "Visa 20.00"))
        self.assertEqual(result["totalAmount"], "")
        self.assertTrue(result["parserWarnings"])

    def test_explicit_rounding_sign_cannot_be_ignored(self):
        result = parse_receipt(rows("CAFE", "TOTAL 10.00", "Rounding - 0.01", "Visa 10.01"))
        self.assertEqual(result["totalAmount"], "")
        self.assertTrue(result["parserWarnings"])

    def test_cash_tender_and_change_are_not_the_total(self):
        result = parse_receipt(rows("SHOP", "Bread 8.10", "TOTAL 8.10",
                                    "CASH 20.00", "CHANGE 11.90"))
        self.assertEqual(result["totalAmount"], "8.10")
        self.assertEqual(len(result["items"]), 1)

    def test_largest_product_price_is_not_an_invented_total(self):
        result = parse_receipt(rows("SHOP", "Bread 3.00", "Rice 25.00"))
        self.assertEqual(result["totalAmount"], "")

    def test_trade_branch_beyond_eight_header_rows_is_preferred(self):
        result = parse_receipt(rows("Your order number is", "159",
            "EXAMPLE RESTAURANTS SDN BHD", "(12345-M)", "Licensee of Good Food",
            "Level 6 Office Building", "No.3 Jalan Example", "City",
            "(CP ID NO: 123456)", "Good Food Bay Branch (#394)",
            "TAX INVOICE", "03/10/2026", "Nasi 5.00", "TOTAL 5.00"))
        self.assertEqual(result["merchant"], "Good Food Bay Branch (#394)")

    def test_nonreceipt_text_alone_does_not_create_a_merchant(self):
        result = parse_receipt(rows("PHONE MODEL 200"))
        self.assertEqual(result["merchant"], "")
        self.assertEqual(result["suggestedCategory"], "")

    def test_multiline_corrections_parse_as_separate_rows(self):
        original = rows("SCRAMBLED")
        merged = merge_corrections(original, {"corrections": [{"lineId": 0,
            "correctedText": "CAFE\nCoffee 3.00\nCake 2.00\nTOTAL 5.00"}]})
        result = parse_receipt([OCRLine(r["finalText"], r["ocrConfidence"])
                                for r in merged["lines"]])
        self.assertEqual(result["merchant"], "CAFE")
        self.assertEqual(result["totalAmount"], "5.00")
        self.assertEqual(len(result["items"]), 2)


class PhoneImagePreparationTests(unittest.TestCase):
    def test_exif_orientation_is_normalized_once(self):
        image = Image.new("RGB", (80, 40))
        exif = Image.Exif()
        exif[274] = 6
        encoded = io.BytesIO()
        image.save(encoded, "JPEG", exif=exif)
        prepared, original = _prepare_ocr_image(encoded.getvalue())
        self.assertEqual(original, (80, 40))
        self.assertEqual((prepared.shape[1], prepared.shape[0]), (40, 80))

    def test_all_exif_transform_dimensions_are_supported(self):
        for orientation in range(1, 9):
            with self.subTest(orientation=orientation):
                image = Image.new("RGB", (80, 40))
                exif = Image.Exif(); exif[274] = orientation
                encoded = io.BytesIO(); image.save(encoded, "JPEG", exif=exif)
                prepared, _ = _prepare_ocr_image(encoded.getvalue())
                expected = (40, 80) if orientation >= 5 else (80, 40)
                self.assertEqual((prepared.shape[1], prepared.shape[0]), expected)
