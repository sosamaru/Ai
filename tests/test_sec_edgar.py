from datetime import UTC, datetime
import json

import pytest

from aipro.intelligence.sec_edgar import (
    FilingEventType,
    SecEdgarClient,
    build_filing_snapshot,
    classify_filing,
    normalize_recent_filings,
)


def payload(filing_date: str = "2026-07-20") -> dict[str, object]:
    return {
        "cik": "0000320193",
        "name": "Example Corp",
        "filings": {
            "recent": {
                "accessionNumber": ["0000320193-26-000001", "0000320193-26-000002"],
                "filingDate": [filing_date, "2026-06-01"],
                "reportDate": ["2026-06-30", "2026-05-31"],
                "form": ["10-Q", "8-K"],
                "primaryDocument": ["form10q.htm", "form8k.htm"],
                "items": ["", "2.02,9.01"],
            }
        },
    }


def test_client_requires_identifying_user_agent_and_uses_read_only_endpoint() -> None:
    with pytest.raises(ValueError, match="contact email"):
        SecEdgarClient("AiPro")

    captured = {}

    class Response:
        def read(self):
            return json.dumps(payload()).encode()
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False

    def opener(req, timeout):
        captured["url"] = req.full_url
        captured["agent"] = req.headers["User-agent"]
        return Response()

    client = SecEdgarClient("AiPro research owner@example.com", opener=opener)
    result = client.fetch_submissions("320193")
    assert result["name"] == "Example Corp"
    assert captured["url"].endswith("/CIK0000320193.json")
    assert "owner@example.com" in captured["agent"]


def test_normalization_and_classification_are_deterministic() -> None:
    events = normalize_recent_filings(payload())
    assert len(events) == 2
    assert events[0].form == "10-Q"
    assert events[0].event_type is FilingEventType.QUARTERLY_REPORT
    assert events[1].event_type is FilingEventType.MATERIAL_EVENT
    assert events[1].items == ("2.02", "9.01")
    assert events[0].sec_url.startswith("https://www.sec.gov/Archives/")
    assert events == normalize_recent_filings(payload())
    assert events[0].fingerprint == normalize_recent_filings(payload())[0].fingerprint


def test_snapshot_fails_closed_for_missing_or_stale_filings() -> None:
    as_of = datetime(2026, 7, 23, tzinfo=UTC)
    fresh = build_filing_snapshot(payload(), as_of_utc=as_of)
    assert fresh.eligible is True
    assert len(fresh.fingerprint) == 64

    stale = build_filing_snapshot(payload("2025-01-01"), as_of_utc=as_of, maximum_age_days=30)
    assert stale.eligible is False
    assert stale.ineligible_reason == "STALE_FILINGS"

    empty = payload()
    empty["filings"]["recent"] = {
        "accessionNumber": [], "filingDate": [], "reportDate": [],
        "form": [], "primaryDocument": [], "items": []
    }
    missing = build_filing_snapshot(empty, as_of_utc=as_of)
    assert missing.eligible is False
    assert missing.ineligible_reason == "NO_RELEVANT_FILINGS"


def test_form_filter_and_invalid_columns_fail_closed() -> None:
    snapshot = build_filing_snapshot(
        payload(),
        as_of_utc=datetime(2026, 7, 23, tzinfo=UTC),
        allowed_forms=("10-Q",),
    )
    assert tuple(event.form for event in snapshot.events) == ("10-Q",)
    assert classify_filing("S-3") is FilingEventType.SECURITIES_OFFERING

    broken = payload()
    broken["filings"]["recent"]["form"] = ["10-Q"]
    with pytest.raises(RuntimeError, match="inconsistent lengths"):
        normalize_recent_filings(broken)
