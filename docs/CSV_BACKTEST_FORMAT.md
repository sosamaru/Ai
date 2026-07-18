# CSV Backtest Data Format

Required UTF-8 columns:

```text
timestamp,symbol,price,change_1h_pct,volatility_pct
```

Rules:

- `timestamp` must be ISO 8601 and include a timezone offset.
- `symbol` is normalized to uppercase.
- `price` must be finite and positive.
- `change_1h_pct` must be finite.
- `volatility_pct` must be finite and non-negative.
- A `(timestamp, symbol)` pair may appear only once.
- Unknown or missing columns are rejected.

The loader sorts accepted rows by timestamp and symbol and computes a canonical SHA-256 dataset fingerprint. Equivalent datasets produce the same fingerprint even if their input row order differs.
