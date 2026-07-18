# Upbit Read-Only Market Data

AiPro can use Upbit's unauthenticated quotation API as the market-data source for the crypto PAPER runtime.

## Enable

```text
AIPRO_MARKET_DATA_PROVIDER=UPBIT
AIPRO_CRYPTO_SYMBOLS=KRW-BTC,KRW-ETH,KRW-XRP
AIPRO_MARKET_DATA_TIMEOUT_SEC=5.0
AIPRO_MARKET_DATA_MAX_ATTEMPTS=3
```

The default remains `AIPRO_MARKET_DATA_PROVIDER=DEMO`, so offline tests and deterministic smoke runs do not make network requests.

## Data construction

For each cycle:

1. Current trade prices are fetched in one `GET /v1/ticker` request.
2. Recent 60-minute candles are fetched for each configured symbol.
3. `change_1h_pct` compares the current ticker price with the previous completed hourly candle close.
4. `volatility_pct` is the population standard deviation of recent hourly percentage returns.

The adapter requires at least two valid hourly candles and rejects missing symbols, duplicate ticker rows, malformed JSON, non-positive prices, non-finite values, and symbol mismatches.

## Reliability

- HTTPS is mandatory.
- Requests have a bounded timeout.
- Transient transport failures, HTTP 429, and selected 5xx responses are retried with bounded backoff.
- Retry exhaustion raises `MarketDataError`; it never substitutes fabricated prices.
- The configured retry count is limited to 1–5 attempts.

## Security boundary

This adapter:

- uses no access key or secret key;
- calls quotation endpoints only;
- cannot query account balances;
- cannot create, cancel, or inspect orders;
- does not alter the PAPER broker or LIVE approval guards.

Selecting Upbit market data changes only the price input. It does not enable LIVE trading.

## Current limitations

- Only KRW trading pairs are accepted by the current crypto runtime.
- REST polling is used; WebSocket streaming is not implemented.
- Hourly candle volatility is a basic engineering feature, not a guarantee of predictive value.
- Candles may be absent when no trade occurred in an interval, so sparse markets can fail validation.
- A future health monitor should track stale timestamps, rate-limit headers, latency, and consecutive failures before unattended PAPER operation.
