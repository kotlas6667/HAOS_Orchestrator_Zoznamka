from __future__ import annotations

import asyncio
import base64
import json
import os
import pickle
import urllib3
import ssl
from pathlib import Path
from typing import Any, Protocol

# CRITICAL: Disable SSL verification BEFORE importing google libraries
# This is a workaround for Windows SSL certificate issues in development
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

import certifi
import requests as _requests
from google.auth.transport.requests import Request
from google.oauth2.service_account import Credentials as ServiceAccountCredentials
from google.oauth2.credentials import Credentials as OAuth2Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# Use the project-local combined CA bundle (Windows system CAs including Zscaler proxy).
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_CORPORATE_CA = _PROJECT_ROOT / "ca-bundle-combined.pem"
_FALLBACK_CA = _PROJECT_ROOT / "cacert-2026-05-14.pem"
ca_bundle = str(_CORPORATE_CA) if _CORPORATE_CA.exists() else (
    str(_FALLBACK_CA) if _FALLBACK_CA.exists() else certifi.where()
)

os.environ["REQUESTS_CA_BUNDLE"] = ca_bundle
os.environ["CURL_CA_BUNDLE"] = ca_bundle
os.environ["SSL_CERT_FILE"] = ca_bundle

# Monkey-patch certifi so that any library calling certifi.where() gets our bundle
certifi.where = lambda: ca_bundle

# Suppress SSL warnings
import warnings
warnings.filterwarnings("ignore", "Unverified HTTPS request")


class GmailProvider(Protocol):
    async def get_emails(self, query: str = "is:unread", max_results: int = 5) -> dict[str, Any]:
        """Fetch emails matching query."""

    async def send_email(self, recipient: str, subject: str, body: str) -> dict[str, Any]:
        """Send an email."""

    async def get_email_details(self, message_id: str) -> dict[str, Any]:
        """Get full email details."""

    async def add_label(self, message_id: str, label_id: str) -> dict[str, Any]:
        """Add label to email."""


class MockGmailProvider:
    async def get_emails(self, query: str = "is:unread", max_results: int = 5) -> dict[str, Any]:
        return {
            "status": "mock",
            "emails": [],
            "query": query,
            "next_step": "Set GMAIL_PROVIDER=oauth or GMAIL_PROVIDER=service_account",
        }

    async def send_email(self, recipient: str, subject: str, body: str) -> dict[str, Any]:
        return {
            "status": "mock",
            "action": "send",
            "recipient": recipient,
            "subject": subject,
            "next_step": "Set up Gmail OAuth credentials",
        }

    async def get_email_details(self, message_id: str) -> dict[str, Any]:
        return {
            "status": "mock",
            "message_id": message_id,
            "next_step": "Set up Gmail OAuth credentials",
        }

    async def add_label(self, message_id: str, label_id: str) -> dict[str, Any]:
        return {
            "status": "mock",
            "message_id": message_id,
            "label_id": label_id,
            "next_step": "Set up Gmail OAuth credentials",
        }


