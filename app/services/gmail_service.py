import os
import re
import base64
import logging
from typing import Optional, Dict, Any, List
import keyring

logger = logging.getLogger(__name__)

SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']
KEYRING_SERVICE = "jobpulse_ai_gmail"
TOKEN_KEY = "oauth_token_json"
CLIENT_CONFIG_KEY = "client_secret_json"

class GmailReaderService:
    """
    Gmail Read-Only Service for Automated OTP & Login Link Extraction.
    Uses Google OAuth2 with restricted read-only scope.
    Credentials and Client Secret are stored strictly in OS Keyring.
    """
    def __init__(self):
        self.creds = None

    def get_client_config(self) -> Optional[dict]:
        """Loads client_secret json from OS Keyring vault, or local client_secret.json and vaults it."""
        import json
        from pathlib import Path
        raw = keyring.get_password(KEYRING_SERVICE, CLIENT_CONFIG_KEY)
        if raw:
            try:
                return json.loads(raw)
            except Exception:
                pass
        # Fallback to local file if available, and auto-vault
        for fname in ["client_secret.json", "client_secrets.json"]:
            p = Path(fname)
            if p.exists():
                try:
                    content = p.read_text(encoding="utf-8")
                    data = json.loads(content)
                    try:
                        keyring.set_password(KEYRING_SERVICE, CLIENT_CONFIG_KEY, content)
                    except Exception:
                        pass
                    return data
                except Exception:
                    pass
        return None

    def get_credentials(self):
        """Retrieves credentials from OS Keyring or returns None if unauthenticated."""
        token_json = keyring.get_password(KEYRING_SERVICE, TOKEN_KEY)
        if token_json:
            try:
                import json
                from google.oauth2.credentials import Credentials
                info = json.loads(token_json)
                self.creds = Credentials.from_authorized_user_info(info, SCOPES)
                return self.creds
            except Exception as e:
                logger.warning(f"Failed to load stored Gmail credentials: {e}")
        return None

    def is_connected(self) -> bool:
        """Returns True if valid Gmail credentials exist."""
        creds = self.get_credentials()
        return creds is not None and (creds.valid or creds.refresh_token is not None)

    def get_connected_email(self) -> Optional[str]:
        """Returns user's connected Gmail address if authenticated."""
        creds = self.get_credentials()
        if not creds:
            return None
        try:
            from googleapiclient.discovery import build
            service = build('gmail', 'v1', credentials=creds)
            profile = service.users().getProfile(userId='me').execute()
            return profile.get('emailAddress')
        except Exception:
            return "Connected"

    def generate_authorization_url(self, redirect_uri: str) -> Optional[str]:
        """Generates Google OAuth2 consent URL using client_secret from vault."""
        config = self.get_client_config()
        if not config:
            return None
        from google_auth_oauthlib.flow import Flow
        flow = Flow.from_client_config(
            config,
            scopes=SCOPES,
            redirect_uri=redirect_uri
        )
        auth_url, _ = flow.authorization_url(
            access_type='offline',
            include_granted_scopes='true',
            prompt='consent'
        )
        return auth_url

    def complete_oauth_callback(self, code: str, redirect_uri: str) -> bool:
        """Exchanges auth code for tokens and persists into OS Keyring."""
        config = self.get_client_config()
        if not config:
            return False
        try:
            import json
            from google_auth_oauthlib.flow import Flow
            flow = Flow.from_client_config(
                config,
                scopes=SCOPES,
                redirect_uri=redirect_uri
            )
            flow.fetch_token(code=code)
            creds = flow.credentials
            
            token_data = {
                'token': creds.token,
                'refresh_token': creds.refresh_token,
                'token_uri': creds.token_uri,
                'client_id': creds.client_id,
                'client_secret': creds.client_secret,
                'scopes': creds.scopes
            }
            keyring.set_password(KEYRING_SERVICE, TOKEN_KEY, json.dumps(token_data))
            self.creds = creds
            logger.info("Gmail OAuth refresh token saved securely into OS Keyring.")
            return True
        except Exception as e:
            logger.error(f"Error completing OAuth token exchange: {e}")
            return False

    def disconnect(self):
        """Removes Gmail OAuth credentials from OS Keyring."""
        try:
            keyring.delete_password(KEYRING_SERVICE, TOKEN_KEY)
        except Exception:
            pass
        self.creds = None

    def extract_otp_or_link_from_text(self, text: str) -> Optional[str]:
        """
        Extracts 4-8 digit numeric verification code or a magic login URL.
        """
        # 1. Look for explicit verification codes (e.g. 'code is 123456', 'code: 1234')
        code_patterns = [
            r"(?:code|pin|otp|passcode|token)(?:\s+is|\s*:)?\s+([0-9]{4,8})\b",
            r"\b([0-9]{6})\b",
            r"\b([0-9]{4})\b",
        ]
        for pat in code_patterns:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                return m.group(1).strip()

        # 2. Look for magic login links
        link_patterns = [
            r'(https?://[^\s<>"]+(?:login|verify|auth|token|magic|session)[^\s<>"]*)',
            r'(https?://[^\s<>"]+confirm[^\s<>"]*)'
        ]
        for pat in link_patterns:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                return m.group(1).strip()

        return None

    def fetch_latest_otp(self, query_keyword: str = "", max_age_seconds: int = 180) -> Optional[Dict[str, Any]]:
        """
        Polls Gmail for recent messages matching the sender or keyword.
        Returns dict with 'otp_or_link', 'subject', 'from', or None.
        """
        creds = self.get_credentials()
        if not creds:
            logger.warning("Gmail service is not connected via OAuth.")
            return None

        try:
            from googleapiclient.discovery import build
            service = build('gmail', 'v1', credentials=creds)
            # Query recent messages (within last few minutes)
            q = "newer_than:1d " + (query_keyword or "verification OR code OR login OR passcode")
            results = service.users().messages().list(userId='me', q=q, maxResults=5).execute()
            messages = results.get('messages', [])

            if not messages:
                return None

            for msg_meta in messages:
                msg = service.users().messages().get(userId='me', id=msg_meta['id'], format='full').execute()
                snippet = msg.get('snippet', '')
                
                # Check snippet first
                otp = self.extract_otp_or_link_from_text(snippet)
                if otp:
                    return {
                        "otp_or_link": otp,
                        "snippet": snippet,
                        "message_id": msg_meta['id']
                    }

            return None
        except Exception as e:
            logger.error(f"Error querying Gmail messages: {e}")
            return None

gmail_reader_service = GmailReaderService()
