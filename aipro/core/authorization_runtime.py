from __future__ import annotations

import json
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from aipro.core.auth_adapters import AuthorizationAuditEvent, AuthorizationAuditStore
from aipro.core.live_authorization import LiveAuthorizationManager, LiveAuthorizationState


class AuthorizationStateStore:
    """Atomic JSON persistence for authorization state. OTP plaintext is never present."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def load(self) -> LiveAuthorizationState:
        if not self.path.exists():
            return LiveAuthorizationState()
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise RuntimeError("invalid authorization state file")
        return LiveAuthorizationState(**payload)

    def save(self, state: LiveAuthorizationState) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(json.dumps(asdict(state), sort_keys=True, separators=(",", ":")), encoding="utf-8")
        temporary.replace(self.path)


class PersistedAuthorizationRuntime:
    """Persists state and appends audit evidence after every successful transition."""

    def __init__(self, *, manager: LiveAuthorizationManager, state_store: AuthorizationStateStore, audit_store: AuthorizationAuditStore) -> None:
        self.manager = manager
        self.state_store = state_store
        self.audit_store = audit_store
        self.manager.state = self.state_store.load()

    def _record(self, event_type: str, *, reason: str = "", now_utc: datetime | None = None) -> None:
        now = (now_utc or datetime.now(UTC)).astimezone(UTC)
        self.state_store.save(self.manager.state)
        self.audit_store.append(
            AuthorizationAuditEvent(
                event_type=event_type,
                created_at_utc=now.isoformat(),
                stage=self.manager.state.stage.value,
                recipient_hash=self.manager.recipient_hash,
                reason=reason,
            )
        )

    def request_email_otp(self, *, now_utc: datetime | None = None) -> str:
        result = self.manager.request_email_otp(now_utc=now_utc)
        self._record(result, now_utc=now_utc)
        return result

    def verify_email_otp(self, code: str, *, now_utc: datetime | None = None) -> str:
        result = self.manager.verify_email_otp(code, now_utc=now_utc)
        self._record(result, now_utc=now_utc)
        return result

    def verify_second_factor(self, code: str, *, now_utc: datetime | None = None) -> str:
        result = self.manager.verify_second_factor(code, now_utc=now_utc)
        self._record(result, now_utc=now_utc)
        return result

    def revoke(self, reason: str, *, now_utc: datetime | None = None) -> str:
        result = self.manager.revoke(reason, now_utc=now_utc)
        self._record(result, reason=reason, now_utc=now_utc)
        return result

    def require_active(self, *, now_utc: datetime | None = None) -> None:
        try:
            self.manager.require_active(now_utc=now_utc)
        except PermissionError:
            self.state_store.save(self.manager.state)
            raise


__all__ = ["AuthorizationStateStore", "PersistedAuthorizationRuntime"]
