from __future__ import annotations

import pytest

from aipro.backtest_csv import BacktestCsvError, parse_backtest_csv

VALID_CSV = """timestamp,symbol,price,change_1h_pct,volatility_pct
2026-01-01T00:00:00+09:00,KRW-BTC,100000000,1.2,2.5
2026-01-01T01:00:00+09:00,KRW-BTC,101000000,0.8,2.1
"""


def test_parse_backtest_csv_returns_sorted_metadata() -> None:
    dataset = parse_backtest_csv(VALID_CSV)
    assert dataset.row_count == 2
    assert dataset.symbols == ("KRW-BTC",)
    assert len(dataset.sha256) == 64


def test_fingerprint_is_stable_for_equivalent_row_order() -> None:
    reversed_csv = """timestamp,symbol,price,change_1h_pct,volatility_pct
2026-01-01T01:00:00+09:00,KRW-BTC,101000000,0.8,2.1
2026-01-01T00:00:00+09:00,KRW-BTC,100000000,1.2,2.5
"""
    assert parse_backtest_csv(VALID_CSV).sha256 == parse_backtest_csv(reversed_csv).sha256


def test_duplicate_timestamp_symbol_is_rejected() -> None:
    duplicate = VALID_CSV + "2026-01-01T00:00:00+09:00,krw-btc,100,0,1\n"
    with pytest.raises(BacktestCsvError, match="duplicate row"):
        parse_backtest_csv(duplicate)


def test_invalid_schema_is_rejected() -> None:
    with pytest.raises(BacktestCsvError, match="invalid CSV schema"):
        parse_backtest_csv("timestamp,symbol,price\n2026-01-01T00:00:00+09:00,KRW-BTC,1\n")


def test_naive_timestamp_is_rejected() -> None:
    csv_text = """timestamp,symbol,price,change_1h_pct,volatility_pct
2026-01-01T00:00:00,KRW-BTC,100,0,1
"""
    with pytest.raises(BacktestCsvError, match="timezone offset"):
        parse_backtest_csv(csv_text)


def test_non_finite_and_negative_volatility_are_rejected() -> None:
    non_finite = """timestamp,symbol,price,change_1h_pct,volatility_pct
2026-01-01T00:00:00+09:00,KRW-BTC,nan,0,1
"""
    negative_volatility = """timestamp,symbol,price,change_1h_pct,volatility_pct
2026-01-01T00:00:00+09:00,KRW-BTC,100,0,-1
"""
    with pytest.raises(BacktestCsvError, match="must be finite"):
        parse_backtest_csv(non_finite)
    with pytest.raises(BacktestCsvError, match="must be non-negative"):
        parse_backtest_csv(negative_volatility)
