# AiPro Completion Manifest

The completion manifest is a deterministic repository audit for the approved PAPER and non-live construction scope. It compares development claims against code files, regression tests, safety or design documentation, and explicit `PROJECT_ROADMAP.md` markers.

## What it verifies

The default manifest checks these claim groups:

1. The `run.py -> telegram.py -> main.py -> TradingApplication` entrypoint contract
2. Purged walk-forward logistic, gradient-boosting, and sequence-model training
3. PAPER champion selection, registry, monitoring, approvals, and governance commands
4. Domain-isolated PAPER strategy validation
5. SEC EDGAR metadata, filing text, XBRL, materiality, and historical outcome analysis
6. Dependency-free CI and secret/LIVE safety boundaries

Every referenced file receives existence, byte-size, and SHA-256 evidence. Every roadmap marker must be present exactly. A claim is complete only when its code, tests, documentation, and roadmap evidence all exist.

## How to produce a manifest

```python
from pathlib import Path

from aipro.research.completion_manifest import (
    build_completion_manifest,
    render_manifest_markdown,
)

manifest = build_completion_manifest(Path("."))
print(render_manifest_markdown(manifest))
```

The manifest fingerprint is deterministic for the same repository contents. Absolute local paths are excluded from the fingerprint.

## Development versus operations

`development_complete` concerns the reviewed repository construction scope only. It does not mean live trading is ready or profitable.

`operational_complete` remains false while any of the following require real external evidence:

- Dedicated SMTP delivery verification
- TOTP enrollment and offline recovery-material storage
- At least 30 calendar days of actual Alpaca PAPER operation
- Independent qualifying crypto and U.S.-stock sessions and orders
- Supervised Upbit inspection and test-order preflight with real order creation disabled
- A separate live-readiness decision from immutable evidence

The validator deliberately cannot infer these outcomes from files, timestamps, comments, or roadmap edits.

## Fail-closed behavior

The manifest becomes incomplete when:

- a required code, test, or documentation file is missing;
- a required roadmap marker is missing;
- a repository path is absolute or attempts `..` traversal;
- claim IDs or operational requirement IDs are duplicated;
- the roadmap or repository root is unavailable.

## Safety boundary

A successful development manifest:

- remains PAPER-only;
- grants no execution authority;
- does not contact a broker or market-data provider;
- does not submit, cancel, replace, or retry orders;
- does not activate LIVE mode or mutate champion state;
- does not prove profitability;
- does not replace the mandatory operational and live-readiness evidence gates.

The manifest is an integrity and traceability report, not a trading signal or deployment approval.
