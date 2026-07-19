# Crypto LIVE approval state machine

AiPro records future LIVE authorization intent through an exact Telegram sequence:

`/ai_upbit_go -> /confirm -> /go`

## Safety behavior

- the sequence expires after 300 seconds by default
- state is persisted in the crypto namespace and survives process restart
- `/confirm` without a valid request fails closed
- final `/go` without confirmation fails closed
- a repeated `/ai_upbit_go` replaces the previous sequence
- expired or invalid persisted state returns to `IDLE`
- status output exposes only the approval stage

Completing the sequence does not enable LIVE mode, submit an order, bypass PAPER validation, or change balances, positions, baselines, strategy state, or exchange evidence. Authenticated order submission remains absent.

The existing `/go` HALTED recovery behavior remains available only when no LIVE approval sequence is active.
