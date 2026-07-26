from __future__ import annotations

import hashlib
import json
import sqlite3
import zipfile
from dataclasses import asdict
from datetime import UTC, datetime

import pytest

from aipro.core.offline_readiness_export import export_operational_readiness_bundle
from aipro.core.offline_readiness_verify import verify_operational_readiness_bundle
from aipro.core.operational_readiness_review import OperationalReadinessReview


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _write_review(path, review: OperationalReadinessReview) -> None:
    payload = _canonical(asdict(review))
    with sqlite3.connect(path) as db:
        db.execute(
            "CREATE TABLE operational_readiness_reviews ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, evaluated_at_utc TEXT NOT NULL, "
            "payload_json TEXT NOT NULL, fingerprint TEXT NOT NULL UNIQUE)"
        )
        db.execute(
            "INSERT INTO operational_readiness_reviews(evaluated_at_utc,payload_json,fingerprint) VALUES(?,?,?)",
            (review.evaluated_at_utc, payload, review.fingerprint),
        )


def _review(*, ready: bool = True) -> OperationalReadinessReview:
    blockers = () if ready else ("SMTP_DELIVERY_EVIDENCE_MISSING",)
    return OperationalReadinessReview(
        evaluated_at_utc=datetime(2026, 7, 27, tzinfo=UTC).isoformat(),
        smtp_delivery_evidence=ready,
        totp_acceptance_evidence=True,
        alpaca_paper_qualifying=True,
        mailbox_arrival_attested=True,
        recovery_storage_attested=True,
        upbit_preflight_attested=True,
        status="READY_FOR_INDEPENDENT_REVIEW" if ready else "NOT_READY",
        blockers=blockers,
        source_fingerprints=("a" * 64, "b" * 64),
    )


def _export(tmp_path, *, ready: bool = True):
    db = tmp_path / "reviews.sqlite3"
    archive = tmp_path / "export.zip"
    _write_review(db, _review(ready=ready))
    export_operational_readiness_bundle(
        review_db=db,
        output_path=archive,
        created_at_utc=datetime(2026, 7, 27, 3, tzinfo=UTC),
    )
    return archive


def _write_entries(path, entries: dict[str, bytes]) -> None:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name in sorted(entries):
            info = zipfile.ZipInfo(name, date_time=(2020, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o600 << 16
            archive.writestr(info, entries[name])


def _entries(path) -> dict[str, bytes]:
    with zipfile.ZipFile(path) as archive:
        return {name: archive.read(name) for name in archive.namelist()}


def test_verify_valid_export_without_source_database(tmp_path) -> None:
    archive = _export(tmp_path)
    result = verify_operational_readiness_bundle(archive_path=archive)

    assert result.valid is True
    assert result.review_status == "READY_FOR_INDEPENDENT_REVIEW"
    assert result.execution_authority is False
    assert len(result.archive_sha256) == 64
    assert len(result.verification_fingerprint) == 64

    (tmp_path / "reviews.sqlite3").unlink()
    assert verify_operational_readiness_bundle(archive_path=archive).valid is True


def test_verify_rejects_extra_or_tampered_content(tmp_path) -> None:
    archive = _export(tmp_path)
    entries = _entries(archive)
    entries["unexpected.txt"] = b"no"
    extra = tmp_path / "extra.zip"
    _write_entries(extra, entries)

    with pytest.raises(ValueError, match="exact ordered file set"):
        verify_operational_readiness_bundle(archive_path=extra)

    entries = _entries(archive)
    payload = json.loads(entries["readiness_review.json"])
    payload["status"] = "NOT_READY"
    entries["readiness_review.json"] = (_canonical(payload) + "\n").encode("utf-8")
    tampered = tmp_path / "tampered.zip"
    _write_entries(tampered, entries)

    with pytest.raises(ValueError, match="content hash mismatch"):
        verify_operational_readiness_bundle(archive_path=tampered)


def test_verify_rejects_execution_authority_even_with_valid_manifest_fingerprint(tmp_path) -> None:
    archive = _export(tmp_path)
    entries = _entries(archive)
    manifest = json.loads(entries["manifest.json"])
    manifest["execution_authority"] = True
    manifest_base = dict(manifest)
    manifest_base.pop("manifest_fingerprint")
    manifest["manifest_fingerprint"] = hashlib.sha256(_canonical(manifest_base).encode("utf-8")).hexdigest()
    entries["manifest.json"] = (_canonical(manifest) + "\n").encode("utf-8")
    altered = tmp_path / "authority.zip"
    _write_entries(altered, entries)

    with pytest.raises(ValueError, match="must not grant execution authority"):
        verify_operational_readiness_bundle(archive_path=altered)


def test_verify_rejects_semantically_inconsistent_review_with_recomputed_hashes(tmp_path) -> None:
    archive = _export(tmp_path, ready=False)
    entries = _entries(archive)
    payload = json.loads(entries["readiness_review.json"])
    payload["blockers"] = []
    review_json = _canonical(payload) + "\n"
    review_fingerprint = hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()

    manifest = json.loads(entries["manifest.json"])
    manifest["review_fingerprint"] = review_fingerprint
    manifest["review_sha256"] = hashlib.sha256(review_json.encode("utf-8")).hexdigest()
    manifest_base = dict(manifest)
    manifest_base.pop("manifest_fingerprint")
    manifest["manifest_fingerprint"] = hashlib.sha256(_canonical(manifest_base).encode("utf-8")).hexdigest()

    entries["readiness_review.json"] = review_json.encode("utf-8")
    entries["manifest.json"] = (_canonical(manifest) + "\n").encode("utf-8")
    altered = tmp_path / "semantic.zip"
    _write_entries(altered, entries)

    with pytest.raises(ValueError, match="blockers do not match evidence checks"):
        verify_operational_readiness_bundle(archive_path=altered)
