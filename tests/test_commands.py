import json

from aipro.app import TradingApplication
from aipro.commands import CommandProcessor
from aipro.config import Settings


def test_command_processor_controls_application(tmp_path):
    app = TradingApplication(Settings(db_path=tmp_path / "app.db", log_dir=tmp_path / "logs"))
    commands = CommandProcessor(app)

    assert commands.handle("/pause") == "PAUSED"
    assert app.status()["mode"] == "PAUSED"
    assert commands.handle("/resume") == "RUNNING"
    assert commands.handle("/halt") == "HALTED"
    assert app.status()["mode"] == "HALTED"
    assert commands.handle("/resume") == "RUNNING"
    assert app.status()["mode"] == "HALTED"
    assert commands.handle("/go") == "RUNNING"
    assert app.status()["mode"] == "RUNNING"


def test_status_and_unknown_commands(tmp_path):
    app = TradingApplication(Settings(db_path=tmp_path / "app.db", log_dir=tmp_path / "logs"))
    commands = CommandProcessor(app)
    payload = json.loads(commands.handle("/status"))
    assert payload["mode"] == "RUNNING"
    assert commands.handle("/what") == "UNKNOWN_COMMAND"
    assert "/status" in commands.handle("/help")
