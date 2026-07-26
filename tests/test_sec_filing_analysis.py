from __future__ import annotations

import json
from math import isclose

import pytest

from aipro.intelligence.sec_edgar import FilingEventType, SecFilingEvent
from aipro.intelligence.sec_filing_analysis import (
    MaterialityLevel,
    PriceObservation,
    SecFilingContentClient,
    build_filing_analysis_report,
    evaluate_historical_outcomes,
    extract_filing_text,
    extract_xbrl_facts,
    score_filing_materiality,
)


def _event(*, cik: str = "320193", form: str = "10-Q") -> SecFilingEvent:
    return SecFilingEvent(
        cik=cik,
        company_name="Example Corp",
        accession_number="0000320193-26-000001",
        form=form,
        filed_at_utc="2026-04-01T00:00:00+00:00",
        report_date="2026-03-31",
        primary_document="example.htm",
        event_type=FilingEventType.QUARTERLY_REPORT,
        sec_url=(
            "https://www.sec.gov/Archives/edgar/data/320193/"
            "000032019326000001/example.htm"
        ),
        items=("2.02",),
    )


def _html() -> str:
    return """
    <html><head><style>.hidden { display:none }</style><script>bankruptcy</script></head>
    <body>
      <h1>Quarterly Report</h1>
      <p>Item 2.02 Results of Operations.</p>
      <p>The company identified a material weakness and will restate prior results.</p>
      <p>Management discussed liquidity, guidance, and operating performance in detail.</p>
      <p>This additional sentence ensures the visible evidence is comfortably above
      the minimum evidence threshold used by the deterministic scorer.</p>
    </body></html>
    """


def _companyfacts(*, cik: int = 320193) -> dict:
    accession = "0000320193-26-000001"
    return {
        "cik": cik,
        "entityName": "Example Corp",
        "facts": {
            "us-gaap": {
                "RevenueFromContractWithCustomerExcludingAssessedTax": {
                    "label": "Revenue",
                    "units": {
                        "USD": [
                            {
                                "start": "2025-01-01",
                                "end": "2025-03-31",
                                "val": 100,
                                "accn": "0000320193-25-000001",
                                "fy": 2025,
                                "fp": "Q1",
                                "form": "10-Q",
                                "filed": "2025-04-01",
                                "frame": "CY2025Q1",
                            },
                            {
                                "start": "2026-01-01",
                                "end": "2026-03-31",
                                "val": 160,
                                "accn": accession,
                                "fy": 2026,
                                "fp": "Q1",
                                "form": "10-Q",
                                "filed": "2026-04-01",
                                "frame": "CY2026Q1",
                            },
                        ]
                    },
                },
                "NetIncomeLoss": {
                    "label": "Net income",
                    "units": {
                        "USD": [
                            {
                                "start": "2025-01-01",
                                "end": "2025-03-31",
                                "val": 20,
                                "accn": "0000320193-25-000001",
                                "fy": 2025,
                                "fp": "Q1",
                                "form": "10-Q",
                                "filed": "2025-04-01",
                            },
                            {
                                "start": "2026-01-01",
                                "end": "2026-03-31",
                                "val": -5,
                                "accn": accession,
                                "fy": 2026,
                                "fp": "Q1",
                                "form": "10-Q",
                                "filed": "2026-04-01",
                            },
                        ]
                    },
                },
            }
        },
    }


def _prices(values: tuple[float, ...]) -> tuple[PriceObservation, ...]:
    return tuple(
        PriceObservation(
            observed_at_utc=f"2026-04-{index + 1:02d}T20:00:00+00:00",
            close=value,
        )
        for index, value in enumerate(values)
    )


def test_visible_text_extraction_is_bounded_and_ignores_scripts():
    result = extract_filing_text(_event(), _html())
    assert "bankruptcy" not in result.text.casefold()
    assert result.detected_items == ("2.02",)
    assert "material weakness" in result.signal_terms
    assert "restatement" in result.signal_terms
    assert result.character_count > 100
    assert len(result.fingerprint) == 64


