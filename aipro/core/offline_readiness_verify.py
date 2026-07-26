from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import zipfile
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

_EXPECTED_FILES = ("manifest.json", "readiness_review.json", "readiness_review.md")
_EXPECTED_MANIFEST_KEYS = {
    "format",
    "created_at_utc",
    "review_fingerprint",
    "review_sha256",
    "status",
    "files",
    "execution_authority",
    "manifest_fingerprint",
}
_EXPECTED_REVIEW_KEYS = {
    "evaluated_at_utc",
    "smtp_delivery_evidence",
    "totp_acceptance_evidence",
    "alpaca_paper_qualifying",
    "mailbox_arrival_attested",
    "recovery_storage_attested",
    "upbit_preflight_attested",
    "status",
    "blockers",
    "source_fingerprints",
}
_EVIDENCE_BLOCKERS = (
    ("smtp_delivery_evidence", "SMTP_DELIVERY_EVIDENCE_MISSING"),
    ("totp_acceptance_evidence", "TOTP_ACCEPTANCE_EVIDENCE_MISSING"),
    ("alpaca_paper_qualifying", "ALPACA_30_DAY_QUALIFYING_EVIDENCE_MISSING"),
    ("mailbox_arrival_attested", "MAILBOX_ARRIVAL_ATTESTATION_MISSING"),
    ("recovery_storage_attested", "TOTP_RECOVERY_STORAGE_ATTESTATION_MISSING"),
    ("upbit_preflight_attested", "UPBIT_PREFLIGHT_ATTESTATION_MISSING"),
)
_ALLOWED_STATUSES = {"NOT_READY", "READY_FOR_INDEPENDENT_REVIEW"}
_HEX_64 = re.compile(r"[0-9a-f]{64}\Z")
_MAX_ARCHIVE_BYTES = 4 * 1024 * 1024
_MAX_ENTRY_BYTES = 1024 * 1024
_MAX_TOTAL_UNCOMPRESSED_BYTES = 2 * 1024 * 1024
_FIXED_ZIP_TIMESTAMP = (2020, 1, 1, 0, 0, 0)


@dataclass(frozen=True, slots=True)
class OfflineReadinessVerification:
    archive_path: str
    archive_sha256: str
    valid: bool
    review_status: str
    created_at_utc: str
    evaluated_at_utc: str
    review_fingerprint: str
    manifest_fingerprint: str
    blockers: tuple[str, ...]
    source_fingerprints: tuple[str, ...]
    checks: tuple[str, ...]
    verification_fingerprint: str
    execution_authority: bool = False


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_text(value: str) -> str:
    return _sha256_bytes(value.encode("utf-8"))


def _require_hex64(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _HEX_64.fullmatch(value):
        raise ValueError(f"{label} must be a lowercase SHA-256 fingerprint")
    return value


def _require_timezone_aware(value: Any, label: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be an ISO-8601 string")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{label} must be a valid ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{label} must be timezone-aware")
    return value


def _load_canonical_object(raw: bytes, label: str) -> tuple[dict[str, Any], str]:
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"{label} must be UTF-8") from exc
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{label} must contain valid JSON") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{label} must contain a JSON object")
    canonical = _canonical_json(value) + "\n"
    if text != canonical:
        raise ValueError(f"{label} is not canonical JSON")
    return value, text


def _render_markdown(payload: dict[str, Any], review_fingerprint: str, manifest_fingerprint: str) -> str:
    blockers = tuple(str(item) for item in payload["blockers"])
    sources = tuple(str(item) for item in payload["source_fingerprints"])
    blocker_lines = "\n".join(f"- {item}" for item in blockers) or "- None recorded"
    source_lines = "\n".join(f"- `{item}`" for item in sources) or "- None recorded"
    return (
        "# AiPro Operational Readiness Review Export\n\n"
        f"- Evaluated at (UTC): `{payload['evaluated_at_utc']}`\n"
        f"- Status: **{payload['status']}**\n"
        f"- Review fingerprint: `{review_fingerprint}`\n"
        f"- Manifest fingerprint: `{manifest_fingerprint}`\n\n"
        "## Evidence checks\n\n"
        f"- SMTP delivery evidence: `{payload['smtp_delivery_evidence']}`\n"
        f"- TOTP acceptance evidence: `{payload['totp_acceptance_evidence']}`\n"
        f"- Alpaca PAPER qualifying evidence: `{payload['alpaca_paper_qualifying']}`\n"
        f"- Mailbox arrival attested: `{payload['mailbox_arrival_attested']}`\n"
        f"- TOTP recovery storage attested: `{payload['recovery_storage_attested']}`\n"
        f"- Upbit preflight attested: `{payload['upbit_preflight_attested']}`\n\n"
        "## Blockers\n\n"
        f"{blocker_lines}\n\n"
        "## Source fingerprints\n\n"
        f"{source_lines}\n\n"
        "## Safety boundary\n\n"
        "This export is an offline review package only. It does not enable LIVE mode, grant authorization, "
        "submit orders, mutate model governance state, prove profitability, or replace independent review.\n"
    )


