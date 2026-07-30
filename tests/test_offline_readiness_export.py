from __future__ import annotations

import hashlib
import json
import zipfile
from dataclasses import asdict
from datetime import UTC, datetime

import pytest

from aipro.core.offline_readiness_export import export_operational_readiness_bundle
from aipro.core.operational_readiness_review import OperationalReadinessReview
from aipro.sqlite_utils import connect


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _write_review(path, review: OperationalReadinessReview, *, fingerprint: str | None = None) -> None:
    payload = _canonical(asdict(review))
    with connect(path) as db:
        db.execute(
            "CREATE TABLE operational_readiness_reviews ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, evaluated_at_utc TEXT NOT NULL, "
            "payload_json TEXT NOT NULL, fingerprint TEXT NOT NULL UNIQUE)"
        )
        db.execute(
            "INSERT INTO operational_readiness_reviews(evaluated_at_utc,payload_json,fingerprint) VALUES(?,?,?)",
            (review.evaluated_at_utc, payload, fingerprint or review.fingerprint),
        )


def _ready_review() -> OperationalReadinessReview:
    return OperationalReadinessReview(
        evaluated_at_utc=datetime(2026, 7, 26, tzinfo=UTC).isoformat(),
        smtp_delivery_evidence=True,
        totp_acceptance_evidence=True,
        alpaca_paper_qualifying=True,
        mailbox_arrival_attested=True,
        recovery_storage_attested=True,
        upbit_preflight_attested=True,
        status="READY_FOR_INDEPENDENT_REVIEW",
        blockers=(),
        source_fingerprints=("a" * 64, "b" * 64),
    )


def test_export_contains_deterministic_review_manifest_and_markdown(tmp_path) -> None:
    review = _ready_review()
    review_db = tmp_path / "reviews.sqlite3"
    _write_review(review_db, review)
    first = tmp_path / "first.zip"
    second = tmp_path / "second.zip"
    created_at = datetime(2026, 7, 27, 3, 0, tzinfo=UTC)

    result = export_operational_readiness_bundle(
        review_db=review_db,
        output_path=first,
        created_at_utc=created_at,
    )
    export_operational_readiness_bundle(
        review_db=review_db,
        output_path=second,
        created_at_utc=created_at,
    )

    assert first.read_bytes() == second.read_bytes()
    assert result.review_status == "READY_FOR_INDEPENDENT_REVIEW"
    with zipfile.ZipFile(first) as archive:
        assert archive.namelist() == ["manifest.json", "readiness_review.json", "readiness_review.md"]
        manifest = json.loads(archive.read("manifest.json"))
        payload = json.loads(archive.read("readiness_review.json"))
        markdown = archive.read("readiness_review.md").decode("utf-8")
    assert manifest["execution_authority"] is False
    assert manifest["review_fingerprint"] == review.fingerprint
    assert payload["status"] == "READY_FOR_INDEPENDENT_REVIEW"
    assert "does not enable LIVE mode" in markdown
    assert "LIVE_READY" not in markdown


def test_export_rejects_tampered_review_fingerprint(tmp_path) -> None:
    review_db = tmp_path / "reviews.sqlite3"
    _write_review(review_db, _ready_review(), fingerprint="0" * 64)
    with pytest.raises(ValueError, match="fingerprint mismatch"):
        export_operational_readiness_bundle(
            review_db=review_db,
            output_path=tmp_path / "export.zip",
            created_at_utc=datetime.now(UTC),
        )


def test_export_preserves_not_ready_blockers(tmp_path) -> None:
    review = OperationalReadinessReview(
        evaluated_at_utc=datetime(2026, 7, 26, tzinfo=UTC).isoformat(),
        smtp_delivery_evidence=False,
        totp_acceptance_evidence=False,
        alpaca_paper_qualifying=False,
        mailbox_arrival_attested=False,
        recovery_storage_attested=False,
        upbit_preflight_attested=False,
        status="NOT_READY",
        blockers=("SMTP_DELIVERY_EVIDENCE_MISSING",),
        source_fingerprints=(),
    )
    review_db = tmp_path / "reviews.sqlite3"
    _write_review(review_db, review)
    result = export_operational_readiness_bundle(
        review_db=review_db,
        output_path=tmp_path / "export.zip",
        created_at_utc=datetime.now(UTC),
    )
    assert result.review_status == "NOT_READY"
    assert result.blockers == ("SMTP_DELIVERY_EVIDENCE_MISSING",)


def test_export_requires_zip_and_timezone_aware_timestamp(tmp_path) -> None:
    review_db = tmp_path / "reviews.sqlite3"
    _write_review(review_db, _ready_review())
    with pytest.raises(ValueError, match="timezone-aware"):
        export_operational_readiness_bundle(
            review_db=review_db,
            output_path=tmp_path / "export.zip",
            created_at_utc=datetime(2026, 7, 27),
        )
    with pytest.raises(ValueError, match="end with .zip"):
        export_operational_readiness_bundle(
            review_db=review_db,
            output_path=tmp_path / "export.json",
            created_at_utc=datetime.now(UTC),
        )
