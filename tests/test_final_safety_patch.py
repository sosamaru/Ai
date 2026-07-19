from __future__ import annotations

import base64
import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta

from aipro.core.execution_gate import LiveExecutionInputs, evaluate_live_execution
from aipro.crypto.upbit_preflight import UpbitOrderPreflightClient, UpbitTestOrderRequest


def _decode_segment(value: str) -> dict[str, object]:
    padded = value + "=" * ((4 - len(value) % 4) % 4)
    return json.loads(base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8"))


def test_upbit_preflight_uses_hs512_and_sha512_query_hash() -> None:
    client = UpbitOrderPreflightClient(access_key="access", secret_key="secret")
    payload = UpbitTestOrderRequest(
        market="KRW-BTC",
        side="bid",
        ord_type="price",
        price="10000",
        identifier="preflight-1",
    ).to_payload()
    token = client._authorization(payload).removeprefix("Bearer ")
    header_segment, payload_segment, signature_segment = token.split(".")

    header = _decode_segment(header_segment)
    jwt_payload = _decode_segment(payload_segment)

    assert header["alg"] == "HS512"
    assert jwt_payload["query_hash_alg"] == "SHA512"
    assert len(str(jwt_payload["query_hash"])) == 128
    assert len(base64.urlsafe_b64decode(signature_segment + "==")) == 64
    assert client.TEST_PATH == "/v1/orders/test"
    assert client.TEST_PATH != "/v1/orders"


def valid_inputs(now: datetime) -> LiveExecutionInputs:
    return LiveExecutionInputs(
        explicit_live_guard=True,
        authorization_active=True,
        paper_validation_passed=True,
        training_evidence_passed=True,
        reconciliation_match=True,
        market_data_fresh=True,
        intelligence_fresh=True,
        required_providers_healthy=True,
        risk_limits_passed=True,
        unique_client_order_id=True,
        preflight_accepted=True,
        kill_switch_active=False,
        live_readiness_review_passed=True,
        authorization_expires_at_utc=(now + timedelta(minutes=10)).isoformat(),
    )


def test_execution_gate_allows_only_when_every_gate_passes() -> None:
    now = datetime(2026, 7, 19, 9, 0, tzinfo=UTC)
    assert evaluate_live_execution(valid_inputs(now), now_utc=now).allowed is True

    failed = replace(
        valid_inputs(now),
        risk_limits_passed=False,
        live_readiness_review_passed=False,
    )
    decision = evaluate_live_execution(failed, now_utc=now)
    assert decision.allowed is False
    assert decision.reasons == (
        "RISK_LIMIT_FAILED",
        "LIVE_READINESS_REVIEW_NOT_PASSED",
    )


def test_execution_gate_rejects_expired_or_naive_authorization() -> None:
    now = datetime(2026, 7, 19, 9, 0, tzinfo=UTC)

    expired = replace(valid_inputs(now), authorization_expires_at_utc=(now - timedelta(seconds=1)).isoformat())
    assert "AUTHORIZATION_EXPIRED" in evaluate_live_execution(expired, now_utc=now).reasons

    invalid = replace(valid_inputs(now), authorization_expires_at_utc="2026-07-19T10:00:00")
    assert "AUTHORIZATION_EXPIRY_INVALID" in evaluate_live_execution(invalid, now_utc=now).reasons
