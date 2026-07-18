# Order Lifecycle

AiPro uses a caller-supplied `client_order_id` as the idempotency key for every order intent.

## States

- `CREATED`: intent accepted and persisted
- `SUBMITTED`: broker or exchange submission started
- `FILLED`: execution completed
- `FAILED`: execution failed permanently
- `CANCELLED`: execution intentionally stopped

Allowed flow:

`CREATED -> SUBMITTED -> FILLED | FAILED | CANCELLED`

`CREATED` may also move directly to `FAILED` or `CANCELLED` before submission.
Terminal states cannot transition again.

## Safety properties

1. `client_order_id` is the SQLite primary key.
2. A duplicate ID cannot create a second order record.
3. Unknown order transitions fail closed.
4. Invalid or terminal-state transitions are rejected.
5. Paper-broker account mutation will be connected in the next implementation step.

This foundation does not submit real exchange orders.
