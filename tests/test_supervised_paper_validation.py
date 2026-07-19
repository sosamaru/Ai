from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta

import pytest

from aipro.crypto.supervised_paper_validation import (
    ComparisonEvidenceObservation,
    PaperValidationEvidenceStore,
    PaperValidationObservation,
    PaperValidationPolicy,
    evaluate_paper_validation,
)

EVALUATED_AT = datetime(2026, 7, 20, 0, 0, tzinfo=UTC)


def observation(**overrides: object) -> PaperValidationObservation:
    started = datetime(2026, 7, 19, 0, 0, tzinfo=UTC)
    values: dict[str, object] = {
        "dataset_fingerprint": "a" * 64,
        "strategy_version": "strategy-v1",
        "config_version": "config-v1",
        "observation_started_at_utc": started.isoformat(),
        "observation_ended_at_utc": (started + timedelta(hours=24)).isoformat(),
        "completed_cycles": 24,
        "restart_recoveries": 1,
        "halted_events": 1,
        "provider_failures": 0,
        "stale_source_events": 0,
        "duplicate_order_ids": 0,
        "unhandled_exceptions": 0,
    }
    values.update(overrides)
    return PaperValidationObservation(**values)


def comparison(
    *, status: str = "MATCH", age_seconds: float = 60.0
) -> ComparisonEvidenceObservation:
    return ComparisonEvidenceObservation(
        status=status,
        compared_at_utc=(EVALUATED_AT - timedelta(seconds=age_seconds)).isoformat(),
        evidence_fingerprint="b" * 64,
    )


def evaluate(**kwargs: object):
    return evaluate_paper_validation(
        observation(),
        comparison_evidence=comparison(),
        evaluated_at=EVALUATED_AT,
        **kwargs,
    )


def test_paper_validation_passes_only_when_every_gate_passes() -> None:
    result = evaluate()

    assert result.status == "PASS"
    assert all(result.checks.values())
    assert len(result.fingerprint) == 64


@pytest.mark.parametrize(
    ("field_name", "value", "failed_check"),
    [
        ("completed_cycles", 23, "minimum_cycles"),
        ("restart_recoveries", 0, "restart_recovery"),
        ("halted_events", 0, "halted_evidence"),
        ("provider_failures", 1, "provider_health"),
        ("stale_source_events", 1, "source_freshness"),
        ("duplicate_order_ids", 1, "unique_order_ids"),
        ("unhandled_exceptions", 1, "runtime_stability"),
    ],
)
def test_paper_validation_fails_closed(field_name: str, value: int, failed_check: str) -> None:
    result = evaluate_paper_validation(
        observation(**{field_name: value}),
        comparison_evidence=comparison(),
        evaluated_at=EVALUATED_AT,
    )

    assert result.status == "FAIL"
    assert result.checks[failed_check] is False


def test_missing_comparison_evidence_fails_closed() -> None:
    result = evaluate_paper_validation(observation(), evaluated_at=EVALUATED_AT)

    assert result.status == "FAIL"
    assert result.checks["comparison_present"] is False
    assert result.checks["comparison_match"] is False
    assert result.checks["comparison_fresh"] is False


@pytest.mark.parametrize("status", ["MISMATCH", "STALE"])
def test_non_matching_comparison_evidence_fails_closed(status: str) -> None:
    result = evaluate_paper_validation(
        observation(),
        comparison_evidence=comparison(status=status),
        evaluated_at=EVALUATED_AT,
    )

    assert result.status == "FAIL"
    assert result.checks["comparison_present"] is True
    assert result.checks["comparison_match"] is False


def test_old_match_evidence_fails_closed() -> None:
    result = evaluate_paper_validation(
        observation(),
        comparison_evidence=comparison(age_seconds=301),
        evaluated_at=EVALUATED_AT,
    )

    assert result.status == "FAIL"
    assert result.checks["comparison_match"] is True
    assert result.checks["comparison_fresh"] is False


def test_policy_can_raise_minimum_observation_cycles() -> None:
    result = evaluate_paper_validation(
        observation(completed_cycles=47),
        PaperValidationPolicy(minimum_completed_cycles=48),
        comparison_evidence=comparison(),
        evaluated_at=EVALUATED_AT,
    )

    assert result.status == "FAIL"
    assert result.checks["minimum_cycles"] is False


def test_validation_payload_and_fingerprint_are_deterministic() -> None:
    first = evaluate()
    second = evaluate()

    assert first.payload_json == second.payload_json
    assert first.fingerprint == second.fingerprint


def test_evidence_store_is_append_only(tmp_path) -> None:
    database_path = tmp_path / "paper-evidence.sqlite3"
    store = PaperValidationEvidenceStore(database_path)
    stored = store.append(evaluate())

    assert stored.status == "PASS"
    with sqlite3.connect(database_path) as connection:
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            connection.execute(
                "UPDATE crypto_paper_validation_evidence SET status = 'FAIL' WHERE evidence_id = ?",
                (stored.evidence_id,),
            )
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            connection.execute(
                "DELETE FROM crypto_paper_validation_evidence WHERE evidence_id = ?",
                (stored.evidence_id,),
            )


def test_duplicate_evidence_fingerprint_is_rejected(tmp_path) -> None:
    store = PaperValidationEvidenceStore(tmp_path / "paper-evidence.sqlite3")
    result = evaluate()
    store.append(result)

    with pytest.raises(sqlite3.IntegrityError):
        store.append(result)


def test_naive_timestamps_are_rejected() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        observation(observation_ended_at_utc="2026-07-20T00:00:00")

    with pytest.raises(ValueError, match="timezone-aware"):
        ComparisonEvidenceObservation(
            status="MATCH",
            compared_at_utc="2026-07-20T00:00:00",
            evidence_fingerprint="b" * 64,
        )
