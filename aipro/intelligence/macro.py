from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Callable, Sequence
from urllib import parse, request


class MacroRegime(StrEnum):
    RISK_ON = "risk_on"
    NEUTRAL = "neutral"
    RISK_OFF = "risk_off"
    INSUFFICIENT_DATA = "insufficient_data"


@dataclass(frozen=True, slots=True)
class MacroObservation:
    series_id: str
    observed_at_utc: str
    value: float
    source: str = "fred"

    def __post_init__(self) -> None:
        if not self.series_id.strip():
            raise ValueError("series_id is required")
        observed = datetime.fromisoformat(self.observed_at_utc)
        if observed.tzinfo is None:
            raise ValueError("observed_at_utc must be timezone-aware")
        object.__setattr__(self, "series_id", self.series_id.strip().upper())


@dataclass(frozen=True, slots=True)
class MacroSnapshot:
    as_of_utc: str
    observations: tuple[MacroObservation, ...]
    regime: MacroRegime
    score: float
    eligible: bool
    ineligible_reason: str | None
    fingerprint: str


class FredClient:
    BASE_URL = "https://api.stlouisfed.org/fred/series/observations"

    def __init__(self, api_key: str, *, opener: Callable[..., Any] | None = None, timeout_sec: float = 10.0) -> None:
        if not api_key.strip():
            raise ValueError("FRED API key is required")
        if timeout_sec <= 0:
            raise ValueError("timeout_sec must be positive")
        self.api_key = api_key.strip()
        self._opener = opener or request.urlopen
        self.timeout_sec = timeout_sec

    def fetch_latest(self, series_id: str) -> MacroObservation:
        normalized = series_id.strip().upper()
        if not normalized:
            raise ValueError("series_id is required")
        query = parse.urlencode({
            "series_id": normalized,
            "api_key": self.api_key,
            "file_type": "json",
            "sort_order": "desc",
            "limit": "10",
        })
        with self._opener(f"{self.BASE_URL}?{query}", timeout=self.timeout_sec) as response:
            payload = json.loads(response.read().decode("utf-8"))
        observations = payload.get("observations", []) if isinstance(payload, dict) else []
        for item in observations:
            if not isinstance(item, dict) or item.get("value") in {None, "."}:
                continue
            date = datetime.fromisoformat(str(item["date"])).replace(tzinfo=UTC)
            return MacroObservation(normalized, date.isoformat(), float(item["value"]))
        raise RuntimeError(f"FRED series {normalized} has no usable observation")


def build_macro_snapshot(
    observations: Sequence[MacroObservation],
    *,
    as_of_utc: datetime,
    max_age_days: int = 45,
) -> MacroSnapshot:
    if as_of_utc.tzinfo is None:
        raise ValueError("as_of_utc must be timezone-aware")
    if max_age_days <= 0:
        raise ValueError("max_age_days must be positive")
    ordered = tuple(sorted(observations, key=lambda item: item.series_id))
    latest_by_series = {item.series_id: item for item in ordered}
    required = {"CPIAUCSL", "DFF", "UNRATE"}
    missing = sorted(required - set(latest_by_series))
    stale = [
        item.series_id
        for item in ordered
        if (as_of_utc.astimezone(UTC) - datetime.fromisoformat(item.observed_at_utc).astimezone(UTC)).days > max_age_days
    ]

    eligible = not missing and not stale
    reason: str | None = None
    if missing:
        reason = "MISSING_REQUIRED_SERIES"
    elif stale:
        reason = "STALE_MACRO_DATA"

    score = 0.0
    regime = MacroRegime.INSUFFICIENT_DATA
    if eligible:
        policy_rate = latest_by_series["DFF"].value
        unemployment = latest_by_series["UNRATE"].value
        cpi = latest_by_series["CPIAUCSL"].value
        score = round((4.5 - policy_rate) * 0.35 + (4.5 - unemployment) * 0.35 + (320.0 - cpi) / 100.0 * 0.30, 6)
        regime = MacroRegime.RISK_ON if score >= 0.35 else MacroRegime.RISK_OFF if score <= -0.35 else MacroRegime.NEUTRAL

    canonical = {
        "as_of_utc": as_of_utc.astimezone(UTC).replace(microsecond=0).isoformat(),
        "observations": [asdict(item) for item in ordered],
        "regime": regime.value,
        "score": score,
        "eligible": eligible,
        "ineligible_reason": reason,
    }
    fingerprint = hashlib.sha256(json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    return MacroSnapshot(
        as_of_utc=canonical["as_of_utc"],
        observations=ordered,
        regime=regime,
        score=score,
        eligible=eligible,
        ineligible_reason=reason,
        fingerprint=fingerprint,
    )


__all__ = ["FredClient", "MacroObservation", "MacroRegime", "MacroSnapshot", "build_macro_snapshot"]