class RealGmailProvider:
    SCOPES = [
        "https://www.googleapis.com/auth/gmail.readonly",
        "https://www.googleapis.com/auth/gmail.modify",
        "https://www.googleapis.com/auth/gmail.send",
    ]

    def __init__(
        self,
        *,
        credentials_path: str | None = None,
        token_path: str | None = None,
        user_email: str | None = None,
        account_id: str | None = None,
        allow_interactive_oauth: bool = False,
    ) -> None:
        self._credentials_path = credentials_path
        self._token_path = token_path or "token.pickle"
        self._user_email = user_email or "me"
        self._account_id = account_id
        self._account_email = user_email if user_email and user_email != "me" else None
        self._allow_interactive_oauth = allow_interactive_oauth
        self._service = None
        # Initialize service immediately in synchronous context
        self._initialize_service()

    @property
    def account_id(self) -> str | None:
        return self._account_id

    @property
    def account_email(self) -> str | None:
        return self._account_email

    def _initialize_service(self) -> None:
        """Initialize Gmail service once at startup (synchronous context)."""
        try:
            if not self._service:
                from google_auth_httplib2 import AuthorizedHttp
                import httplib2

                creds = self._load_credentials()

                # Disable SSL verification for corporate proxy (Zscaler)
                http = httplib2.Http(disable_ssl_certificate_validation=True)
                authorized_http = AuthorizedHttp(creds, http)

                self._service = build(
                    "gmail",
                    "v1",
                    http=authorized_http,
                    static_discovery=False,
                    cache_discovery=False
                )
        except Exception as e:
            print(f"Warning: Could not initialize Gmail service at startup: {e}")
            import traceback
            traceback.print_exc()
            # Service will be retried in _get_service()

    def _get_service(self):
        """Get cached authenticated Gmail service."""
        if self._service is None:
            # Try to initialize if not already done
            self._initialize_service()
        if self._service is None:
            raise RuntimeError(
                "Gmail nie je pripojený. Zapni Google účty v nastaveniach a prihlás sa cez OAuth."
            )
        return self._service

    def _load_credentials(self) -> OAuth2Credentials | ServiceAccountCredentials:
        """Load credentials from pickle; refresh if needed. Interactive OAuth only if allowed."""
        # Prefer multi-account helper (refresh without browser)
        if os.path.exists(self._token_path):
            try:
                from app.tools.google_accounts import load_credentials as _ga_load
                return _ga_load(self._token_path)
            except Exception as e:
                print(f"Token load/refresh via google_accounts failed ({e})")

        creds = None
        if os.path.exists(self._token_path):
            with open(self._token_path, "rb") as token_file:
                creds = pickle.load(token_file)

            if creds and creds.valid:
                return creds

            if creds and creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                    with open(self._token_path, "wb") as tf:
                        pickle.dump(creds, tf)
                    return creds
                except Exception as e:
                    print(f"Token refresh failed ({e})")

        if not self._allow_interactive_oauth:
            raise RuntimeError(
                f"Chýba platný Gmail token ({self._token_path}). "
                "Pripoj účet cez dashboard → Google účty."
            )

        if not self._credentials_path or not os.path.exists(self._credentials_path):
            raise FileNotFoundError(
                f"Credentials file not found: {self._credentials_path}. "
                "Download from Google Cloud Console > APIs & Services > Credentials"
            )

        flow = InstalledAppFlow.from_client_secrets_file(
            self._credentials_path, self.SCOPES
        )
        creds = flow.run_local_server(port=0)

        with open(self._token_path, "wb") as token_file:
            pickle.dump(creds, token_file)

        return creds

    async def get_emails(self, query: str = "is:unread", max_results: int = 5) -> dict[str, Any]:
        """Fetch emails from Gmail."""
        try:
            # Run synchronous Google API call in thread pool to avoid async/sync mixing
            def _fetch_emails():
                service = self._get_service()
                results = service.users().messages().list(
                    userId=self._user_email,
                    q=query,
                    maxResults=max_results,
                ).execute()
                return results
            
            results = await asyncio.to_thread(_fetch_emails)
            messages = results.get("messages", [])
            email_list = []

            for msg in messages:
                msg_data = await self.get_email_details(msg["id"])
                email_list.append(msg_data)

            return {
                "status": "success",
                "total": results.get("resultSizeEstimate", 0),
                "emails": email_list,
                "query": query,
            }
        except HttpError as error:
            return {
                "status": "error",
                "error": str(error),
                "message": "Failed to fetch emails",
            }

    async def send_email(self, recipient: str, subject: str, body: str) -> dict[str, Any]:
        """Send an email via Gmail."""
        try:
            def _send():
                service = self._get_service()
                message = self._create_message(recipient, subject, body)
                result = service.users().messages().send(
                    userId=self._user_email,
                    body=message
                ).execute()
                return result

            result = await asyncio.to_thread(_send)
            return {
                "status": "success",
                "action": "send",
                "message_id": result["id"],
                "recipient": recipient,
                "subject": subject,
            }
        except HttpError as error:
            return {
                "status": "error",
                "error": str(error),
                "recipient": recipient,
            }

    async def get_email_details(self, message_id: str) -> dict[str, Any]:
        """Get full email details."""
        try:
            def _get_details():
                service = self._get_service()
                message = service.users().messages().get(
                    userId=self._user_email,
                    id=message_id,
                    format="full"
                ).execute()
                
                headers = message["payload"]["headers"]
                subject = next((h["value"] for h in headers if h["name"] == "Subject"), "No Subject")
                sender = next((h["value"] for h in headers if h["name"] == "From"), "Unknown")
                date = next((h["value"] for h in headers if h["name"] == "Date"), "")

                body_text = ""
                if "parts" in message["payload"]:
                    for part in message["payload"]["parts"]:
                        if part["mimeType"] == "text/plain":
                            body_text = base64.urlsafe_b64decode(part["body"]["data"]).decode()
                            break
                elif "body" in message["payload"]:
                    body_text = base64.urlsafe_b64decode(
                        message["payload"]["body"].get("data", "")
                    ).decode()

                return {
                    "message_id": message_id,
                    "subject": subject,
                    "from": sender,
                    "date": date,
                    "body": body_text[:500],  # First 500 chars
                    "labels": message.get("labelIds", []),
                }
            
            details = await asyncio.to_thread(_get_details)
            details["status"] = "success"
            return details
        except HttpError as error:
            return {
                "status": "error",
                "error": str(error),
                "message_id": message_id,
            }

    async def add_label(self, message_id: str, label_id: str) -> dict[str, Any]:
        """Add label to email."""
        try:
            def _add_label():
                service = self._get_service()
                service.users().messages().modify(
                    userId=self._user_email,
                    id=message_id,
                    body={"addLabelIds": [label_id]}
                ).execute()

            await asyncio.to_thread(_add_label)
            return {
                "status": "success",
                "action": "label_added",
                "message_id": message_id,
                "label_id": label_id,
            }
        except HttpError as error:
            return {
                "status": "error",
                "error": str(error),
            }

    @staticmethod
    def _create_message(recipient: str, subject: str, body: str) -> dict[str, Any]:
        """Create a message for sending."""
        from email.mime.text import MIMEText

        message = MIMEText(body)
        message["to"] = recipient
        message["subject"] = subject

        raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
        return {"raw": raw_message}
