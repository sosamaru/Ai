from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest

from aipro.intelligence.macro import FredClient, MacroObservation, MacroRegime, build_macro_snapshot


class FakeResponse:
    def __init__(self, payload: object) -> None:
        self.payload = payload

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def observation(series_id: str, value: float, *, age_days: int = 0) -> MacroObservation:
    observed = datetime(2026, 7, 21, tzinfo=UTC) - timedelta(days=age_days)
    return MacroObservation(series_id, observed.isoformat(), value)


def test_fred_client_returns_latest_usable_observation() -> None:
    captured = {}

    def opener(url: str, timeout: float):
        captured["url"] = url
        return FakeResponse({"observations": [{"date": "2026-07-01", "value": "."}, {"date": "2026-06-01", "value": "4.1"}]})

    result = FredClient("secret", opener=opener).fetch_latest("unrate")
    assert result.series_id == "UNRATE"
    assert result.value == 4.1
    assert "api_key=secret" in captured["url"]
    assert "series_id=UNRATE" in captured["url"]


def test_macro_snapshot_is_deterministic_and_eligible() -> None:
    as_of = datetime(2026, 7, 21, tzinfo=UTC)
    values = (
        observation("CPIAUCSL", 315.0),
        observation("DFF", 4.0),
        observation("UNRATE", 4.0),
    )
    first = build_macro_snapshot(values, as_of_utc=as_of)
    second = build_macro_snapshot(tuple(reversed(values)), as_of_utc=as_of)

    assert first == second
    assert first.eligible is True
    assert first.regime in {MacroRegime.RISK_ON, MacroRegime.NEUTRAL, MacroRegime.RISK_OFF}
    assert len(first.fingerprint) == 64


def test_macro_snapshot_fails_closed_when_required_series_missing() -> None:
    snapshot = build_macro_snapshot(
        (observation("DFF", 4.0), observation("UNRATE", 4.0)),
        as_of_utc=datetime(2026, 7, 21, tzinfo=UTC),
    )
    assert snapshot.eligible is False
    assert snapshot.regime is MacroRegime.INSUFFICIENT_DATA
    assert snapshot.ineligible_reason == "MISSING_REQUIRED_SERIES"


def test_macro_snapshot_fails_closed_when_data_is_stale() -> None:
    snapshot = build_macro_snapshot(
        (
            observation("CPIAUCSL", 315.0, age_days=60),
            observation("DFF", 4.0),
            observation("UNRATE", 4.0),
        ),
        as_of_utc=datetime(2026, 7, 21, tzinfo=UTC),
        max_age_days=45,
    )
    assert snapshot.eligible is False
    assert snapshot.ineligible_reason == "STALE_MACRO_DATA"


def test_naive_timestamp_is_rejected() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        MacroObservation("DFF", "2026-07-21T00:00:00", 4.0)
