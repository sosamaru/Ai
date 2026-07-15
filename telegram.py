"""Optional Telegram entry layer; console mode works without a token."""
from __future__ import annotations

import logging

from main import build_application


def launch() -> int:
    app = build_application()
    logging.getLogger(__name__).info("AiPro starting through telegram.py")
    app.run_once()
    return 0
