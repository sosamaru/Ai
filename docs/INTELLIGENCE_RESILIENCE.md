# Intelligence resilience layer

The intelligence providers are wrapped by an asset-neutral safety layer before any future PAPER feature extraction.

## Included controls

- bounded exponential retry
- sliding-window rate limiting
- circuit breaker with recovery timeout
- TTL cache
- provider and operation scoped execution evidence
- append-only SQLite evidence with update/delete blocking

The executor fails closed when the provider circuit is open or the local rate limit is exceeded. Cached values are returned only before their explicit TTL expires.

Execution evidence records status, attempts, cache use, circuit state, timestamps, error class, and a SHA-256 fingerprint. It does not store API keys or Authorization headers.

This layer does not submit orders, enable LIVE mode, mutate balances, or connect intelligence output directly to strategy decisions.
