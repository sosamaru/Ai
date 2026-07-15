import json
import logging

from aipro.broker import PaperBroker
from aipro.config import Settings
from aipro.market import DemoMarketData
from aipro.models import Signal
from aipro.risk import RiskManager
from aipro.storage import Storage
from aipro.strategy import MomentumStrategy

LOGGER = logging.getLogger(__name__)


class TradingApplication:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.storage = Storage(settings.db_path)
        self.market = DemoMarketData()
        self.strategy = MomentumStrategy()
        self.risk = RiskManager(settings.daily_loss_limit_pct)
        self.broker = PaperBroker(float(settings.initial_cash_krw))
        self.baseline_equity = float(settings.initial_cash_krw)

    def run_once(self) -> None:
        snapshots = self.market.snapshots()
        prices = {item.symbol: item.price for item in snapshots}
        equity = self.broker.equity(prices)
        daily_return_pct = (equity / self.baseline_equity - 1) * 100
        if self.risk.evaluate(daily_return_pct):
            for symbol in list(self.broker.positions):
                self.broker.sell_all(symbol, prices[symbol])
            LOGGER.critical("HALTED: daily loss limit reached")
            self.storage.record("halt", json.dumps({"return_pct": daily_return_pct}))
            return

        for snapshot in snapshots:
            decision = self.strategy.decide(snapshot)
            LOGGER.info("%s %s confidence=%.2f reason=%s", decision.symbol, decision.signal.value, decision.confidence, decision.reason)
            self.storage.record("decision", json.dumps({"symbol": decision.symbol, "signal": decision.signal.value, "confidence": decision.confidence, "reason": decision.reason}))
            if decision.signal is Signal.BUY:
                if len(self.broker.positions) >= self.settings.max_positions:
                    continue
                amount = self.risk.position_size(self.broker.cash_krw, self.settings.max_position_pct, self.settings.min_order_krw)
                if amount:
                    self.broker.buy(snapshot.symbol, snapshot.price, amount)
            elif decision.signal is Signal.SELL:
                self.broker.sell_all(snapshot.symbol, snapshot.price)

        LOGGER.info("cycle complete mode=%s cash=%.0f equity=%.0f positions=%d", self.settings.mode, self.broker.cash_krw, self.broker.equity(prices), len(self.broker.positions))
