import pytest

from aipro.core import AssetClass, TradingDomain
from aipro.crypto import CRYPTO_DOMAIN
from aipro.us_stocks import US_STOCK_DOMAIN, USStockCapitalPolicy


def test_crypto_and_us_stock_domains_are_distinct() -> None:
    assert CRYPTO_DOMAIN.asset_class is AssetClass.CRYPTO
    assert US_STOCK_DOMAIN.asset_class is AssetClass.US_STOCK
    assert CRYPTO_DOMAIN.currency == "KRW"
    assert US_STOCK_DOMAIN.currency == "USD"


def test_live_order_submission_is_disabled_for_both_domains() -> None:
    assert CRYPTO_DOMAIN.live_order_submission_enabled is False
    assert US_STOCK_DOMAIN.live_order_submission_enabled is False
    assert US_STOCK_DOMAIN.enabled is False


def test_us_stock_capital_is_isolated_at_two_hundred_thousand_krw() -> None:
    policy = USStockCapitalPolicy()

    assert policy.budget_krw == 200_000
    assert policy.maximum_deployable_krw == 190_000
    assert policy.max_positions == 3


def test_disabled_domain_cannot_enable_live_orders() -> None:
    with pytest.raises(ValueError, match="disabled domains cannot submit live orders"):
        TradingDomain(
            asset_class=AssetClass.US_STOCK,
            currency="USD",
            enabled=False,
            live_order_submission_enabled=True,
        )
