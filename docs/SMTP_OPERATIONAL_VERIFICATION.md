# SMTP Operational Verification

This procedure verifies real OTP delivery without enabling trading or storing OTP plaintext.

## Safety boundary

- Run only as a supervised owner-controlled check.
- Never commit SMTP credentials, recipients, OTP values, or provider recovery codes.
- The evidence database stores only a SHA-256 recipient hash, delivery outcome, provider label, timestamp, reason category, and deterministic fingerprint.
- Delivery success does not authorize LIVE trading and does not satisfy TOTP, PAPER-duration, reconciliation, risk, freshness, or live-readiness gates.

## Required environment

```bash
AIPRO_SMTP_VERIFY=YES
AIPRO_SMTP_HOST=<smtp-host>
AIPRO_SMTP_PORT=587
AIPRO_SMTP_USERNAME=<smtp-username>
AIPRO_SMTP_PASSWORD=<smtp-password>
AIPRO_SMTP_SENDER=<sender-address>
AIPRO_SMTP_STARTTLS=1
AIPRO_SMTP_VERIFY_RECIPIENT=<owner-controlled-recipient>
AIPRO_SMTP_PROVIDER=<provider-label>
AIPRO_SMTP_VERIFY_DB=data/smtp_verification_evidence.sqlite3
```

## Run

```bash
python -m aipro.core.smtp_operational_verification
```

The command fails closed unless `AIPRO_SMTP_VERIFY=YES` is present. It returns exit code `0` only when the SMTP server accepts the message. A delivery failure is recorded using only the exception type; exception text is deliberately excluded because provider errors can contain sensitive account details.

## Manual completion check

Code-level delivery acceptance is not enough to mark SMTP operational verification complete. The owner must also confirm that the message arrived in the intended mailbox and that the sender/domain configuration is expected. Record that human confirmation outside the repository without copying the OTP value.
