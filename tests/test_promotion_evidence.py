"""Invented evidence exercises gates; never actual market/PAPER performance."""
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from aipro.core.performance import ClosedTrade, EquityObservation
from aipro.intelligence.promotion import PerformanceEvidence, PaperPromotionStore, evaluate_promotion

START = datetime(2025, 1, 1, tzinfo=UTC)


def track(model, start=START, better=False, phase="oos"):
    equity = 10000.
    points, trades = [EquityObservation(start.isoformat(), equity)], []
    for i in range(80):
        at = (start + timedelta(days=i + 1)).isoformat()
        change = ((.008 if i % 2 == 0 else -.002) if better else (.006 if i % 2 == 0 else -.004))
        pnl = equity * change
        for j in range(2):
            trades.append(ClosedTrade(at, pnl / 2, equity / 2, "weak_bull" if i // 2 % 2 else "sideways", model))
        equity += pnl
        points.append(EquityObservation(at, equity, .5))
    return PerformanceEvidence("us_stock", model * 64, "d" * 64, phase, tuple(points), tuple(trades),
        100., 100., 20000., .15, .05, .1, .8, False, points[0].at, points[-1].at)


def evidence():
    return track("a"), track("b", better=True), track("b", START + timedelta(days=90), True, "shadow")


def test_paper_promotion_requires_full_oos_and_elapsed_shadow_and_is_atomic(tmp_path):
    old, new, shadow = evidence()
    now = START + timedelta(days=180)
    paired = track("a", START + timedelta(days=90), False, "shadow")
    decision = evaluate_promotion(old, new, shadow, now=now, champion_shadow=paired)
    assert decision["approved"], decision["reasons"]
    store = PaperPromotionStore(tmp_path / "models.db")
    store.initialize("us_stock", old.model_fingerprint)
    store.compare_and_promote(old, new, shadow, now=now, champion_shadow=paired)
    assert store.current("us_stock") == new.model_fingerprint
    assert store.current("crypto") is None
    with pytest.raises(ValueError, match="changed"):
        store.compare_and_promote(old, new, shadow, now=now, champion_shadow=paired)


def test_historical_winner_cannot_promote_without_beating_current_shadow():
    old, new, shadow = evidence()
    now = START + timedelta(days=180)
    assert not evaluate_promotion(old, new, shadow, now=now)["approved"]
    paired = replace(shadow, model_fingerprint=old.model_fingerprint)
    result = evaluate_promotion(old, new, shadow, now=now, champion_shadow=paired)
    assert not result["approved"]
    assert "shadow_return_or_drawdown_not_better" in result["reasons"]


@pytest.mark.parametrize("change,reason", [
    ({"synthetic": True}, "synthetic"),
    ({"brier": .4}, "calibration"),
    ({"stress_net_return": -.01}, "cost_or_walk"),
    ({"positive_walk_forward_fraction": .2}, "cost_or_walk"),
    ({"trades": ()}, "insufficient_closed"),
    ({"captured_until": (START + timedelta(days=90)).isoformat()}, "elapsed"),
])
def test_bad_shadow_evidence_cannot_replace_champion(change, reason):
    old, new, shadow = evidence()
    result = evaluate_promotion(old, new, replace(shadow, **change), now=START + timedelta(days=180))
    assert not result["approved"] and any(reason in r for r in result["reasons"])


def test_future_or_mismatched_portfolio_samples_rejected():
    old, new, shadow = evidence()
    with pytest.raises(ValueError, match="future"):
        evaluate_promotion(old, new, shadow, now=START)
    with pytest.raises(ValueError, match="timestamps"):
        evaluate_promotion(old, replace(new, points=new.points[1:]), shadow, now=START + timedelta(days=180))
    with pytest.raises(ValueError, match="domains"):
        evaluate_promotion(old, replace(new, domain="crypto"), shadow, now=START + timedelta(days=180))
