"""Immutable, content-derived IDs.

An ID is a prefix plus the first 24 hex characters of the SHA-256 of the canonical JSON of
the identifying fields. The same content always gets the same ID, and any change to the
content gives a different ID. Nothing in the system assigns random or sequential IDs.
"""
from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from enum import Enum
from typing import Any

from .timeutil import iso_utc


def _canon(value: Any) -> Any:
    if isinstance(value, datetime):
        return iso_utc(value)
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            raise ValueError("NaN and infinity cannot be hashed into an ID")
        return value  # json.dumps writes the shortest round-trip repr, which is deterministic
    if isinstance(value, dict):
        return {str(k): _canon(v) for k, v in sorted(value.items(), key=lambda kv: str(kv[0]))}
    if isinstance(value, (list, tuple)):
        return [_canon(v) for v in value]
    if isinstance(value, (set, frozenset)):
        return sorted(_canon(v) for v in value)
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if hasattr(value, "model_dump"):
        return _canon(value.model_dump())
    raise TypeError(f"cannot canonicalize {type(value).__name__}")


def canonical_json(payload: Any) -> str:
    return json.dumps(_canon(payload), sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def make_id(prefix: str, payload: Any) -> str:
    return f"{prefix}_{sha256_hex(canonical_json(payload))[:24]}"
