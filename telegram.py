"""Telegram entry layer.

The command processor is fully testable without a Telegram token. Network polling
will be connected only after credentials are supplied through environment secrets.
"""
from __future__ import annotations

import logging

from aipro.commands import CommandProcessor
from main import build_application


def launch(command: str | None = None) -> int:
    app = build_application()
    processor = CommandProcessor(app)
    logging.getLogger(__name__).info("AiPro starting through telegram.py")
    if command is not None:
        logging.getLogger(__name__).info("command result: %s", processor.handle(command))
    else:
        app.run_once()
    return 0
