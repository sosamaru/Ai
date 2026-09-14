"""Authenticated Telegram control layer with a safe console fallback."""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any
from urllib import parse, request
from urllib.error import URLError

from aipro.app import TradingApplication
from aipro.crypto.live_approval import LiveApprovalStateMachine
from main import build_application

LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class TelegramCommandRouter:
    app: TradingApplication
    allowed_chat_ids: frozenset[int]
    approval: LiveApprovalStateMachine | None = field(init=False, default=None)

    def __post_init__(self) -> None:
        if getattr(self.app, "asset_class", None) != "us_stock":
            self.approval = LiveApprovalStateMachine(self.app.storage)

    def handle(self, chat_id: int, text: str) -> str:
        if chat_id not in self.allowed_chat_ids:
            LOGGER.warning("Rejected unauthorized Telegram chat_id=%s", chat_id)
            return "권한이 없습니다."

        if not text.strip():
            return "명령어를 입력하세요. /help를 사용하세요."
        command = text.strip().split(maxsplit=1)[0].split("@", maxsplit=1)[0].lower()
        if getattr(self.app, "asset_class", None) == "us_stock":
            return self._handle_us(command)
        if command == "/status":
            return self._format_status()
        if command == "/run_once":
            if self.app.risk.halted:
                return "HALTED 상태입니다. /go로 명시적으로 재개해야 합니다."
            self.app.run_once()
            return "1회 거래 사이클을 실행했습니다.\n\n" + self._format_status()
        if command == "/ai_upbit_go":
            status = self.approval.request()
            return (
                "업비트 LIVE 승인 요청을 기록했습니다. 실제 주문은 활성화되지 않았습니다.\n"
                f"만료: {status.expires_at_utc}\n"
                "계속하려면 만료 전에 /confirm을 입력하세요."
            )
        if command == "/confirm":
            try:
                status = self.approval.confirm()
            except RuntimeError:
                return "승인 순서가 올바르지 않거나 요청이 만료되었습니다. /ai_upbit_go부터 다시 시작하세요."
            return (
                "2단계 확인이 기록되었습니다. 실제 주문은 아직 활성화되지 않았습니다.\n"
                f"만료: {status.expires_at_utc}\n"
                "최종 단계로 /go를 입력하세요."
            )
        if command == "/go":
            approval_status = self.approval.status()
            if approval_status.stage == "CONFIRMED":
                self.approval.consume()
                return (
                    "3단계 승인 절차를 완료했습니다. 승인 의도만 기록되었으며, "
                    "실제 주문 제출 기능은 계속 비활성화되어 있습니다."
                )
            if approval_status.stage == "REQUESTED":
                return "먼저 /confirm을 입력해야 합니다."
            if not self.app.risk.halted:
                return "이미 실행 가능한 상태입니다. 기준금액은 변경하지 않았습니다."
            self.app.resume()
            return "HALTED를 해제하고 현재 평가금액으로 기준금액을 재설정했습니다."
        if command in {"/start", "/help"}:
            return (
                "AiPro 명령어\n"
                "/status - 현재 상태 조회\n"
                "/run_once - PAPER 거래 사이클 1회 실행\n"
                "/ai_upbit_go - 업비트 LIVE 승인 요청 시작\n"
                "/confirm - LIVE 승인 요청 2단계 확인\n"
                "/go - 승인 최종 단계 또는 HALTED 명시적 해제\n"
                "/help - 명령어 보기"
            )
        return "지원하지 않는 명령입니다. /help를 사용하세요."

    def _handle_us(self, command: str) -> str:
        if command in {"/status", "/portfolio"}:
            return self._format_us_status()
        if command == "/run_once":
            result = self.app.run_once()
            return f"로컬 모의 사이클: {result.get('reason', 'processed')}\n" + self._format_us_status()
        if command == "/halt":
            self.app.halt()
            return "신규 매수를 중단했습니다. 보유분은 다음 유효한 장중 시세에서 모의 청산을 시도합니다."
        if command == "/go":
            try:
                self.app.resume()
            except RuntimeError as exc:
                return f"재개 불가: {exc}"
            return "모의거래 중단을 해제했습니다. 일일 기준금액과 수익 목표 중단은 유지합니다."
        if command in {"/ai_upbit_go", "/confirm"}:
            return "미국 주식 전용 모의 운용입니다. 업비트 승인 명령은 적용되지 않습니다."
        return "미국 주식 PAPER 명령\n/status 또는 /portfolio\n/run_once\n/halt\n/go\n/help"

    def _format_us_status(self) -> str:
        status = self.app.status()
        lines = ["AiPro 미국 주식 · 로컬 모의거래", "외부 지원금: 1,000,000원 / 추가 입금: 0원",
                 f"전체 중단: {status.get('global_halt') or '없음'}"]
        if status.get("stale"):
            lines.append("주의: 마지막 평가 시세가 오래되었습니다.")
        if status.get("short_model_id"):
            model = status["short_model_id"]
            lines.append("단타 모델: " + ("미학습 규칙" if model == "untrained-rule-baseline" else model))
        if status.get("model_last_reason"):
            lines.append("모델 상태: " + status["model_last_reason"])
        if not status["sleeves"]:
            lines.append("시장 입력 대기 중입니다.")
        for key, label in (("short", "단타"), ("long", "장기")):
            book = status["sleeves"].get(key)
            if book:
                lines.append(f"{label}: 평가 {float(book['equity_krw']):,.0f}원 / 일간 {float(book['daily_return_pct']):+.2f}% / 보유 {len(book['positions'])}개")
                lines.append(f"  가용 현금 {float(book['cash_krw']):,.0f}원 / 미결제 {float(book['unsettled_krw']):,.0f}원 / 중단 {book['halt'] or ('목표 도달' if book['profit_stop'] else '없음')}")
        return "\n".join(lines)

    def _format_status(self) -> str:
        status = self.app.status()
        approval = self.approval.status()
        halt_text = "HALTED" if status["halted"] else "READY"
        return (
            f"AiPro 상태: {halt_text}\n"
            f"모드: {status['mode']}\n"
            f"KST 거래일: {status['trading_date']}\n"
            f"현금: {status['cash_krw']:,.0f} KRW\n"
            f"평가금액: {status['equity_krw']:,.0f} KRW\n"
            f"기준금액: {status['baseline_equity_krw']:,.0f} KRW\n"
            f"일일 수익률: {status['daily_return_pct']:.4f}%\n"
            f"보유 포지션: {status['positions']}개\n"
            f"LIVE 승인 단계: {approval.stage}"
        )


