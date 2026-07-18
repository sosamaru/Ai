from __future__ import annotations

import base64
import io
import json
from urllib.error import HTTPError, URLError

import pytest

from aipro.crypto.account import (
    UpbitAccountError,
    UpbitAuthenticationError,
    UpbitCredentials,
    UpbitPermissionError,
    UpbitReadOnlyAccountClient,
    UpbitResponseError,
)


class FakeResponse:
    def __init__(self, payload: object) -> None:
        self.payload = json.dumps(payload).encode("utf-8")

    def read(self) -> bytes:
        return self.payload

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        return None


def _decode_segment(segment: str) -> dict[str, object]:
    padded = segment + "=" * (-len(segment) % 4)
    return json.loads(base64.urlsafe_b64decode(padded).decode("utf-8"))


def _order() -> dict[str, object]:
    return {
        "uuid": "order-1",
        "market": "KRW-BTC",
        "side": "bid",
        "state": "wait",
        "ord_type": "limit",
        "price": "100000000",
        "volume": "0.01",
        "remaining_volume": "0.01",
        "executed_volume": "0",
        "created_at": "2026-07-18T20:00:00+09:00",
        "identifier": "aipro-1",
    }


def test_credentials_hide_secrets_and_load_from_env(monkeypatch) -> None:
    monkeypatch.setenv("AIPRO_UPBIT_ACCESS_KEY", "access")
    monkeypatch.setenv("AIPRO_UPBIT_SECRET_KEY", "secret")
    credentials = UpbitCredentials.from_env()
    assert credentials.access_key == "access"
    assert "access" not in repr(credentials)
    assert "secret" not in repr(credentials)


def test_balance_request_is_get_only_and_uses_bearer_jwt() -> None:
    captured = {}

    def opener(request, timeout: float):
        captured["method"] = request.method
        captured["authorization"] = request.headers["Authorization"]
        captured["url"] = request.full_url
        captured["timeout"] = timeout
        return FakeResponse([
            {
                "currency": "KRW",
                "balance": "100000",
                "locked": "0",
                "avg_buy_price": "0",
                "unit_currency": "KRW",
            }
        ])

    client = UpbitReadOnlyAccountClient(
        UpbitCredentials("access", "secret"),
        opener=opener,
        nonce_factory=lambda: "fixed-nonce",
        max_attempts=1,
    )
    balances = client.balances()

    assert balances[0].currency == "KRW"
    assert captured["method"] == "GET"
    assert captured["url"].endswith("/v1/accounts")
    token = str(captured["authorization"]).removeprefix("Bearer ")
    header, payload, _ = token.split(".")
    assert _decode_segment(header)["alg"] == "HS512"
    assert _decode_segment(payload) == {"access_key": "access", "nonce": "fixed-nonce"}


def test_order_query_hash_is_in_jwt_and_response_is_validated() -> None:
    captured = {}

    def opener(request, timeout: float):
        captured["authorization"] = request.headers["Authorization"]
        captured["url"] = request.full_url
        return FakeResponse(_order())

    client = UpbitReadOnlyAccountClient(
        UpbitCredentials("access", "secret"),
        opener=opener,
        nonce_factory=lambda: "nonce-1",
        max_attempts=1,
    )
    order = client.order(order_uuid="order-1")

    assert order.uuid == "order-1"
    assert captured["url"].endswith("/v1/order?uuid=order-1")
    payload = _decode_segment(str(captured["authorization"]).split(".")[1])
    assert payload["query_hash_alg"] == "SHA512"
    assert isinstance(payload["query_hash"], str)
    assert len(payload["query_hash"]) == 128


def test_non_read_only_endpoint_is_blocked_before_network() -> None:
    client = UpbitReadOnlyAccountClient(UpbitCredentials("access", "secret"))
    with pytest.raises(UpbitPermissionError, match="non-read-only"):
        client._get_json("/v1/orders", {})


def test_authentication_and_permission_errors_are_classified() -> None:
    def auth_error(request, timeout: float):
        body = io.BytesIO(json.dumps({"error": {"name": "jwt_verification"}}).encode())
        raise HTTPError(request.full_url, 401, "unauthorized", {}, body)

    client = UpbitReadOnlyAccountClient(
        UpbitCredentials("access", "secret"), opener=auth_error, max_attempts=1
    )
    with pytest.raises(UpbitAuthenticationError, match="jwt_verification"):
        client.balances()

    def permission_error(request, timeout: float):
        body = io.BytesIO(json.dumps({"error": {"name": "out_of_scope"}}).encode())
        raise HTTPError(request.full_url, 403, "forbidden", {}, body)

    client = UpbitReadOnlyAccountClient(
        UpbitCredentials("access", "secret"), opener=permission_error, max_attempts=1
    )
    with pytest.raises(UpbitPermissionError, match="read permission"):
        client.open_orders()


def test_transient_failure_retries_with_new_nonce() -> None:
    calls = 0
    nonces = iter(("nonce-1", "nonce-2"))
    sleeps: list[float] = []

    def opener(request, timeout: float):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise URLError("temporary")
        return FakeResponse([])

    client = UpbitReadOnlyAccountClient(
        UpbitCredentials("access", "secret"),
        opener=opener,
        nonce_factory=lambda: next(nonces),
        max_attempts=2,
        backoff_sec=0.5,
        sleep=sleeps.append,
    )
    assert client.open_orders() == ()
    assert calls == 2
    assert sleeps == [0.5]


def test_malformed_or_duplicate_responses_fail_closed() -> None:
    client = UpbitReadOnlyAccountClient(
        UpbitCredentials("access", "secret"),
        opener=lambda request, timeout: FakeResponse({"currency": "KRW"}),
        max_attempts=1,
    )
    with pytest.raises(UpbitResponseError, match="must be a list"):
        client.balances()

    client = UpbitReadOnlyAccountClient(
        UpbitCredentials("access", "secret"),
        opener=lambda request, timeout: FakeResponse([_order(), _order()]),
        max_attempts=1,
    )
    with pytest.raises(UpbitResponseError, match="duplicate UUIDs"):
        client.open_orders()


def test_retry_exhaustion_does_not_expose_credentials() -> None:
    client = UpbitReadOnlyAccountClient(
        UpbitCredentials("super-access", "super-secret"),
        opener=lambda request, timeout: (_ for _ in ()).throw(URLError("offline")),
        max_attempts=1,
    )
    with pytest.raises(UpbitAccountError) as exc_info:
        client.balances()
    message = str(exc_info.value)
    assert "super-access" not in message
    assert "super-secret" not in message
