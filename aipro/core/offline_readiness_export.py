from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import zipfile
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from aipro.sqlite_utils import connect


@dataclass(frozen=True, slots=True)
class OfflineReadinessExport:
    created_at_utc: str
    review_fingerprint: str
    review_status: str
    blockers: tuple[str, ...]
    source_fingerprints: tuple[str, ...]
    manifest_fingerprint: str
    archive_path: str


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _latest_review(review_db: str | Path) -> tuple[dict[str, Any], str]:
    try:
        with connect(str(review_db), timeout=5.0) as db:
            row = db.execute(
                "SELECT payload_json,fingerprint FROM operational_readiness_reviews ORDER BY id DESC LIMIT 1"
            ).fetchone()
    except sqlite3.Error as exc:
        raise ValueError("operational readiness review database is unavailable") from exc
    if not row:
        raise ValueError("operational readiness review evidence is missing")
    payload = json.loads(str(row[0]))
    if not isinstance(payload, dict):
        raise ValueError("invalid operational readiness review payload")
    fingerprint = str(row[1])
    if _sha256_text(_canonical_json(payload)) != fingerprint:
        raise ValueError("operational readiness review fingerprint mismatch")
    return payload, fingerprint


def _render_markdown(payload: dict[str, Any], review_fingerprint: str, manifest_fingerprint: str) -> str:
    blockers = tuple(str(item) for item in payload.get("blockers", ()))
    sources = tuple(str(item) for item in payload.get("source_fingerprints", ()))
    blocker_lines = "\n".join(f"- {item}" for item in blockers) or "- None recorded"
    source_lines = "\n".join(f"- `{item}`" for item in sources) or "- None recorded"
    return (
        "# AiPro Operational Readiness Review Export\n\n"
        f"- Evaluated at (UTC): `{payload.get('evaluated_at_utc', '')}`\n"
        f"- Status: **{payload.get('status', 'NOT_READY')}**\n"
        f"- Review fingerprint: `{review_fingerprint}`\n"
        f"- Manifest fingerprint: `{manifest_fingerprint}`\n\n"
        "## Evidence checks\n\n"
        f"- SMTP delivery evidence: `{bool(payload.get('smtp_delivery_evidence', False))}`\n"
        f"- TOTP acceptance evidence: `{bool(payload.get('totp_acceptance_evidence', False))}`\n"
        f"- Alpaca PAPER qualifying evidence: `{bool(payload.get('alpaca_paper_qualifying', False))}`\n"
        f"- Mailbox arrival attested: `{bool(payload.get('mailbox_arrival_attested', False))}`\n"
        f"- TOTP recovery storage attested: `{bool(payload.get('recovery_storage_attested', False))}`\n"
        f"- Upbit preflight attested: `{bool(payload.get('upbit_preflight_attested', False))}`\n\n"
        "## Blockers\n\n"
        f"{blocker_lines}\n\n"
        "## Source fingerprints\n\n"
        f"{source_lines}\n\n"
        "## Safety boundary\n\n"
        "This export is an offline review package only. It does not enable LIVE mode, grant authorization, "
        "submit orders, mutate model governance state, prove profitability, or replace independent review.\n"
    )


def export_operational_readiness_bundle(
    *,
    review_db: str | Path,
    output_path: str | Path,
    created_at_utc: datetime,
) -> OfflineReadinessExport:
    if created_at_utc.tzinfo is None:
        raise ValueError("created_at_utc must be timezone-aware")
    destination = Path(output_path)
    if destination.suffix.lower() != ".zip":
        raise ValueError("output_path must end with .zip")
    destination.parent.mkdir(parents=True, exist_ok=True)

    payload, review_fingerprint = _latest_review(review_db)
    status = str(payload.get("status", "NOT_READY"))
    if status not in {"NOT_READY", "READY_FOR_INDEPENDENT_REVIEW"}:
        raise ValueError("unsupported readiness status")

    review_json = _canonical_json(payload) + "\n"
    manifest_base = {
        "format": "aipro-operational-readiness-export-v1",
        "created_at_utc": created_at_utc.astimezone(UTC).isoformat(),
        "review_fingerprint": review_fingerprint,
        "review_sha256": _sha256_text(review_json),
        "status": status,
        "files": ("manifest.json", "readiness_review.json", "readiness_review.md"),
        "execution_authority": False,
    }
    manifest_fingerprint = _sha256_text(_canonical_json(manifest_base))
    manifest = dict(manifest_base, manifest_fingerprint=manifest_fingerprint)
    markdown = _render_markdown(payload, review_fingerprint, manifest_fingerprint)

    entries = {
        "manifest.json": _canonical_json(manifest) + "\n",
        "readiness_review.json": review_json,
        "readiness_review.md": markdown,
    }
    fixed_timestamp = (2020, 1, 1, 0, 0, 0)
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name in sorted(entries):
            info = zipfile.ZipInfo(name, date_time=fixed_timestamp)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o600 << 16
            archive.writestr(info, entries[name].encode("utf-8"))

    return OfflineReadinessExport(
        created_at_utc=created_at_utc.astimezone(UTC).isoformat(),
        review_fingerprint=review_fingerprint,
        review_status=status,
        blockers=tuple(str(item) for item in payload.get("blockers", ())),
        source_fingerprints=tuple(str(item) for item in payload.get("source_fingerprints", ())),
        manifest_fingerprint=manifest_fingerprint,
        archive_path=str(destination),
    )


def main() -> int:
    if os.environ.get("AIPRO_EXPORT_READINESS") != "YES":
        print("Readiness export blocked: set AIPRO_EXPORT_READINESS=YES for an explicit offline export.")
        return 2
    result = export_operational_readiness_bundle(
        review_db=os.environ.get("AIPRO_READINESS_REVIEW_DB", "data/operational_readiness_reviews.sqlite3"),
        output_path=os.environ.get("AIPRO_READINESS_EXPORT_PATH", "data/operational_readiness_export.zip"),
        created_at_utc=datetime.now(UTC),
    )
    print(_canonical_json(asdict(result)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["OfflineReadinessExport", "export_operational_readiness_bundle"]
