from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Callable

from aipro.storage import Storage

APPROVAL_STATE_KEY = "crypto.live_approval"


@dataclass(frozen=True, slots=True)
class LiveApprovalStatus:
    stage: str
    requested_at_utc: str | None
    confirmed_at_utc: str | None
    expires_at_utc: str | None

    @property
    def active(self) -> bool:
        return self.stage in {"REQUESTED", "CONFIRMED"}


class LiveApprovalStateMachine:
    """Restart-safe, expiring approval sequence for future crypto LIVE enablement.

    This component only records authorization intent. It does not enable LIVE mode,
    submit orders, or bypass any readiness guard.
    """

    def __init__(
        self,
        storage: Storage,
        *,
        ttl_seconds: int = 300,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        self.storage = storage
        self.ttl_seconds = ttl_seconds
        self._clock = clock or (lambda: datetime.now(UTC))

    def _now(self) -> datetime:
        value = self._clock()
        if value.tzinfo is None:
            raise ValueError("approval clock must return a timezone-aware datetime")
        return value.astimezone(UTC)

    def _empty(self) -> LiveApprovalStatus:
        return LiveApprovalStatus("IDLE", None, None, None)

    def _load_raw(self) -> LiveApprovalStatus:
        raw = self.storage.get_state(APPROVAL_STATE_KEY)
        if not raw:
            return self._empty()
        try:
            payload = json.loads(raw)
            status = LiveApprovalStatus(
                stage=str(payload["stage"]),
                requested_at_utc=payload.get("requested_at_utc"),
                confirmed_at_utc=payload.get("confirmed_at_utc"),
                expires_at_utc=payload.get("expires_at_utc"),
            )
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            self.clear(reason="invalid_persisted_state")
            return self._empty()
        if status.stage not in {"IDLE", "REQUESTED", "CONFIRMED"}:
            self.clear(reason="invalid_persisted_stage")
            return self._empty()
        return status

    def _persist(self, status: LiveApprovalStatus, event: str) -> None:
        payload = {
            "stage": status.stage,
            "requested_at_utc": status.requested_at_utc,
            "confirmed_at_utc": status.confirmed_at_utc,
            "expires_at_utc": status.expires_at_utc,
        }
        self.storage.set_state(APPROVAL_STATE_KEY, json.dumps(payload, sort_keys=True))
        self.storage.record(event, json.dumps(payload, sort_keys=True))

    def status(self) -> LiveApprovalStatus:
        status = self._load_raw()
        if not status.active or status.expires_at_utc is None:
            return status
        expires = datetime.fromisoformat(status.expires_at_utc)
        if expires.tzinfo is None or self._now() >= expires.astimezone(UTC):
            self.clear(reason="expired")
            return self._empty()
        return status

    def request(self) -> LiveApprovalStatus:
        now = self._now()
        expires = now + timedelta(seconds=self.ttl_seconds)
        status = LiveApprovalStatus(
            stage="REQUESTED",
            requested_at_utc=now.isoformat(),
            confirmed_at_utc=None,
            expires_at_utc=expires.isoformat(),
        )
        self._persist(status, "crypto_live_approval_requested")
        return status

    def confirm(self) -> LiveApprovalStatus:
        current = self.status()
        if current.stage != "REQUESTED":
            raise RuntimeError("live approval must be requested before confirmation")
        now = self._now()
        status = LiveApprovalStatus(
            stage="CONFIRMED",
            requested_at_utc=current.requested_at_utc,
            confirmed_at_utc=now.isoformat(),
            expires_at_utc=current.expires_at_utc,
        )
        self._persist(status, "crypto_live_approval_confirmed")
        return status

    def consume(self) -> LiveApprovalStatus:
        current = self.status()
        if current.stage != "CONFIRMED":
            raise RuntimeError("live approval must be confirmed before finalization")
        self.clear(reason="consumed")
        return current

    def clear(self, *, reason: str) -> None:
        empty = self._empty()
        self.storage.set_state(APPROVAL_STATE_KEY, json.dumps({
            "stage": empty.stage,
            "requested_at_utc": None,
            "confirmed_at_utc": None,
            "expires_at_utc": None,
        }, sort_keys=True))
        self.storage.record(
            "crypto_live_approval_cleared",
            json.dumps({"reason": reason}, sort_keys=True),
        )


__all__ = [
    "APPROVAL_STATE_KEY",
    "LiveApprovalStateMachine",
    "LiveApprovalStatus",
]
