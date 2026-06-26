"""
tools/assets/sources/_env.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Small env-var helper shared by asset sources.

The project ships a ``.env`` with *placeholder* credentials (e.g.
``PIXABAY_API_KEY=your_pixabay_api_key``) so the app starts without secrets.
A naive ``bool(os.getenv(...))`` treats those placeholders as real keys, so the
source fires a request that 400/401s and spams the logs. :func:`configured`
returns the value only when it looks like a genuine credential.
"""

from __future__ import annotations

import os
from typing import Optional

# Substrings/values that mark an unset placeholder credential. Compared
# case-insensitively. ``your_*`` covers the shipped defaults
# (your_pixabay_api_key, your_freesound_api_key, your_jamendo_client_id …).
_PLACEHOLDER_MARKERS = ("your_", "changeme", "change-me", "xxx", "<", "todo", "placeholder")


def configured(name: str) -> Optional[str]:
    """Return ``os.environ[name]`` only if it is set and not a placeholder.

    Returns ``None`` for missing, blank, or obvious-placeholder values so a
    source's ``available()`` reports ``False`` and the tier is skipped silently.
    """
    raw = os.getenv(name)
    if not raw:
        return None
    value = raw.strip()
    if not value:
        return None
    lowered = value.lower()
    if any(marker in lowered for marker in _PLACEHOLDER_MARKERS):
        return None
    return value


__all__ = ["configured"]
