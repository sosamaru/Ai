from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any, Callable
from urllib import request

PAPER_BASE_URL = "https://paper-api.alpaca.markets"


@dataclass(frozen=True, slots=True)
class AlpacaPaperConfig:
    key_id: str
    secret_key: str
    base_url: str = PAPER_BASE_URL
    timeout_seconds: float = 10.0

    def __post_init__(self) -> None:
        if not self.key_id.strip() or not self.secret_key.strip():
            raise ValueError("Alpaca PAPER credentials are required")
        if self.base_url.rstrip("/") != PAPER_BASE_URL:
            raise ValueError("AlpacaPaperClient accepts the PAPER domain only")
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")


@dataclass(frozen=True, slots=True)
class PaperOrderRequest:
    symbol: str
    side: str
    quantity: str
    order_type: str = "market"
    time_in_force: str = "day"
    client_order_id: str = ""
    limit_price: str | None = None

    def __post_init__(self) -> None:
        if not self.symbol.strip() or self.side not in {"buy", "sell"}:
            raise ValueError("valid symbol and side are required")
        if self.order_type not in {"market", "limit"}:
            raise ValueError("only market and limit PAPER orders are supported")
        try:
            if float(self.quantity) <= 0:
                raise ValueError
        except (TypeError, ValueError) as exc:
            raise ValueError("quantity must be positive") from exc
        if self.order_type == "limit" and not self.limit_price:
            raise ValueError("limit_price is required for limit orders")
        if not self.client_order_id.strip():
            raise ValueError("client_order_id is required for duplicate protection")


@dataclass(frozen=True, slots=True)
class PaperApiEvidence:
    operation: str
    occurred_at_utc: str
    request_fingerprint: str
    response_status: int
    provider_order_id: str
    client_order_id: str

    @property
    def fingerprint(self) -> str:
        payload = json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class AlpacaPaperClient:
    """Minimal PAPER-only Alpaca Trading API adapter.

    The base URL is fixed to the paper domain and cannot be changed to the live domain.
    """

    def __init__(
        self,
        config: AlpacaPaperConfig,
        *,
        opener: Callable[..., Any] | None = None,
    ) -> None:
        self.config = config
        self._opener = opener or request.urlopen
        self._seen_client_order_ids: set[str] = set()

    def _call(self, method: str, path: str, body: dict[str, Any] | None = None) -> tuple[int, Any]:
        url = f"{PAPER_BASE_URL}{path}"
        data = None if body is None else json.dumps(body, separators=(",", ":")).encode("utf-8")
        req = request.Request(
            url,
            data=data,
            method=method,
            headers={
                "APCA-API-KEY-ID": self.config.key_id,
                "APCA-API-SECRET-KEY": self.config.secret_key,
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
        )
        with self._opener(req, timeout=self.config.timeout_seconds) as response:
            raw = response.read().decode("utf-8")
            return int(getattr(response, "status", 200)), json.loads(raw) if raw else {}

    def get_account(self) -> dict[str, Any]:
        _, payload = self._call("GET", "/v2/account")
        if not isinstance(payload, dict):
            raise RuntimeError("invalid Alpaca PAPER account response")
        return payload

    def list_positions(self) -> tuple[dict[str, Any], ...]:
        _, payload = self._call("GET", "/v2/positions")
        if not isinstance(payload, list):
            raise RuntimeError("invalid Alpaca PAPER positions response")
        return tuple(item for item in payload if isinstance(item, dict))

    def submit_order(self, order: PaperOrderRequest) -> tuple[dict[str, Any], PaperApiEvidence]:
        client_id = order.client_order_id.strip()
        if client_id in self._seen_client_order_ids:
            raise RuntimeError("duplicate PAPER client_order_id")
        body: dict[str, Any] = {
            "symbol": order.symbol.strip().upper(),
            "side": order.side,
            "qty": order.quantity,
            "type": order.order_type,
            "time_in_force": order.time_in_force,
            "client_order_id": client_id,
        }
        if order.limit_price is not None:
            body["limit_price"] = order.limit_price
        canonical = json.dumps(body, sort_keys=True, separators=(",", ":"))
        status, payload = self._call("POST", "/v2/orders", body)
        if not isinstance(payload, dict):
            raise RuntimeError("invalid Alpaca PAPER order response")
        provider_order_id = str(payload.get("id", "")).strip()
        returned_client_id = str(payload.get("client_order_id", client_id)).strip()
        if status >= 300 or not provider_order_id or returned_client_id != client_id:
            raise RuntimeError("Alpaca PAPER order was not accepted consistently")
        self._seen_client_order_ids.add(client_id)
        evidence = PaperApiEvidence(
            operation="SUBMIT_PAPER_ORDER",
            occurred_at_utc=datetime.now(UTC).isoformat(),
            request_fingerprint=hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
            response_status=status,
            provider_order_id=provider_order_id,
            client_order_id=client_id,
        )
        return payload, evidence

    def get_order_by_client_id(self, client_order_id: str) -> dict[str, Any]:
        from urllib.parse import quote

        normalized = client_order_id.strip()
        if not normalized:
            raise ValueError("client_order_id is required")
        _, payload = self._call("GET", f"/v2/orders:by_client_order_id?client_order_id={quote(normalized)}")
        if not isinstance(payload, dict):
            raise RuntimeError("invalid Alpaca PAPER order lookup response")
        return payload


__all__ = [
    "AlpacaPaperClient",
    "AlpacaPaperConfig",
    "PaperApiEvidence",
    "PaperOrderRequest",
]
