"""
tools/llm/byok.py
~~~~~~~~~~~~~~~~~~
Symmetric encryption for stored BYOK API keys.

User-supplied provider keys are encrypted at rest in Supabase so the database
alone never exposes a usable credential. We use Fernet (AES-128-CBC + HMAC) with
a key from ``BYOK_FERNET_KEY``. Generate it once:

    python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

and store it in Secrets Manager / SSM (never commit it). Rotating the key
invalidates all stored credentials — users would re-enter their key.
"""

from __future__ import annotations

import os
from functools import lru_cache

from cryptography.fernet import Fernet


@lru_cache(maxsize=1)
def _fernet() -> Fernet:
    key = os.environ.get("BYOK_FERNET_KEY")
    if not key:
        raise RuntimeError(
            "BYOK_FERNET_KEY is not set — cannot encrypt/decrypt BYOK keys. "
            "Generate one with cryptography.fernet.Fernet.generate_key() and set "
            "it in the environment (Secrets Manager / SSM)."
        )
    return Fernet(key.encode() if isinstance(key, str) else key)


def encrypt_secret(plaintext: str) -> str:
    """Encrypt a raw secret → opaque token safe to store in the DB."""
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt_secret(token: str) -> str:
    """Decrypt a token produced by :func:`encrypt_secret` back to plaintext."""
    return _fernet().decrypt(token.encode()).decode()


__all__ = ["encrypt_secret", "decrypt_secret"]
