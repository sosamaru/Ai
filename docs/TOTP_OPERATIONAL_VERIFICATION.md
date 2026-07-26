# TOTP Operational Verification

This procedure verifies that the owner has enrolled the AiPro TOTP secret in an authenticator application and can produce a valid current code.

It does not enable LIVE trading, grant authorization, create an order, or mark live readiness complete.

## Safety boundary

- The TOTP secret must be supplied only through the local `AIPRO_TOTP_SECRET` environment variable.
- The current authenticator code is entered through a hidden terminal prompt.
- Neither the secret nor the code is written to the evidence database.
- Evidence stores only a normalized enrollment-label hash, time counter, outcome, reason category, timestamp, and SHA-256 fingerprint.
- A successfully accepted time counter cannot be accepted again for the same enrollment label.
- Recovery codes or backup material must never be committed to GitHub.

## Required preparation

1. Generate or retrieve the reviewed AiPro TOTP secret outside the repository.
2. Enroll it in a trusted authenticator application.
3. Store recovery material offline in a physically separate location.
4. Synchronize the computer clock through the operating system time service.
5. Close screen-sharing and recording applications before entering the code.

## Supervised command

Set the secret only in the local process environment. Do not add it to a committed `.env` file.

```bash
AIPRO_TOTP_VERIFY=YES \
AIPRO_TOTP_SECRET=<base32-secret> \
AIPRO_TOTP_ENROLLMENT_LABEL="AiPro primary operator" \
AIPRO_TOTP_EVIDENCE_DB=data/totp_operational_evidence.sqlite3 \
python -m aipro.core.verify_totp
```

On Windows PowerShell:

```powershell
$env:AIPRO_TOTP_VERIFY="YES"
$env:AIPRO_TOTP_SECRET="<base32-secret>"
$env:AIPRO_TOTP_ENROLLMENT_LABEL="AiPro primary operator"
$env:AIPRO_TOTP_EVIDENCE_DB="data/totp_operational_evidence.sqlite3"
python -m aipro.core.verify_totp
```

The terminal requests the current six-digit authenticator code without echoing it.

## Result interpretation

- `accepted / current_code_verified`: the supplied code was valid for the current time window and the counter was claimed once.
- `rejected / invalid_code`: the code did not validate. Check enrollment, clock synchronization, and the active account entry.
- `rejected / replay_detected`: a code from the same time counter was already accepted for this enrollment label.

A successful run is only one piece of operational evidence. The owner must separately confirm that recovery material is stored offline. SMTP verification, 30 calendar days of qualifying Alpaca PAPER evidence, supervised Upbit inspection and test-order preflight, domain-specific reconciliation and risk gates, and an independent live-readiness review remain mandatory.
