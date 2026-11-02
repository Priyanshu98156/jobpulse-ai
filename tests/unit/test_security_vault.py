import pytest
from app.core.security import encrypt_pii, decrypt_pii, mask_secret

def test_encrypt_decrypt_pii_roundtrip():
    sensitive_data = "candidate_confidential_email@example.com"
    ciphertext = encrypt_pii(sensitive_data)
    assert ciphertext is not None
    assert ciphertext != sensitive_data
    # Decrypt
    decrypted = decrypt_pii(ciphertext)
    assert decrypted == sensitive_data

def test_mask_secret():
    assert mask_secret("sk_live_1234567890abcdef") == "sk_••••••••cdef"
    assert mask_secret("short") == "••••••••"
    assert mask_secret("") == "••••••••"
    assert mask_secret(None) == "••••••••"

