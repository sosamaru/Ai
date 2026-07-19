from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from aipro.crypto.account import AccountOrder, UpbitAccountError, UpbitReadOnlyAccountClient


class ReconciliationStatus(StrEnum):
    FOUND_BY_UUID = "FOUND_BY_UUID"
    FOUND_BY_IDENTIFIER = "FOUND_BY_IDENTIFIER"
    NOT_FOUND = "NOT_FOUND"
    AMBIGUOUS = "AMBIGUOUS"
    LOOKUP_FAILED = "LOOKUP_FAILED"


@dataclass(frozen=True, slots=True)
class OrderLookupKey:
    order_uuid: str | None = None
    identifier: str | None = None

    def __post_init__(self) -> None:
        uuid_value = (self.order_uuid or "").strip()
        identifier_value = (self.identifier or "").strip()
        if not uuid_value and not identifier_value:
            raise ValueError("order_uuid or identifier is required")
        object.__setattr__(self, "order_uuid", uuid_value or None)
        object.__setattr__(self, "identifier", identifier_value or None)


@dataclass(frozen=True, slots=True)
class ReconciliationResult:
    status: ReconciliationStatus
    retry_submission_allowed: bool
    matched_order: AccountOrder | None = None
    reason: str = ""


class ExchangeOrderReconciler:
    """Resolve ambiguous order outcomes using read-only exchange inspection only."""

    def __init__(self, client: UpbitReadOnlyAccountClient) -> None:
        self._client = client

    def reconcile(self, key: OrderLookupKey) -> ReconciliationResult:
        by_uuid: AccountOrder | None = None
        by_identifier: AccountOrder | None = None

        try:
            if key.order_uuid:
                by_uuid = self._client.order(order_uuid=key.order_uuid)
            if key.identifier:
                by_identifier = self._client.order(identifier=key.identifier)
        except UpbitAccountError as exc:
            return ReconciliationResult(
                status=ReconciliationStatus.LOOKUP_FAILED,
                retry_submission_allowed=False,
                reason=str(exc),
            )

        if by_uuid and by_identifier and by_uuid.uuid != by_identifier.uuid:
            return ReconciliationResult(
                status=ReconciliationStatus.AMBIGUOUS,
                retry_submission_allowed=False,
                reason="UUID and identifier resolved to different exchange orders",
            )
        matched = by_uuid or by_identifier
        if matched is None:
            return ReconciliationResult(
                status=ReconciliationStatus.NOT_FOUND,
                retry_submission_allowed=False,
                reason="absence cannot be proven safely from a failed single-order lookup contract",
            )
        return ReconciliationResult(
            status=(
                ReconciliationStatus.FOUND_BY_UUID
                if by_uuid is not None
                else ReconciliationStatus.FOUND_BY_IDENTIFIER
            ),
            retry_submission_allowed=False,
            matched_order=matched,
            reason="existing exchange order confirmed; duplicate submission blocked",
        )


__all__ = [
    "ExchangeOrderReconciler",
    "OrderLookupKey",
    "ReconciliationResult",
    "ReconciliationStatus",
]
