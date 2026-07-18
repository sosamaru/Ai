# PAPER Order Retention Policy

AiPro keeps recent completed PAPER orders inside the active `paper_account` state and moves older completed orders into the immutable `paper_order_archive` SQLite table.

## Default policy

- Retain the latest 1,000 completed orders in active account state.
- Archive older terminal orders only when `archive_completed_orders()` is explicitly called.
- Never archive `PENDING` or `PARTIALLY_FILLED` orders.
- Preserve archived orders indefinitely until a separately reviewed export/deletion policy exists.

Terminal statuses eligible for archival:

- `FILLED`
- `NO_POSITION`
- `REJECTED`
- `CANCELLED`
- `TIMEOUT`

## Safety guarantees

1. Archived order payloads are immutable. An attempt to overwrite the same client order ID with different contents fails.
2. Duplicate client order IDs are checked against both active and archived orders.
3. Reconciliation reads both active and archived filled orders.
4. Active account state is persisted only after every selected order has been written successfully to the archive.
5. Restart recovery can still retrieve archived orders by client order ID.
6. Archival does not change cash, positions, fills, or the daily baseline.

## Ordering

Completed order age is determined from immutable `paper_order_filled` and `paper_order_no_position` event insertion order, not dictionary order or wall-clock string sorting.

## Current limitation

The archive is bounded only on the active-state side. Archived evidence is intentionally retained without automatic deletion. A future export and signed-checkpoint policy is required before archive rows may be removed safely.
