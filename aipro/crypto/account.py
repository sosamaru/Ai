from __future__ import annotations

import base64
import hashlib
import hmac
import json
import math
import os
import time
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import unquote, urlencode
from urllib.request import Request, urlopen

UPBIT_EXCHANGE_API_BASE_URL = "https://api.upbit.com"
_READ_ONLY_PATHS = frozenset({"/v1/accounts", "/v1/order", "/v1/orders/open", "/v1/orders/closed"})


class UpbitAccountError(RuntimeError):
    """Base error for authenticated read-only Upbit account inspection."""


class UpbitAuthenticationError(UpbitAccountError):
    """Raised when credentials or authentication are rejected."""


class UpbitPermissionError(UpbitAccountError):
    """Raised when an API key lacks the required read permission."""


class UpbitResponseError(UpbitAccountError):
    """Raised when an authenticated response is malformed or unsafe."""


class HttpResponse(Protocol):
    def read(self) -> bytes: ...
    def __enter__(self) -> HttpResponse: ...
    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None: ...


OpenUrl = Callable[..., HttpResponse]
Sleep = Callable[[float], None]
NonceFactory = Callable[[], str]


@dataclass(frozen=True, slots=True)
class UpbitCredentials:
    access_key: str = field(repr=False)
    secret_key: str = field(repr=False)

    def __post_init__(self) -> None:
        if not self.access_key.strip() or not self.secret_key.strip():
            raise ValueError("Upbit access and secret keys must both be configured")

    @classmethod
    def from_env(cls) -> UpbitCredentials:
        return cls(
            access_key=os.getenv("AIPRO_UPBIT_ACCESS_KEY", "").strip(),
            secret_key=os.getenv("AIPRO_UPBIT_SECRET_KEY", "").strip(),
        )


@dataclass(frozen=True, slots=True)
class AccountBalance:
    currency: str
    balance: Decimal
    locked: Decimal
    average_buy_price: Decimal
    unit_currency: str


@dataclass(frozen=True, slots=True)
class AccountOrder:
    uuid: str
    market: str
    side: str
    state: str
    order_type: str
    price: Decimal | None
    volume: Decimal | None
    remaining_volume: Decimal | None
    executed_volume: Decimal
    created_at: str
    identifier: str | None = None


def _base64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _canonical_query(params: Mapping[str, object]) -> str:
    if not params:
        return ""
    return unquote(urlencode(list(params.items()), doseq=True))


