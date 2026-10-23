#!/usr/bin/env python3
"""Connect one local Inklur account to a Google Gmail account.

This script is for local/development use. It opens Google's OAuth flow on this
machine and stores the refresh token encrypted through gmail_engine.store_gmail_token().
For a hosted multi-user site, use a web OAuth callback instead of this CLI flow.

Usage:
    python connect_gmail.py user@example.com
    python connect_gmail.py user@example.com --credentials path/to/credentials.json
"""

import argparse
import os
import sqlite3
import sys
from contextlib import closing
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_CREDENTIALS_PATH = BASE_DIR / "credentials.json"
SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]


def say(message):
    try:
        print(str(message), flush=True)
    except UnicodeEncodeError:
        print(str(message).encode("ascii", "replace").decode("ascii"), flush=True)


def ask_yes_no(prompt):
    try:
        return input(prompt).strip().lower() in {"y", "yes"}
    except (EOFError, KeyboardInterrupt):
        return False


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Connect a Google Gmail account to an existing Inklur user."
    )
    parser.add_argument(
        "email",
        nargs="?",
        help="Email address used to sign in to Inklur; prompts if omitted.",
    )
    parser.add_argument(
        "--credentials",
        type=Path,
        default=DEFAULT_CREDENTIALS_PATH,
        help="Google OAuth client credentials JSON file (default: credentials.json beside this script).",
    )
    return parser.parse_args(argv)


def get_integration_modules():
    """Load app/Gmail dependencies only after CLI help and basic checks."""
    script_dir = str(BASE_DIR)
    if script_dir not in sys.path:
        sys.path.insert(0, script_dir)

    try:
        import gmail_engine
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
    except ImportError as error:
        raise RuntimeError(
            "Gmail dependencies are missing. Install google-auth-oauthlib, "
            "google-api-python-client, and the requirements used by gmail_engine.py."
        ) from error

    return gmail_engine, InstalledAppFlow, build


def get_user_email(raw_email, gmail_engine):
    if raw_email:
        candidate = raw_email.strip()
    else:
        try:
            candidate = input("Inklur sign-in email: ").strip()
        except (EOFError, KeyboardInterrupt):
            return None

    try:
        return gmail_engine.normalize_account_email(candidate)
    except ValueError as error:
        say(str(error))
        return None


def user_exists(user_email, gmail_engine):
    database_path = Path(gmail_engine.DB_PATH)
    if not database_path.is_file():
        say(
            f"Inklur database not found: {database_path}. "
            "Run the app and finish its database migration first."
        )
        return False

    try:
        gmail_engine.ensure_gmail_schema()
        with closing(sqlite3.connect(str(database_path), timeout=10)) as connection:
            row = connection.execute(
                "SELECT id FROM users WHERE lower(email) = ?",
                (user_email,),
            ).fetchone()
    except (sqlite3.Error, ValueError) as error:
        say(f"Could not verify the Inklur account: {error}")
        return False

    if row is None:
        say("That email is not registered in the Inklur database. Sign up first.")
        return False
    return True


def authorize_gmail(credentials_path, InstalledAppFlow):
    if not credentials_path.is_file():
        say(f"Google OAuth credentials file was not found: {credentials_path}")
        say("Place your OAuth client JSON there, or pass its path with --credentials.")
        return None

    try:
        flow = InstalledAppFlow.from_client_secrets_file(
            str(credentials_path),
            SCOPES,
        )
        credentials = flow.run_local_server(
            host="localhost",
            port=0,
            access_type="offline",
            prompt="consent",
        )
    except Exception as error:
        say(f"Google authorization failed ({type(error).__name__}).")
        return None

    if not credentials or not credentials.refresh_token:
        say("Google did not return a refresh token; nothing was saved.")
        say(
            "If this account was previously authorized, remove the Inklur app's "
            "Google access and run this script again."
        )
        return None

    return credentials


def get_google_account_email(credentials, build):
    try:
        service = build("gmail", "v1", credentials=credentials, cache_discovery=False)
        profile = service.users().getProfile(userId="me").execute()
        email = str(profile.get("emailAddress", "")).strip().lower()
        return email or None
    except Exception as error:
        say(f"Could not verify the authorized Gmail account ({type(error).__name__}).")
        return None


def connect_gmail(user_email, credentials_path):
    try:
        gmail_engine, InstalledAppFlow, build = get_integration_modules()
    except RuntimeError as error:
        say(str(error))
        return 1

    normalized_email = get_user_email(user_email, gmail_engine)
    if not normalized_email:
        say("No valid Inklur email was supplied; cancelled.")
        return 1

    if not user_exists(normalized_email, gmail_engine):
        return 1

    # Agar tumhare paas .env me key set hai toh ye check skip bhi kar sakte ho, 
    # par safety ke liye agar GMAIL_TOKEN_KEY missing ho toh warning dega.
    if not os.getenv("GMAIL_TOKEN_KEY"):
        say("Warning: GMAIL_TOKEN_KEY environment variable set nahi hai. Encrypted token save karne me dikkat aa sakti hai.")

    credentials = authorize_gmail(credentials_path, InstalledAppFlow)
    if credentials is None:
        return 1

    google_email = get_google_account_email(credentials, build)
    if not google_email:
        say("Could not verify which Google account was authorized; token was not saved.")
        return 1

    say(f"Authorized Google account: {google_email}")
    if google_email != normalized_email:
        say("This Google address differs from the Inklur sign-in address.")
        if not ask_yes_no(
            "Save this Gmail connection to the selected Inklur account? [y/N]: "
        ):
            say("Cancelled; no token was saved.")
            return 1

    try:
        gmail_engine.store_gmail_token(normalized_email, credentials.to_json())
    except (ValueError, sqlite3.Error) as error:
        say(f"Could not save the encrypted Gmail connection: {error}")
        return 1

    say(f"Gmail was connected to the Inklur account {normalized_email}.")
    say("The OAuth token was saved through gmail_engine.store_gmail_token().")
    return 0


def main(argv=None):
    args = parse_args(argv)
    return connect_gmail(args.email, args.credentials)


if __name__ == "__main__":
    sys.exit(main())