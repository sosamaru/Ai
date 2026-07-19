from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict
from pathlib import Path

from aipro.core.live_authorization import LiveAuthorizationState


class LiveAuthorizationStateStore:
    """Atomic local state persistence. OTP plaintext and TOTP secrets are never stored."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def save(self, state: LiveAuthorizationState) -> None:
        payload = json.dumps(asdict(state), sort_keys=True, separators=(",", ":"))
        fd, temporary = tempfile.mkstemp(prefix=self.path.name, dir=str(self.path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def load(self) -> LiveAuthorizationState:
        if not self.path.exists():
            return LiveAuthorizationState()
        data = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise RuntimeError("invalid authorization state")
        allowed = set(LiveAuthorizationState.__dataclass_fields__)
        if set(data) - allowed:
            raise RuntimeError("unexpected authorization state fields")
        return LiveAuthorizationState(**data)


__all__ = ["LiveAuthorizationStateStore"]
