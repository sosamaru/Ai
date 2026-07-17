import pytest

from aipro.config import Settings


def test_defaults_are_safe(monkeypatch):
    for key in ("AIPRO_MODE", "AIPRO_LIVE_CONFIRM", "ENABLE_LIVE_TRADING"):
        monkeypatch.delenv(key, raising=False)
    settings = Settings.from_env()
    assert settings.mode == "PAPER"
    assert settings.enable_live_trading is False
    assert settings.live_confirm == "NO"


def test_live_mode_requires_both_guards(monkeypatch):
    monkeypatch.setenv("AIPRO_MODE", "LIVE")
    monkeypatch.setenv("AIPRO_LIVE_CONFIRM", "NO")
    monkeypatch.setenv("ENABLE_LIVE_TRADING", "0")
    with pytest.raises(RuntimeError):
        Settings.from_env()


def test_live_mode_can_only_start_with_explicit_double_confirmation(monkeypatch):
    monkeypatch.setenv("AIPRO_MODE", "LIVE")
    monkeypatch.setenv("AIPRO_LIVE_CONFIRM", "YES")
    monkeypatch.setenv("ENABLE_LIVE_TRADING", "1")
    settings = Settings.from_env()
    assert settings.mode == "LIVE"
    assert settings.enable_live_trading is True
