from main import build_application


def test_application_runs_one_safe_paper_cycle(monkeypatch, tmp_path):
    monkeypatch.setenv("AIPRO_MODE", "PAPER")
    monkeypatch.setenv("ENABLE_LIVE_TRADING", "0")
    monkeypatch.setenv("AIPRO_LIVE_CONFIRM", "NO")
    monkeypatch.setenv("AIPRO_LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("AIPRO_DB_PATH", str(tmp_path / "aipro.db"))

    app = build_application()
    app.run_once()

    assert app.settings.mode == "PAPER"
    assert app.settings.enable_live_trading is False
    assert (tmp_path / "aipro.db").exists()