def _read_archive(path: Path) -> tuple[dict[str, bytes], str]:
    if path.suffix.lower() != ".zip":
        raise ValueError("archive_path must end with .zip")
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise ValueError("readiness export archive is unavailable") from exc
    if size <= 0 or size > _MAX_ARCHIVE_BYTES:
        raise ValueError("readiness export archive size is outside the allowed limit")
    try:
        archive_bytes = path.read_bytes()
        with zipfile.ZipFile(path) as archive:
            infos = archive.infolist()
            names = tuple(info.filename for info in infos)
            if names != _EXPECTED_FILES:
                raise ValueError("readiness export archive must contain the exact ordered file set")
            if archive.comment:
                raise ValueError("readiness export archive comment is not allowed")
            total_size = 0
            entries: dict[str, bytes] = {}
            for info in infos:
                if info.is_dir() or info.flag_bits & 0x1:
                    raise ValueError("readiness export archive contains an unsupported entry")
                if info.compress_type != zipfile.ZIP_DEFLATED:
                    raise ValueError("readiness export archive compression is unsupported")
                if info.date_time != _FIXED_ZIP_TIMESTAMP:
                    raise ValueError("readiness export archive timestamp is not deterministic")
                mode = info.external_attr >> 16
                if stat.S_IFMT(mode) == stat.S_IFLNK:
                    raise ValueError("readiness export archive symbolic links are not allowed")
                if mode & 0o777 != 0o600:
                    raise ValueError("readiness export archive permissions are invalid")
                if info.file_size < 0 or info.file_size > _MAX_ENTRY_BYTES:
                    raise ValueError("readiness export archive entry size is outside the allowed limit")
                total_size += info.file_size
                if total_size > _MAX_TOTAL_UNCOMPRESSED_BYTES:
                    raise ValueError("readiness export archive is too large after decompression")
                entries[info.filename] = archive.read(info)
    except (OSError, zipfile.BadZipFile, RuntimeError) as exc:
        raise ValueError("readiness export archive is invalid") from exc
    return entries, _sha256_bytes(archive_bytes)


