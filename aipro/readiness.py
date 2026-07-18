from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from aipro.backtest import BacktestResult

AssetClass = Literal["crypto", "us_stocks"]


@dataclass(frozen=True, slots=True)
class PaperReadinessCriteria:
    min_sample_count: int = 500
    min_closed_trades: int = 20
    min_fee_adjusted_return_pct: float = 0.0
    max_drawdown_pct: float = -15.0
    min_win_rate_pct: float = 35.0
    max_average_exposure_pct: float = 85.0
    min_regime_count: int = 3
    require_out_of_sample: bool = True

    def __post_init__(self) -> None:
        if self.min_sample_count < 1:
            raise ValueError("min_sample_count must be positive")
        if self.min_closed_trades < 1:
            raise ValueError("min_closed_trades must be positive")
        if self.max_drawdown_pct >= 0:
            raise ValueError("max_drawdown_pct must be negative")
        if not 0 <= self.min_win_rate_pct <= 100:
            raise ValueError("min_win_rate_pct must be between 0 and 100")
        if not 0 < self.max_average_exposure_pct <= 100:
            raise ValueError("max_average_exposure_pct must be in (0, 100]")
        if self.min_regime_count < 1:
            raise ValueError("min_regime_count must be positive")


@dataclass(frozen=True, slots=True)
class PaperReadinessEvidence:
    sample_count: int
    regime_count: int
    out_of_sample_validated: bool
    dataset_sha256: str | None = None

    def __post_init__(self) -> None:
        if self.sample_count < 0:
            raise ValueError("sample_count must be non-negative")
        if self.regime_count < 0:
            raise ValueError("regime_count must be non-negative")
        if self.dataset_sha256 is not None and len(self.dataset_sha256) != 64:
            raise ValueError("dataset_sha256 must be a 64-character SHA-256 hex digest")


@dataclass(frozen=True, slots=True)
class ReadinessCheck:
    code: str
    passed: bool
    actual: float | int | bool
    required: float | int | bool
    message: str


@dataclass(frozen=True, slots=True)
class PaperReadinessReport:
    asset_class: AssetClass
    passed: bool
    checks: tuple[ReadinessCheck, ...]
    dataset_sha256: str | None

    @property
    def failure_codes(self) -> tuple[str, ...]:
        return tuple(check.code for check in self.checks if not check.passed)

    def to_dict(self) -> dict[str, object]:
        return {
            "asset_class": self.asset_class,
            "status": "PASS" if self.passed else "FAIL",
            "dataset_sha256": self.dataset_sha256,
            "failure_codes": list(self.failure_codes),
            "checks": [
                {
                    "code": check.code,
                    "passed": check.passed,
                    "actual": check.actual,
                    "required": check.required,
                    "message": check.message,
                }
                for check in self.checks
            ],
        }

    def to_text(self) -> str:
        lines = [
            f"AiPro {self.asset_class} PAPER readiness: {'PASS' if self.passed else 'FAIL'}"
        ]
        for check in self.checks:
            marker = "PASS" if check.passed else "FAIL"
            lines.append(f"[{marker}] {check.code}: {check.message}")
        return "\n".join(lines)


def evaluate_paper_readiness(
    *,
    asset_class: AssetClass,
    result: BacktestResult,
    evidence: PaperReadinessEvidence,
    criteria: PaperReadinessCriteria | None = None,
) -> PaperReadinessReport:
    if asset_class not in {"crypto", "us_stocks"}:
        raise ValueError("asset_class must be crypto or us_stocks")

    policy = criteria or PaperReadinessCriteria()
    checks = (
        _minimum_check(
            "sample_count",
            evidence.sample_count,
            policy.min_sample_count,
            "historical rows",
        ),
        _minimum_check(
            "closed_trade_count",
            result.closed_trade_count,
            policy.min_closed_trades,
            "closed trades",
        ),
        _minimum_check(
            "fee_adjusted_return_pct",
            result.total_return_pct,
            policy.min_fee_adjusted_return_pct,
            "fee- and slippage-adjusted total return percent",
        ),
        _drawdown_check(result.max_drawdown_pct, policy.max_drawdown_pct),
        _minimum_check(
            "win_rate_pct",
            result.win_rate_pct,
            policy.min_win_rate_pct,
            "closed-trade win rate percent",
        ),
        _maximum_check(
            "average_exposure_pct",
            result.average_exposure_pct,
            policy.max_average_exposure_pct,
            "average capital exposure percent",
        ),
        _minimum_check(
            "regime_count",
            evidence.regime_count,
            policy.min_regime_count,
            "distinct tested market regimes",
        ),
        ReadinessCheck(
            code="out_of_sample_validated",
            passed=(not policy.require_out_of_sample) or evidence.out_of_sample_validated,
            actual=evidence.out_of_sample_validated,
            required=policy.require_out_of_sample,
            message=(
                "out-of-sample validation is present"
                if evidence.out_of_sample_validated
                else "out-of-sample validation is missing"
            ),
        ),
    )

    return PaperReadinessReport(
        asset_class=asset_class,
        passed=all(check.passed for check in checks),
        checks=checks,
        dataset_sha256=evidence.dataset_sha256,
    )


def _minimum_check(code: str, actual: float | int, required: float | int, label: str) -> ReadinessCheck:
    passed = actual >= required
    return ReadinessCheck(
        code=code,
        passed=passed,
        actual=actual,
        required=required,
        message=f"{label}: actual={actual}, required>={required}",
    )


def _maximum_check(code: str, actual: float | int, required: float | int, label: str) -> ReadinessCheck:
    passed = actual <= required
    return ReadinessCheck(
        code=code,
        passed=passed,
        actual=actual,
        required=required,
        message=f"{label}: actual={actual}, required<={required}",
    )


def _drawdown_check(actual: float, required: float) -> ReadinessCheck:
    passed = actual >= required
    return ReadinessCheck(
        code="max_drawdown_pct",
        passed=passed,
        actual=actual,
        required=required,
        message=f"maximum drawdown percent: actual={actual}, required>={required}",
    )


__all__ = [
    "PaperReadinessCriteria",
    "PaperReadinessEvidence",
    "PaperReadinessReport",
    "ReadinessCheck",
    "evaluate_paper_readiness",
]
