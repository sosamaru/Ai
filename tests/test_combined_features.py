from datetime import UTC, datetime, timedelta

import pytest

from aipro.intelligence.combined_features import (
    FEATURE_NAMES,
    SCHEMA_VERSION,
    CombinedFeaturePolicy,
    build_combined_paper_feature_vector,
)
from aipro.intelligence.features import PaperIntelligenceSnapshot
from aipro.intelligence.macro import MacroRegime, MacroSnapshot
from aipro.intelligence.market_features import MarketFeatureSnapshot
from aipro.intelligence.sec_edgar import FilingEventType, FilingSnapshot, SecFilingEvent

NOW = datetime(2026, 7, 23, 10, 0, tzinfo=UTC)


def _news(*, eligible: bool = True, symbol: str = "AAPL", as_of: datetime = NOW) -> PaperIntelligenceSnapshot:
    return PaperIntelligenceSnapshot(
        symbol=symbol,
        as_of_utc=as_of.isoformat(),
        article_count=4,
        positive_count=2,
        negative_count=1,
        neutral_count=1,
        fused_sentiment_score=0.25,
        fused_sentiment_confidence=0.8,
        native_sentiment_score=0.2,
        native_relevance=0.7,
        event_counts=(("earnings", 1),),
        freshest_article_at_utc=as_of.isoformat(),
        eligible=eligible,
        ineligible_reason=None if eligible else "STALE_INTELLIGENCE",
        fingerprint="a" * 64,
    )


def _macro(*, eligible: bool = True, as_of: datetime = NOW) -> MacroSnapshot:
    return MacroSnapshot(
        as_of_utc=as_of.isoformat(),
        observations=(),
        regime=MacroRegime.RISK_ON,
        score=0.4,
        eligible=eligible,
        ineligible_reason=None if eligible else "STALE_MACRO_DATA",
        fingerprint="b" * 64,
    )


def _filings(*, eligible: bool = True, as_of: datetime = NOW) -> FilingSnapshot:
    event = SecFilingEvent(
        cik="320193",
        company_name="Apple Inc.",
        accession_number="0000320193-26-000001",
        form="8-K",
        filed_at_utc=as_of.isoformat(),
        report_date="2026-07-23",
        primary_document="event.htm",
        event_type=FilingEventType.MATERIAL_EVENT,
        sec_url="https://www.sec.gov/Archives/edgar/data/320193/1/event.htm",
    )
    return FilingSnapshot(
        cik="320193",
        company_name="Apple Inc.",
        as_of_utc=as_of.isoformat(),
        events=(event,),
        newest_filing_at_utc=as_of.isoformat(),
        eligible=eligible,
        ineligible_reason=None if eligible else "STALE_FILINGS",
        fingerprint="c" * 64,
    )


def _market(*, eligible: bool = True, symbol: str = "AAPL", as_of: datetime = NOW) -> MarketFeatureSnapshot:
    return MarketFeatureSnapshot(
        symbol=symbol,
        as_of_utc=as_of.isoformat(),
        bar_count=30,
        return_short_pct=1.0,
        return_medium_pct=2.0,
        realized_volatility_pct=3.0,
        average_true_range_pct=1.2,
        volume_ratio=1.1,
        quote_volume_average=1_000_000.0,
        spread_bps_average=2.5,
        illiquidity_score=0.01,
        trend_score=0.3,
        eligible=eligible,
        ineligible_reasons=() if eligible else ("STALE_MARKET_DATA",),
        fingerprint="d" * 64,
    )


def _build(**overrides):
    data = {
        "symbol": "AAPL",
        "as_of_utc": NOW,
        "news": _news(),
        "macro": _macro(),
        "filings": _filings(),
        "market": _market(),
    }
    data.update(overrides)
    return build_combined_paper_feature_vector(**data)


def test_builds_stable_versioned_vector() -> None:
    first = _build()
    second = _build()
    assert first.schema_version == SCHEMA_VERSION
    assert first.feature_names == FEATURE_NAMES
    assert len(first.values) == len(FEATURE_NAMES)
    assert first.eligible is True
    assert first.fingerprint == second.fingerprint
    assert first.as_mapping()["filing_material_event_count"] == 1.0


def test_fails_closed_when_required_component_is_ineligible() -> None:
    result = _build(macro=_macro(eligible=False), market=_market(eligible=False))
    assert result.eligible is False
    assert "MACRO:STALE_MACRO_DATA" in result.ineligible_reasons
    assert "MARKET:STALE_MARKET_DATA" in result.ineligible_reasons


def test_rejects_symbol_mismatch() -> None:
    with pytest.raises(ValueError, match="component symbol mismatch"):
        _build(news=_news(symbol="MSFT"))


def test_detects_component_time_skew() -> None:
    result = _build(
        macro=_macro(as_of=NOW - timedelta(minutes=10)),
        policy=CombinedFeaturePolicy(maximum_component_skew_seconds=300),
    )
    assert result.eligible is False
    assert "COMPONENT_TIME_SKEW" in result.ineligible_reasons


def test_optional_component_can_be_ineligible_without_blocking() -> None:
    result = _build(
        filings=_filings(eligible=False),
        policy=CombinedFeaturePolicy(require_filings=False),
    )
    assert result.eligible is True
