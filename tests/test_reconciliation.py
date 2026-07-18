from datetime import date

import pytest

from aipro.app import TradingApplication
from aipro.broker import PaperBroker, Position
from aipro.config import Settings
from aipro.reconciliation import reconcile_paper_account
from aipro.storage import Storage


def test_reconciliation_accepts_consistent_account(tmp_path) -> None:
    storage = Storage(tmp_path / "aipro.db")
    broker = PaperBroker.restore(1_000_000, storage)

    broker.submit_buy("order-buy", "KRW-BTC", 100_000_000.0, 400_000)
    report = reconcile_paper_account(broker, 1_000_000)

    assert report.is_consistent is True
    assert report.issues == ()
    assert report.expected_cash_krw == pytest.approx(600_000.0)


def test_reconciliation_detects_cash_tampering_without_mutation(tmp_path) -> None:
    storage = Storage(tmp_path / "aipro.db")
    broker = PaperBroker.restore(1_000_000, storage)
    broker.submit_buy("order-buy", "KRW-BTC", 100_000_000.0, 400_000)
    broker.cash_krw += 1_000
    cash_before = broker.cash_krw

    report = reconcile_paper_account(broker, 1_000_000)

    assert report.is_consistent is False
    assert {issue.code for issue in report.issues} == {"CASH_MISMATCH"}
    assert broker.cash_krw == cash_before


def test_reconciliation_detects_position_quantity_tampering(tmp_path) -> None:
    storage = Storage(tmp_path / "aipro.db")
    broker = PaperBroker.restore(1_000_000, storage)
    broker.submit_buy("order-buy", "KRW-BTC", 100_000_000.0, 400_000)
    broker.positions["KRW-BTC"] = Position(quantity=0.001, average_price=100_000_000.0)

    report = reconcile_paper_account(broker, 1_000_000)

    assert report.is_consistent is False
    issue = next(issue for issue in report.issues if issue.code == "POSITION_QUANTITY_MISMATCH")
    assert issue.symbol == "KRW-BTC"
    assert issue.expected == pytest.approx(0.004)
    assert issue.actual == pytest.approx(0.001)


def test_application_status_exposes_reconciliation_summary(tmp_path) -> None:
    settings = Settings(
        initial_cash_krw=1_000_000,
        db_path=tmp_path / "aipro.db",
        log_dir=tmp_path / "logs",
    )
    app = TradingApplication(settings, date_provider=lambda: date(2026, 7, 18))
    app.run_once()

    status = app.status()
    details = app.reconciliation_status()

    assert status["reconciliation_ok"] is True
    assert status["reconciliation_issue_count"] == 0
    assert details["consistent"] is True
    assert details["issues"] == []
