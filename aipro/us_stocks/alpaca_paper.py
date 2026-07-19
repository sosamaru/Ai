from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any
from urllib import parse, request


@dataclass(frozen=True, slots=True)
class AlpacaPaperOrderRequest:
    symbol: str
    side: str
    order_type: str
    time_in_force: str
    client_order_id: str
    qty: str = ""
    notional: str = ""
    limit_price: str = ""

    def to_payload(self) -> dict[str, Any]:
        symbol = self.symbol.strip().upper()
        if not symbol or self.side not in {"buy", "sell"}:
            raise ValueError("invalid symbol or side")
        if self.order_type not in {"market", "limit", "stop", "stop_limit"}:
            raise ValueError("unsupported order type")
        if not self.client_order_id.strip() or len(self.client_order_id) > 128:
            raise ValueError("unique client_order_id is required")
        if bool(self.qty) == bool(self.notional):
            raise ValueError("exactly one of qty or notional is required")
        payload: dict[str, Any] = {
            "symbol": symbol,
            "side": self.side,
            "type": self.order_type,
            "time_in_force": self.time_in_force,
            "client_order_id": self.client_order_id.strip(),
        }
        payload["qty" if self.qty else "notional"] = self.qty or self.notional
        if self.order_type in {"limit", "stop_limit"}:
            if not self.limit_price:
                raise ValueError("limit_price is required")
            payload["limit_price"] = self.limit_price
        return payload


class AlpacaPaperClient:
    """PAPER-only Alpaca Trading API client. Live domains are rejected."""

    PAPER_BASE_URL = "https://paper-api.alpaca.markets"

    def __init__(self, *, key_id: str, secret_key: str, base_url: str = PAPER_BASE_URL, timeout_sec: float = 10.0) -> None:
        normalized = base_url.rstrip("/")
        if normalized != self.PAPER_BASE_URL:
            raise ValueError("AlpacaPaperClient accepts only the official PAPER domain")
        if not key_id.strip() or not secret_key.strip():
            raise ValueError("Alpaca PAPER credentials are required")
        self.key_id = key_id.strip()
        self.secret_key = secret_key.strip()
        self.base_url = normalized
        self.timeout_sec = timeout_sec

    @classmethod
    def from_env(cls) -> "AlpacaPaperClient":
        return cls(key_id=os.environ["APCA_PAPER_API_KEY_ID"], secret_key=os.environ["APCA_PAPER_API_SECRET_KEY"])

    def _request(self, method: str, path: str, payload: dict[str, Any] | None = None, query: dict[str, str] | None = None) -> Any:
        url = f"{self.base_url}{path}"
        if query:
            url = f"{url}?{parse.urlencode(query)}"
        data = None if payload is None else json.dumps(payload, separators=(",", ":")).encode("utf-8")
        req = request.Request(url, data=data, method=method, headers={
            "APCA-API-KEY-ID": self.key_id,
            "APCA-API-SECRET-KEY": self.secret_key,
            "Content-Type": "application/json",
            "Accept": "application/json",
        })
        with request.urlopen(req, timeout=self.timeout_sec) as response:
            raw = response.read().decode("utf-8")
            return json.loads(raw) if raw else None

    def get_account(self) -> dict[str, Any]:
        result = self._request("GET", "/v2/account")
        if not isinstance(result, dict):
            raise RuntimeError("invalid Alpaca account response")
        return result

    def submit_order(self, order: AlpacaPaperOrderRequest) -> dict[str, Any]:
        result = self._request("POST", "/v2/orders", order.to_payload())
        if not isinstance(result, dict) or not result.get("id"):
            raise RuntimeError("invalid Alpaca order response")
        return result

    def list_orders(self, *, status: str = "all", limit: int = 500) -> tuple[dict[str, Any], ...]:
        if status not in {"open", "closed", "all"} or not 1 <= limit <= 500:
            raise ValueError("invalid order query")
        result = self._request("GET", "/v2/orders", query={"status": status, "limit": str(limit)})
        if not isinstance(result, list):
            raise RuntimeError("invalid Alpaca orders response")
        return tuple(item for item in result if isinstance(item, dict))

    def get_order(self, order_id: str) -> dict[str, Any]:
        if not order_id.strip():
            raise ValueError("order_id is required")
        result = self._request("GET", f"/v2/orders/{parse.quote(order_id.strip(), safe='')}")
        if not isinstance(result, dict):
            raise RuntimeError("invalid Alpaca order response")
        return result


__all__ = ["AlpacaPaperClient", "AlpacaPaperOrderRequest"]
