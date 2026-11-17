import base64
from contextlib import contextmanager
import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import sqlite3
import threading
import time
from email.message import EmailMessage
from pathlib import Path
from typing import Iterator, Optional
from urllib.parse import urlencode, urlsplit

from cryptography.fernet import Fernet, InvalidToken
from fastapi import HTTPException, Request, Response
from google.auth.exceptions import GoogleAuthError
from google.auth.transport.requests import Request as GoogleRequest
from google.oauth2 import id_token
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from oauthlib.oauth2.rfc6749.errors import OAuth2Error
from pydantic import BaseModel, Field
import requests

logger = logging.getLogger(__name__)

GMAIL_SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/gmail.send",
]
SESSION_COOKIE = "gmail_session"
SESSION_MAX_AGE = 60 * 60 * 24 * 30
CLIENT_SECRETS_PATH = Path(__file__).resolve().parents[1] / "client_secret.json"
_OAUTH_TRANSPORT_LOCK = threading.Lock()


class SendEmailRequest(BaseModel):
    recipient: str = Field(min_length=3, max_length=320)
    subject: str = Field(min_length=1, max_length=998)
    body: str = Field(min_length=1, max_length=100_000)


def _required_setting(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise HTTPException(
            status_code=503,
            detail=f"The server is missing the {name} configuration.",
        )
    return value


def _db_path() -> Path:
    path = Path(
        os.getenv(
            "GMAIL_TOKEN_DB",
            str(Path(__file__).resolve().parents[1] / "data" / "gmail.sqlite3"),
        )
    ).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _connect_db() -> sqlite3.Connection:
    connection = sqlite3.connect(_db_path(), timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS gmail_tokens (
            session_id TEXT PRIMARY KEY,
            email TEXT NOT NULL,
            encrypted_credentials BLOB NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS gmail_oauth_states (
            state TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            expires_at INTEGER NOT NULL,
            code_verifier TEXT
        )
        """
    )
    oauth_state_columns = {
        row["name"]
        for row in connection.execute("PRAGMA table_info(gmail_oauth_states)")
    }
    if "code_verifier" not in oauth_state_columns:
        connection.execute(
            "ALTER TABLE gmail_oauth_states ADD COLUMN code_verifier TEXT"
        )
    return connection


@contextmanager
def _db_connection() -> Iterator[sqlite3.Connection]:
    connection = _connect_db()
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def _signed_session(session_id: str, expires_at: int) -> str:
    payload = f"{session_id}.{expires_at}"
    signature = hmac.new(
        _required_setting("GMAIL_SESSION_SECRET").encode(),
        payload.encode(),
        hashlib.sha256,
    ).hexdigest()
    return f"{payload}.{signature}"


def _get_session_id(request: Request) -> Optional[str]:
    value = request.cookies.get(SESSION_COOKIE, "")
    try:
        session_id, expires_at, signature = value.split(".", 2)
        payload = f"{session_id}.{expires_at}"
        expected = hmac.new(
            _required_setting("GMAIL_SESSION_SECRET").encode(),
            payload.encode(),
            hashlib.sha256,
        ).hexdigest()
        if (
            len(session_id) != 64
            or int(expires_at) < int(time.time())
            or not hmac.compare_digest(signature, expected)
        ):
            return None
    except (ValueError, HTTPException):
        return None
    return session_id


def _ensure_session(request: Request, response: Response) -> str:
    session_id = _get_session_id(request)
    if session_id is None:
        session_id = secrets.token_hex(32)
        response.set_cookie(
            SESSION_COOKIE,
            _signed_session(session_id, int(time.time()) + SESSION_MAX_AGE),
            max_age=SESSION_MAX_AGE,
            httponly=True,
            secure=os.getenv("GMAIL_COOKIE_SECURE", "true").lower() == "true",
            samesite=os.getenv("GMAIL_COOKIE_SAMESITE", "lax").lower(),
            path="/",
        )
    return session_id


def _require_session(request: Request) -> str:
    session_id = _get_session_id(request)
    if session_id is None:
        raise HTTPException(status_code=401, detail="Connect your Gmail account.")
    return session_id


def _fernet() -> Fernet:
    try:
        return Fernet(_required_setting("GMAIL_TOKEN_ENCRYPTION_KEY").encode())
    except ValueError as error:
        raise HTTPException(
            status_code=503,
            detail="The Gmail token encryption key is invalid.",
        ) from error


def _client_secrets_file() -> Path:
    path = Path(os.getenv("GOOGLE_CLIENT_SECRETS_FILE", str(CLIENT_SECRETS_PATH)))
    if not path.is_file():
        raise HTTPException(
            status_code=503,
            detail="The Google OAuth client-secrets JSON file is not configured.",
        )
    return path


def _redirect_uri() -> str:
    return _required_setting("GOOGLE_REDIRECT_URI")


def _frontend_url() -> str:
    return os.getenv("FRONTEND_URL", "http://localhost:5173").rstrip("/")


def _fetch_oauth_token(flow: Flow, request: Request) -> None:
    callback_url = str(request.url)
    callback = urlsplit(callback_url)
    redirect_uri = urlsplit(_redirect_uri())
    if (
        callback.scheme != redirect_uri.scheme
        or callback.netloc != redirect_uri.netloc
        or callback.path != redirect_uri.path
    ):
        raise HTTPException(
            status_code=400,
            detail="The OAuth callback does not match the configured redirect URI.",
        )

    is_local_dev_http = (
        redirect_uri.scheme == "http"
        and redirect_uri.hostname in {"localhost", "127.0.0.1", "::1"}
        and os.getenv("ENV", "").lower() == "dev"
    )
    try:
        if redirect_uri.scheme == "https":
            flow.fetch_token(authorization_response=callback_url)
        elif is_local_dev_http:
            with _OAUTH_TRANSPORT_LOCK:
                previous_transport_setting = os.environ.get(
                    "OAUTHLIB_INSECURE_TRANSPORT"
                )
                try:
                    os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"
                    flow.fetch_token(authorization_response=callback_url)
                finally:
                    if previous_transport_setting is None:
                        os.environ.pop("OAUTHLIB_INSECURE_TRANSPORT", None)
                    else:
                        os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = (
                            previous_transport_setting
                        )
        else:
            raise HTTPException(
                status_code=503,
                detail="OAuth requires HTTPS. HTTP callbacks are allowed only for localhost when ENV=dev.",
            )
    except OAuth2Error as exc:
        logger.exception(
            "Gmail OAuth token exchange failed (%s): %s",
            type(exc).__name__,
            exc,
        )
        raise HTTPException(
            status_code=400,
            detail=f"OAuth token exchange failed ({type(exc).__name__}): {exc}",
        ) from exc


def gmail_status(request: Request, response: Response) -> dict:
    session_id = _ensure_session(request, response)
    with _db_connection() as connection:
        token = connection.execute(
            "SELECT email FROM gmail_tokens WHERE session_id = ?",
            (session_id,),
        ).fetchone()
    if token is None:
        return {"connected": False, "email": None}
    return {"connected": True, "email": token["email"]}


def gmail_login(request: Request, response: Response) -> dict:
    session_id = _ensure_session(request, response)
    state = secrets.token_urlsafe(32)
    flow = Flow.from_client_secrets_file(
        str(_client_secrets_file()),
        scopes=GMAIL_SCOPES,
        state=state,
    )
    flow.redirect_uri = _redirect_uri()
    authorization_url, state = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
    )
    if not flow.code_verifier:
        raise HTTPException(
            status_code=500,
            detail="Google OAuth did not generate a PKCE code verifier.",
        )
    with _db_connection() as connection:
        connection.execute(
            "DELETE FROM gmail_oauth_states WHERE expires_at < ?",
            (int(time.time()),),
        )
        connection.execute(
            """
            INSERT INTO gmail_oauth_states
                (state, session_id, expires_at, code_verifier)
            VALUES (?, ?, ?, ?)
            """,
            (state, session_id, int(time.time()) + 600, flow.code_verifier),
        )
    return {"authorization_url": authorization_url}


def _consume_oauth_state(state: str, session_id: str) -> Optional[str]:
    with _db_connection() as connection:
        record = connection.execute(
            """
            SELECT session_id, expires_at, code_verifier
            FROM gmail_oauth_states
            WHERE state = ?
            """,
            (state,),
        ).fetchone()
        connection.execute("DELETE FROM gmail_oauth_states WHERE state = ?", (state,))
    if (
        record is None
        or record["session_id"] != session_id
        or record["expires_at"] < int(time.time())
        or not record["code_verifier"]
    ):
        return None
    return record["code_verifier"]


def _frontend_redirect(**params: str) -> Response:
    return Response(
        status_code=303,
        headers={"Location": f"{_frontend_url()}/?{urlencode(params)}"},
    )


def gmail_callback(request: Request, error: Optional[str], state: Optional[str]) -> Response:
    session_id = _get_session_id(request)
    code_verifier = (
        _consume_oauth_state(state, session_id)
        if session_id is not None and state
        else None
    )
    if code_verifier is None:
        logger.warning("Rejected Gmail OAuth callback with invalid or expired state.")
        raise HTTPException(status_code=400, detail="Invalid or expired OAuth state")
    if error:
        return _frontend_redirect(gmail_error="authorization_cancelled")

    try:
        flow = Flow.from_client_secrets_file(
            str(_client_secrets_file()),
            scopes=GMAIL_SCOPES,
            state=state,
        )
        flow.redirect_uri = _redirect_uri()
        flow.code_verifier = code_verifier
        _fetch_oauth_token(flow, request)
        credentials = flow.credentials
        if not credentials.id_token:
            raise ValueError("Google did not return a verified account identity.")
        identity = id_token.verify_oauth2_token(
            credentials.id_token,
            GoogleRequest(),
            audience=credentials.client_id,
        )
        email = identity.get("email")
        if not email or identity.get("email_verified") is not True:
            raise ValueError("Google did not verify the Gmail account address.")
    except (GoogleAuthError, requests.RequestException, ValueError) as exc:
        logger.warning("Gmail OAuth callback failed: %s", exc)
        return _frontend_redirect(gmail_error="authorization_failed")

    encrypted = _fernet().encrypt(credentials.to_json().encode())
    with _db_connection() as connection:
        connection.execute(
            """
            INSERT INTO gmail_tokens (session_id, email, encrypted_credentials)
            VALUES (?, ?, ?)
            ON CONFLICT(session_id) DO UPDATE SET
                email = excluded.email,
                encrypted_credentials = excluded.encrypted_credentials
            """,
            (session_id, email, encrypted),
        )
    return _frontend_redirect(gmail="connected")


def _load_credentials(session_id: str) -> tuple[Credentials, str]:
    with _db_connection() as connection:
        record = connection.execute(
            "SELECT email, encrypted_credentials FROM gmail_tokens WHERE session_id = ?",
            (session_id,),
        ).fetchone()
    if record is None:
        raise HTTPException(status_code=401, detail="Connect your Gmail account first.")

    try:
        credentials_json = _fernet().decrypt(record["encrypted_credentials"]).decode()
        credentials = Credentials.from_authorized_user_info(
            json.loads(credentials_json),
            scopes=GMAIL_SCOPES,
        )
    except (InvalidToken, KeyError, ValueError, json.JSONDecodeError) as exc:
        logger.exception("Could not decrypt stored Gmail credentials.")
        raise HTTPException(
            status_code=500,
            detail="Stored Gmail credentials could not be read. Disconnect and reconnect.",
        ) from exc
    return credentials, record["email"]


def _save_credentials(session_id: str, credentials: Credentials) -> None:
    encrypted = _fernet().encrypt(credentials.to_json().encode())
    with _db_connection() as connection:
        connection.execute(
            "UPDATE gmail_tokens SET encrypted_credentials = ? WHERE session_id = ?",
            (encrypted, session_id),
        )


def send_gmail(request: Request, payload: SendEmailRequest) -> dict:
    session_id = _require_session(request)
    recipient = payload.recipient.strip()
    if (
        not re.fullmatch(r"[^@\s<>]+@[^@\s<>]+\.[^@\s<>]+", recipient)
        or "\r" in payload.subject
        or "\n" in payload.subject
    ):
        raise HTTPException(status_code=422, detail="Enter a valid recipient and subject.")

    credentials, sender = _load_credentials(session_id)
    try:
        if credentials.expired and credentials.refresh_token:
            credentials.refresh(GoogleRequest())
            _save_credentials(session_id, credentials)
        elif not credentials.valid:
            raise HTTPException(
                status_code=401,
                detail="Gmail authorization expired. Reconnect your account and retry.",
            )

        message = EmailMessage()
        message["To"] = recipient
        message["From"] = sender
        message["Subject"] = payload.subject.strip()
        message.set_content(payload.body)
        raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
        result = (
            build("gmail", "v1", credentials=credentials, cache_discovery=False)
            .users()
            .messages()
            .send(userId="me", body={"raw": raw_message})
            .execute()
        )
    except HTTPException:
        raise
    except HttpError as exc:
        status_code = int(exc.resp.status)
        logger.warning("Gmail API send failed with HTTP %s.", status_code)
        raise HTTPException(
            status_code=502,
            detail="Gmail could not send this message. Your draft is unchanged; retry when ready.",
        ) from exc
    except (GoogleAuthError, requests.RequestException) as exc:
        logger.warning("Gmail authorization or network request failed: %s", exc)
        raise HTTPException(
            status_code=502,
            detail="Gmail could not be reached. Your draft is unchanged; retry when ready.",
        ) from exc

    message_id = result.get("id")
    if not message_id:
        logger.error("Gmail API send response did not contain a message ID.")
        raise HTTPException(
            status_code=502,
            detail="Gmail did not confirm the message was sent. Check Sent mail before retrying.",
        )
    return {"sent": True, "message_id": message_id}


def disconnect_gmail(request: Request, response: Response) -> dict:
    session_id = _get_session_id(request)
    revoked = False
    if session_id:
        try:
            credentials, _ = _load_credentials(session_id)
            token = credentials.refresh_token or credentials.token
            if token:
                revocation_response = requests.post(
                    "https://oauth2.googleapis.com/revoke",
                    params={"token": token},
                    timeout=10,
                )
                revocation_response.raise_for_status()
                revoked = True
        except (HTTPException, requests.RequestException) as exc:
            logger.warning("Could not revoke the Gmail authorization: %s", exc)
        with _db_connection() as connection:
            connection.execute(
                "DELETE FROM gmail_tokens WHERE session_id = ?",
                (session_id,),
            )
            connection.execute(
                "DELETE FROM gmail_oauth_states WHERE session_id = ?",
                (session_id,),
            )
    response.delete_cookie(SESSION_COOKIE, path="/", samesite="lax")
    return {"connected": False, "revoked": revoked}
