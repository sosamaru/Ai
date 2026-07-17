"""Authenticated Telegram control layer with a safe console fallback."""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from typing import Any
from urllib import parse, request
from urllib.error import URLError

from aipro.app import TradingApplication
from main import build_application

LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class TelegramCommandRouter:
    app: TradingApplication
    allowed_chat_ids: frozenset[int]

    def handle(self, chat_id: int, text: str) -> str:
        if chat_id not in self.allowed_chat_ids:
            LOGGER.warning("Rejected unauthorized Telegram chat_id=%s", chat_id)
            return "권한이 없습니다."

        command = text.strip().split(maxsplit=1)[0].split("@", maxsplit=1)[0].lower()
        if command == "/status":
            return self._format_status()
        if command == "/run_once":
            if self.app.risk.halted:
                return "HALTED 상태입니다. /go로 명시적으로 재개해야 합니다."
            self.app.run_once()
            return "1회 거래 사이클을 실행했습니다.\n\n" + self._format_status()
        if command == "/go":
            if not self.app.risk.halted:
                return "이미 실행 가능한 상태입니다. 기준금액은 변경하지 않았습니다."
            self.app.resume()
            return "HALTED를 해제하고 현재 평가금액으로 기준금액을 재설정했습니다."
        if command in {"/start", "/help"}:
            return (
                "AiPro 명령어\n"
                "/status - 현재 상태 조회\n"
                "/run_once - PAPER 거래 사이클 1회 실행\n"
                "/go - HALTED 상태 명시적 해제\n"
                "/help - 명령어 보기"
            )
        return "지원하지 않는 명령입니다. /help를 사용하세요."

    def _format_status(self) -> str:
        status = self.app.status()
        halt_text = "HALTED" if status["halted"] else "READY"
        return (
            f"AiPro 상태: {halt_text}\n"
            f"모드: {status['mode']}\n"
            f"KST 거래일: {status['trading_date']}\n"
            f"현금: {status['cash_krw']:,.0f} KRW\n"
            f"평가금액: {status['equity_krw']:,.0f} KRW\n"
            f"기준금액: {status['baseline_equity_krw']:,.0f} KRW\n"
            f"일일 수익률: {status['daily_return_pct']:.4f}%\n"
            f"보유 포지션: {status['positions']}개"
        )


class TelegramBotClient:
    def __init__(self, token: str, timeout_sec: int) -> None:
        self.base_url = f"https://api.telegram.org/bot{token}"
        self.timeout_sec = timeout_sec
        self.offset = 0

    def _call(self, method: str, payload: dict[str, Any]) -> dict[str, Any]:
        encoded = parse.urlencode(payload).encode("utf-8")
        req = request.Request(f"{self.base_url}/{method}", data=encoded)
        with request.urlopen(req, timeout=self.timeout_sec + 10) as response:
            result = json.loads(response.read().decode("utf-8"))
        if not result.get("ok"):
            raise RuntimeError(f"Telegram API error: {result}")
        return result

    def get_updates(self) -> list[dict[str, Any]]:
        result = self._call(
            "getUpdates",
            {"offset": self.offset, "timeout": self.timeout_sec, "allowed_updates": '["message"]'},
        )
        updates = result.get("result", [])
        if updates:
            self.offset = max(item["update_id"] for item in updates) + 1
        return updates

    def send_message(self, chat_id: int, text: str) -> None:
        self._call("sendMessage", {"chat_id": chat_id, "text": text})


def _run_polling(app: TradingApplication) -> int:
    settings = app.settings
    router = TelegramCommandRouter(app, settings.telegram_allowed_chat_ids)
    client = TelegramBotClient(
        settings.telegram_bot_token,
        settings.telegram_poll_timeout_sec,
    )
    LOGGER.info("AiPro Telegram polling started")

    while True:
        try:
            for update in client.get_updates():
                message = update.get("message") or {}
                chat = message.get("chat") or {}
                chat_id = chat.get("id")
                text = message.get("text")
                if not isinstance(chat_id, int) or not isinstance(text, str):
                    continue
                response = router.handle(chat_id, text)
                client.send_message(chat_id, response)
        except KeyboardInterrupt:
            LOGGER.info("AiPro Telegram polling stopped")
            return 0
        except (URLError, TimeoutError, RuntimeError, json.JSONDecodeError) as exc:
            LOGGER.error("Telegram polling error: %s", exc)
            time.sleep(3)


def launch() -> int:
    app = build_application()
    LOGGER.info("AiPro starting through telegram.py")
    if not app.settings.telegram_bot_token:
        LOGGER.info("Telegram token not configured; running one console cycle")
        app.run_once()
        return 0
    return _run_polling(app)
