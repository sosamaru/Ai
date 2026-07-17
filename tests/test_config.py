from __future__ import annotations

import pytest

from aipro.config import Settings


_ENV_KEYS = (
    "AIPRO_MODE",
    "AIPRO_INITIAL_CASH_KRW",
    "AIPRO_MAX_POSITIONS",
    "AIPRO_MAX_POSITION_PCT",
    "AIPRO_DAILY_LOSS_LIMIT_PCT",
    "AIPRO_MIN_ORDER_KRW",
    "AIPRO_DB_PATH",
    "AIPRO_LOG_DIR",
    "AIPRO_LOG_LEVEL",
    "AIPRO_LIVE_CONFIRM",
    "ENABLE_LIVE_TRADING",
    "AIPRO_TELEGRAM_BOT_TOKEN",
    "AIPRO_TELEGRAM_ALLOWED_CHAT_IDS",
    "AIPRO_TELEGRAM_POLL_TIMEOUT_SEC",
)


def _clear_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in _ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


def test_defaults_are_safe_and_paper_only(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_environment(monkeypatch)

    settings = Settings.from_env()

    assert settings.mode == "PAPER"
    assert settings.live_confirm == "NO"
    assert settings.enable_live_trading is False
    assert settings.daily_loss_limit_pct < 0
    assert settings.min_order_krw >= 5_000
    assert settings.telegram_bot_token == ""
    assert settings.telegram_allowed_chat_ids == frozenset()


@pytest.mark.parametrize("mode", ["paper", "PAPER"])
def test_paper_mode_is_case_insensitive(
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
) -> None:
    _clear_environment(monkeypatch)
    monkeypatch.setenv("AIPRO_MODE", mode)

    assert Settings.from_env().mode == "PAPER"


def test_live_mode_requires_both_guards(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_environment(monkeypatch)
    monkeypatch.setenv("AIPRO_MODE", "LIVE")

    with pytest.raises(RuntimeError, match="LIVE blocked"):
        Settings.from_env()

    monkeypatch.setenv("AIPRO_LIVE_CONFIRM", "YES")
    with pytest.raises(RuntimeError, match="LIVE blocked"):
        Settings.from_env()

    monkeypatch.delenv("AIPRO_LIVE_CONFIRM")
    monkeypatch.setenv("ENABLE_LIVE_TRADING", "1")
    with pytest.raises(RuntimeError, match="LIVE blocked"):
        Settings.from_env()


def test_live_mode_accepts_only_explicit_double_confirmation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_environment(monkeypatch)
    monkeypatch.setenv("AIPRO_MODE", "LIVE")
    monkeypatch.setenv("AIPRO_LIVE_CONFIRM", "YES")
    monkeypatch.setenv("ENABLE_LIVE_TRADING", "1")

    settings = Settings.from_env()

    assert settings.mode == "LIVE"
    assert settings.live_confirm == "YES"
    assert settings.enable_live_trading is True


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("AIPRO_MODE", "INVALID", "AIPRO_MODE"),
        ("AIPRO_MAX_POSITIONS", "0", "max_positions"),
        ("AIPRO_MAX_POSITION_PCT", "0", "max_position_pct"),
        ("AIPRO_MAX_POSITION_PCT", "1.01", "max_position_pct"),
        ("AIPRO_DAILY_LOSS_LIMIT_PCT", "0", "daily_loss_limit_pct"),
        ("AIPRO_TELEGRAM_POLL_TIMEOUT_SEC", "0", "telegram_poll_timeout_sec"),
        ("AIPRO_TELEGRAM_POLL_TIMEOUT_SEC", "51", "telegram_poll_timeout_sec"),
    ],
)
def test_invalid_risk_settings_are_rejected(
    monkeypatch: pytest.MonkeyPatch,
    field: str,
    value: str,
    message: str,
) -> None:
    _clear_environment(monkeypatch)
    monkeypatch.setenv(field, value)

    with pytest.raises(ValueError, match=message):
        Settings.from_env()


def test_telegram_token_requires_authorized_chat_ids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_environment(monkeypatch)
    monkeypatch.setenv("AIPRO_TELEGRAM_BOT_TOKEN", "secret-token")

    with pytest.raises(RuntimeError, match="Telegram blocked"):
        Settings.from_env()


def test_telegram_chat_ids_are_parsed_and_deduplicated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_environment(monkeypatch)
    monkeypatch.setenv("AIPRO_TELEGRAM_BOT_TOKEN", "secret-token")
    monkeypatch.setenv("AIPRO_TELEGRAM_ALLOWED_CHAT_IDS", "123, 456,123")

    settings = Settings.from_env()

    assert settings.telegram_allowed_chat_ids == frozenset({123, 456})


def test_invalid_telegram_chat_id_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_environment(monkeypatch)
    monkeypatch.setenv("AIPRO_TELEGRAM_ALLOWED_CHAT_IDS", "123,not-a-number")

    with pytest.raises(ValueError, match="must contain integers"):
        Settings.from_env()
