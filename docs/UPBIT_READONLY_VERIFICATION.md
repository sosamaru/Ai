# Upbit read-only supervised verification

This command verifies the isolated authenticated Upbit account boundary without enabling order submission or cancellation.

## Safety boundary

- Only the existing GET-only `UpbitReadOnlyAccountClient` is used.
- No broker, strategy, PAPER balance, daily baseline, or LIVE approval state is modified.
- Mutation capability is absent from the verification module.
- Output excludes API keys, Authorization headers, balances, average prices, order UUIDs, and identifiers.
- A SHA-256 snapshot fingerprint is emitted so repeated observations can be compared without storing raw account data.

## API-key requirements

Create a dedicated Upbit API key with the least privileges needed for account and order inspection.

- Enable account inquiry and order inquiry only.
- Disable order creation and cancellation permissions.
- Disable withdrawal and deposit-management permissions.
- Restrict the key to the supervised machine's public IP address.
- Never commit credentials or command output containing private diagnostics.

## Environment

Set credentials only in the supervised runtime environment:

```bash
AIPRO_UPBIT_ACCESS_KEY=<read-only-access-key>
AIPRO_UPBIT_SECRET_KEY=<read-only-secret-key>
AIPRO_UPBIT_READONLY_VERIFY=YES
```

The explicit verification guard is required on every run.

## Run

```bash
python -m aipro.crypto.verify_readonly
```

A successful probe exits with code `0` and prints one compact JSON object. The report contains:

- UTC observation time
- balance asset count and currency symbols
- open-order count, markets, and states
- deterministic snapshot fingerprint
- verified read permission categories
- `mutation_capability: "absent"`

Exit code `1` means credentials, permissions, transport, or response validation failed. Exit code `2` means the explicit supervised verification guard was not set.

## Evidence handling

Store only the redacted JSON report and operational notes. Do not store raw API responses, Authorization headers, keys, balance quantities, average buy prices, order UUIDs, or identifiers in GitHub.

This verification is evidence for the read-only boundary only. It does not authorize LIVE trading and must not be used to populate PAPER balances or daily baselines.
