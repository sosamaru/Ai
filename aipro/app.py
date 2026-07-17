from __future__ import annotations

import json
import logging
from typing import Any

from aipro.broker import PaperBroker
from aipro.config import Settings
from aipro.market import DemoMarketData
from aipro.models import Signal
from aipro.risk import RiskManager
from aipro.storage import Storage
from aipro.strategy import MomentumStrategy

LOGGER = logging.getLogger(__name__)
STATE_KEY = "trading_application"
STATE_VERSION = 1


class TradingApplication:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.storage = Storage(settings.db_path)
        self.market = DemoMarketData()
        self.strategy = MomentumStrategy()
        self.risk = RiskManager(settings.daily_loss_limit_pct)
        self.broker = PaperBroker(float(settings.initial_cash_krw))
        self.baseline_equity = float(settings.initial_cash_krw)
        self._restore_state()

    def _restore_state(self) -> None:
        state = self.storage.load_state(STATE_KEY)
        if state is None:
            self._persist_state()
            return
        if int(state.get("version", 0)) != STATE_VERSION:
            raise ValueError("unsupported runtime state version")
        broker_state = state.get("broker")
        if not isinstance(broker_state, dict):
            raise ValueError("runtime state is missing broker data")
        self.broker = PaperBroker.from_dict(broker_state)
        self.baseline_equity = float(state["baseline_equity"])
        self.risk.halted = bool(state.get("halted", False))
        LOGGER.info(
            "runtime state restored cash=%.0f positions=%d halted=%s",
            self.broker.cash_krw,
            len(self.broker.positions),
            self.risk.halted,
        )

    def _state_payload(self) -> dict[str, Any]:
        return {
            "version": STATE_VERSION,
            "broker": self.broker.to_dict(),
            "baseline_equity": self.baseline_equity,
            "halted": self.risk.halted,
        }

    def _persist_state(self) -> None:
        self.storage.save_state(STATE_KEY, self._state_payload())

    def run_once(self) -> None:
        snapshots = self.market.snapshots()
        prices = {item.symbol: item.price for item in snapshots}
        equity = self.broker.equity(prices)
        daily_return_pct = (equity / self.baseline_equity - 1) * 100
        if self.risk.evaluate(daily_return_pct):
            for symbol in list(self.broker.positions):
                self.broker.sell_all(symbol, prices[symbol])
            self._persist_state()
            LOGGER.critical("HALTED: daily loss limit reached")
            self.storage.record(
                "halt",
                json.dumps({"return_pct": daily_return_pct}),
            )
            return

        for snapshot in snapshots:
            decision = self.strategy.decide(snapshot)
            LOGGER.info(
                "%s %s confidence=%.2f reason=%s",
                decision.symbol,
                decision.signal.value,
                decision.confidence,
                decision.reason,
            )
            self.storage.record(
                "decision",
                json.dumps(
                    {
                        "symbol": decision.symbol,
                        "signal": decision.signal.value,
                        "confidence": decision.confidence,
                        "reason": decision.reason,
                    }
                ),
            )
            if decision.signal is Signal.BUY:
                if len(self.broker.positions) >= self.settings.max_positions:
                    continue
                amount = self.risk.position_size(
                    self.broker.cash_krw,
                    self.settings.max_position_pct,
                    self.settings.min_order_krw,
                )
                if amount:
                    self.broker.buy(snapshot.symbol, snapshot.price, amount)
                    self._persist_state()
            elif decision.signal is Signal.SELL:
                proceeds = self.broker.sell_all(snapshot.symbol, snapshot.price)
                if proceeds:
                    self._persist_state()

        self._persist_state()
        LOGGER.info(
            "cycle complete mode=%s cash=%.0f equity=%.0f positions=%d",
            self.settings.mode,
            self.broker.cash_krw,
            self.broker.equity(prices),
            len(self.broker.positions),
        )
