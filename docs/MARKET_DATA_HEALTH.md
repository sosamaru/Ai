# Market Data Health Gate

AiPro wraps the configured crypto market-data provider with a fail-closed health gate before strategy decisions and PAPER orders are allowed.

## Checks

- Request latency must not exceed `AIPRO_MARKET_DATA_MAX_LATENCY_SEC`.
- Empty snapshot batches are rejected.
- Consecutive provider failures are counted.
- The time since the last successful snapshot is exposed and can be checked against `AIPRO_MARKET_DATA_MAX_SNAPSHOT_AGE_SEC`.
- Provider, success/failure timestamps, latency, age, failure count, and last error are exposed in application status.

## Failure behavior

- Provider exceptions are converted to `MarketDataHealthError`.
- Strategy decisions and PAPER orders are not executed after the health failure.
- If a cycle ID was created before the failure, it is cleared and an immutable `cycle_aborted_market_data` event is recorded.
- Health failure does not enable LIVE trading and does not change balances, positions, or daily baselines.

## Configuration

```text
AIPRO_MARKET_DATA_MAX_LATENCY_SEC=10.0
AIPRO_MARKET_DATA_MAX_SNAPSHOT_AGE_SEC=120.0
AIPRO_MARKET_DATA_MAX_CONSECUTIVE_FAILURES=3
```

## Current limitation

The current freshness age measures time since AiPro's last validated successful snapshot. Source-exchange ticker and candle timestamps are not yet carried in `MarketSnapshot`; direct exchange timestamp validation remains a separate follow-up task.