def _jwt_token(credentials: UpbitCredentials, query_string: str, nonce: str) -> str:
    header = {"alg": "HS512", "typ": "JWT"}
    payload: dict[str, str] = {
        "access_key": credentials.access_key,
        "nonce": nonce,
    }
    if query_string:
        payload["query_hash"] = hashlib.sha512(query_string.encode("utf-8")).hexdigest()
        payload["query_hash_alg"] = "SHA512"
    encoded_header = _base64url(json.dumps(header, separators=(",", ":")).encode("utf-8"))
    encoded_payload = _base64url(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signing_input = f"{encoded_header}.{encoded_payload}".encode("ascii")
    signature = hmac.new(credentials.secret_key.encode("utf-8"), signing_input, hashlib.sha512).digest()
    return f"{encoded_header}.{encoded_payload}.{_base64url(signature)}"


@dataclass(slots=True)
class UpbitReadOnlyAccountClient:
    credentials: UpbitCredentials
    base_url: str = UPBIT_EXCHANGE_API_BASE_URL
    timeout_sec: float = 5.0
    max_attempts: int = 3
    backoff_sec: float = 0.25
    opener: OpenUrl = urlopen
    sleep: Sleep = time.sleep
    nonce_factory: NonceFactory = lambda: str(uuid.uuid4())

    def __post_init__(self) -> None:
        if not self.base_url.startswith("https://"):
            raise ValueError("Upbit account base_url must use HTTPS")
        if self.timeout_sec <= 0:
            raise ValueError("timeout_sec must be positive")
        if not 1 <= self.max_attempts <= 5:
            raise ValueError("max_attempts must be between 1 and 5")
        if self.backoff_sec < 0:
            raise ValueError("backoff_sec must be non-negative")

    def balances(self) -> tuple[AccountBalance, ...]:
        payload = self._get_json("/v1/accounts", {})
        if not isinstance(payload, list):
            raise UpbitResponseError("Upbit accounts response must be a list")
        balances = tuple(self._parse_balance(item) for item in payload)
        currencies = [item.currency for item in balances]
        if len(currencies) != len(set(currencies)):
            raise UpbitResponseError("Upbit accounts response contains duplicate currencies")
        return balances

    def order(self, *, order_uuid: str | None = None, identifier: str | None = None) -> AccountOrder:
        if not order_uuid and not identifier:
            raise ValueError("order_uuid or identifier is required")
        params: dict[str, object] = {}
        if order_uuid:
            params["uuid"] = order_uuid
        elif identifier:
            params["identifier"] = identifier
        payload = self._get_json("/v1/order", params)
        return self._parse_order(payload)

    def open_orders(self, *, market: str | None = None, state: str = "wait") -> tuple[AccountOrder, ...]:
        if state not in {"wait", "watch"}:
            raise ValueError("state must be wait or watch")
        params: dict[str, object] = {"state": state}
        if market:
            params["market"] = market.strip().upper()
        payload = self._get_json("/v1/orders/open", params)
        if not isinstance(payload, list):
            raise UpbitResponseError("Upbit open-orders response must be a list")
        orders = tuple(self._parse_order(item) for item in payload)
        order_ids = [item.uuid for item in orders]
        if len(order_ids) != len(set(order_ids)):
            raise UpbitResponseError("Upbit order response contains duplicate UUIDs")
        return orders

    def _get_json(self, path: str, params: Mapping[str, object]) -> object:
        if path not in _READ_ONLY_PATHS:
            raise UpbitPermissionError(f"non-read-only Upbit endpoint blocked: {path}")
        query_string = _canonical_query(params)
        url = f"{self.base_url.rstrip('/')}{path}"
        if query_string:
            url = f"{url}?{query_string}"
        last_error: BaseException | None = None
        for attempt in range(1, self.max_attempts + 1):
            token = _jwt_token(self.credentials, query_string, self.nonce_factory())
            request = Request(
                url,
                headers={
                    "Accept": "application/json",
                    "Authorization": f"Bearer {token}",
                    "User-Agent": "AiPro/readonly-account-inspection",
                },
                method="GET",
            )
            try:
                with self.opener(request, timeout=self.timeout_sec) as response:
                    raw = response.read()
                return json.loads(raw.decode("utf-8"))
            except HTTPError as exc:
                last_error = exc
                name = self._error_name(exc)
                if name in {"out_of_scope"}:
                    raise UpbitPermissionError("Upbit API key lacks required read permission") from exc
                if name in {
                    "invalid_query_payload",
                    "jwt_verification",
                    "expired_access_key",
                    "nonce_used",
                    "no_authorization_ip",
                    "no_authorization_token",
                }:
                    raise UpbitAuthenticationError(f"Upbit authentication rejected: {name}") from exc
                if exc.code not in {429, 500, 502, 503, 504}:
                    raise UpbitAccountError(f"Upbit account request failed: HTTP {exc.code}") from exc
            except (URLError, TimeoutError, UnicodeDecodeError, json.JSONDecodeError) as exc:
                last_error = exc
            if attempt < self.max_attempts:
                self.sleep(self.backoff_sec * attempt)
        raise UpbitAccountError(f"Upbit account request failed after {self.max_attempts} attempts") from last_error

    @staticmethod
    def _error_name(exc: HTTPError) -> str:
        try:
            payload = json.loads(exc.read().decode("utf-8"))
            error = payload.get("error", {}) if isinstance(payload, dict) else {}
            return str(error.get("name", ""))
        except (UnicodeDecodeError, json.JSONDecodeError, AttributeError):
            return ""

    @staticmethod
    def _decimal(value: object, field_name: str, *, optional: bool = False) -> Decimal | None:
        if value in {None, ""} and optional:
            return None
        try:
            parsed = Decimal(str(value))
        except (InvalidOperation, ValueError) as exc:
            raise UpbitResponseError(f"invalid decimal field: {field_name}") from exc
        if not parsed.is_finite() or parsed < 0:
            raise UpbitResponseError(f"invalid decimal field: {field_name}")
        return parsed

    @classmethod
    def _parse_balance(cls, item: object) -> AccountBalance:
        if not isinstance(item, dict):
            raise UpbitResponseError("Upbit account item must be an object")
        try:
            currency = str(item["currency"]).upper()
            unit_currency = str(item["unit_currency"]).upper()
            balance = cls._decimal(item["balance"], "balance")
            locked = cls._decimal(item["locked"], "locked")
            average = cls._decimal(item["avg_buy_price"], "avg_buy_price")
        except KeyError as exc:
            raise UpbitResponseError("Upbit account item is missing a required field") from exc
        if not currency or not unit_currency:
            raise UpbitResponseError("Upbit account currency fields must not be empty")
        assert isinstance(balance, Decimal) and isinstance(locked, Decimal) and isinstance(average, Decimal)
        return AccountBalance(currency, balance, locked, average, unit_currency)

    @classmethod
    def _parse_order(cls, item: object) -> AccountOrder:
        if not isinstance(item, dict):
            raise UpbitResponseError("Upbit order response must be an object")
        try:
            order_uuid = str(item["uuid"])
            market = str(item["market"]).upper()
            side = str(item["side"])
            state = str(item["state"])
            order_type = str(item["ord_type"])
            created_at = str(item["created_at"])
            price = cls._decimal(item.get("price"), "price", optional=True)
            volume = cls._decimal(item.get("volume"), "volume", optional=True)
            remaining = cls._decimal(item.get("remaining_volume"), "remaining_volume", optional=True)
            executed = cls._decimal(item.get("executed_volume", "0"), "executed_volume")
        except KeyError as exc:
            raise UpbitResponseError("Upbit order response is missing a required field") from exc
        if not all((order_uuid, market, side, state, order_type, created_at)):
            raise UpbitResponseError("Upbit order response contains an empty required field")
        assert isinstance(executed, Decimal)
        return AccountOrder(
            uuid=order_uuid,
            market=market,
            side=side,
            state=state,
            order_type=order_type,
            price=price,
            volume=volume,
            remaining_volume=remaining,
            executed_volume=executed,
            created_at=created_at,
            identifier=None if item.get("identifier") in {None, ""} else str(item["identifier"]),
        )


__all__ = [
    "AccountBalance",
    "AccountOrder",
    "UPBIT_EXCHANGE_API_BASE_URL",
    "UpbitAccountError",
    "UpbitAuthenticationError",
    "UpbitCredentials",
    "UpbitPermissionError",
    "UpbitReadOnlyAccountClient",
    "UpbitResponseError",
]
