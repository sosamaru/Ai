# AiPro Full Build Directive

Updated: 2026-07-23

## Owner instruction

AiPro development must complete every software and infrastructure construction stage that can be completed before long-duration evidence accumulation begins.

Long-duration evidence accumulation includes elapsed PAPER trading days, live-market observation periods, and other results that cannot honestly be produced without real time passing. These must remain explicitly incomplete until the required evidence exists.

## Completion target

Before declaring the software build complete, the repository must include production-quality, broker-neutral implementations for:

1. Data ingestion, normalization, freshness, lineage, deduplication, and provider resilience.
2. Feature engineering for market, liquidity, volatility, macroeconomic, filing, news, sentiment, regime, and portfolio-state inputs.
3. Labeling, leakage prevention, purging, embargoes, walk-forward evaluation, combinatorial purged cross-validation, untouched holdout evaluation, and selection-bias controls.
4. Baseline models, regularized linear models, tree ensembles, gradient boosting, calibrated classifiers/regressors, temporal deep-learning candidates, probabilistic forecasts, and ensemble/meta-model interfaces.
5. Optional reinforcement-learning research environments isolated from order execution and never granted direct LIVE authority.
6. Hyperparameter search with bounded budgets, deterministic seeds, experiment tracking, reproducible artifacts, and locked out-of-sample evaluation.
7. Drift, uncertainty, calibration, feature ablation, feature importance, explainability, model registry, promotion, rollback, and champion/challenger controls.
8. Transaction-cost, spread, slippage, liquidity, latency, partial-fill, outage, and market-impact simulation.
9. Risk-adjusted expected-value scoring, volatility targeting, exposure limits, correlation controls, concentration controls, drawdown controls, tail-risk stress tests, and fail-closed sizing.
10. Independent crypto and US-stock research, balances, baselines, credentials, model records, validation, and deployment artifacts.
11. PAPER orchestration, monitoring, telemetry, audit evidence, alerting, restart recovery, configuration validation, secret handling, CI, documentation, and operator runbooks.
12. A completion manifest proving that implementation, tests, documentation, limitations, and roadmap status are synchronized.

## Modern-technology policy

AiPro must continuously evaluate modern algorithms and AI methods through replaceable interfaces rather than hard-coding one fashionable model.

Candidate families include, where technically and financially appropriate:

- Regularized linear and generalized linear models.
- Random forests and extremely randomized trees.
- Gradient-boosted decision trees.
- Temporal convolutional, recurrent, attention, Temporal Fusion Transformer, patch-based transformer, and other time-series architectures.
- Probabilistic and quantile forecasting.
- Regime-switching and hidden-state models.
- Bayesian or uncertainty-aware model comparison.
- Stacking, blending, bagging, boosting, and champion/challenger ensembles.
- Representation learning for text, filings, news, and structured time series.
- Reinforcement-learning candidates in simulation-only research environments.
- Causal, invariant, and robustness-oriented research methods when supported by evidence.

No model is accepted because it is modern, complex, popular, or described as AI. Every candidate must beat simpler baselines after realistic costs under leakage-safe out-of-sample validation. Unsupported complexity must be rejected.

## Research and source policy

- Prefer peer-reviewed papers, primary research papers, and official project documentation.
- Record source, publication date, assumptions, limitations, license, and intended integration point.
- Treat LLM output as untrusted research input and never as a direct trading command.
- Prevent training-cutoff contamination, look-ahead bias, survivorship bias, selection bias, and repeated holdout reuse.
- Do not claim profitability from architecture completion.

## Safety and deployment boundary

- PAPER remains the default.
- Software-build completion is not live-readiness approval.
- Real-money order capability remains gated by independent validation, authorization, risk, reconciliation, freshness, and kill-switch checks.
- Crypto and US-stock domains remain isolated.
- No AI model, confidence score, recent profit, or owner instruction can bypass a failed hard safety gate.

## Completion notification rule

The owner must be informed only when all non-elapsed-time construction checklist items are complete and verified by passing CI, synchronized documentation, and a completion manifest.

The completion notice must clearly separate:

- Software construction complete.
- Long-duration PAPER evidence still pending.
- Live-readiness not approved unless every independent gate passes.
