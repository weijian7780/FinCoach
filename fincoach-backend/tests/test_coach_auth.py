import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from fastapi import HTTPException


class CoachAuthTests(unittest.TestCase):
    def test_rejects_missing_and_malformed_bearer_headers(self):
        from app.auth import require_authenticated_user

        for header in (None, "", "Basic abc", "Bearer", "Bearer   ", "Bearer one two"):
            with self.subTest(header=header):
                with self.assertRaises(HTTPException) as caught:
                    require_authenticated_user(header)
                self.assertEqual(caught.exception.status_code, 401)

    def test_returns_server_verified_user_from_get_user(self):
        from app.auth import require_authenticated_user

        auth = SimpleNamespace(
            get_user=lambda token: SimpleNamespace(
                user=SimpleNamespace(id="user-1", is_anonymous=False)
            )
        )
        # A verified token also needs the server-side active-account check.
        client = MagicMock()
        client.auth = auth
        client.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value.data = {"status": "active"}
        with (patch("app.auth.get_supabase", return_value=client),
              patch("app.config.ACCOUNT_ACCESS_ENFORCED", True)):
            user = require_authenticated_user("Bearer valid-token")

        self.assertEqual(user.user_id, "user-1")
        self.assertEqual(user.token, "valid-token")
        client.table.assert_called_once_with("account_access")

    def test_rejects_invalid_claims_without_leaking_error(self):
        from app.auth import require_authenticated_user

        cases = [
            SimpleNamespace(get_user=lambda token: SimpleNamespace(user=None)),
            SimpleNamespace(
                get_user=lambda token: SimpleNamespace(
                    user=SimpleNamespace(id="user-1", is_anonymous=True)
                )
            ),
            SimpleNamespace(get_user=lambda token: (_ for _ in ()).throw(RuntimeError("secret"))),
        ]
        for auth in cases:
            with self.subTest(auth=auth):
                with patch("app.auth.get_supabase", return_value=SimpleNamespace(auth=auth)):
                    with self.assertRaises(HTTPException) as caught:
                        require_authenticated_user("Bearer invalid-token")
                self.assertEqual(caught.exception.status_code, 401)
                self.assertEqual(caught.exception.detail, "Authentication required.")


class UserSupabaseClientTests(unittest.TestCase):
    def test_user_client_uses_publishable_key_and_bearer_header(self):
        from app.supabase_client import get_user_supabase

        with (
            patch("app.supabase_client.SUPABASE_URL", "https://project.supabase.co"),
            patch("app.supabase_client.SUPABASE_PUBLISHABLE_KEY", "publishable-key"),
            patch("app.supabase_client.create_client", return_value="client") as constructor,
        ):
            result = get_user_supabase("access-token")

        self.assertEqual(result, "client")
        url, key, options = constructor.call_args.args
        self.assertEqual(url, "https://project.supabase.co")
        self.assertEqual(key, "publishable-key")
        self.assertEqual(options.headers["Authorization"], "Bearer access-token")
        self.assertFalse(options.auto_refresh_token)
        self.assertFalse(options.persist_session)

    def test_user_client_rejects_missing_server_configuration(self):
        from app.supabase_client import get_user_supabase

        with (
            patch("app.supabase_client.SUPABASE_URL", ""),
            patch("app.supabase_client.SUPABASE_PUBLISHABLE_KEY", ""),
        ):
            with self.assertRaises(RuntimeError):
                get_user_supabase("access-token")


if __name__ == "__main__":
    unittest.main()
