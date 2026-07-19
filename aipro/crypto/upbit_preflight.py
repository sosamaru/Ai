from __future__ import annotations

import base64
import hashlib
import hmac
import json
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any, Callable
from urllib import request


def _b64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _jwt_hs512(access_key: str, secret_key: str, query_string: str) -> str:
    header = {"alg": "HS512", "typ": "JWT"}
    payload: dict[str, str] = {"access_key": access_key, "nonce": str(uuid.uuid4())}
    if query_string:
        payload["query_hash"] = hashlib.sha512(query_string.encode("utf-8")).hexdigest()
        payload["query_hash_alg"] = "SHA512"
    encoded_header = _b64url(json.dumps(header, separators=(",", ":")).encode("utf-8"))
    encoded_payload = _b64url(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signing_input = f"{encoded_header}.{encoded_payload}"
    signature = hmac.new(secret_key.encode("utf-8"), signing_input.encode("ascii"), hashlib.sha512).digest()
    return f"{signing_input}.{_b64url(signature)}"


@dataclass(frozen=True, slots=True)
class UpbitPreflightConfig:
    access_key: str
    secret_key: str
    base_url: str
    timeout_seconds: float = 10.0

    def __post_init__(self) -> None:
        if not self.access_key.strip() or not self.secret_key.strip():
            raise ValueError("Upbit credentials are required")
        if not self.base_url.startswith("https://") or "api.upbit.com" not in self.base_url:
            raise ValueError("valid Upbit API base URL is required")
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")


@dataclass(frozen=True, slots=True)
class UpbitTestOrder:
    market: str
    side: str
    ord_type: str
    volume: str | None = None
    price: str | None = None
    time_in_force: str | None = None

    def __post_init__(self) -> None:
        if not self.market.strip() or self.side not in {"bid", "ask"}:
            raise ValueError("valid market and side are required")
        if self.ord_type not in {"limit", "price", "market", "best"}:
            raise ValueError("unsupported order type")
        if self.ord_type in {"limit", "market"} and not self.volume:
            raise ValueError("volume is required for limit and market-sell orders")
        if self.ord_type in {"limit", "price"} and not self.price:
            raise ValueError("price is required for limit and market-buy orders")

    def body(self) -> dict[str, str]:
        result = {"market": self.market.strip().upper(), "side": self.side, "ord_type": self.ord_type}
        if self.volume is not None:
            result["volume"] = self.volume
        if self.price is not None:
            result["price"] = self.price
        if self.time_in_force is not None:
            result["time_in_force"] = self.time_in_force
        return result


@dataclass(frozen=True, slots=True)
class UpbitPreflightEvidence:
    occurred_at_utc: str
    market: str
    side: str
    ord_type: str
    request_fingerprint: str
    accepted: bool
    response_code: str

    @property
    def fingerprint(self) -> str:
        payload = json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class UpbitTestOrderClient:
    """Calls only Upbit's non-executing test-order endpoint."""

    TEST_PATH = "/v1/orders/test"

    def __init__(self, config: UpbitPreflightConfig, *, opener: Callable[..., Any] | None = None) -> None:
        self.config = config
        self._opener = opener or request.urlopen

    @staticmethod
    def _query_string(body: dict[str, str]) -> str:
        # Preserve insertion order exactly; Upbit validates the same ordered parameter string.
        from urllib.parse import urlencode

        return urlencode(list(body.items()))

    def test_order(self, order: UpbitTestOrder) -> tuple[dict[str, Any], UpbitPreflightEvidence]:
        body = order.body()
        query_string = self._query_string(body)
        token = _jwt_hs512(self.config.access_key, self.config.secret_key, query_string)
        req = request.Request(
            f"{self.config.base_url.rstrip('/')}{self.TEST_PATH}",
            data=json.dumps(body, separators=(",", ":")).encode("utf-8"),
            method="POST",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
        )
        with self._opener(req, timeout=self.config.timeout_seconds) as response:
            raw = response.read().decode("utf-8")
            payload = json.loads(raw) if raw else {}
            status = int(getattr(response, "status", 200))
        if not isinstance(payload, dict):
            raise RuntimeError("invalid Upbit test-order response")
        accepted = status < 300 and "error" not in payload
        response_code = "ACCEPTED" if accepted else str(payload.get("error", {}).get("name", "REJECTED"))
        canonical = json.dumps(body, sort_keys=True, separators=(",", ":"))
        evidence = UpbitPreflightEvidence(
            occurred_at_utc=datetime.now(UTC).isoformat(),
            market=body["market"],
            side=body["side"],
            ord_type=body["ord_type"],
            request_fingerprint=hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
            accepted=accepted,
            response_code=response_code,
        )
        if not accepted:
            raise RuntimeError(f"Upbit test order rejected: {response_code}")
        return payload, evidence


__all__ = [
    "UpbitPreflightConfig",
    "UpbitPreflightEvidence",
    "UpbitTestOrder",
    "UpbitTestOrderClient",
]
