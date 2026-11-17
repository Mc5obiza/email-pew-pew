import base64
import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from email import policy
from email.parser import BytesParser
from unittest.mock import Mock, patch
from urllib.parse import parse_qs, urlparse

from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from google.oauth2.credentials import Credentials
from oauthlib.oauth2.rfc6749.errors import InvalidGrantError
import pytest

from helper.gmail import _db_connection, _fernet
from main import app


pytestmark = pytest.mark.integration


class GmailRoutesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.previous_environment = os.environ.copy()
        os.environ.update(
            {
                "GMAIL_SESSION_SECRET": "test-session-secret-that-is-long-enough",
                "GMAIL_TOKEN_ENCRYPTION_KEY": Fernet.generate_key().decode(),
                "GMAIL_TOKEN_DB": os.path.join(self.temp_dir.name, "gmail.sqlite3"),
                "GMAIL_COOKIE_SECURE": "false",
                "ENV": "dev",
                "GOOGLE_CLIENT_SECRETS_FILE": os.path.join(
                    self.temp_dir.name, "client_secret.json"
                ),
                "GOOGLE_REDIRECT_URI": "http://localhost:8000/auth/gmail/callback",
            }
        )
        os.environ.pop("OAUTHLIB_INSECURE_TRANSPORT", None)
        self.client = TestClient(app, base_url="http://localhost:8000")

    def _write_client_secrets(self) -> None:
        with open(os.environ["GOOGLE_CLIENT_SECRETS_FILE"], "w", encoding="utf-8") as file:
            json.dump(
                {
                    "web": {
                        "client_id": "test-client-id",
                        "client_secret": "test-client-secret",
                        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                        "token_uri": "https://oauth2.googleapis.com/token",
                        "redirect_uris": [
                            "http://localhost:8000/auth/gmail/callback"
                        ],
                    }
                },
                file,
            )

    def tearDown(self) -> None:
        self.client.close()
        os.environ.clear()
        os.environ.update(self.previous_environment)
        self.temp_dir.cleanup()

    def test_status_creates_session_and_reports_disconnected(self) -> None:
        response = self.client.get("/auth/gmail/status")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"connected": False, "email": None})
        self.assertIn("gmail_session", response.cookies)
        self.assertEqual(
            self.client.get("/auth/gmail/status").json(),
            {"connected": False, "email": None},
        )

    def test_send_requires_connected_session(self) -> None:
        self.client.get("/auth/gmail/status")

        response = self.client.post(
            "/auth/gmail/send",
            json={
                "recipient": "recipient@example.com",
                "subject": "Internship application",
                "body": "Hello",
            },
        )

        self.assertEqual(response.status_code, 401)

    def test_login_starts_oauth_and_cancelled_callback_is_reported(self) -> None:
        self._write_client_secrets()

        login = self.client.get("/auth/gmail/login")

        self.assertEqual(login.status_code, 200)
        authorization_url = login.json()["authorization_url"]
        query = parse_qs(urlparse(authorization_url).query)
        self.assertEqual(
            set(query["scope"][0].split()),
            {
                "openid",
                "https://www.googleapis.com/auth/userinfo.email",
                "https://www.googleapis.com/auth/gmail.send",
            },
        )
        state = query["state"][0]

        callback = self.client.get(
            "/auth/gmail/callback",
            params={"error": "access_denied", "state": state},
            follow_redirects=False,
        )

        self.assertEqual(callback.status_code, 303)
        self.assertIn("gmail_error=authorization_cancelled", callback.headers["location"])

    def test_successful_callback_saves_verified_account(self) -> None:
        self._write_client_secrets()
        login = self.client.get("/auth/gmail/login")
        state = parse_qs(urlparse(login.json()["authorization_url"]).query)["state"][0]
        with _db_connection() as connection:
            stored_verifier = connection.execute(
                "SELECT code_verifier FROM gmail_oauth_states WHERE state = ?",
                (state,),
            ).fetchone()["code_verifier"]
        credentials = Mock(
            id_token="verified-id-token",
            client_id="test-client-id",
            to_json=Mock(
                return_value=json.dumps(
                    {
                        "token": "access-token",
                        "refresh_token": "refresh-token",
                        "token_uri": "https://oauth2.googleapis.com/token",
                        "client_id": "test-client-id",
                        "client_secret": "test-client-secret",
                        "scopes": ["https://www.googleapis.com/auth/gmail.send"],
                    }
                )
            ),
        )
        flow = Mock(credentials=credentials)

        def fetch_token(**kwargs: str) -> None:
            self.assertEqual(flow.code_verifier, stored_verifier)
            self.assertEqual(os.environ.get("OAUTHLIB_INSECURE_TRANSPORT"), "1")
            self.assertEqual(
                kwargs["authorization_response"].split("?", 1)[0],
                "http://localhost:8000/auth/gmail/callback",
            )

        flow.fetch_token.side_effect = fetch_token

        with (
            patch("helper.gmail.Flow.from_client_secrets_file", return_value=flow),
            patch(
                "helper.gmail.id_token.verify_oauth2_token",
                return_value={
                    "email": "sender@example.com",
                    "email_verified": True,
                },
            ),
        ):
            callback = self.client.get(
                "/auth/gmail/callback",
                params={"code": "test-code", "state": state},
                follow_redirects=False,
            )

        self.assertEqual(callback.status_code, 303)
        self.assertIn("gmail=connected", callback.headers["location"])
        self.assertNotIn("OAUTHLIB_INSECURE_TRANSPORT", os.environ)
        self.assertEqual(
            self.client.get("/auth/gmail/status").json(),
            {"connected": True, "email": "sender@example.com"},
        )

    def test_oauth_token_error_returns_readable_bad_request(self) -> None:
        self._write_client_secrets()
        login = self.client.get("/auth/gmail/login")
        state = parse_qs(urlparse(login.json()["authorization_url"]).query)["state"][0]
        flow = Mock()
        flow.fetch_token.side_effect = InvalidGrantError(
            description="Missing code verifier"
        )

        with patch("helper.gmail.Flow.from_client_secrets_file", return_value=flow):
            callback = self.client.get(
                "/auth/gmail/callback",
                params={"code": "test-code", "state": state},
            )

        self.assertEqual(callback.status_code, 400)
        self.assertIn("InvalidGrantError", callback.json()["detail"])
        self.assertIn("Missing code verifier", callback.json()["detail"])

    def test_unknown_oauth_state_returns_bad_request(self) -> None:
        self.client.get("/auth/gmail/status")

        callback = self.client.get(
            "/auth/gmail/callback",
            params={"code": "test-code", "state": "unknown-state"},
        )

        self.assertEqual(callback.status_code, 400)
        self.assertEqual(callback.json(), {"detail": "Invalid or expired OAuth state"})

    def test_local_http_oauth_is_rejected_outside_dev_environment(self) -> None:
        self._write_client_secrets()
        login = self.client.get("/auth/gmail/login")
        state = parse_qs(urlparse(login.json()["authorization_url"]).query)["state"][0]
        os.environ["ENV"] = "production"

        callback = self.client.get(
            "/auth/gmail/callback",
            params={"code": "test-code", "state": state},
        )

        self.assertEqual(callback.status_code, 503)
        self.assertNotIn("OAUTHLIB_INSECURE_TRANSPORT", os.environ)

    def test_send_uses_gmail_api_and_confirms_message_id(self) -> None:
        self.client.get("/auth/gmail/status")
        session_id = self.client.cookies["gmail_session"].split(".", 1)[0]
        credentials = Credentials(
            token="access-token",
            refresh_token="refresh-token",
            token_uri="https://oauth2.googleapis.com/token",
            client_id="client-id",
            client_secret="client-secret",
            scopes=["https://www.googleapis.com/auth/gmail.send"],
            expiry=datetime.now(timezone.utc) + timedelta(hours=1),
        )
        encrypted = _fernet().encrypt(credentials.to_json().encode())
        with _db_connection() as connection:
            connection.execute(
                """
                INSERT INTO gmail_tokens (session_id, email, encrypted_credentials)
                VALUES (?, ?, ?)
                """,
                (session_id, "sender@example.com", encrypted),
            )

        execute = Mock(return_value={"id": "gmail-message-id"})
        send = Mock()
        send.execute = execute
        messages = Mock()
        messages.send.return_value = send
        users = Mock()
        users.messages.return_value = messages
        gmail_service = Mock()
        gmail_service.users.return_value = users

        with patch("helper.gmail.build", return_value=gmail_service):
            response = self.client.post(
                "/auth/gmail/send",
                json={
                    "recipient": "recipient@example.com",
                    "subject": "Internship application",
                    "body": "Hello from the draft.",
                },
            )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(
            response.json(),
            {"sent": True, "message_id": "gmail-message-id"},
        )
        sent_message = messages.send.call_args.kwargs["body"]["raw"]
        decoded_message = base64.urlsafe_b64decode(sent_message)
        parsed_message = BytesParser(policy=policy.default).parsebytes(decoded_message)
        self.assertEqual(parsed_message["To"], "recipient@example.com")
        self.assertEqual(parsed_message["Subject"], "Internship application")
        self.assertEqual(parsed_message.get_content(), "Hello from the draft.\n")

    def test_disconnect_removes_saved_account(self) -> None:
        self.client.get("/auth/gmail/status")
        session_id = self.client.cookies["gmail_session"].split(".", 1)[0]
        credentials = Credentials(
            token="access-token",
            refresh_token="refresh-token",
            token_uri="https://oauth2.googleapis.com/token",
            client_id="client-id",
            client_secret="client-secret",
            scopes=["https://www.googleapis.com/auth/gmail.send"],
            expiry=datetime.now(timezone.utc) + timedelta(hours=1),
        )
        with _db_connection() as connection:
            connection.execute(
                """
                INSERT INTO gmail_tokens (session_id, email, encrypted_credentials)
                VALUES (?, ?, ?)
                """,
                (
                    session_id,
                    "sender@example.com",
                    _fernet().encrypt(credentials.to_json().encode()),
                ),
            )

        with patch("helper.gmail.requests.post") as revoke:
            response = self.client.delete("/auth/gmail/disconnect")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"connected": False, "revoked": True})
        self.assertEqual(
            revoke.call_args.kwargs["params"],
            {"token": "refresh-token"},
        )
        self.assertEqual(
            self.client.get("/auth/gmail/status").json(),
            {"connected": False, "email": None},
        )


if __name__ == "__main__":
    unittest.main()
