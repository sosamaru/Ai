from __future__ import annotations

from dataclasses import dataclass, field

from telegram import TelegramCommandRouter


@dataclass
class FakeRisk:
    halted: bool = False


@dataclass
class FakeApp:
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


def test_unauthorized_chat_is_rejected() -> None:
    app = FakeApp()
    router = TelegramCommandRouter(app, frozenset({123}))  # type: ignore[arg-type]

    response = router.handle(999, "/status")

    assert response == "권한이 없습니다."
    assert app.run_count == 0
    assert app.resume_count == 0


def test_authorized_status_returns_safe_summary() -> None:
    app = FakeApp()
    router = TelegramCommandRouter(app, frozenset({123}))  # type: ignore[arg-type]

    response = router.handle(123, "/status")

    assert "AiPro 상태: READY" in response
    assert "모드: PAPER" in response
    assert "평가금액: 1,000,000 KRW" in response


def test_run_once_is_blocked_while_halted() -> None:
    app = FakeApp(risk=FakeRisk(halted=True))
    router = TelegramCommandRouter(app, frozenset({123}))  # type: ignore[arg-type]

    response = router.handle(123, "/run_once")

    assert "HALTED" in response
    assert app.run_count == 0


def test_run_once_executes_when_ready() -> None:
    app = FakeApp()
    router = TelegramCommandRouter(app, frozenset({123}))  # type: ignore[arg-type]

    response = router.handle(123, "/run_once")

    assert app.run_count == 1
    assert "1회 거래 사이클" in response


def test_go_only_resumes_halted_application() -> None:
    app = FakeApp()
    router = TelegramCommandRouter(app, frozenset({123}))  # type: ignore[arg-type]

    already_ready = router.handle(123, "/go")
    assert "기준금액은 변경하지 않았습니다" in already_ready
    assert app.resume_count == 0

    app.risk.halted = True
    resumed = router.handle(123, "/go")
    assert "HALTED를 해제" in resumed
    assert app.resume_count == 1
    assert app.risk.halted is False


def test_bot_suffix_is_accepted() -> None:
    app = FakeApp()
    router = TelegramCommandRouter(app, frozenset({123}))  # type: ignore[arg-type]

    response = router.handle(123, "/status@AiProBot")

    assert "AiPro 상태" in response
