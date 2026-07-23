"""Optional gradient-boosting backends for PAPER research.

The module never imports third-party libraries at import time. Backends are
resolved only after an explicit request, so the core application and CI remain
usable without XGBoost, LightGBM, or CatBoost installed.
"""

from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
from importlib.util import find_spec
from typing import Any, Callable, Mapping


class OptionalBackendError(RuntimeError):
    """Base error for optional model backend failures."""


class BackendUnavailable(OptionalBackendError):
    """Raised when an explicitly requested backend is not installed."""


class BackendConfigurationError(OptionalBackendError):
    """Raised when unsafe or unsupported parameters are supplied."""


@dataclass(frozen=True)
class BackendSpec:
    name: str
    package: str
    estimator_path: str
    allowed_parameters: frozenset[str]
    deterministic_defaults: Mapping[str, Any]


@dataclass(frozen=True)
class BackendStatus:
    name: str
    package: str
    available: bool
    reason: str


BACKENDS: dict[str, BackendSpec] = {
    "xgboost": BackendSpec(
        name="xgboost",
        package="xgboost",
        estimator_path="xgboost.XGBClassifier",
        allowed_parameters=frozenset(
            {
                "n_estimators",
                "max_depth",
                "learning_rate",
                "subsample",
                "colsample_bytree",
                "min_child_weight",
                "reg_alpha",
                "reg_lambda",
                "random_state",
                "n_jobs",
            }
        ),
        deterministic_defaults={"random_state": 0, "n_jobs": 1},
    ),
    "lightgbm": BackendSpec(
        name="lightgbm",
        package="lightgbm",
        estimator_path="lightgbm.LGBMClassifier",
        allowed_parameters=frozenset(
            {
                "n_estimators",
                "max_depth",
                "num_leaves",
                "learning_rate",
                "subsample",
                "colsample_bytree",
                "min_child_samples",
                "reg_alpha",
                "reg_lambda",
                "random_state",
                "n_jobs",
                "verbosity",
            }
        ),
        deterministic_defaults={"random_state": 0, "n_jobs": 1, "verbosity": -1},
    ),
    "catboost": BackendSpec(
        name="catboost",
        package="catboost",
        estimator_path="catboost.CatBoostClassifier",
        allowed_parameters=frozenset(
            {
                "iterations",
                "depth",
                "learning_rate",
                "l2_leaf_reg",
                "random_seed",
                "thread_count",
                "verbose",
                "allow_writing_files",
            }
        ),
        deterministic_defaults={
            "random_seed": 0,
            "thread_count": 1,
            "verbose": False,
            "allow_writing_files": False,
        },
    ),
}


def backend_status(name: str) -> BackendStatus:
    spec = _get_spec(name)
    available = find_spec(spec.package) is not None
    return BackendStatus(
        name=spec.name,
        package=spec.package,
        available=available,
        reason="available" if available else "optional dependency not installed",
    )


def list_backend_statuses() -> tuple[BackendStatus, ...]:
    return tuple(backend_status(name) for name in sorted(BACKENDS))


def build_backend(name: str, parameters: Mapping[str, Any] | None = None) -> Any:
    """Construct one explicitly requested estimator.

    This function is PAPER/research infrastructure only. It does not train,
    promote, persist, or grant trading authority to the returned estimator.
    """

    spec = _get_spec(name)
    status = backend_status(name)
    if not status.available:
        raise BackendUnavailable(f"{name}: {status.reason}")

    supplied = dict(parameters or {})
    unsupported = sorted(set(supplied) - spec.allowed_parameters)
    if unsupported:
        raise BackendConfigurationError(
            f"{name}: unsupported parameters: {', '.join(unsupported)}"
        )

    merged = dict(spec.deterministic_defaults)
    merged.update(supplied)
    _validate_resource_limits(name, merged)
    factory = _load_factory(spec.estimator_path)
    return factory(**merged)


def _get_spec(name: str) -> BackendSpec:
    normalized = name.strip().lower()
    try:
        return BACKENDS[normalized]
    except KeyError as exc:
        raise BackendConfigurationError(f"unknown backend: {name!r}") from exc


def _load_factory(path: str) -> Callable[..., Any]:
    module_name, attribute = path.rsplit(".", 1)
    module = import_module(module_name)
    factory = getattr(module, attribute, None)
    if factory is None or not callable(factory):
        raise BackendUnavailable(f"estimator factory not found: {path}")
    return factory


def _validate_resource_limits(name: str, parameters: Mapping[str, Any]) -> None:
    for key in ("n_estimators", "iterations"):
        value = parameters.get(key)
        if value is not None and (not isinstance(value, int) or not 1 <= value <= 5000):
            raise BackendConfigurationError(f"{name}: {key} must be an integer in [1, 5000]")

    for key in ("n_jobs", "thread_count"):
        value = parameters.get(key)
        if value is not None and value not in (1,):
            raise BackendConfigurationError(
                f"{name}: {key} must remain 1 for deterministic bounded research"
            )
