from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from aipro.crypto.account_snapshot import StoredAccountSnapshot

_RECONCILIATION_STATES = frozenset({"MATCH", "MISMATCH", "STALE"})


@dataclass(frozen=True, slots=True)
class PaperAccountObservation:
    observed_at_utc: str
    balances: dict[str, Decimal]
    open_order_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class SnapshotComparison:
    status: str
    compared_at_utc: str
    snapshot_id: int
    snapshot_fingerprint: str
    snapshot_age_seconds: float
    balance_mismatches: tuple[str, ...]
    exchange_only_currencies: tuple[str, ...]
    paper_only_currencies: tuple[str, ...]
    exchange_only_order_ids: tuple[str, ...]
    paper_only_order_ids: tuple[str, ...]
    evidence_fingerprint: str


@dataclass(frozen=True, slots=True)
class StoredComparisonEvidence:
    evidence_id: int
    snapshot_id: int
    status: str
    compared_at_utc: str
    evidence_fingerprint: str
    payload_json: str


def _decimal(value: object, field_name: str) -> Decimal:
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"invalid decimal field: {field_name}") from exc
    if not parsed.is_finite() or parsed < 0:
        raise ValueError(f"invalid decimal field: {field_name}")
    return parsed


def _paper_timestamp(observation: PaperAccountObservation) -> datetime:
    timestamp = datetime.fromisoformat(observation.observed_at_utc)
    if timestamp.tzinfo is None:
        raise ValueError("PAPER observation timestamp must be timezone-aware")
    return timestamp.astimezone(UTC)


