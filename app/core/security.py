import base64
import logging
from typing import Optional
from cryptography.fernet import Fernet
import keyring
from sqlalchemy.types import TypeDecorator, Text

logger = logging.getLogger(__name__)

KEYRING_SERVICE_VAULT = "jobpulse_ai"
MASTER_KEY_NAME = "master_fernet_key"

_in_memory_vault: dict[tuple[str, str], str] = {}

def get_or_create_master_key() -> bytes:
    """
    Retrieves the master encryption key from the OS Keyring (Windows Credential Manager).
    If absent, generates a new cryptographic key and persists it securely in the OS Keyring.
    Provides memory fallback for headless Linux CI runners.
    """
    stored_key = None
    try:
        stored_key = keyring.get_password(KEYRING_SERVICE_VAULT, MASTER_KEY_NAME)
    except Exception as e:
        logger.warning(f"OS Keyring unavailable in current environment: {e}. Using memory vault.")
        stored_key = _in_memory_vault.get((KEYRING_SERVICE_VAULT, MASTER_KEY_NAME))

    if not stored_key:
        new_key = Fernet.generate_key().decode("utf-8")
        try:
            keyring.set_password(KEYRING_SERVICE_VAULT, MASTER_KEY_NAME, new_key)
            logger.info("Generated new master Fernet key and saved to OS Keyring.")
            return new_key.encode("utf-8")
        except Exception as e:
            logger.warning(f"Could not persist master key to OS Keyring: {e}. Falling back to memory vault.")
            _in_memory_vault[(KEYRING_SERVICE_VAULT, MASTER_KEY_NAME)] = new_key
            return new_key.encode("utf-8")
    return stored_key.encode("utf-8")

_fernet_instance: Optional[Fernet] = None

def get_fernet() -> Fernet:
    global _fernet_instance
    if _fernet_instance is None:
        key = get_or_create_master_key()
        _fernet_instance = Fernet(key)
    return _fernet_instance

def encrypt_pii(plaintext: Optional[str]) -> Optional[str]:
    """Encrypts sensitive PII string using master Fernet key."""
    if not plaintext:
        return plaintext
    try:
        f = get_fernet()
        return f.encrypt(plaintext.encode("utf-8")).decode("utf-8")
    except Exception as e:
        logger.error(f"Error encrypting PII: {e}")
        return plaintext

def decrypt_pii(ciphertext: Optional[str]) -> Optional[str]:
    """Decrypts ciphertext string into plaintext."""
    if not ciphertext:
        return ciphertext
    try:
        f = get_fernet()
        return f.decrypt(ciphertext.encode("utf-8")).decode("utf-8")
    except Exception:
        # In case the string was unencrypted legacy data
        return ciphertext

def set_keyring_secret(service: str, key_id: str, secret: str):
    """Stores an API key or password strictly in OS Keyring with memory fallback for CI."""
    try:
        keyring.set_password(service, key_id, secret)
    except Exception as e:
        logger.warning(f"OS Keyring set_password unavailable: {e}. Falling back to memory vault.")
        _in_memory_vault[(service, key_id)] = secret

def get_keyring_secret(service: str, key_id: str) -> Optional[str]:
    """Retrieves an API key or password strictly from OS Keyring with memory fallback for CI."""
    try:
        val = keyring.get_password(service, key_id)
        if val is not None:
            return val
    except Exception as e:
        logger.warning(f"OS Keyring get_password unavailable: {e}. Falling back to memory vault.")
    return _in_memory_vault.get((service, key_id))

def delete_keyring_secret(service: str, key_id: str):
    """Removes a secret from OS Keyring."""
    try:
        keyring.delete_password(service, key_id)
    except Exception:
        pass
    _in_memory_vault.pop((service, key_id), None)

def mask_secret(secret: Optional[str]) -> str:
    """Masks secret to prevent leakage in UI or logs."""
    if not secret:
        return "••••••••"
    if len(secret) <= 8:
        return "••••••••"
    return f"{secret[:3]}••••••••{secret[-4:]}"

class EncryptedText(TypeDecorator):
    """
    SQLAlchemy Column type that automatically encrypts sensitive PII on write
    and decrypts on read using Fernet with master key in OS Keyring.
    """
    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        return encrypt_pii(str(value))

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return decrypt_pii(str(value))

