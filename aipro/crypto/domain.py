from aipro.core import AssetClass, TradingDomain


CRYPTO_DOMAIN = TradingDomain(
    asset_class=AssetClass.CRYPTO,
    currency="KRW",
    enabled=True,
    live_order_submission_enabled=False,
)
