from pathlib import Path

from cryptography.fernet import Fernet
import secrets


BACKEND_DIR = Path(__file__).resolve().parent
ENV_FILE = BACKEND_DIR / ".env"


def main() -> None:
    if ENV_FILE.exists() and ENV_FILE.stat().st_size > 0:
        print(f"Kept existing configuration: {ENV_FILE}")
        return

    session_secret = secrets.token_urlsafe(48)
    encryption_key = Fernet.generate_key().decode("ascii")
    configuration = f"""# Generated locally. Keep this file private and do not commit it.
ENV=dev
GOOGLE_CLIENT_SECRETS_FILE=client_secret.json
GOOGLE_REDIRECT_URI=http://localhost:8000/auth/gmail/callback
OPENROUTER_MODEL=openai/gpt-4o-mini
FRONTEND_URL=http://localhost:5173
FRONTEND_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
GMAIL_SESSION_SECRET={session_secret}
GMAIL_TOKEN_ENCRYPTION_KEY={encryption_key}
GMAIL_COOKIE_SECURE=false
GMAIL_COOKIE_SAMESITE=lax
GMAIL_TOKEN_DB=data/gmail.sqlite3
"""
    ENV_FILE.write_text(configuration, encoding="utf-8")
    print(f"Created local Gmail configuration: {ENV_FILE}")
    print("Next, add your Google OAuth client JSON as backend/client_secret.json.")


if __name__ == "__main__":
    main()
