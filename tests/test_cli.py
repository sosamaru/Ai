from __future__ import annotations

from pathlib import Path

from aipro import cli


def test_cli_exposes_required_commands() -> None:
    parser = cli.build_parser()
    for command in ("doctor", "run", "compile", "smoke", "integration", "test", "all"):
        parsed = parser.parse_args([command])
        assert parsed.command == command


def test_integration_test_contract_points_to_existing_files() -> None:
    assert cli.INTEGRATION_TEST_PATHS
    assert all((cli.PROJECT_ROOT / Path(path)).is_file() for path in cli.INTEGRATION_TEST_PATHS)


def test_doctor_passes_in_supported_ci_environment(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("AIPRO_MODE", "PAPER")
    monkeypatch.setenv("AIPRO_LIVE_CONFIRM", "NO")
    monkeypatch.setenv("ENABLE_LIVE_TRADING", "0")
    monkeypatch.setenv("AIPRO_MARKET_DATA_PROVIDER", "DEMO")
    monkeypatch.setenv("AIPRO_TELEGRAM_BOT_TOKEN", "")
    monkeypatch.setenv("AIPRO_TELEGRAM_ALLOWED_CHAT_IDS", "")
    monkeypatch.setenv("AIPRO_DB_PATH", str(tmp_path / "aipro.db"))
    monkeypatch.setenv("AIPRO_LOG_DIR", str(tmp_path / "logs"))

    assert cli.doctor(require_pytest=True) == 0


def test_smoke_command_executes_isolated_paper_cycle() -> None:
    assert cli.smoke_test() == 0
