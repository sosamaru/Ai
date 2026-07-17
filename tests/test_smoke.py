from main import build_application


def test_application_builds_in_paper_mode(monkeypatch, tmp_path):
    monkeypatch.setenv("AIPRO_MODE", "PAPER")
    monkeypatch.setenv("ENABLE_LIVE_TRADING", "0")
    monkeypatch.setenv("AIPRO_LIVE_CONFIRM", "NO")
    monkeypatch.setenv("AIPRO_LOG_DIR", str(tmp_path / "logs"))
    app = build_application()
    assert app is not None
