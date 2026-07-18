from aipro.crypto.market import DemoMarketData as DomainMarketData
from aipro.crypto.strategy import MomentumStrategy as DomainStrategy
from aipro.market import DemoMarketData as LegacyMarketData
from aipro.strategy import MomentumStrategy as LegacyStrategy


def test_legacy_market_import_points_to_crypto_domain() -> None:
    assert LegacyMarketData is DomainMarketData


def test_legacy_strategy_import_points_to_crypto_domain() -> None:
    assert LegacyStrategy is DomainStrategy


def test_demo_market_symbols_remain_crypto_only() -> None:
    symbols = {snapshot.symbol for snapshot in DomainMarketData().snapshots()}
    assert symbols == {"KRW-BTC", "KRW-ETH", "KRW-XRP"}
