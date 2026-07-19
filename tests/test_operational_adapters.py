from __future__ import annotations

import json
import sqlite3
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from aipro.core.auth_adapters import (
    AuthorizationAuditEvent,
    AuthorizationAuditStore,
    SmtpOtpConfig,
    SmtpOtpSender,
    TotpVerifier,
)
from aipro.core.execution_gate import LiveExecutionInputs, evaluate_live_execution
from aipro.crypto.upbit_preflight import UpbitPreflightConfig, UpbitTestOrder, UpbitTestOrderClient
from aipro.us_stocks.alpaca_paper import AlpacaPaperClient, AlpacaPaperConfig, PaperOrderRequest


class FakeSmtp:
    def __init__(self, *args, **kwargs) -> None:
        self.message = None
        self.logged_in = False

    def login(self, username: str, password: str) -> None:
        self.logged_in = True

    def send_message(self, message) -> None:
        self.message = message

    def quit(self) -> None:
        pass


def test_smtp_sender_builds_message_without_exposing_password() -> None:
    holder = {}

    def factory(*args, **kwargs):
        holder["client"] = FakeSmtp()
        return holder["client"]

    sender = SmtpOtpSender(
        SmtpOtpConfig(
            host="smtp.example.com",
            port=465,
            username="owner@example.com",
            password="secret",
            sender_email="owner@example.com",
        ),
        smtp_factory=factory,
    )
    sender.send(
        recipient="owner@example.com",
        code="123456",
        expires_at_utc=datetime(2026, 7, 19, 8, 0, tzinfo=UTC),
    )
    message = holder["client"].message
    assert "123456" in message.get_content()
    assert "secret" not in message.as_string()


def test_totp_matches_rfc_vector() -> None:
    secret = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"
    verifier = TotpVerifier(secret, digits=8, period_seconds=30, window=0)
    assert verifier.verify("94287082", at_utc=datetime.fromtimestamp(59, tz=UTC))
    assert not verifier.verify("00000000", at_utc=datetime.fromtimestamp(59, tz=UTC))


def test_authorization_audit_is_append_only(tmp_path) -> None:
    database = tmp_path / "auth.sqlite3"
    store = AuthorizationAuditStore(database)
    event = AuthorizationAuditEvent(
        event="OTP_SENT",
        stage="EMAIL_PENDING",
        occurred_at_utc="2026-07-19T08:00:00+00:00",
        recipient_hash="a" * 64,
    )
    store.append(event)
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT COUNT(*) FROM authorization_audit").fetchone()[0] == 1
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            connection.execute("DELETE FROM authorization_audit")


class FakeResponse:
    def __init__(self, payload, status=200) -> None:
        self.payload = payload
        self.status = status

    def read(self):
        return json.dumps(self.payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def test_alpaca_client_rejects_live_domain_and_duplicate_ids() -> None:
    with pytest.raises(ValueError, match="PAPER domain"):
        AlpacaPaperConfig("key", "secret", base_url="https://api.alpaca.markets")

    def opener(req, timeout):
        return FakeResponse({"id": "order-1", "client_order_id": "cid-1"})

    client = AlpacaPaperClient(AlpacaPaperConfig("key", "secret"), opener=opener)
    request_order = PaperOrderRequest("AAPL", "buy", "1", client_order_id="cid-1")
    payload, evidence = client.submit_order(request_order)
    assert payload["id"] == "order-1"
    assert evidence.client_order_id == "cid-1"
    with pytest.raises(RuntimeError, match="duplicate"):
        client.submit_order(request_order)


def test_upbit_preflight_calls_only_test_endpoint() -> None:
    captured = {}

    def opener(req, timeout):
        captured["url"] = req.full_url
        captured["authorization"] = req.headers["Authorization"]
        return FakeResponse({"result": "success"})

    client = UpbitTestOrderClient(
        UpbitPreflightConfig("access", "secret", "https://sg-api.upbit.com"),
        opener=opener,
    )
    _, evidence = client.test_order(
        UpbitTestOrder("SGD-BTC", "bid", "limit", volume="0.001", price="100000")
    )
    assert captured["url"].endswith("/v1/orders/test")
    assert captured["authorization"].startswith("Bearer ")
    assert evidence.accepted is True


def test_live_execution_gate_requires_every_condition() -> None:
    now = datetime(2026, 7, 19, 8, 0, tzinfo=UTC)
    valid = LiveExecutionInputs(
        explicit_live_guard=True,
        authorization_active=True,
        paper_validation_passed=True,
        reconciliation_match=True,
        market_data_fresh=True,
        intelligence_fresh=True,
        required_providers_healthy=True,
        risk_limits_passed=True,
        unique_client_order_id=True,
        preflight_accepted=True,
        kill_switch_active=False,
        authorization_expires_at_utc=(now + timedelta(minutes=10)).isoformat(),
    )
    assert evaluate_live_execution(valid, now_utc=now).allowed is True

    invalid = replace(valid, risk_limits_passed=False)
    decision = evaluate_live_execution(invalid, now_utc=now)
    assert decision.allowed is False
    assert "RISK_LIMIT_FAILED" in decision.reasons
