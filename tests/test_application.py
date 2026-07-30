from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _source(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_entrypoint_chain_preserves_run_telegram_main_application_contract():
    run_source = _source("run.py")
    telegram_source = _source("telegram.py")
    main_source = _source("main.py")

    assert "from aipro.env_loader import load_env_file" in run_source
    assert "from telegram import launch" in run_source
    assert "load_env_file()" in run_source
    assert "raise SystemExit(launch())" in run_source

    assert "from main import build_application" in telegram_source
    assert "def launch() -> int:" in telegram_source
    assert "app = build_application()" in telegram_source

    assert "from aipro.crypto.application import TradingApplication" in main_source
    assert "def build_application() -> TradingApplication:" in main_source
    assert "return TradingApplication(settings)" in main_source
