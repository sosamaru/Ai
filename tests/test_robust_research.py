from dataclasses import replace
from datetime import UTC, datetime, timedelta
import math
import sqlite3

import pytest

from aipro.backtest import BacktestBar, BacktestConfig, BacktestEngine
from aipro.models import Decision, Signal
from aipro.core.performance import ClosedTrade, EquityObservation, performance_report
from aipro.intelligence.calibration import fit_calibrator, reliability_report
from aipro.research.experiment_ledger import ExperimentLedger, ExperimentSpec
from aipro.research.robust_statistics import BootstrapPolicy, mean_interval, monte_carlo, paired_improvement, deflated_sharpe
from aipro.sqlite_utils import connect

START = datetime(2026, 1, 1, tzinfo=UTC)


def test_closed_backtest_pnl_includes_entry_fee_and_first_fill_drawdown():
    class Strategy:
        def decide(self, snapshot):
            return Decision(snapshot.symbol, Signal.BUY if snapshot.change_1h_pct > 0 else Signal.SELL, 1, "test")
    result = BacktestEngine(Strategy(), BacktestConfig(initial_cash_krw=10000, max_position_pct=1, fee_rate=.01, slippage_bps=0)).run([
        BacktestBar(START, "X", 100, 1, 1), BacktestBar(START + timedelta(hours=1), "X", 100, -1, 1)])
    assert result.trades[-1].realized_pnl_krw == pytest.approx(-199)
    assert result.final_equity_krw - result.initial_equity_krw == pytest.approx(-199)
    assert result.max_drawdown_pct == pytest.approx(-1.99)


@pytest.mark.parametrize("field", ["fee_rate", "slippage_bps", "initial_cash_krw", "max_position_pct"])
def test_backtest_nonfinite_policy_rejected(field):
    with pytest.raises(ValueError):
        BacktestConfig(**{field: float("nan")})


def test_block_bootstrap_reproducible_paired_and_negative_ev():
    values = [.01, -.005, .015, -.002] * 20
    assert mean_interval(values) == mean_interval(values)
    delta = paired_improvement(values, [r + .002 for r in values])
    assert delta["lower"] == pytest.approx(.002)
    assert mean_interval([-.01] * 40)["upper"] < 0
    many = mean_interval(values, BootstrapPolicy(trial_budget=5))
    assert many["confidence"] > mean_interval(values)["confidence"]


def test_monte_carlo_reports_survival_and_ruin_without_return_guarantees():
    safe = monte_carlo([.001] * 40)
    assert safe["capital_survival_probability"] == 1
    ruin = monte_carlo([-.20] * 40)
    assert ruin["capital_survival_probability"] == 0
    assert ruin["large_loss_probability"] == 1
    assert ruin["negative_terminal_return_probability"] == 1


@pytest.mark.parametrize("values", [[.01] * 3, [float("nan")] * 50, [float("inf")] * 50])
def test_bootstrap_rejects_insufficient_or_invalid_evidence(values):
    with pytest.raises(ValueError):
        mean_interval(values)


def test_bootstrap_rejects_false_tail_precision():
    with pytest.raises(ValueError, match="too few"):
        BootstrapPolicy(samples=100, trial_budget=20)


def test_deflated_sharpe_requires_all_trial_dispersion():
    values = [.01, -.009, .002, -.003] * 30
    single = deflated_sharpe(values, independent_trials=1, trial_sharpe_std=.3)
    searched = deflated_sharpe(values, independent_trials=20, trial_sharpe_std=.3)
    assert searched["probability"] < single["probability"]


def test_performance_uses_daily_closes_and_cost_inclusive_episodes():
    points = [EquityObservation((START + timedelta(days=i)).isoformat(), eq, .4)
              for i, eq in enumerate([100, 110, 99, 108.9])]
    trades = [ClosedTrade(points[1].at, 10, 100, "weak_bull", "M"), ClosedTrade(points[2].at, -11, 110, "sideways", "M")]
    report = performance_report(points, trades, domain="crypto", fee_cost=2, slippage_cost=1, turnover_notional=200)
    assert report["total_return"] == pytest.approx(.089)
    assert report["maximum_drawdown"] == pytest.approx(.1)
    assert report["profit_factor"] == pytest.approx(10 / 11)
    assert report["expected_value_per_trade"] == -.5
    assert report["cagr"] is None
    assert report["annualization_periods"] == 365
    assert report["fee_cost"] == 2
    assert report["exposure"] == pytest.approx(.4)


