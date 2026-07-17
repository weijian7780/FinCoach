import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import HTTPException

from app.receipt_routes import verify_access_token
from app.main import app


class ReceiptRouteAuthTests(unittest.TestCase):
    def test_rejects_missing_bearer_token(self):
        with self.assertRaises(HTTPException) as caught:
            verify_access_token(None)
        self.assertEqual(caught.exception.status_code, 401)

    def test_verifies_supabase_token_and_returns_user_id(self):
        client = SimpleNamespace(
            auth=SimpleNamespace(
                get_claims=lambda token: SimpleNamespace(
                    claims={"sub": "user-1", "role": "authenticated"}
                )
            )
        )
        with patch("app.auth.get_supabase", return_value=client):
            self.assertEqual(verify_access_token("Bearer valid-token"), "user-1")


class ReceiptWarmupTests(unittest.TestCase):
    def test_fastapi_lifespan_preloads_paddleocr_before_serving_requests(self):
        async def run_lifespan():
            with patch("app.main.get_ocr_engine", create=True) as engine:
                async with app.router.lifespan_context(app):
                    pass
                engine.assert_called_once_with()

        asyncio.run(run_lifespan())


if __name__ == "__main__":
    unittest.main()
