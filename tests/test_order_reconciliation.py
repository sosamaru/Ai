from __future__ import annotations

from decimal import Decimal

import pytest

from aipro.crypto.account import AccountOrder, UpbitAccountError
from aipro.crypto.order_reconciliation import (
    ExchangeOrderReconciler,
    OrderLookupKey,
    ReconciliationStatus,
)


def order(uuid: str, identifier: str | None = None) -> AccountOrder:
    return AccountOrder(
        uuid=uuid,
        market="KRW-BTC",
        side="bid",
        state="wait",
        order_type="limit",
        price=Decimal("100"),
        volume=Decimal("1"),
        remaining_volume=Decimal("1"),
        executed_volume=Decimal("0"),
        created_at="2026-07-19T00:00:00+00:00",
        identifier=identifier,
    )


class FakeClient:
    def __init__(self, *, by_uuid=None, by_identifier=None, error=None) -> None:
        self.by_uuid = by_uuid
        self.by_identifier = by_identifier
        self.error = error
        self.calls: list[tuple[str | None, str | None]] = []

    def order(self, *, order_uuid=None, identifier=None):
        self.calls.append((order_uuid, identifier))
        if self.error:
            raise self.error
        return self.by_uuid if order_uuid else self.by_identifier


def test_lookup_key_requires_stable_identity() -> None:
    with pytest.raises(ValueError):
        OrderLookupKey()


def test_uuid_match_blocks_duplicate_submission() -> None:
    client = FakeClient(by_uuid=order("u-1"))
    result = ExchangeOrderReconciler(client).reconcile(OrderLookupKey(order_uuid="u-1"))
    assert result.status is ReconciliationStatus.FOUND_BY_UUID
    assert result.matched_order.uuid == "u-1"
    assert result.retry_submission_allowed is False


def test_identifier_match_blocks_duplicate_submission() -> None:
    client = FakeClient(by_identifier=order("u-1", "client-1"))
    result = ExchangeOrderReconciler(client).reconcile(OrderLookupKey(identifier="client-1"))
    assert result.status is ReconciliationStatus.FOUND_BY_IDENTIFIER
    assert result.retry_submission_allowed is False


def test_conflicting_identifiers_are_ambiguous_and_fail_closed() -> None:
    client = FakeClient(by_uuid=order("u-1"), by_identifier=order("u-2", "client-1"))
    result = ExchangeOrderReconciler(client).reconcile(
        OrderLookupKey(order_uuid="u-1", identifier="client-1")
    )
    assert result.status is ReconciliationStatus.AMBIGUOUS
    assert result.retry_submission_allowed is False
    assert result.matched_order is None


def test_lookup_failure_never_allows_resubmission() -> None:
    client = FakeClient(error=UpbitAccountError("timeout"))
    result = ExchangeOrderReconciler(client).reconcile(OrderLookupKey(order_uuid="u-1"))
    assert result.status is ReconciliationStatus.LOOKUP_FAILED
    assert result.retry_submission_allowed is False


def test_unproven_absence_never_allows_resubmission() -> None:
    client = FakeClient(by_uuid=None)
    result = ExchangeOrderReconciler(client).reconcile(OrderLookupKey(order_uuid="u-1"))
    assert result.status is ReconciliationStatus.NOT_FOUND
    assert result.retry_submission_allowed is False
