"""Bounded dependence-preserving research estimates; not market guarantees.

All returns are fractions. Circular block bootstrap retains within-block serial
dependence, not arbitrary nonstationarity. Budgets and block length must be fixed
before results are inspected. No IID shuffle is represented as robust evidence.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from random import Random
from statistics import NormalDist, fmean, stdev

from aipro.core.evidence import finite, integer


@dataclass(frozen=True)
class BootstrapPolicy:
    samples: int = 1000
    block_length: int = 5
    alpha: float = 0.05
    trial_budget: int = 1
    seed: int = 17

    def __post_init__(self):
        integer(self.samples, "bootstrap samples", 100, 10000)
        integer(self.block_length, "block length", 1, 1000)
        integer(self.trial_budget, "trial budget", 1, 100)
        integer(self.seed, "seed", 0, 2**32 - 1)
        finite(self.alpha, "alpha", 0.001, 0.1)
        if self.samples * self.alpha / self.trial_budget < 5:
            raise ValueError("too few bootstrap draws for multiplicity-adjusted tail")


def quantile(values, q):
    ordered = sorted(values)
    if not ordered:
        return None
    finite(q, "quantile", 0, 1)
    index = (len(ordered) - 1) * q
    lo, hi = math.floor(index), math.ceil(index)
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (index - lo)


def _values(values, policy):
    result = tuple(finite(x) for x in values)
    if len(result) < max(20, 4 * policy.block_length) or len(result) > 20000:
        raise ValueError("insufficient independent blocks or excessive sample count")
    if policy.samples * len(result) > 20_000_000:
        raise ValueError("bootstrap operation budget exceeded")
    return result


def block_paths(values, policy):
    values = _values(values, policy)
    random = Random(policy.seed)
    n = len(values)
    for _ in range(policy.samples):
        path = []
        while len(path) < n:
            start = random.randrange(n)
            path.extend(values[(start + j) % n] for j in range(min(policy.block_length, n - len(path))))
        yield path


def mean_interval(values, policy=BootstrapPolicy()) -> dict:
    values = _values(values, policy)
    means = [fmean(path) for path in block_paths(values, policy)]
    alpha = policy.alpha / policy.trial_budget
    return {"mean": fmean(values), "lower": quantile(means, alpha / 2),
            "upper": quantile(means, 1 - alpha / 2), "confidence": 1 - alpha,
            "observations": len(values), "block_length": policy.block_length,
            "trial_budget": policy.trial_budget, "method": "circular_block_percentile_bootstrap",
            "assumption": "approximately stationary dependent returns; predeclared block length"}


def paired_improvement(champion, challenger, policy=BootstrapPolicy()) -> dict:
    if len(champion) != len(challenger):
        raise ValueError("paired observations must share identical timestamps and length")
    return mean_interval(tuple(finite(b) - finite(a) for a, b in zip(champion, challenger)), policy)


def monte_carlo(returns, policy=BootstrapPolicy(), *, loss_limit=0.1, capital_floor=0.5) -> dict:
    finite(loss_limit, "loss limit", 0.001, 1)
    finite(capital_floor, "capital floor", 0, 1)
    returns = _values(returns, policy)
    if any(x < -1 for x in returns):
        raise ValueError("unlevered capital returns cannot be below -100%")
    terminal, drawdowns, minima = [], [], []
    for path in block_paths(returns, policy):
        equity = peak = lowest = 1.0
        drawdown = 0.0
        for value in path:
            equity *= 1 + value
            if not math.isfinite(equity):
                raise ValueError("simulated compounded capital overflow")
            peak, lowest = max(peak, equity), min(lowest, equity)
            drawdown = max(drawdown, 1 - equity / peak)
        terminal.append(equity - 1)
        drawdowns.append(drawdown)
        minima.append(lowest)
    return {"paths": policy.samples, "horizon_observations": len(returns),
            "expected_terminal_return": fmean(terminal),
            "terminal_return_interval": [quantile(terminal, .025), quantile(terminal, .975)],
            "drawdown_quantiles": {str(q): quantile(drawdowns, q) for q in (.5, .95, .99)},
            "large_loss_probability": fmean(d >= loss_limit for d in drawdowns),
            "negative_terminal_return_probability": fmean(r <= 0 for r in terminal),
            "capital_survival_probability": fmean(m > capital_floor for m in minima),
            "loss_limit": loss_limit, "capital_floor": capital_floor,
            "limitations": "Conditional on supplied returns and block-stationarity; unseen crashes are not inferred."}


def deflated_sharpe(returns, *, independent_trials: int, trial_sharpe_std: float) -> dict:
    """Bailey/Lopez de Prado approximation; per-observation Sharpe inputs.

    trial_sharpe_std must come from ALL recorded comparable trial Sharpes, never
    from the winning series alone. Correlated-trial effective count is external.
    """
    values = tuple(finite(x) for x in returns)
    integer(independent_trials, "independent trials", 1, 10000)
    finite(trial_sharpe_std, "trial Sharpe std", 0)
    if len(values) < 30 or stdev(values) == 0:
        return {"probability": None, "reason": "insufficient_or_constant_returns"}
    normal = NormalDist()
    variance = fmean((x - fmean(values)) ** 2 for x in values)
    skew = fmean((x - fmean(values)) ** 3 for x in values) / variance**1.5
    kurtosis = fmean((x - fmean(values)) ** 4 for x in values) / variance**2
    sr = fmean(values) / stdev(values)
    benchmark = 0.0
    if independent_trials > 1:
        gamma = .5772156649015329
        benchmark = trial_sharpe_std * ((1 - gamma) * normal.inv_cdf(1 - 1 / independent_trials)
                                       + gamma * normal.inv_cdf(1 - 1 / (independent_trials * math.e)))
    denominator = 1 - skew * sr + (kurtosis - 1) * sr * sr / 4
    probability = normal.cdf((sr - benchmark) * math.sqrt(len(values) - 1) / math.sqrt(denominator)) if denominator > 0 else None
    return {"probability": probability, "per_observation_sharpe": sr, "selection_benchmark": benchmark,
            "assumption": "effective independent trial count and variance supplied from experiment history; asymptotic approximation"}