def test_xbrl_extraction_matches_accession_and_builds_prior_comparisons():
    result = extract_xbrl_facts(_event(), _companyfacts())
    assert result.eligible
    assert len(result.current_facts) == 2
    by_concept = {item.concept: item for item in result.comparisons}
    revenue = by_concept["RevenueFromContractWithCustomerExcludingAssessedTax"]
    income = by_concept["NetIncomeLoss"]
    assert isclose(revenue.change_ratio or 0.0, 0.6)
    assert income.sign_reversal
    assert len(result.fingerprint) == 64


def test_xbrl_cik_mismatch_fails_closed():
    with pytest.raises(ValueError, match="CIK"):
        extract_xbrl_facts(_event(), _companyfacts(cik=1))


def test_materiality_combines_form_items_text_and_xbrl_changes():
    event = _event()
    text = extract_filing_text(event, _html())
    xbrl = extract_xbrl_facts(event, _companyfacts())
    assessment = score_filing_materiality(event, text, xbrl)
    assert assessment.evidence_sufficient
    assert assessment.level is MaterialityLevel.CRITICAL
    assert assessment.score >= 75
    assert any(reason.startswith("xbrl:NetIncomeLoss") for reason in assessment.reasons)


def test_historical_outcomes_include_benchmark_adjusted_returns():
    report = evaluate_historical_outcomes(
        _event(),
        _prices((100.0, 110.0, 121.0, 119.0)),
        horizons=(1, 2),
        benchmark_prices=_prices((100.0, 105.0, 110.0, 111.0)),
    )
    assert report.eligible
    assert len(report.outcomes) == 2
    first, second = report.outcomes
    assert isclose(first.raw_return, 0.10)
    assert isclose(first.benchmark_return or 0.0, 0.05)
    assert isclose(first.abnormal_return or 0.0, 0.05)
    assert isclose(second.raw_return, 0.21)
    assert isclose(second.abnormal_return or 0.0, 0.11)


def test_insufficient_forward_prices_return_ineligible_evidence():
    report = evaluate_historical_outcomes(
        _event(),
        _prices((100.0, 101.0)),
        horizons=(5,),
    )
    assert not report.eligible
    assert report.ineligible_reason == "INSUFFICIENT_FORWARD_PRICES"
    assert report.outcomes == ()


def test_duplicate_price_timestamps_fail_closed():
    duplicate = PriceObservation("2026-04-01T20:00:00+00:00", 101.0)
    with pytest.raises(ValueError, match="unique"):
        evaluate_historical_outcomes(
            _event(),
            (PriceObservation("2026-04-01T20:00:00+00:00", 100.0), duplicate),
            horizons=(1,),
        )


def test_full_report_is_deterministic_and_never_grants_authority():
    first = build_filing_analysis_report(
        _event(),
        filing_html=_html(),
        companyfacts_payload=_companyfacts(),
        prices=_prices((100.0, 110.0, 121.0)),
        horizons=(1, 2),
    )
    second = build_filing_analysis_report(
        _event(),
        filing_html=_html(),
        companyfacts_payload=_companyfacts(),
        prices=_prices((100.0, 110.0, 121.0)),
        horizons=(1, 2),
    )
    assert first.fingerprint == second.fingerprint
    assert first.paper_only
    assert not first.grants_execution_authority


class _Response:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self, size: int = -1) -> bytes:
        return self.payload if size < 0 else self.payload[:size]


def test_content_client_is_read_only_identified_and_bounded():
    calls = []

    def opener(req, *, timeout):
        calls.append((req, timeout))
        return _Response(json.dumps(_companyfacts()).encode())

    client = SecFilingContentClient(
        "AiPro Research research@example.com",
        maximum_response_bytes=100_000,
        opener=opener,
    )
    payload = client.fetch_companyfacts("320193")
    assert payload["cik"] == 320193
    request_object, timeout = calls[0]
    assert request_object.full_url.endswith("CIK0000320193.json")
    assert request_object.headers["User-agent"].endswith("research@example.com")
    assert timeout == 15.0


def test_content_client_rejects_non_sec_filing_urls():
    client = SecFilingContentClient(
        "AiPro Research research@example.com",
        opener=lambda *_args, **_kwargs: _Response(b""),
    )
    with pytest.raises(ValueError, match="SEC"):
        client.fetch_filing_html("https://example.com/filing.htm")
