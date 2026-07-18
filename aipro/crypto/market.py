from aipro.models import MarketSnapshot


class DemoMarketData:
    """Deterministic crypto market data for offline smoke tests."""

    def snapshots(self) -> list[MarketSnapshot]:
        return [
            MarketSnapshot("KRW-BTC", 150_000_000.0, 1.2, 2.1),
            MarketSnapshot("KRW-ETH", 5_000_000.0, 0.2, 1.8),
            MarketSnapshot("KRW-XRP", 3_000.0, -1.4, 3.0),
        ]
