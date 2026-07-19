from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta

import pytest

from aipro.core.auth_adapters import AuthorizationAuditEvent, AuthorizationAuditStore, TotpVerifier
from aipro.core.authorization_runtime import AuthorizationStateStore, PersistedAuthorizationRuntime
from aipro.core.live_authorization import LiveAuthorizationManager
from aipro.crypto.upbit_preflight import UpbitOrderPreflightClient, UpbitTestOrderRequest
from aipro.us_stocks.alpaca_paper import AlpacaPaperClient, AlpacaPaperOrderRequest


class MemoryOtpSender:
    def __init__(self) -> None:
        self.code = ""

    def send(self, *, recipient: str, code: str, expires_at_utc: datetime) -> None:
        self.code = code


class FixedSecondFactor:
    def verify(self, code: str, *, at_utc: datetime) -> bool:
        return code == "654321"


def test_totp_rfc6238_sha1_vector() -> None:
    verifier = TotpVerifier("GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ", digits=8, window=0)
    assert verifier.verify("94287082", at_utc=datetime.fromtimestamp(59, tz=UTC))
    assert not verifier.verify("94287081", at_utc=datetime.fromtimestamp(59, tz=UTC))


def test_authorization_audit_is_append_only(tmp_path) -> None:
    path = tmp_path / "auth.sqlite3"
    store = AuthorizationAuditStore(path)
    event = AuthorizationAuditEvent("OTP_SENT", datetime.now(UTC).isoformat(), "EMAIL_PENDING", "a" * 64)
    store.append(event)
    assert store.count() == 1
    with sqlite3.connect(path) as db:
        with pytest.raises(sqlite3.IntegrityError):
            db.execute("DELETE FROM authorization_audit")


def test_persisted_runtime_survives_restart(tmp_path) -> None:
    now = datetime(2026, 7, 19, tzinfo=UTC)
    sender = MemoryOtpSender()
    manager = LiveAuthorizationManager(recipient="owner@example.com", otp_sender=sender, second_factor=FixedSecondFactor())
    state_store = AuthorizationStateStore(tmp_path / "state.json")
    audit_store = AuthorizationAuditStore(tmp_path / "audit.sqlite3")
    runtime = PersistedAuthorizationRuntime(manager=manager, state_store=state_store, audit_store=audit_store)
    runtime.request_email_otp(now_utc=now)
    runtime.verify_email_otp(sender.code, now_utc=now + timedelta(seconds=1))
    runtime.verify_second_factor("654321", now_utc=now + timedelta(seconds=2))
    assert audit_store.count() == 3

    restored = LiveAuthorizationManager(recipient="owner@example.com", otp_sender=sender, second_factor=FixedSecondFactor())
    restored_runtime = PersistedAuthorizationRuntime(manager=restored, state_store=state_store, audit_store=audit_store)
    restored_runtime.require_active(now_utc=now + timedelta(minutes=1))


def test_alpaca_client_rejects_live_domain_and_validates_order() -> None:
    with pytest.raises(ValueError):
        AlpacaPaperClient(key_id="x", secret_key="y", base_url="https://api.alpaca.markets")
    payload = AlpacaPaperOrderRequest(
        symbol="aapl",
        side="buy",
        order_type="market",
        time_in_force="day",
        client_order_id="unique-1",
        notional="100",
    ).to_payload()
    assert payload["symbol"] == "AAPL"
    assert payload["notional"] == "100"
    assert "qty" not in payload


def test_upbit_preflight_cannot_target_real_order_path() -> None:
    client = UpbitOrderPreflightClient(access_key="access", secret_key="secret")
    assert client.TEST_PATH == "/v1/orders/test"
    assert client.TEST_PATH != "/v1/orders"
    payload = UpbitTestOrderRequest(
        market="KRW-BTC",
        side="bid",
        ord_type="price",
        price="10000",
        identifier="test-1",
    ).to_payload()
    assert payload["ord_type"] == "price"
    assert payload["identifier"] == "test-1"


def test_upbit_preflight_rejects_invalid_market() -> None:
    with pytest.raises(ValueError):
        UpbitTestOrderRequest(market="BTC-USD", side="bid", ord_type="price", price="100").to_payload()
