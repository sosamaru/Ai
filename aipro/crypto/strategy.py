from aipro.models import Decision, MarketSnapshot, Signal


class MomentumStrategy:
    """Baseline momentum strategy owned by the crypto domain."""

    def decide(self, snapshot: MarketSnapshot) -> Decision:
        if snapshot.volatility_pct > 8:
            return Decision(snapshot.symbol, Signal.HOLD, 0.9, "volatility guard")
        if snapshot.change_1h_pct >= 1.0:
            return Decision(
                snapshot.symbol,
                Signal.BUY,
                min(0.95, 0.55 + snapshot.change_1h_pct / 20),
                "positive momentum",
            )
        if snapshot.change_1h_pct <= -1.0:
            return Decision(
                snapshot.symbol,
                Signal.SELL,
                min(0.95, 0.55 + abs(snapshot.change_1h_pct) / 20),
                "negative momentum",
            )
        return Decision(snapshot.symbol, Signal.HOLD, 0.6, "no edge")
