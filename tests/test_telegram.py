from __future__ import annotations

from dataclasses import dataclass, field

from aipro.storage import Storage
from telegram import TelegramCommandRouter


@dataclass
class FakeRisk:
    halted: bool = False


@dataclass
class FakeApp:
    storage: Storage
    risk: FakeRisk = field(default_factory=FakeRisk)
    run_count: int = 0
    resume_count: int = 0

    def status(self) -> dict[str, object]:
        return {
            "mode": "PAPER",
            "halted": self.risk.halted,
            "trading_date": "2026-07-17",
            "cash_krw": 800000.0,
            "equity_krw": 1000000.0,
            "baseline_equity_krw": 1000000.0,
            "daily_return_pct": 0.0,
            "positions": 1,
        }

    def run_once(self) -> None:
        self.run_count += 1

    def resume(self) -> None:
        self.resume_count += 1
        self.risk.halted = False


def app(tmp_path) -> FakeApp:
    return FakeApp(storage=Storage(tmp_path / "telegram.db"))


def test_unauthorized_chat_is_rejected(tmp_path) -> None:
    fake = app(tmp_path)
    router = TelegramCommandRouter(fake, frozenset({123}))  # type: ignore[arg-type]

    response = router.handle(999, "/status")

    assert response == "권한이 없습니다."
    assert fake.run_count == 0
    assert fake.resume_count == 0


def test_authorized_status_returns_safe_summary(tmp_path) -> None:
    fake = app(tmp_path)
    router = TelegramCommandRouter(fake, frozenset({123}))  # type: ignore[arg-type]

    response = router.handle(123, "/status")

    assert "AiPro 상태: READY" in response
    assert "모드: PAPER" in response
    assert "평가금액: 1,000,000 KRW" in response
    assert "LIVE 승인 단계: IDLE" in response


def test_run_once_is_blocked_while_halted(tmp_path) -> None:
    fake = app(tmp_path)
    fake.risk.halted = True
    router = TelegramCommandRouter(fake, frozenset({123}))  # type: ignore[arg-type]

    response = router.handle(123, "/run_once")

    assert "HALTED" in response
    assert fake.run_count == 0


def test_run_once_executes_when_ready(tmp_path) -> None:
    fake = app(tmp_path)
    router = TelegramCommandRouter(fake, frozenset({123}))  # type: ignore[arg-type]

    response = router.handle(123, "/run_once")

    assert fake.run_count == 1
    assert "1회 거래 사이클" in response


def test_go_only_resumes_halted_application_without_active_approval(tmp_path) -> None:
    fake = app(tmp_path)
    router = TelegramCommandRouter(fake, frozenset({123}))  # type: ignore[arg-type]

    already_ready = router.handle(123, "/go")
    assert "기준금액은 변경하지 않았습니다" in already_ready
    assert fake.resume_count == 0

    fake.risk.halted = True
    resumed = router.handle(123, "/go")
    assert "HALTED를 해제" in resumed
    assert fake.resume_count == 1
    assert fake.risk.halted is False


def test_live_approval_requires_request_confirm_go_sequence(tmp_path) -> None:
    fake = app(tmp_path)
    router = TelegramCommandRouter(fake, frozenset({123}))  # type: ignore[arg-type]

    invalid_confirm = router.handle(123, "/confirm")
    assert "순서가 올바르지 않" in invalid_confirm

    requested = router.handle(123, "/ai_upbit_go")
    assert "승인 요청" in requested
    assert router.handle(123, "/go") == "먼저 /confirm을 입력해야 합니다."

    confirmed = router.handle(123, "/confirm")
    assert "2단계" in confirmed

    finalized = router.handle(123, "/go")
    assert "3단계 승인 절차" in finalized
    assert "실제 주문 제출 기능은 계속 비활성화" in finalized
    assert fake.resume_count == 0


def test_approval_state_survives_router_restart(tmp_path) -> None:
    fake = app(tmp_path)
    first = TelegramCommandRouter(fake, frozenset({123}))  # type: ignore[arg-type]
    first.handle(123, "/ai_upbit_go")

    second = TelegramCommandRouter(fake, frozenset({123}))  # type: ignore[arg-type]
    assert "2단계" in second.handle(123, "/confirm")


def test_bot_suffix_is_accepted(tmp_path) -> None:
    fake = app(tmp_path)
    router = TelegramCommandRouter(fake, frozenset({123}))  # type: ignore[arg-type]

    response = router.handle(123, "/status@AiProBot")
    assert "AiPro 상태" in response
