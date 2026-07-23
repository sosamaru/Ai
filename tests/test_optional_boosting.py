from __future__ import annotations

import pytest

from aipro.intelligence import optional_boosting as boosting


def test_registry_contains_supported_optional_backends() -> None:
    assert set(boosting.BACKENDS) == {"xgboost", "lightgbm", "catboost"}


def test_unknown_backend_fails_closed() -> None:
    with pytest.raises(boosting.BackendConfigurationError, match="unknown backend"):
        boosting.backend_status("unknown")


def test_status_does_not_import_optional_package(monkeypatch: pytest.MonkeyPatch) -> None:
    imported: list[str] = []

    def forbidden_import(name: str):
        imported.append(name)
        raise AssertionError("optional package import should be lazy")

    monkeypatch.setattr(boosting, "import_module", forbidden_import)
    monkeypatch.setattr(boosting, "find_spec", lambda package: None)

    status = boosting.backend_status("xgboost")

    assert status.available is False
    assert imported == []


def test_missing_dependency_raises_clear_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(boosting, "find_spec", lambda package: None)

    with pytest.raises(boosting.BackendUnavailable, match="not installed"):
        boosting.build_backend("lightgbm")


def test_unsupported_parameter_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(boosting, "find_spec", lambda package: object())

    with pytest.raises(boosting.BackendConfigurationError, match="unsupported parameters"):
        boosting.build_backend("xgboost", {"eval_metric_callback": object()})


def test_unbounded_parallelism_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(boosting, "find_spec", lambda package: object())

    with pytest.raises(boosting.BackendConfigurationError, match="must remain 1"):
        boosting.build_backend("xgboost", {"n_jobs": 4})


def test_excessive_iteration_count_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(boosting, "find_spec", lambda package: object())

    with pytest.raises(boosting.BackendConfigurationError, match="\[1, 5000\]"):
        boosting.build_backend("catboost", {"iterations": 5001})


def test_factory_receives_deterministic_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    class DummyEstimator:
        def __init__(self, **kwargs: object) -> None:
            captured.update(kwargs)

    monkeypatch.setattr(boosting, "find_spec", lambda package: object())
    monkeypatch.setattr(boosting, "_load_factory", lambda path: DummyEstimator)

    estimator = boosting.build_backend("catboost", {"iterations": 25})

    assert isinstance(estimator, DummyEstimator)
    assert captured == {
        "random_seed": 0,
        "thread_count": 1,
        "verbose": False,
        "allow_writing_files": False,
        "iterations": 25,
    }
