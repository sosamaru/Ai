# AiPro Execution and Test Runbook

Updated: 2026-07-31

This runbook provides one consistent command surface for Windows, macOS/Linux, VPS, and GitHub Actions while preserving:

`run.py -> telegram.py -> main.py -> TradingApplication`

All verification commands force or expect safe PAPER operation. They do not grant LIVE authority and do not create real-money orders.

## 1. Supported Python

Use Python 3.11, 3.12, or 3.13.

Windows verification:

```powershell
py -0p
```

macOS/Linux verification:

```bash
python3 --version
```

## 2. Install the test dependency

The core runtime uses the Python standard library. The test commands additionally require pytest:

```powershell
py -3.12 -m pip install --upgrade "pytest>=8,<10"
```

On macOS/Linux, replace `py -3.12` with the supported Python executable available on the system.

## 3. Windows commands

Command Prompt:

```bat
aipro.cmd doctor --require-pytest
aipro.cmd smoke
aipro.cmd integration
aipro.cmd test
aipro.cmd all
aipro.cmd run
```

PowerShell:

```powershell
.\aipro.ps1 doctor --require-pytest
.\aipro.ps1 smoke
.\aipro.ps1 integration
.\aipro.ps1 test
.\aipro.ps1 all
.\aipro.ps1 run
```

The launchers select Python 3.13, 3.12, or 3.11 in that order and fail with a direct message when none is installed.

## 4. Cross-platform commands

Run from the repository root:

```bash
python -m aipro doctor --require-pytest
python -m aipro compile
python -m aipro smoke
python -m aipro integration
python -m aipro test
python -m aipro all
python -m aipro run
```

Command purposes:

- `doctor`: checks the supported Python version, entrypoint files, imports, environment configuration, writable DB/log paths, and pytest availability.
- `compile`: compiles the source and tests and fails on syntax/import-bytecode compilation errors.
- `smoke`: launches one isolated deterministic PAPER cycle using temporary DB/log paths and DEMO market data.
- `integration`: runs the concrete application, market-health, Telegram, V2, and final-integration regression set.
- `test`: runs the complete regression suite with warnings treated as errors.
- `all`: runs doctor, compile, smoke, integration, and the complete regression suite in sequence and stops at the first failure.
- `run`: launches the canonical `run.py` execution path.

## 5. GitHub manual execution

The `AiPro manual execution and integration tests` workflow supports manual execution from the Actions tab after the workflow is present on the default branch.

Available targets:

- `doctor`
- `compile`
- `smoke`
- `integration`
- `test`
- `all`

Available Python versions:

- 3.11
- 3.12
- 3.13

Every run uploads its console log as an artifact for 14 days.

## 6. Common failure reasons

### Python version failure

Message:

```text
[FAIL] Python: Python 3.11~3.13 중 하나가 필요합니다.
```

Cause: unsupported or missing Python runtime.

Correction: install Python 3.11, 3.12, or 3.13 and enable the Python launcher or PATH option.

### pytest unavailable

Message:

```text
[FAIL] pytest: 미설치
```

Correction:

```powershell
py -3.12 -m pip install --upgrade "pytest>=8,<10"
```

### Telegram blocked

Message contains:

```text
Telegram blocked: configure AIPRO_TELEGRAM_ALLOWED_CHAT_IDS
```

Cause: a bot token is configured but no authorized numeric chat ID is configured.

Correction: set both `AIPRO_TELEGRAM_BOT_TOKEN` and `AIPRO_TELEGRAM_ALLOWED_CHAT_IDS`, or leave both blank for one safe console cycle.

### LIVE blocked

Message contains:

```text
LIVE blocked
```

Cause: `AIPRO_MODE=LIVE` was configured without all reviewed guards. Current repository scope has no real-order endpoint, so normal operation must remain PAPER.

Correction: set `AIPRO_MODE=PAPER`, `AIPRO_LIVE_CONFIRM=NO`, and `ENABLE_LIVE_TRADING=0`.

### DB or log path failure

Message:

```text
[FAIL] 저장 경로
```

Cause: the configured DB parent directory or log directory cannot be created or written.

Correction: use a writable local path and confirm antivirus, ransomware protection, or folder permissions are not blocking Python.

### Upbit or Telegram network failure

Cause: firewall, DNS, proxy, VPN, provider outage, invalid token, or blocked network access.

Correction: first run `smoke`, which uses DEMO data and no Telegram token. If smoke passes but external operation fails, the failure is external configuration/network related rather than the core runtime.

## 7. Verification order

Use this order when a machine reports execution unavailable:

```text
doctor -> compile -> smoke -> integration -> test -> run
```

Do not skip directly to external API or Telegram operation. A failure at each stage now returns a non-zero exit code and prints the exact stage that failed.
