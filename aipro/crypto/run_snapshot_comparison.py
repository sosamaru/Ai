from __future__ import annotations

import json
import os
import sys
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from aipro.crypto.account_snapshot import ReadOnlyAccountSnapshotStore
from aipro.crypto.snapshot_reconciliation import (
    PaperAccountObservation,
    SnapshotComparisonEvidenceStore,
    compare_snapshot_to_paper,
)

_GUARD_ENV = "AIPRO_UPBIT_SNAPSHOT_COMPARE"
_SNAPSHOT_DB_ENV = "AIPRO_UPBIT_SNAPSHOT_DB"
_PAPER_OBSERVATION_ENV = "AIPRO_PAPER_OBSERVATION_JSON"
_EVIDENCE_DB_ENV = "AIPRO_UPBIT_COMPARISON_DB"
_MAX_AGE_ENV = "AIPRO_UPBIT_SNAPSHOT_MAX_AGE_SEC"


def _required_path(name: str) -> Path:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is required")
    return Path(value)


def _load_paper_observation(path: Path) -> PaperAccountObservation:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("failed to read PAPER observation JSON") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("PAPER observation must be a JSON object")
    observed_at = str(payload.get("observed_at_utc", "")).strip()
    if not observed_at:
        raise RuntimeError("observed_at_utc is required")
    try:
        timestamp = datetime.fromisoformat(observed_at)
    except ValueError as exc:
        raise RuntimeError("observed_at_utc must be ISO-8601") from exc
    if timestamp.tzinfo is None:
        raise RuntimeError("observed_at_utc must be timezone-aware")
    balances_payload = payload.get("balances")
    if not isinstance(balances_payload, dict):
        raise RuntimeError("balances must be a JSON object")
    balances: dict[str, Decimal] = {}
    for raw_currency, raw_value in balances_payload.items():
        currency = str(raw_currency).strip().upper()
        if not currency or currency in balances:
            raise RuntimeError("balances contain an empty or duplicate currency")
        try:
            value = Decimal(str(raw_value))
        except (InvalidOperation, ValueError) as exc:
            raise RuntimeError(f"invalid balance for {currency}") from exc
        if not value.is_finite() or value < 0:
            raise RuntimeError(f"invalid balance for {currency}")
        balances[currency] = value
    order_ids_payload = payload.get("open_order_ids", [])
    if not isinstance(order_ids_payload, list):
        raise RuntimeError("open_order_ids must be a JSON array")
    order_ids = tuple(str(value).strip() for value in order_ids_payload)
    if any(not value for value in order_ids) or len(order_ids) != len(set(order_ids)):
        raise RuntimeError("open_order_ids contain an empty or duplicate value")
    return PaperAccountObservation(
        observed_at_utc=timestamp.astimezone(UTC).isoformat(),
        balances=balances,
        open_order_ids=order_ids,
    )


def run() -> dict[str, object]:
    if os.getenv(_GUARD_ENV, "").strip().upper() != "YES":
        raise RuntimeError(f"explicit guard required: {_GUARD_ENV}=YES")
    snapshot_store = ReadOnlyAccountSnapshotStore(_required_path(_SNAPSHOT_DB_ENV))
    snapshot = snapshot_store.latest()
    if snapshot is None:
        raise RuntimeError("no exchange snapshot is available")
    paper = _load_paper_observation(_required_path(_PAPER_OBSERVATION_ENV))
    evidence_store = SnapshotComparisonEvidenceStore(_required_path(_EVIDENCE_DB_ENV))
    try:
        max_age = float(os.getenv(_MAX_AGE_ENV, "300").strip())
    except ValueError as exc:
        raise RuntimeError(f"{_MAX_AGE_ENV} must be numeric") from exc
    comparison = compare_snapshot_to_paper(
        snapshot,
        paper,
        max_snapshot_age_seconds=max_age,
    )
    evidence = evidence_store.append(comparison)
    return {
        "status": comparison.status,
        "snapshot_id": comparison.snapshot_id,
        "snapshot_age_seconds": comparison.snapshot_age_seconds,
        "balance_mismatch_count": len(comparison.balance_mismatches),
        "exchange_only_currency_count": len(comparison.exchange_only_currencies),
        "paper_only_currency_count": len(comparison.paper_only_currencies),
        "exchange_only_order_count": len(comparison.exchange_only_order_ids),
        "paper_only_order_count": len(comparison.paper_only_order_ids),
        "evidence_id": evidence.evidence_id,
        "evidence_fingerprint": evidence.evidence_fingerprint,
    }


def main() -> int:
    try:
        report = run()
    except Exception as exc:  # command boundary: fail closed with no traceback/secrets
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True))
        return 1
    print(json.dumps({"ok": True, **report}, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
