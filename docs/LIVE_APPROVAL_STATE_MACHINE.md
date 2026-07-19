# Crypto LIVE approval state machine

## Scope

This component persists the operator approval sequence:

`/ai_upbit_go -> /confirm -> /go`

It does not submit, cancel, replace, or retry exchange orders. An `ACTIVE` approval state is only evidence that the operator sequence and safety checks completed. Order execution remains absent until a separate implementation and readiness review.

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
6. The readiness evidence fingerprint must be unchanged at activation.
7. `/go` cannot skip `/confirm`.
8. Restarting the process does not reset or bypass approval state.
9. Expired approval cannot be confirmed or activated.
10. The explicit LIVE environment guard must be enabled at activation.
11. Audit events are append-only; database triggers block UPDATE and DELETE.
12. Approval state is crypto-only and cannot authorize the US-stock domain.

## Operational integration

Telegram command handlers should translate commands into these calls:

- `/ai_upbit_go`: `LiveApprovalStore.request(...)`
- `/confirm <approval_id>`: `LiveApprovalStore.confirm(...)`
- `/go <approval_id>`: `LiveApprovalStore.activate(...)`

The runtime must call `revoke(...)` immediately when HALTED engages, readiness becomes FAIL, credentials change, the operator requests stop, or a process safety invariant fails.

## Important limitation

`ACTIVE` does not mean that authenticated order submission is implemented or permitted. The trading application must still require its existing double LIVE guards and a separately reviewed execution adapter.