def verify_operational_readiness_bundle(*, archive_path: str | Path) -> OfflineReadinessVerification:
    path = Path(archive_path)
    entries, archive_sha256 = _read_archive(path)
    manifest, manifest_text = _load_canonical_object(entries["manifest.json"], "manifest.json")
    payload, review_text = _load_canonical_object(entries["readiness_review.json"], "readiness_review.json")

    if set(manifest) != _EXPECTED_MANIFEST_KEYS:
        raise ValueError("manifest.json fields do not match export format v1")
    if set(payload) != _EXPECTED_REVIEW_KEYS:
        raise ValueError("readiness_review.json fields do not match export format v1")
    if manifest["format"] != "aipro-operational-readiness-export-v1":
        raise ValueError("unsupported readiness export format")
    if manifest["files"] != list(_EXPECTED_FILES):
        raise ValueError("manifest file list does not match archive contents")
    if manifest["execution_authority"] is not False:
        raise ValueError("readiness export must not grant execution authority")

    created_at_utc = _require_timezone_aware(manifest["created_at_utc"], "manifest created_at_utc")
    evaluated_at_utc = _require_timezone_aware(payload["evaluated_at_utc"], "review evaluated_at_utc")
    review_fingerprint = _require_hex64(manifest["review_fingerprint"], "review_fingerprint")
    review_sha256 = _require_hex64(manifest["review_sha256"], "review_sha256")
    manifest_fingerprint = _require_hex64(manifest["manifest_fingerprint"], "manifest_fingerprint")

    if _sha256_text(review_text) != review_sha256:
        raise ValueError("readiness review content hash mismatch")
    if _sha256_text(_canonical_json(payload)) != review_fingerprint:
        raise ValueError("readiness review fingerprint mismatch")
    manifest_base = dict(manifest)
    del manifest_base["manifest_fingerprint"]
    if _sha256_text(_canonical_json(manifest_base)) != manifest_fingerprint:
        raise ValueError("manifest fingerprint mismatch")
    if manifest_text != _canonical_json(manifest) + "\n":
        raise ValueError("manifest canonicalization mismatch")

    status = payload["status"]
    if not isinstance(status, str) or status not in _ALLOWED_STATUSES:
        raise ValueError("unsupported readiness status")
    if manifest["status"] != status:
        raise ValueError("manifest and review status do not match")
    for field, _ in _EVIDENCE_BLOCKERS:
        if type(payload[field]) is not bool:
            raise ValueError(f"{field} must be boolean")
    blockers = payload["blockers"]
    if not isinstance(blockers, list) or not all(isinstance(item, str) and item for item in blockers):
        raise ValueError("review blockers must be a list of non-empty strings")
    expected_blockers = tuple(blocker for field, blocker in _EVIDENCE_BLOCKERS if not payload[field])
    if tuple(blockers) != expected_blockers:
        raise ValueError("review blockers do not match evidence checks")
    expected_status = "READY_FOR_INDEPENDENT_REVIEW" if not expected_blockers else "NOT_READY"
    if status != expected_status:
        raise ValueError("review status does not match evidence checks")

    sources = payload["source_fingerprints"]
    if not isinstance(sources, list):
        raise ValueError("source_fingerprints must be a list")
    source_fingerprints = tuple(_require_hex64(item, "source fingerprint") for item in sources)
    if len(set(source_fingerprints)) != len(source_fingerprints):
        raise ValueError("source_fingerprints must not contain duplicates")

    try:
        markdown = entries["readiness_review.md"].decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("readiness_review.md must be UTF-8") from exc
    if markdown != _render_markdown(payload, review_fingerprint, manifest_fingerprint):
        raise ValueError("readiness review Markdown does not match verified evidence")

    checks = (
        "archive_structure",
        "canonical_manifest",
        "canonical_review",
        "content_fingerprints",
        "readiness_semantics",
        "human_readable_summary",
        "no_execution_authority",
    )
    verification_base = {
        "archive_sha256": archive_sha256,
        "review_status": status,
        "created_at_utc": created_at_utc,
        "evaluated_at_utc": evaluated_at_utc,
        "review_fingerprint": review_fingerprint,
        "manifest_fingerprint": manifest_fingerprint,
        "blockers": tuple(blockers),
        "source_fingerprints": source_fingerprints,
        "checks": checks,
        "execution_authority": False,
    }
    verification_fingerprint = _sha256_text(_canonical_json(verification_base))
    return OfflineReadinessVerification(
        archive_path=str(path),
        archive_sha256=archive_sha256,
        valid=True,
        review_status=status,
        created_at_utc=created_at_utc,
        evaluated_at_utc=evaluated_at_utc,
        review_fingerprint=review_fingerprint,
        manifest_fingerprint=manifest_fingerprint,
        blockers=tuple(blockers),
        source_fingerprints=source_fingerprints,
        checks=checks,
        verification_fingerprint=verification_fingerprint,
    )


def main() -> int:
    if os.environ.get("AIPRO_VERIFY_READINESS") != "YES":
        print("Readiness verification blocked: set AIPRO_VERIFY_READINESS=YES for explicit offline verification.")
        return 2
    try:
        result = verify_operational_readiness_bundle(
            archive_path=os.environ.get("AIPRO_READINESS_EXPORT_PATH", "data/operational_readiness_export.zip")
        )
    except ValueError as exc:
        print(_canonical_json({"valid": False, "error": str(exc), "execution_authority": False}))
        return 1
    print(_canonical_json(asdict(result)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["OfflineReadinessVerification", "verify_operational_readiness_bundle"]