class TelegramBotClient:
    def __init__(self, token: str, timeout_sec: int) -> None:
        self.base_url = f"https://api.telegram.org/bot{token}"
        self.timeout_sec = timeout_sec
        self.offset = 0

    def _call(self, method: str, payload: dict[str, Any]) -> dict[str, Any]:
        encoded = parse.urlencode(payload).encode("utf-8")
        req = request.Request(f"{self.base_url}/{method}", data=encoded)
        try:
            with request.urlopen(req, timeout=self.timeout_sec + 10) as response:
                raw = response.read(1_000_001)
            if len(raw) > 1_000_000:
                raise ValueError("response too large")
            decoded = json.loads(raw)
        except (OSError, ValueError) as exc:
            # HTTP exception strings may contain the bot-token URL or raw body.
            raise RuntimeError(f"Telegram request failed ({type(exc).__name__})") from None
        if not isinstance(decoded, dict):
            raise RuntimeError("Telegram API returned a non-object response")
        if decoded.get("ok") is not True:
            raise RuntimeError("Telegram API rejected the request")
        return decoded

    def get_updates(self) -> list[dict[str, Any]]:
        result = self._call(
            "getUpdates",
            {"offset": self.offset, "timeout": self.timeout_sec, "allowed_updates": '["message"]'},
        )
        raw_updates = result.get("result", [])
        if not isinstance(raw_updates, list):
            raise RuntimeError("Telegram API result must be a list")

        updates: list[dict[str, Any]] = []
        rejected = 0
        seen: set[int] = set()
        for item in raw_updates:
            if (not isinstance(item, dict) or type(item.get("update_id")) is not int
                    or not self.offset <= item["update_id"] < 2**63):
                rejected += 1
                continue
            if item["update_id"] in seen:
                continue
            seen.add(item["update_id"])
            updates.append(item)
        if rejected:
            LOGGER.warning("Ignored %d malformed Telegram updates", rejected)
        if updates:
            self.offset = max(int(item["update_id"]) for item in updates) + 1
        return sorted(updates, key=lambda item: item["update_id"])

    def send_message(self, chat_id: int, text: str) -> None:
        self._call("sendMessage", {"chat_id": chat_id, "text": text})


def _run_polling(app: TradingApplication) -> int:
    settings = app.settings
    router = TelegramCommandRouter(app, settings.telegram_allowed_chat_ids)
    client = TelegramBotClient(
        settings.telegram_bot_token,
        min(settings.telegram_poll_timeout_sec, settings.paper_interval_seconds or settings.telegram_poll_timeout_sec),
    )
    LOGGER.info("AiPro Telegram polling started")
    next_cycle = time.monotonic()

    while True:
        try:
            if settings.paper_interval_seconds and time.monotonic() >= next_cycle:
                app.run_once()
                next_cycle = time.monotonic() + settings.paper_interval_seconds
            for update in client.get_updates():
                message = update.get("message") or {}
                if not isinstance(message, dict):
                    continue
                chat = message.get("chat") or {}
                if not isinstance(chat, dict):
                    continue
                chat_id = chat.get("id")
                text = message.get("text")
                if type(chat_id) is not int or not isinstance(text, str):
                    continue
                response = router.handle(chat_id, text)
                client.send_message(chat_id, response)
        except KeyboardInterrupt:
            LOGGER.info("AiPro Telegram polling stopped")
            return 0
        except (URLError, TimeoutError, RuntimeError, ValueError, OSError) as exc:
            LOGGER.error("Telegram polling error (%s)", type(exc).__name__)
            time.sleep(3)


def launch() -> int:
    app = build_application()
    LOGGER.info("AiPro starting through telegram.py")
    if not app.settings.telegram_bot_token:
        LOGGER.info("Telegram token not configured; running PAPER console execution")
        while True:
            try:
                result = app.run_once()
                if not app.settings.paper_interval_seconds:
                    if isinstance(result, dict) and result.get("processed") is False and result.get("reason") != "duplicate_frame":
                        return 1
                    return 0
                time.sleep(app.settings.paper_interval_seconds)
            except KeyboardInterrupt:
                return 0
            except (OSError, ValueError, RuntimeError) as exc:
                LOGGER.error("PAPER cycle stopped (%s)", type(exc).__name__)
                if not app.settings.paper_interval_seconds:
                    return 1
                time.sleep(app.settings.paper_interval_seconds)
    return _run_polling(app)
