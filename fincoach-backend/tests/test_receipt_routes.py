import asyncio
from io import BytesIO
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from PIL import Image

from app.receipt_routes import verify_access_token
from app.main import app


def png_bytes(width: int, height: int) -> bytes:
    image = Image.new("RGB", (width, height), "white")
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


class ReceiptRouteAuthTests(unittest.TestCase):
    def test_rejects_missing_bearer_token(self):
        with self.assertRaises(HTTPException) as caught:
            verify_access_token(None)
        self.assertEqual(caught.exception.status_code, 401)

    def test_verifies_supabase_token_and_returns_user_id(self):
        client = SimpleNamespace(
            auth=SimpleNamespace(
                get_user=lambda token: SimpleNamespace(
                    user=SimpleNamespace(id="user-1", is_anonymous=False)
                )
            )
        )
        # Shared authentication now checks account access after verifying the JWT.
        client.table = MagicMock()
        client.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = SimpleNamespace(data={"status": "active"})
        with patch("app.auth.get_supabase", return_value=client):
            self.assertEqual(verify_access_token("Bearer valid-token"), "user-1")


class ReceiptImageValidationTests(unittest.TestCase):
    def test_rejects_a_malformed_matching_image_before_ocr(self):
        from app.receipt_routes import router

        isolated_app = FastAPI()
        isolated_app.include_router(router)
        with (
            patch("app.receipt_routes.verify_access_token", return_value="user-1"),
            patch("app.receipt_routes.extract_receipt") as extract,
        ):
            response = TestClient(isolated_app, raise_server_exceptions=False).post(
                "/receipts/extract",
                headers={"Authorization": "Bearer valid-token"},
                files={"file": ("receipt.png", png_bytes(1, 1)[:-8], "image/png")},
            )

        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json(), {"detail": "Receipt image is invalid or unsupported."})
        extract.assert_not_called()

    def test_accepts_a_small_matching_image_and_starts_ocr(self):
        from app.receipt_routes import router

        isolated_app = FastAPI()
        isolated_app.include_router(router)
        image_bytes = png_bytes(1, 1)
        with (
            patch("app.receipt_routes.verify_access_token", return_value="user-1"),
            patch(
                "app.receipt_routes.extract_receipt",
                return_value={"merchant": "Campus Mart"},
            ) as extract,
        ):
            response = TestClient(isolated_app).post(
                "/receipts/extract",
                headers={"Authorization": "Bearer valid-token"},
                files={"file": ("receipt.png", image_bytes, "image/png")},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"merchant": "Campus Mart"})
        extract.assert_called_once_with(image_bytes)

    def test_rejects_an_image_that_exceeds_the_pixel_limit_before_ocr(self):
        from app.receipt_routes import router

        isolated_app = FastAPI()
        isolated_app.include_router(router)
        with (
            patch("app.receipt_routes.MAX_RECEIPT_PIXELS", 1, create=True),
            patch("app.receipt_routes.verify_access_token", return_value="user-1"),
            patch("app.receipt_routes.extract_receipt") as extract,
        ):
            response = TestClient(isolated_app, raise_server_exceptions=False).post(
                "/receipts/extract",
                headers={"Authorization": "Bearer valid-token"},
                files={"file": ("receipt.png", png_bytes(2, 1), "image/png")},
            )

        self.assertEqual(response.status_code, 413)
        self.assertEqual(response.json(), {"detail": "Receipt image dimensions are too large."})
        extract.assert_not_called()

    def test_rejects_a_content_type_that_does_not_match_the_image(self):
        from app.receipt_routes import router

        isolated_app = FastAPI()
        isolated_app.include_router(router)
        with (
            patch("app.receipt_routes.verify_access_token", return_value="user-1"),
            patch("app.receipt_routes.extract_receipt") as extract,
        ):
            response = TestClient(isolated_app, raise_server_exceptions=False).post(
                "/receipts/extract",
                headers={"Authorization": "Bearer valid-token"},
                files={"file": ("receipt.png", png_bytes(1, 1), "image/jpeg")},
            )

        self.assertEqual(response.status_code, 415)
        self.assertEqual(response.json(), {"detail": "Image content does not match its declared type."})
        extract.assert_not_called()


class ReceiptWarmupTests(unittest.TestCase):
    def test_ready_is_healthy_after_all_optional_models_warm(self):
        with (
            patch("app.main.get_ocr_engine"),
            patch("app.main.warm_embeddings"),
            TestClient(app, raise_server_exceptions=False) as client,
        ):
            response = client.get("/ready")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "status": "ok",
                "components": {"ocr": "ready", "embeddings": "ready"},
            },
        )

    def test_warmup_failure_keeps_liveness_available_and_marks_readiness_degraded(self):
        with (
            patch(
                "app.main.get_ocr_engine",
                side_effect=RuntimeError("missing OCR model"),
            ),
            patch("app.main.warm_embeddings"),
            TestClient(app, raise_server_exceptions=False) as client,
        ):
            liveness = client.get("/health")
            readiness = client.get("/ready")

        self.assertEqual(liveness.status_code, 200)
        self.assertEqual(liveness.json(), {"status": "ok"})
        self.assertEqual(readiness.status_code, 503)
        self.assertEqual(
            readiness.json(),
            {
                "status": "degraded",
                "components": {"ocr": "unavailable", "embeddings": "ready"},
            },
        )

    def test_fastapi_lifespan_preloads_paddleocr_before_serving_requests(self):
        async def run_lifespan():
            with (
                patch("app.main.get_ocr_engine", create=True) as engine,
                patch("app.main.warm_embeddings", create=True),
            ):
                async with app.router.lifespan_context(app):
                    pass
                engine.assert_called_once_with()

        asyncio.run(run_lifespan())


if __name__ == "__main__":
    unittest.main()
