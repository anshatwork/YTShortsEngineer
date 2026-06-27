"""
agents/long_to_shorts/api/db/user_llm_credentials_store.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Supabase-backed store for per-user BYOK (bring-your-own-key) LLM credentials.

One row per user. The raw API key is **never** stored or returned in plaintext:
it is Fernet-encrypted (see tools/llm/byok) before insert and only decrypted in
the worker when a job needs it. All access uses the service-role client; the
table has no user-facing RLS policy, so a stolen anon key cannot read it.
"""

from __future__ import annotations

import logging
from typing import Optional

from agents.long_to_shorts.api.supabase_client import get_worker_client
from tools.llm.byok import decrypt_secret, encrypt_secret
from tools.llm.credentials import LLMCredential, redact_key

logger = logging.getLogger(__name__)

_TABLE = "user_llm_credentials"


class SupabaseUserLLMCredentialStore:
    """Encrypted-at-rest store for users' own LLM provider keys."""

    def upsert(
        self, *, user_id: str, provider: str, api_key: str, model: Optional[str] = None
    ) -> None:
        """Validate + encrypt the key and upsert the user's BYOK credential."""
        # Construct an LLMCredential first so an unsupported provider / empty key
        # is rejected before we touch the DB.
        LLMCredential(provider=provider, api_key=api_key, model=model)
        row = {
            "user_id": user_id,
            "provider": provider,
            "api_key_enc": encrypt_secret(api_key),
            "model": model,
        }
        get_worker_client().table(_TABLE).upsert(row).execute()
        logger.info(
            "Stored BYOK credential — user=%s provider=%s key=%s",
            user_id, provider, redact_key(api_key),
        )

    def get(self, user_id: str) -> Optional[LLMCredential]:
        """Return the decrypted credential for *user_id*, or None if unset.

        Decryption failures (e.g. BYOK_FERNET_KEY rotated) return None and log a
        warning *without* the key, so a job falls back to our default provider
        rather than crashing.
        """
        res = (
            get_worker_client().table(_TABLE)
            .select("provider, api_key_enc, model")
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )
        rows = res.data or []
        if not rows:
            return None
        row = rows[0]
        try:
            api_key = decrypt_secret(row["api_key_enc"])
            return LLMCredential(
                provider=row["provider"], api_key=api_key, model=row.get("model")
            )
        except Exception as exc:  # noqa: BLE001 — never leak the ciphertext/key
            logger.warning(
                "Could not decrypt BYOK credential for user=%s (%s); "
                "falling back to default provider.",
                user_id, type(exc).__name__,
            )
            return None

    def get_meta(self, user_id: str) -> Optional[dict]:
        """Non-secret status for the UI: provider + model only, never the key."""
        res = (
            get_worker_client().table(_TABLE)
            .select("provider, model, updated_at")
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )
        rows = res.data or []
        return rows[0] if rows else None

    def delete(self, user_id: str) -> None:
        get_worker_client().table(_TABLE).delete().eq("user_id", user_id).execute()
        logger.info("Deleted BYOK credential — user=%s", user_id)


user_llm_credential_store = SupabaseUserLLMCredentialStore()

__all__ = ["SupabaseUserLLMCredentialStore", "user_llm_credential_store"]
