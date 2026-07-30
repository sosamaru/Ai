"""Dependency-free loading of local ``.env`` files.

The loader is intentionally small and deterministic. Existing process environment
variables win by default so secret-manager and CI injection cannot be overwritten by
a local file.
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import MutableMapping

_ENV_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _decode_value(raw: str, *, line_number: int) -> str:
    value = raw.strip()
    if not value:
        return ""
    if value[0] not in {"'", '"'}:
        return value
    quote = value[0]
    if len(value) < 2 or value[-1] != quote:
        raise ValueError(f"unterminated quoted value in .env line {line_number}")
    inner = value[1:-1]
    if quote == "'":
        return inner
    try:
        return bytes(inner, "utf-8").decode("unicode_escape")
    except UnicodeDecodeError as exc:
        raise ValueError(f"invalid escape sequence in .env line {line_number}") from exc


def load_env_file(
    path: str | Path = ".env",
    *,
    environ: MutableMapping[str, str] | None = None,
    override: bool = False,
) -> int:
    """Load one UTF-8 ``.env`` file and return the number of assigned variables.

    Blank lines and comments are ignored. ``export KEY=value`` is accepted. Inline
    comments and variable interpolation are deliberately unsupported because both can
    make secret handling ambiguous. A missing file is a normal no-op.
    """

    target = Path(path)
    if not target.exists():
        return 0
    if not target.is_file():
        raise ValueError(f".env path is not a file: {target}")

    destination = os.environ if environ is None else environ
    assigned = 0
    for line_number, raw_line in enumerate(target.read_text(encoding="utf-8").splitlines(), 1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        if "=" not in line:
            raise ValueError(f"invalid .env assignment on line {line_number}")
        name, raw_value = line.split("=", 1)
        key = name.strip()
        if not _ENV_NAME.fullmatch(key):
            raise ValueError(f"invalid environment variable name on line {line_number}: {key!r}")
        if not override and key in destination:
            continue
        destination[key] = _decode_value(raw_value, line_number=line_number)
        assigned += 1
    return assigned


__all__ = ["load_env_file"]
