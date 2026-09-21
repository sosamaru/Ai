"""Small, dependency-free contracts shared by research and PAPER monitoring."""
from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha256
import json
import math
import re


def finite(value, name="value", low=None, high=None) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{name} must be a finite number")
    if low is not None and value < low or high is not None and value > high:
        raise ValueError(f"{name} outside fixed bounds")
    return float(value)


def integer(value, name, low, high) -> int:
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f"{name} outside integer bounds")
    return value


def domain(value: str) -> str:
    if value not in {"crypto", "us_stock"}:
        raise ValueError("explicit crypto or us_stock domain required")
    return value


def instant(value: str | datetime) -> datetime:
    result = datetime.fromisoformat(value) if isinstance(value, str) else value
    if not isinstance(result, datetime) or result.tzinfo is None or result.utcoffset() is None:
        raise ValueError("timezone-aware timestamp required")
    return result.astimezone(UTC)


def canonical(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def fingerprint(value) -> str:
    return sha256(canonical(value).encode()).hexdigest()


def digest(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
        raise ValueError("SHA-256 evidence required")
    return value