def test_intraday_ticks_do_not_fabricate_daily_sharpe():
    points = [EquityObservation((START + timedelta(seconds=i)).isoformat(), 100 + i) for i in range(100)]
    report = performance_report(points, domain="us_stock")
    assert report["sharpe_ratio"] is None and report["cagr"] is None
    assert report["number_of_trades"] == 0 and report["profit_factor"] is None


def spec(name="e", domain="us_stock"):
    return ExperimentSpec(name, domain, "a" * 64, "b" * 64, "v1", {"EV_lower": 0}, 2)


def test_experiment_rules_and_trial_budget_are_immutable(tmp_path):
    ledger = ExperimentLedger(tmp_path / "research.db")
    ledger.register(spec())
    with pytest.raises(ValueError, match="criteria changed"):
        ledger.register(replace(spec(), failure_policy={"EV_lower": -1}))
    ledger.reserve_trial("e", "first", {"x": 1})
    ledger.reserve_trial("e", "second", {"x": 2})
    with pytest.raises(ValueError, match="budget"):
        ledger.reserve_trial("e", "third", {})
    with connect(ledger.path) as db, pytest.raises(sqlite3.IntegrityError, match="immutable"):
        db.execute("DELETE FROM research_trials")


def test_holdout_remains_consumed_after_crash_and_dataset_rename(tmp_path):
    ledger = ExperimentLedger(tmp_path / "research.db")
    ledger.register(spec())
    ledger.reserve_trial("e", "M", {})
    ledger.open_holdout("e", "M", START, START + timedelta(days=30), "c" * 64)
    # No finish call: an interrupted evaluation must not reopen the holdout.
    ledger.register(replace(spec("renamed"), dataset_fingerprint="d" * 64))
    ledger.reserve_trial("renamed", "M", {})
    with pytest.raises(ValueError, match="overlaps"):
        ledger.open_holdout("renamed", "M", START + timedelta(days=1), START + timedelta(days=31), "c" * 64)
    with pytest.raises(ValueError, match="tuning is closed"):
        ledger.reserve_trial("e", "late", {})
    ledger.register(spec("crypto", "crypto"))
    ledger.reserve_trial("crypto", "M", {})
    ledger.open_holdout("crypto", "M", START, START + timedelta(days=30), "c" * 64)


def test_calibration_curve_includes_probability_one():
    report = reliability_report([0, .5, 1], [0, 1, 1])
    assert sum(x["count"] for x in report["reliability_curve"]) == 3
    assert report["brier_score"] == pytest.approx(.25 / 3)


def test_platt_fit_uses_separate_resolved_calibration_partition():
    p, y = [.9] * 100, [i % 2 for i in range(100)]
    args = dict(training_end=9, calibration_indices=range(10, 110), calibration_label_ends=range(11, 111), test_start=120)
    fitted = fit_calibrator(p, y, **args)
    assert abs(fitted.predict(.9) - .5) < .1
    with pytest.raises(ValueError, match="before test"):
        fit_calibrator(p, y, **{**args, "test_start": 110})
    with pytest.raises(ValueError, match="before test"):
        fit_calibrator(p, y, **{**args, "training_end": 10})


def test_isotonic_requires_large_sample_and_monotone_tied_groups():
    p, y = [.1, .9] * 500, [0, 1] * 500
    c = fit_calibrator(p, y, training_end=0, calibration_indices=range(1, 1001),
                       calibration_label_ends=range(2, 1002), test_start=1002, method="isotonic")
    assert c.predict(.1) <= c.predict(.5) <= c.predict(.9)
    with pytest.raises(ValueError, match="insufficient"):
        fit_calibrator(p[:100], y[:100], training_end=0, calibration_indices=range(1, 101),
                       calibration_label_ends=range(2, 102), test_start=102, method="isotonic")
