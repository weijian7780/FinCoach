import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app import config, receipt_category
from app.receipt_category import classify_category


class CategoryClassifierTests(unittest.TestCase):
    def test_uses_jev_choice_when_confident(self):
        with (
            patch.object(config, "TYPESAFE_CATEGORY_ENABLED", True),
            patch.object(config, "TYPESAFE_API_KEY", "key"),
            patch.object(config, "TYPESAFE_CATEGORY_MIN_CONFIDENCE", 0.6),
            patch.object(receipt_category, "_jev_classify", return_value=("Food", 0.96)),
        ):
            self.assertEqual(
                classify_category("Starbucks", [{"description": "Vt Pep Mocha"}]),
                ("Food", 0.96, "jev"),
            )

    def test_low_confidence_jev_falls_back_to_embeddings(self):
        with (
            patch.object(config, "TYPESAFE_CATEGORY_ENABLED", True),
            patch.object(config, "TYPESAFE_API_KEY", "key"),
            patch.object(config, "TYPESAFE_CATEGORY_MIN_CONFIDENCE", 0.6),
            patch.object(config, "RECEIPT_CATEGORY_EMBED_FALLBACK", True),
            patch.object(receipt_category, "_jev_classify", return_value=("Food", 0.30)),
            patch.object(receipt_category, "_embedding_classify", return_value=("Transport", 0.51)),
        ):
            self.assertEqual(
                classify_category("Grab", [{"description": "Ride"}]),
                ("Transport", 0.51, "bge-m3"),
            )

    def test_jev_error_falls_back_to_embeddings(self):
        with (
            patch.object(config, "TYPESAFE_CATEGORY_ENABLED", True),
            patch.object(config, "TYPESAFE_API_KEY", "key"),
            patch.object(config, "RECEIPT_CATEGORY_EMBED_FALLBACK", True),
            patch.object(receipt_category, "_jev_classify", side_effect=TimeoutError("slow")),
            patch.object(receipt_category, "_embedding_classify", return_value=("Food", 0.44)),
        ):
            self.assertEqual(
                classify_category("Kopitiam", [{"description": "Kopi"}]),
                ("Food", 0.44, "bge-m3"),
            )

    def test_unavailable_when_disabled_and_no_fallback(self):
        with (
            patch.object(config, "TYPESAFE_CATEGORY_ENABLED", False),
            patch.object(config, "RECEIPT_CATEGORY_EMBED_FALLBACK", False),
        ):
            self.assertEqual(classify_category("Anywhere", []), ("", 0.0, "unavailable"))

    def test_never_raises_when_every_path_fails(self):
        with (
            patch.object(config, "TYPESAFE_CATEGORY_ENABLED", True),
            patch.object(config, "TYPESAFE_API_KEY", "key"),
            patch.object(config, "RECEIPT_CATEGORY_EMBED_FALLBACK", True),
            patch.object(receipt_category, "_jev_classify", side_effect=RuntimeError("boom")),
            patch.object(receipt_category, "_embedding_classify", side_effect=RuntimeError("no model")),
        ):
            self.assertEqual(classify_category("X", [{"description": "Y"}]), ("", 0.0, "unavailable"))

    def test_jev_classify_builds_choice_state_and_reads_answer(self):
        captured: dict = {}

        class FakeClient:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def system_one(self, **kwargs):
                captured.update(kwargs)
                return SimpleNamespace(
                    choices={"category": SimpleNamespace(choice="Food", confidence=0.9)}
                )

        def fake_choice(**kwargs):
            captured["choice_kwargs"] = kwargs
            return kwargs

        fake_sdk = SimpleNamespace(TypeSafeClient=FakeClient, Choice=fake_choice)
        with patch.dict("sys.modules", {"typesafe_sdk": fake_sdk}):
            choice, confidence = receipt_category._jev_classify(
                "Starbucks", [{"description": "Vt Pep Mocha"}]
            )

        self.assertEqual((choice, confidence), ("Food", 0.9))
        self.assertEqual(captured["state"]["merchant"], "Starbucks")
        self.assertEqual(captured["state"]["items"], ["Vt Pep Mocha"])
        self.assertIn("category", captured["questions"])
        self.assertIn("Food", captured["choice_kwargs"]["criteria"])

    def test_jev_confidence_derived_from_probabilities_when_absent(self):
        class Answer:
            choice = "Transport"
            probabilities = {"Transport": 0.7, "Food": 0.3}

        class FakeClient:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def system_one(self, **_kwargs):
                return SimpleNamespace(choices={"category": Answer()})

        fake_sdk = SimpleNamespace(TypeSafeClient=FakeClient, Choice=lambda **k: k)
        with patch.dict("sys.modules", {"typesafe_sdk": fake_sdk}):
            choice, confidence = receipt_category._jev_classify("Petronas", [])

        self.assertEqual(choice, "Transport")
        self.assertAlmostEqual(confidence, 0.7)


if __name__ == "__main__":
    unittest.main()
