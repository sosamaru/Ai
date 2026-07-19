from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Mapping


@dataclass(frozen=True, slots=True)
class PaperValidationObservation:
    dataset_fingerprint: str
    strategy_version: str
    config_version: str
    observation_started_at_utc: str
    observation_ended_at_utc: str
    completed_cycles: int
    restart_recoveries: int
    halted_events: int
    provider_failures: int
    stale_source_events: int
    duplicate_order_ids: int
    unhandled_exceptions: int

    def __post_init__(self) -> None:
        if len(self.dataset_fingerprint) != 64:
            raise ValueError("dataset_fingerprint must be a SHA-256 hex digest")
        int(self.dataset_fingerprint, 16)
        if not self.strategy_version.strip() or not self.config_version.strip():
            raise ValueError("strategy_version and config_version are required")
        started = datetime.fromisoformat(self.observation_started_at_utc)
        ended = datetime.fromisoformat(self.observation_ended_at_utc)
        if started.tzinfo is None or ended.tzinfo is None:
            raise ValueError("observation timestamps must be timezone-aware")
        if ended < started:
            raise ValueError("observation end must not precede start")
        for field_name in (
            "completed_cycles",
            "restart_recoveries",
            "halted_events",
            "provider_failures",
            "stale_source_events",
            "duplicate_order_ids",
            "unhandled_exceptions",
        ):
            if getattr(self, field_name) < 0:
                raise ValueError(f"{field_name} must be non-negative")


@dataclass(frozen=True, slots=True)
class PaperValidationPolicy:
    minimum_completed_cycles: int = 24
    maximum_provider_failures: int = 0
    maximum_stale_source_events: int = 0
    require_restart_recovery: bool = True
    require_halted_evidence: bool = True

    def __post_init__(self) -> None:
        if self.minimum_completed_cycles <= 0:
            raise ValueError("minimum_completed_cycles must be positive")
        if self.maximum_provider_failures < 0 or self.maximum_stale_source_events < 0:
            raise ValueError("failure limits must be non-negative")


@dataclass(frozen=True, slots=True)
class PaperValidationResult:
    status: str
    checks: Mapping[str, bool]
    fingerprint: str
    payload_json: str


@dataclass(frozen=True, slots=True)
class StoredPaperValidationEvidence:
    evidence_id: int
    created_at_utc: str
    status: str
    fingerprint: str
    payload_json: str


def evaluate_paper_validation(
    observation: PaperValidationObservation,
    policy: PaperValidationPolicy | None = None,
) -> PaperValidationResult:
    active_policy = policy or PaperValidationPolicy()
    checks = {
        "minimum_cycles": observation.completed_cycles >= active_policy.minimum_completed_cycles,
        "restart_recovery": (
            observation.restart_recoveries > 0 if active_policy.require_restart_recovery else True
        ),
        "halted_evidence": observation.halted_events > 0 if active_policy.require_halted_evidence else True,
        "provider_health": observation.provider_failures <= active_policy.maximum_provider_failures,
        "source_freshness": observation.stale_source_events <= active_policy.maximum_stale_source_events,
        "unique_order_ids": observation.duplicate_order_ids == 0,
        "runtime_stability": observation.unhandled_exceptions == 0,
    }
    status = "PASS" if all(checks.values()) else "FAIL"
    payload = {
        "schema_version": 1,
        "asset_domain": "crypto",
        "mode": "PAPER",
        "status": status,
        "checks": dict(sorted(checks.items())),
        "observation": {
            "dataset_fingerprint": observation.dataset_fingerprint.lower(),
            "strategy_version": observation.strategy_version,
            "config_version": observation.config_version,
            "observation_started_at_utc": observation.observation_started_at_utc,
            "observation_ended_at_utc": observation.observation_ended_at_utc,
            "completed_cycles": observation.completed_cycles,
            "restart_recoveries": observation.restart_recoveries,
            "halted_events": observation.halted_events,
            "provider_failures": observation.provider_failures,
            "stale_source_events": observation.stale_source_events,
            "duplicate_order_ids": observation.duplicate_order_ids,
            "unhandled_exceptions": observation.unhandled_exceptions,
        },
        "policy": {
            "minimum_completed_cycles": active_policy.minimum_completed_cycles,
            "maximum_provider_failures": active_policy.maximum_provider_failures,
            "maximum_stale_source_events": active_policy.maximum_stale_source_events,
            "require_restart_recovery": active_policy.require_restart_recovery,
            "require_halted_evidence": active_policy.require_halted_evidence,
        },
    }
    payload_json = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    fingerprint = hashlib.sha256(payload_json.encode("utf-8")).hexdigest()
    return PaperValidationResult(status, checks, fingerprint, payload_json)


class PaperValidationEvidenceStore:
    """Append-only evidence store isolated from PAPER runtime state."""

    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS crypto_paper_validation_evidence (
                    evidence_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    asset_domain TEXT NOT NULL CHECK(asset_domain = 'crypto'),
                    mode TEXT NOT NULL CHECK(mode = 'PAPER'),
                    created_at_utc TEXT NOT NULL,
                    status TEXT NOT NULL CHECK(status IN ('PASS', 'FAIL')),
                    fingerprint TEXT NOT NULL UNIQUE CHECK(length(fingerprint) = 64),
                    payload_json TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TRIGGER IF NOT EXISTS crypto_paper_validation_evidence_no_update
                BEFORE UPDATE ON crypto_paper_validation_evidence
                BEGIN
                    SELECT RAISE(ABORT, 'paper validation evidence is immutable');
                END
                """
            )
            connection.execute(
                """
                CREATE TRIGGER IF NOT EXISTS crypto_paper_validation_evidence_no_delete
                BEFORE DELETE ON crypto_paper_validation_evidence
                BEGIN
                    SELECT RAISE(ABORT, 'paper validation evidence is immutable');
                END
                """
            )

    def append(self, result: PaperValidationResult) -> StoredPaperValidationEvidence:
        if result.status not in {"PASS", "FAIL"}:
            raise ValueError("invalid validation result status")
        created_at_utc = datetime.now(UTC).isoformat()
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO crypto_paper_validation_evidence (
                    asset_domain, mode, created_at_utc, status, fingerprint, payload_json
                ) VALUES ('crypto', 'PAPER', ?, ?, ?, ?)
                """,
                (created_at_utc, result.status, result.fingerprint, result.payload_json),
            )
            evidence_id = int(cursor.lastrowid)
        return StoredPaperValidationEvidence(
            evidence_id=evidence_id,
            created_at_utc=created_at_utc,
            status=result.status,
            fingerprint=result.fingerprint,
            payload_json=result.payload_json,
        )


__all__ = [
    "PaperValidationEvidenceStore",
    "PaperValidationObservation",
    "PaperValidationPolicy",
    "PaperValidationResult",
    "StoredPaperValidationEvidence",
    "evaluate_paper_validation",
]
