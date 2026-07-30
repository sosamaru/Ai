# Persistent crypto LIVE approval evidence

## Scope

This component persists the operator approval sequence:

`/ai_upbit_go -> /confirm -> /go`

The implementation lives in `aipro/crypto/persistent_live_approval.py` so the existing `aipro/crypto/live_approval.py` compatibility API remains unchanged. This separation resolves the stale PR conflict without deleting or replacing current behavior.

It does not submit, cancel, replace, or retry exchange orders. An `ACTIVE` approval state is only evidence that the operator sequence and safety checks completed. It does not grant execution authority.

## States

- `REQUESTED`: readiness passed, HALTED is false, and an approval window was opened.
- `CONFIRMED`: the same operator confirmed the same approval ID before expiry.
- `ACTIVE`: the same operator issued `/go`; readiness evidence is unchanged, readiness still passes, HALTED remains false, and the environment LIVE guard is enabled.
- `EXPIRED`: the approval window elapsed.
- `REVOKED`: an operator or safety event revoked the sequence.

## Fail-closed rules

1. Readiness must pass before a request is created.
2. HALTED blocks request and activation.
3. Approval TTL is restricted to 30–900 seconds.
4. A second unexpired request is rejected.
5. Operator identity is stored only as a SHA-256 fingerprint and must match at every step.
6. Readiness fingerprints must be valid SHA-256 hexadecimal values and must remain unchanged at activation.
7. `/go` cannot skip `/confirm`.
8. Restarting the process does not reset or bypass approval state.
9. Expired approval cannot be confirmed or activated.
10. The explicit LIVE environment guard must be enabled at activation.
11. Persisted states, fingerprints, and timestamps are validated when read.
12. Audit events are append-only; database triggers block UPDATE and DELETE.
13. Approval state is crypto-only and cannot authorize the US-stock domain.

## Operational integration

Telegram command handlers may translate commands into these calls after a separate integration review:

- `/ai_upbit_go`: `LiveApprovalStore.request(...)`
- `/confirm <approval_id>`: `LiveApprovalStore.confirm(...)`
- `/go <approval_id>`: `LiveApprovalStore.activate(...)`

The runtime must call `revoke(...)` when HALTED engages, readiness becomes FAIL, credentials change, the operator requests stop, or a process safety invariant fails.

## Important limitation

`ACTIVE` does not mean that authenticated order submission is implemented or permitted. The trading application must still require all existing LIVE guards, operational evidence, independent readiness review, reconciliation, freshness, risk, HALTED, and kill-switch gates.
