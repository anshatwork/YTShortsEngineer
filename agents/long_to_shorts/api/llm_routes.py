"""
agents/long_to_shorts/api/llm_routes.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
BYOK (bring-your-own-key) LLM credential management.

Lets a user store their own provider API key so their jobs run on their key and
bypass our GPU. The raw key is encrypted at rest and never returned — GET only
exposes non-secret status (provider + model).

Endpoints (mounted at /api/v1/llm)
    PUT    /credentials   Store / replace the caller's BYOK key
    GET    /credentials   Non-secret status (provider, model, configured?)
    DELETE /credentials   Remove the caller's BYOK key (revert to our GPU)
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from agents.long_to_shorts.api.auth import get_current_user_id
from tools.llm.credentials import BYOK_PROVIDERS

logger = logging.getLogger(__name__)

router = APIRouter()


class LLMCredentialIn(BaseModel):
    provider: str = Field(..., description=f"One of: {', '.join(BYOK_PROVIDERS)}")
    api_key: str = Field(..., min_length=8, description="Your provider API key (stored encrypted)")
    model: Optional[str] = Field(None, description="Optional model id override")


class LLMCredentialStatus(BaseModel):
    configured: bool
    provider: Optional[str] = None
    model: Optional[str] = None


@router.put(
    "/credentials",
    response_model=LLMCredentialStatus,
    summary="Store or replace your BYOK LLM API key",
)
async def put_credentials(
    body: LLMCredentialIn,
    user_id: str = Depends(get_current_user_id),
) -> LLMCredentialStatus:
    if body.provider not in BYOK_PROVIDERS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unsupported provider. Supported: {', '.join(BYOK_PROVIDERS)}",
        )
    from agents.long_to_shorts.api.db.user_llm_credentials_store import (
        user_llm_credential_store,
    )

    try:
        user_llm_credential_store.upsert(
            user_id=user_id,
            provider=body.provider,
            api_key=body.api_key,
            model=body.model,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))

    return LLMCredentialStatus(configured=True, provider=body.provider, model=body.model)


@router.get(
    "/credentials",
    response_model=LLMCredentialStatus,
    summary="Whether you have a BYOK key configured (never returns the key)",
)
async def get_credentials(
    user_id: str = Depends(get_current_user_id),
) -> LLMCredentialStatus:
    from agents.long_to_shorts.api.db.user_llm_credentials_store import (
        user_llm_credential_store,
    )

    meta = user_llm_credential_store.get_meta(user_id)
    if not meta:
        return LLMCredentialStatus(configured=False)
    return LLMCredentialStatus(
        configured=True, provider=meta.get("provider"), model=meta.get("model")
    )


@router.delete(
    "/credentials",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete your BYOK key (jobs revert to our GPU)",
)
async def delete_credentials(
    user_id: str = Depends(get_current_user_id),
):
    # NOTE: no `-> None` return annotation — newer FastAPI fails to import 204
    # routes annotated that way (see project notes).
    from agents.long_to_shorts.api.db.user_llm_credentials_store import (
        user_llm_credential_store,
    )

    user_llm_credential_store.delete(user_id)


__all__ = ["router"]
