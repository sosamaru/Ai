from __future__ import annotations

import base64
import sqlite3
from datetime import UTC, datetime

import pytest

from aipro.core.auth_adapters import AuthorizationAuditEvent, AuthorizationAuditStore, TotpVerifier
from aipro.core.live_authorization import AuthorizationStage, LiveAuthorizationState
from aipro.core.live_authorization_store import LiveAuthorizationStateStore
from aipro.crypto.upbit_preflight import UpbitOrderPreflightClient, UpbitTestOrderRequest
from aipro.us_stocks.alpaca_paper import AlpacaPaperClient, AlpacaPaperOrderRequest
from aipro.us_stocks.paper_evidence import AlpacaPaperEvidenceCollector, PaperEvidenceStore


def test_totp_verifier_accepts_generated_code() -> None:
    secret = base64.b32encode(b"12345678901234567890").decode()
    verifier = TotpVerifier(secret, window=0)
    at = datetime(2026, 1, 1, tzinfo=UTC)
    counter = int(at.timestamp()) // 30
    assert verifier.verify(verifier._code_for_counter(counter), at_utc=at)
    assert not verifier.verify("000000", at_utc=at)


def test_authorization_audit_is_append_only(tmp_path) -> None:
    path = tmp_path / "auth.db"
    store = AuthorizationAuditStore(path)
    event = AuthorizationAuditEvent("OTP_SENT", datetime.now(UTC).isoformat(), "EMAIL_PENDING", "a" * 64)
    store.append(event)
    assert store.count() == 1
    with sqlite3.connect(path) as db, pytest.raises(sqlite3.IntegrityError):
        db.execute("DELETE FROM authorization_audit")


def test_authorization_state_survives_restart(tmp_path) -> None:
    store = LiveAuthorizationStateStore(tmp_path / "authorization.json")
    state = LiveAuthorizationState(stage=AuthorizationStage.ACTIVE, recipient_hash="a" * 64, activated_at_utc=datetime.now(UTC).isoformat(), lease_expires_at_utc="2099-01-01T00:00:00+00:00")
    store.save(state)
    loaded = store.load()
    assert loaded.stage == AuthorizationStage.ACTIVE
    assert loaded.recipient_hash == state.recipient_hash


def test_alpaca_client_rejects_live_domain_and_validates_order() -> None:
    with pytest.raises(ValueError):
        AlpacaPaperClient(key_id="k", secret_key="s", base_url="https://api.alpaca.markets")
    payload = AlpacaPaperOrderRequest(symbol="AAPL", side="buy", order_type="market", time_in_force="day", client_order_id="unique-1", qty="1").to_payload()
    assert payload["symbol"] == "AAPL"
    assert payload["qty"] == "1"


def test_upbit_preflight_has_no_real_order_path() -> None:
    assert UpbitOrderPreflightClient.TEST_PATH == "/v1/orders/test"
    assert UpbitOrderPreflightClient.TEST_PATH != "/v1/orders"
    payload = UpbitTestOrderRequest(market="KRW-BTC", side="bid", ord_type="price", price="5000").to_payload()
    assert payload["price"] == "5000"


def test_paper_evidence_collector_persists_snapshot(tmp_path) -> None:
    class FakeClient:
        def get_account(self):
            return {"equity": "100000"}
        def list_orders(self, *, status: str, limit: int):
            return ({"id": "1", "status": "filled"},)

    path = tmp_path / "paper.db"
    store = PaperEvidenceStore(path)
    snapshot = AlpacaPaperEvidenceCollector(FakeClient(), store).collect(captured_at_utc=datetime.now(UTC))
    assert len(snapshot.fingerprint) == 64
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT COUNT(*) FROM paper_evidence").fetchone()[0] == 1
        with pytest.raises(sqlite3.IntegrityError):
            db.execute("UPDATE paper_evidence SET payload_json='x'")
