# Exchange Order Reconciliation

This component handles an ambiguous order outcome after a timeout or interrupted response.

## Safety policy

- Reconciliation uses only the authenticated read-only `GET /v1/order` client.
- A lookup may use the exchange UUID, the client-generated identifier, or both.
- Any confirmed existing order blocks resubmission.
- Conflicting UUID and identifier results are `AMBIGUOUS` and block resubmission.
- Lookup failures and unproven absence also block resubmission.
- This component never submits, cancels, edits, or retries an order.

`retry_submission_allowed` is intentionally always false in this phase. A future LIVE submission adapter must remain absent until supervised PAPER readiness, explicit approval, idempotency persistence, and exchange-specific not-found semantics are independently validated.
