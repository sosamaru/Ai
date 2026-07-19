from datetime import UTC, datetime, timedelta

from aipro.us_stocks.paper_training import (
    PaperTrainingEvidence,
    evaluate_paper_training,
)


def evidence(**overrides):
    started = datetime(2026, 7, 1, tzinfo=UTC)
    values = {
        "started_at_utc": started.isoformat(),
        "evaluated_at_utc": (started + timedelta(days=31)).isoformat(),
        "completed_sessions": 22,
        "completed_orders": 80,
        "net_return_pct": 3.5,
        "maximum_drawdown_pct": 4.0,
        "worst_daily_return_pct": -1.5,
        "expectancy_per_trade_pct": 0.08,
        "stale_data_events": 0,
        "duplicate_order_events": 0,
        "unreconciled_order_events": 0,
    }
    values.update(overrides)
    return PaperTrainingEvidence(**values)


def test_valid_thirty_day_training_passes() -> None:
    decision = evaluate_paper_training(evidence())
    assert decision.passed is True
    assert decision.reasons == ()
    assert len(decision.evidence_fingerprint) == 64


def test_short_training_window_fails_closed() -> None:
    started = datetime(2026, 7, 1, tzinfo=UTC)
    decision = evaluate_paper_training(
        evidence(evaluated_at_utc=(started + timedelta(days=29)).isoformat())
    )
    assert decision.passed is False
    assert "MINIMUM_30_DAY_WINDOW_NOT_MET" in decision.reasons


def test_positive_return_does_not_override_safety_failures() -> None:
    decision = evaluate_paper_training(
        evidence(
            net_return_pct=25.0,
            maximum_drawdown_pct=12.0,
            duplicate_order_events=1,
            unreconciled_order_events=2,
        )
    )
    assert decision.passed is False
    assert "MAXIMUM_DRAWDOWN_EXCEEDED" in decision.reasons
    assert "DUPLICATE_ORDER_EVENTS_PRESENT" in decision.reasons
    assert "UNRECONCILED_ORDER_EVENTS_PRESENT" in decision.reasons


def test_non_positive_expectancy_fails_even_with_net_profit() -> None:
    decision = evaluate_paper_training(evidence(net_return_pct=2.0, expectancy_per_trade_pct=0.0))
    assert decision.passed is False
    assert "NON_POSITIVE_EXPECTANCY" in decision.reasons
