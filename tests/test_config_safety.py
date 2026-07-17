from __future__ import annotations

import pytest

from aipro.config import Settings


def test_defaults_are_safe(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "AIPRO_MODE",
        "AIPRO_INITIAL_CASH_KRW",
        "AIPRO_MAX_POSITIONS",
        "AIPRO_MAX_POSITION_PCT",
        "AIPRO_DAILY_LOSS_LIMIT_PCT",
        "AIPRO_MIN_ORDER_KRW",
        "AIPRO_LIVE_CONFIRM",
        "ENABLE_LIVE_TRADING",
    ):
        monkeypatch.delenv(name, raising=False)

    settings = Settings.from_env()

    assert settings.mode == "PAPER"
    assert settings.live_confirm == "NO"
    assert settings.enable_live_trading is False
    assert settings.daily_loss_limit_pct < 0


def test_live_requires_both_guards(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AIPRO_MODE", "LIVE")
    monkeypatch.setenv("AIPRO_LIVE_CONFIRM", "YES")
    monkeypatch.setenv("ENABLE_LIVE_TRADING", "0")

    with pytest.raises(RuntimeError, match="LIVE blocked"):
        Settings.from_env()


def test_live_can_only_pass_when_both_guards_are_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AIPRO_MODE", "LIVE")
    monkeypatch.setenv("AIPRO_LIVE_CONFIRM", "YES")
    monkeypatch.setenv("ENABLE_LIVE_TRADING", "1")

    settings = Settings.from_env()

    assert settings.mode == "LIVE"
    assert settings.enable_live_trading is True


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("max_positions", 0, "max_positions"),
        ("max_position_pct", 0.0, "max_position_pct"),
        ("max_position_pct", 1.01, "max_position_pct"),
        ("daily_loss_limit_pct", 0.0, "daily_loss_limit_pct"),
    ],
)
def test_invalid_risk_settings_are_rejected(field: str, value: object, message: str) -> None:
    values = {
        "max_positions": 2,
        "max_position_pct": 0.40,
        "daily_loss_limit_pct": -10.0,
    }
    values[field] = value

    settings = Settings(**values)

    with pytest.raises(ValueError, match=message):
        settings.validate()
