from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import uuid
from dataclasses import dataclass
from typing import Any
from urllib import request
from urllib.parse import urlencode


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _jwt_hs512(payload: dict[str, Any], secret: str) -> str:
    header = {"alg": "HS512", "typ": "JWT"}
    encoded_header = _b64url(json.dumps(header, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    encoded_payload = _b64url(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    signing_input = f"{encoded_header}.{encoded_payload}".encode("ascii")
    signature = hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha512).digest()
    return f"{encoded_header}.{encoded_payload}.{_b64url(signature)}"


@dataclass(frozen=True, slots=True)
class UpbitTestOrderRequest:
    market: str
    side: str
    ord_type: str
    volume: str = ""
    price: str = ""
    time_in_force: str = ""
    identifier: str = ""

    def to_payload(self) -> dict[str, str]:
        if not self.market.startswith("KRW-") or self.side not in {"bid", "ask"}:
            raise ValueError("invalid Upbit market or side")
        if self.ord_type not in {"limit", "price", "market", "best"}:
            raise ValueError("unsupported Upbit order type")
        if self.ord_type in {"limit", "market"} and not self.volume:
            raise ValueError("volume is required")
        if self.ord_type in {"limit", "price"} and not self.price:
            raise ValueError("price is required")
        if self.ord_type == "best" and not self.time_in_force:
            raise ValueError("time_in_force is required for best orders")
        payload = {"market": self.market, "side": self.side, "ord_type": self.ord_type}
        for key, value in (
            ("volume", self.volume),
            ("price", self.price),
            ("time_in_force", self.time_in_force),
            ("identifier", self.identifier),
        ):
            if value:
                payload[key] = value
        return payload


class UpbitOrderPreflightClient:
    """Authenticated test-order client. It cannot call the real `/v1/orders` endpoint."""

    BASE_URL = "https://api.upbit.com"
    TEST_PATH = "/v1/orders/test"

    def __init__(self, *, access_key: str, secret_key: str, timeout_sec: float = 10.0) -> None:
        if not access_key.strip() or not secret_key.strip():
            raise ValueError("Upbit API credentials are required")
        self.access_key = access_key.strip()
        self.secret_key = secret_key.strip()
        self.timeout_sec = timeout_sec

    @classmethod
    def from_env(cls) -> "UpbitOrderPreflightClient":
        return cls(access_key=os.environ["UPBIT_ACCESS_KEY"], secret_key=os.environ["UPBIT_SECRET_KEY"])

    def _authorization(self, payload: dict[str, str]) -> str:
        query_string = urlencode(payload)
        jwt_payload = {
            "access_key": self.access_key,
            "nonce": str(uuid.uuid4()),
            "query_hash": hashlib.sha512(query_string.encode("utf-8")).hexdigest(),
            "query_hash_alg": "SHA512",
        }
        return f"Bearer {_jwt_hs512(jwt_payload, self.secret_key)}"

    def test_order(self, order: UpbitTestOrderRequest) -> dict[str, Any]:
        payload = order.to_payload()
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        req = request.Request(
            f"{self.BASE_URL}{self.TEST_PATH}",
            data=body,
            method="POST",
            headers={
                "Authorization": self._authorization(payload),
                "Content-Type": "application/json; charset=utf-8",
                "Accept": "application/json",
            },
        )
        with request.urlopen(req, timeout=self.timeout_sec) as response:
            result = json.loads(response.read().decode("utf-8"))
        if not isinstance(result, dict):
            raise RuntimeError("invalid Upbit test-order response")
        return result


__all__ = ["UpbitOrderPreflightClient", "UpbitTestOrderRequest"]