def compare_snapshot_to_paper(
    snapshot: StoredAccountSnapshot,
    paper: PaperAccountObservation,
    *,
    now: datetime | None = None,
    max_snapshot_age_seconds: float = 300.0,
    balance_tolerance: Decimal = Decimal("0.00000001"),
) -> SnapshotComparison:
    if max_snapshot_age_seconds <= 0:
        raise ValueError("max_snapshot_age_seconds must be positive")
    if balance_tolerance < 0:
        raise ValueError("balance_tolerance must be non-negative")
    reference = now or datetime.now(UTC)
    if reference.tzinfo is None:
        raise ValueError("comparison timestamp must be timezone-aware")
    _paper_timestamp(paper)

    age = snapshot.age_seconds(now=reference)
    payload = json.loads(snapshot.payload_json)
    balances_payload = payload.get("balances")
    orders_payload = payload.get("open_orders")
    if not isinstance(balances_payload, list) or not isinstance(orders_payload, list):
        raise ValueError("snapshot payload is missing balances or open_orders")

    exchange_balances: dict[str, Decimal] = {}
    for item in balances_payload:
        if not isinstance(item, dict):
            raise ValueError("snapshot balance entry must be an object")
        currency = str(item.get("currency", "")).strip().upper()
        if not currency or currency in exchange_balances:
            raise ValueError("snapshot balances contain an empty or duplicate currency")
        exchange_balances[currency] = _decimal(item.get("balance", ""), "balance") + _decimal(
            item.get("locked", ""), "locked"
        )

    paper_balances = {key.strip().upper(): value for key, value in paper.balances.items()}
    if any(not key for key in paper_balances):
        raise ValueError("PAPER balances contain an empty currency")
    for key, value in paper_balances.items():
        if not isinstance(value, Decimal) or not value.is_finite() or value < 0:
            raise ValueError(f"invalid PAPER balance for {key}")

    exchange_currencies = set(exchange_balances)
    paper_currencies = set(paper_balances)
    balance_mismatches = tuple(
        sorted(
            currency
            for currency in exchange_currencies & paper_currencies
            if abs(exchange_balances[currency] - paper_balances[currency]) > balance_tolerance
        )
    )

    exchange_order_ids: set[str] = set()
    for item in orders_payload:
        if not isinstance(item, dict):
            raise ValueError("snapshot order entry must be an object")
        order_id = str(item.get("uuid", "")).strip()
        if not order_id or order_id in exchange_order_ids:
            raise ValueError("snapshot orders contain an empty or duplicate UUID")
        exchange_order_ids.add(order_id)
    paper_order_ids = {str(value).strip() for value in paper.open_order_ids}
    if "" in paper_order_ids:
        raise ValueError("PAPER order IDs must not be empty")

    exchange_only_currencies = tuple(sorted(exchange_currencies - paper_currencies))
    paper_only_currencies = tuple(sorted(paper_currencies - exchange_currencies))
    exchange_only_order_ids = tuple(sorted(exchange_order_ids - paper_order_ids))
    paper_only_order_ids = tuple(sorted(paper_order_ids - exchange_order_ids))

    if age > max_snapshot_age_seconds:
        status = "STALE"
    elif any(
        (
            balance_mismatches,
            exchange_only_currencies,
            paper_only_currencies,
            exchange_only_order_ids,
            paper_only_order_ids,
        )
    ):
        status = "MISMATCH"
    else:
        status = "MATCH"

    compared_at_utc = reference.astimezone(UTC).isoformat()
    canonical = {
        "status": status,
        "compared_at_utc": compared_at_utc,
        "snapshot_id": snapshot.snapshot_id,
        "snapshot_fingerprint": snapshot.fingerprint,
        "snapshot_age_seconds": round(age, 6),
        "balance_mismatches": balance_mismatches,
        "exchange_only_currencies": exchange_only_currencies,
        "paper_only_currencies": paper_only_currencies,
        "exchange_only_order_ids": exchange_only_order_ids,
        "paper_only_order_ids": paper_only_order_ids,
    }
    evidence_fingerprint = hashlib.sha256(
        json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return SnapshotComparison(evidence_fingerprint=evidence_fingerprint, **canonical)


class SnapshotComparisonEvidenceStore:
    """Append-only comparison evidence; never mutates exchange or PAPER state."""

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
                CREATE TABLE IF NOT EXISTS exchange_snapshot_comparison_evidence (
                    evidence_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    asset_domain TEXT NOT NULL CHECK(asset_domain = 'crypto'),
                    source TEXT NOT NULL CHECK(source = 'upbit-readonly-vs-paper'),
                    snapshot_id INTEGER NOT NULL,
                    status TEXT NOT NULL CHECK(status IN ('MATCH', 'MISMATCH', 'STALE')),
                    compared_at_utc TEXT NOT NULL,
                    evidence_fingerprint TEXT NOT NULL UNIQUE CHECK(length(evidence_fingerprint) = 64),
                    payload_json TEXT NOT NULL,
                    created_at_utc TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TRIGGER IF NOT EXISTS exchange_snapshot_comparison_no_update
                BEFORE UPDATE ON exchange_snapshot_comparison_evidence
                BEGIN
                    SELECT RAISE(ABORT, 'comparison evidence is immutable');
                END
                """
            )
            connection.execute(
                """
                CREATE TRIGGER IF NOT EXISTS exchange_snapshot_comparison_no_delete
                BEFORE DELETE ON exchange_snapshot_comparison_evidence
                BEGIN
                    SELECT RAISE(ABORT, 'comparison evidence is immutable');
                END
                """
            )

    def append(self, comparison: SnapshotComparison) -> StoredComparisonEvidence:
        if comparison.status not in _RECONCILIATION_STATES:
            raise ValueError(f"invalid comparison status: {comparison.status}")
        payload_json = json.dumps(asdict(comparison), sort_keys=True, separators=(",", ":"))
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO exchange_snapshot_comparison_evidence (
                    asset_domain, source, snapshot_id, status, compared_at_utc,
                    evidence_fingerprint, payload_json, created_at_utc
                ) VALUES ('crypto', 'upbit-readonly-vs-paper', ?, ?, ?, ?, ?, ?)
                """,
                (
                    comparison.snapshot_id,
                    comparison.status,
                    comparison.compared_at_utc,
                    comparison.evidence_fingerprint,
                    payload_json,
                    datetime.now(UTC).isoformat(),
                ),
            )
            evidence_id = int(cursor.lastrowid)
        return StoredComparisonEvidence(
            evidence_id=evidence_id,
            snapshot_id=comparison.snapshot_id,
            status=comparison.status,
            compared_at_utc=comparison.compared_at_utc,
            evidence_fingerprint=comparison.evidence_fingerprint,
            payload_json=payload_json,
        )


__all__ = [
    "PaperAccountObservation",
    "SnapshotComparison",
    "SnapshotComparisonEvidenceStore",
    "StoredComparisonEvidence",
    "compare_snapshot_to_paper",
]
