# AiPro Modern AI and Quantitative Research Plan

Updated: 2026-07-23

## Purpose

This document defines the modern model, validation, execution-simulation, and governance capabilities that must be constructible before long-duration PAPER evidence accumulation becomes the primary remaining task.

The project will not attempt to force every algorithm into production. It will provide governed candidate interfaces, reproducible evaluation, and rejection gates so that only methods demonstrating incremental out-of-sample value after realistic costs may advance.

## Required model families

### Baselines and classical machine learning

- Naive, moving-average, volatility-scaled, and simple rule baselines.
- Linear, logistic, ridge, lasso, and elastic-net candidates.
- Random forest and extremely randomized tree candidates.
- Gradient-boosted tree adapters with optional XGBoost, LightGBM, and CatBoost backends.
- Calibrated probability and quantile-regression interfaces.

### Temporal and deep-learning research candidates

- Temporal convolutional and recurrent sequence models.
- Temporal Fusion Transformer-style multi-horizon forecasting.
- Patch-based time-series transformer candidates.
- Representation-learning interfaces for structured time series.
- Probabilistic multi-horizon forecasts and uncertainty estimates.

Deep-learning dependencies must remain optional. Absence of GPU libraries may not break the core PAPER system.

### Regime and uncertainty models

- Hidden-state and regime-switching interfaces.
- Change-point and feature-distribution drift detection.
- Ensemble disagreement and predictive-uncertainty signals.
- Confidence calibration and abstention.

### Text and filing intelligence

- Filing text and XBRL fact extraction.
- Event and materiality scoring.
- Timestamp-safe text embeddings and classifier interfaces.
- LLM-assisted research only through recorded, bounded, and untrusted evidence adapters.
- Explicit contamination, cutoff-date, future-information, and prompt-lineage checks.

### Ensemble and model governance

- Bagging, blending, stacking, and champion/challenger interfaces.
- Immutable experiment and model records.
- Model promotion, rejection, rollback, and retirement.
- Per-domain registries for crypto and US stocks.

### Reinforcement learning boundary

- Optional simulation-only research environment.
- Candidate algorithms may include value-based and actor-critic families.
- Reward functions must include risk, drawdown, turnover, costs, and constraint violations.
- RL agents may not call broker adapters or receive direct LIVE authority.
- RL must beat supervised and rule-based baselines under identical locked evaluation before consideration.

## Required validation stack

- Chronological holdout sets that are never reused for tuning.
- Purging and embargoes.
- Expanding and rolling walk-forward evaluation.
- Combinatorial purged cross-validation where dataset size permits.
- Probability-of-backtest-overfitting and deflated-performance controls where applicable.
- Multiple-testing and selection-bias accounting.
- Dependence-preserving bootstrap and stress scenarios.
- Regime, asset, timeframe, and cost-sensitivity slices.
- Calibration, directional accuracy, MAE/RMSE, information coefficient, Sharpe/Sortino, drawdown, turnover, hit rate, expectancy, tail loss, and stability reporting.
- Null, shuffled-label, and simple-baseline comparisons.

## Required execution-aware simulation

- Fees, bid/ask spread, slippage, latency, partial fills, rejected orders, outages, stale quotes, liquidity limits, and configurable market impact.
- Corporate-action and survivorship-safe handling for US stocks.
- Exchange and market-session differences kept domain-specific.
- No strategy may be promoted using frictionless results alone.

## Required portfolio and risk layer

- Risk-adjusted expected-value scoring.
- Volatility targeting and capped fractional sizing.
- Correlation and concentration controls.
- Gross/net exposure limits.
- Liquidity and turnover budgets.
- Drawdown, daily-loss, gap-risk, and tail-stress controls.
- Uncertainty, disagreement, stale data, and drift must reduce or block sizing.
- Position-sizing outputs remain proposals until all independent PAPER execution gates pass.

## Required infrastructure and MLOps

- Dataset, feature, label, experiment, and model fingerprints.
- Deterministic seeds and environment manifests.
- Optional dependency groups for classical ML, deep learning, NLP, and RL.
- Experiment tracking and artifact manifests without storing secrets.
- Configuration schema validation.
- Monitoring for data quality, feature drift, prediction drift, calibration drift, model performance, costs, and operational health.
- Reproducible CI smoke tests using small deterministic fixtures.
- Completion manifest that compares roadmap claims with repository code and tests.

## Completion definition before evidence accumulation

Construction is complete only when:

1. Every required interface and safety gate above is implemented or explicitly rejected with a documented reason.
2. Core and optional modules fail safely when dependencies or data are unavailable.
3. CI passes.
4. Documentation, roadmap, limitations, and runbooks match actual code.
5. Crypto and US-stock artifacts remain independently addressable.
6. The completion manifest reports no unaccounted construction gaps.
7. The remaining incomplete items require real elapsed PAPER time, real credentials, owner enrollment, or independently reviewed live-readiness evidence.

Construction completion does not mean expected profitability or approval for real-money trading.

## Primary research basis

The implementation plan is informed by primary research on interpretable multi-horizon transformers, modular deep-reinforcement-learning environments with market frictions, and finance-specific leakage-safe validation. Research claims must be rechecked when integrated, and source limitations must be recorded in code or documentation.
