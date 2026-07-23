# Optional Gradient-Boosting Backends

AiPro treats XGBoost, LightGBM, and CatBoost as optional PAPER research backends.
They are not imported during normal application startup and are not mandatory CI
dependencies.

## Guarantees

- Core PAPER operation remains available when every optional package is absent.
- A backend is imported only after an explicit `build_backend()` request.
- Unknown backends and unsupported parameters fail closed.
- Deterministic single-thread defaults are enforced.
- Excessive estimator/iteration counts are rejected.
- CatBoost file writing is disabled by default.
- Returned estimators receive no market-data, persistence, promotion, broker, or
  order-execution authority from this module.

## Supported adapters

- `xgboost.XGBClassifier`
- `lightgbm.LGBMClassifier`
- `catboost.CatBoostClassifier`

Installation and licensing remain operator-controlled. Availability alone does
not qualify a model. Every candidate must still pass the repository's domain
isolation, purged validation, cost-aware expected-value, calibration,
stability, locked-holdout, registry, risk, and PAPER evidence gates.

## Example

```python
from aipro.intelligence.optional_boosting import build_backend

candidate = build_backend(
    "xgboost",
    {"n_estimators": 200, "max_depth": 4, "learning_rate": 0.03},
)
```

The object above is only a research candidate. It cannot place orders or enable
LIVE mode.
