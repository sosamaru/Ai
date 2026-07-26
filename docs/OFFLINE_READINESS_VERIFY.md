# Offline Operational Readiness Verification

This workflow verifies an AiPro operational-readiness export without opening the source SQLite databases.

## Purpose

The verifier is intended for offline independent inspection of the ZIP created by `aipro.core.offline_readiness_export`. It fails closed when archive structure, canonical content, fingerprints, evidence semantics, or the human-readable summary do not match.

A successful result means only that the export is internally consistent with the version-1 format. It does not prove that an operator attestation is true, that credentials are secure, that the required PAPER duration elapsed, that a strategy is profitable, or that LIVE trading is approved.

## Explicit execution

Set:

```text
AIPRO_VERIFY_READINESS=YES
AIPRO_READINESS_EXPORT_PATH=data/operational_readiness_export.zip
```

Run:

```text
python -m aipro.core.offline_readiness_verify
```

Without the exact opt-in value, the command exits without reading the archive.

## Fail-closed checks

The verifier checks:

1. the input is a bounded ZIP containing exactly `manifest.json`, `readiness_review.json`, and `readiness_review.md` in deterministic order;
2. entries are regular, unencrypted, size-bounded DEFLATE files with deterministic timestamps and restricted permissions;
3. both JSON files are canonical UTF-8 JSON with the exact version-1 fields;
4. archive, review-content, review, and manifest SHA-256 fingerprints match;
5. `execution_authority` is exactly `false`;
6. status, Boolean evidence checks, and the ordered blocker list are semantically consistent;
7. source fingerprints are valid, unique lowercase SHA-256 values;
8. the Markdown summary exactly matches the verified JSON evidence and safety boundary.

The successful result includes the archive hash, review and manifest fingerprints, completed check names, and a deterministic verification fingerprint. It does not persist secrets or extract files to disk.

## Safety and trust boundary

SHA-256 checks detect accidental or deliberate modification after export, but they do not identify who created the archive. A detached digital-signature scheme would require separately reviewed key ownership, rotation, revocation, and verification rules.

This verifier does not enable LIVE mode, create authorization leases, submit or modify orders, mutate HALTED or kill-switch state, change model-governance records, or replace an independent reviewer.
