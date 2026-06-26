"""
core/cache/keys.py
~~~~~~~~~~~~~~~~~~~
Deterministic, content-addressable cache keys.

A key is ``sha256(operation | stage_version | canonical_json(inputs))``. Because
it is derived purely from the operation and its inputs, the *same* inputs always
map to the *same* key — which is exactly what makes the cache double as the
idempotency mechanism (the key IS the deterministic artifact id).

``stage_version`` is a per-operation integer that callers bump whenever the
operation's logic changes in a way that should invalidate old outputs (e.g. a new
ffmpeg filter graph or a reworked LLM prompt). Forgetting to bump it would serve
stale output, so each call site keeps its version as a named constant.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

# Read in 1 MiB chunks so we never load a multi-GB video into memory to hash it.
_FILE_CHUNK = 1 << 20


def canonical_json(value: Any) -> str:
    """Stable JSON encoding: sorted keys, no insignificant whitespace.

    Two logically-equal input dicts always produce the same string regardless of
    key insertion order, so they hash to the same cache key.
    """
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def make_key(operation: str, version: int, inputs: Any) -> str:
    """Return the hex sha256 cache key for an operation + version + inputs."""
    h = hashlib.sha256()
    h.update(operation.encode("utf-8"))
    h.update(b"\x00")
    h.update(str(version).encode("utf-8"))
    h.update(b"\x00")
    h.update(canonical_json(inputs).encode("utf-8"))
    return h.hexdigest()


def hash_text(text: str) -> str:
    """sha256 of a UTF-8 string (use to fold large text into a key input)."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def hash_file(path: str | Path) -> str:
    """sha256 of a file's bytes, streamed so large media files stay off-heap."""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(_FILE_CHUNK), b""):
            h.update(chunk)
    return h.hexdigest()


def file_signature(path: str | Path) -> dict:
    """Cheap, content-sensitive fingerprint for a source file used as a cache input.

    Avoids hashing multi-GB media on the hot path: a file's identity is captured
    by its basename + byte size + last-modified time, all of which change if the
    file is replaced or re-encoded. Use :func:`hash_file` instead when you need a
    cross-machine-stable content hash.
    """
    p = Path(path)
    try:
        st = p.stat()
        return {"name": p.name, "size": st.st_size, "mtime_ns": st.st_mtime_ns}
    except OSError:
        return {"name": p.name, "size": -1, "mtime_ns": -1}


__all__ = ["canonical_json", "make_key", "hash_text", "hash_file", "file_signature"]
