# AiPro Professional Runtime and Merge Audit

Date: 2026-07-30

## Scope

This audit reviews the current `main` integration after merge consolidation. It covers the preserved entrypoint chain, local startup behavior, configuration validation, Telegram response handling, SQLite contention, crypto market-data health wrapping, persistent approval transitions, Python-version compatibility, and pull-request validation.

The scope remains PAPER and non-live. No real-order endpoint, broker mutation authority, LIVE-readiness approval, or profitability claim is introduced.

## Findings corrected

### Local environment loading

The repository documented `.env.example`, but the runtime did not load a local `.env` file. `run.py` now performs dependency-free loading before application construction. Existing process environment values take precedence, preventing local files from overriding CI, VPS, service-manager, or secret-manager injection.

### Fail-closed configuration

Runtime validation now rejects non-positive initial cash and minimum order values, minimum orders above initial cash, unsupported log levels, and non-finite numeric values such as `NaN` for risk and market-data limits.

### Market-data wrapper concurrency

The crypto compatibility runtime temporarily routes the legacy application's market access through the health checker. That swap is now protected by a reentrant lock so concurrent status and cycle calls cannot make the health checker delegate to itself or restore the wrong provider.

### SQLite contention and approval atomicity

Core storage connections now use a bounded SQLite busy timeout. Persistent crypto approval transitions acquire an immediate transaction before reading or changing state. A competing process therefore waits for a bounded period and then fails closed instead of overwriting an approval sequence based on stale state.

### Telegram payload hardening

Telegram responses must now be JSON objects, update results must be lists, and malformed update entries are ignored without corrupting the polling offset. Network-level `OSError` failures are handled by the polling retry boundary.

### Warning-free compatibility validation

The optional boosting regression test used an invalid Python string escape. It now uses a raw regular expression. CI treats warnings as errors so similar defects cannot silently return.

## Validation contract

The pull-request workflow now runs on Python 3.11, 3.12, and 3.13. For each version it:

1. compiles root entrypoints, application packages, and tests;
2. executes `python run.py` through the full PAPER entrypoint chain using deterministic demo data and temporary storage;
3. runs the complete pytest suite with warnings promoted to errors;
4. preserves a per-version pytest log artifact.

The entrypoint remains:

`run.py -> telegram.py -> main.py -> TradingApplication`

## Merge policy

The audit branch is based on the latest `main`. It may be merged only after all matrix jobs pass. New work should continue on short-lived branches based on the latest `main`; stale branches must be rebased or replaced rather than force-merged over newer safety and documentation changes.

## Remaining limitations

Repository validation cannot prove operational or LIVE readiness. The following still require owner-controlled external evidence:

- SMTP delivery and mailbox confirmation;
- TOTP enrollment and offline recovery-material storage;
- supervised Upbit inspection and test-order preflight with real order creation absent;
- at least 30 calendar days of qualifying Alpaca PAPER evidence;
- independent crypto and U.S.-stock session evidence;
- an independent live-readiness decision.

The core runtime intentionally remains dependency-free. Optional boosting and deep-learning backends require separately provisioned research environments and are not exercised as real third-party binaries in core CI.
