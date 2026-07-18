from __future__ import annotations

from datetime import datetime, timezone

import pytest

from aipro.backtest import BacktestResult
from aipro.readiness import (
    PaperReadinessCriteria,
    PaperReadinessEvidence,
    evaluate_paper_readiness,
)


def _result(
    *,
    total_return_pct: float = 8.0,
    max_drawdown_pct: float = -8.0,
    closed_trade_count: int = 30,
    win_rate_pct: float = 50.0,
    average_exposure_pct: float = 60.0,
) -> BacktestResult:
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return BacktestResult(
        initial_equity_krw=1_000_000.0,
        final_equity_krw=1_080_000.0,
        total_return_pct=total_return_pct,
        max_drawdown_pct=max_drawdown_pct,
        trade_count=60,
        closed_trade_count=closed_trade_count,
        win_rate_pct=win_rate_pct,
        total_fees_krw=10_000.0,
        average_exposure_pct=average_exposure_pct,
        equity_curve=((now, 1_000_000.0),),
        trades=(),
    )


def _evidence(**overrides: object) -> PaperReadinessEvidence:
    values: dict[str, object] = {
        "sample_count": 1_000,
        "regime_count": 3,
        "out_of_sample_validated": True,
        "dataset_sha256": "a" * 64,
    }
    values.update(overrides)
    return PaperReadinessEvidence(**values)  # type: ignore[arg-type]


def test_crypto_readiness_passes_when_all_checks_pass() -> None:
    report = evaluate_paper_readiness(
        asset_class="crypto",
        result=_result(),
        evidence=_evidence(),
    )

    assert report.passed is True
    assert report.failure_codes == ()
    assert report.to_dict()["status"] == "PASS"
    assert "crypto PAPER readiness: PASS" in report.to_text()


def test_report_exposes_all_failure_reasons() -> None:
    report = evaluate_paper_readiness(
        asset_class="crypto",
        result=_result(
            total_return_pct=-2.0,
            max_drawdown_pct=-25.0,
            closed_trade_count=4,
            win_rate_pct=20.0,
            average_exposure_pct=95.0,
        ),
        evidence=_evidence(
            sample_count=100,
            regime_count=1,
            out_of_sample_validated=False,
        ),
    )

    assert report.passed is False
    assert report.failure_codes == (
        "sample_count",
        "closed_trade_count",
        "fee_adjusted_return_pct",
        "max_drawdown_pct",
        "win_rate_pct",
        "average_exposure_pct",
        "regime_count",
        "out_of_sample_validated",
    )


def test_asset_reports_are_explicitly_separate() -> None:
    crypto = evaluate_paper_readiness(
        asset_class="crypto",
        result=_result(),
        evidence=_evidence(),
    )
    us_stocks = evaluate_paper_readiness(
        asset_class="us_stocks",
        result=_result(),
        evidence=_evidence(),
    )

    assert crypto.asset_class == "crypto"
    assert us_stocks.asset_class == "us_stocks"
    assert crypto.to_dict()["asset_class"] != us_stocks.to_dict()["asset_class"]


def test_custom_policy_can_raise_the_gate() -> None:
    strict = PaperReadinessCriteria(
        min_sample_count=2_000,
        min_closed_trades=50,
        min_fee_adjusted_return_pct=10.0,
        max_drawdown_pct=-5.0,
        min_win_rate_pct=60.0,
        max_average_exposure_pct=50.0,
        min_regime_count=4,
    )
    report = evaluate_paper_readiness(
        asset_class="crypto",
        result=_result(),
        evidence=_evidence(),
        criteria=strict,
    )

    assert report.passed is False


def test_invalid_evidence_and_asset_class_are_rejected() -> None:
    with pytest.raises(ValueError, match="64-character"):
        PaperReadinessEvidence(
            sample_count=1,
            regime_count=1,
            out_of_sample_validated=True,
            dataset_sha256="bad",
        )

    with pytest.raises(ValueError, match="asset_class"):
        evaluate_paper_readiness(
            asset_class="forex",  # type: ignore[arg-type]
            result=_result(),
            evidence=_evidence(),
        )
