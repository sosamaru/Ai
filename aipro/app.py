from __future__ import annotations

import json
import logging
from dataclasses import asdict

from aipro.broker import Fill, PaperBroker
from aipro.config import Settings
from aipro.controller import AppMode, Controller
from aipro.execution import OrderGuard
from aipro.market import DemoMarketData
from aipro.models import Signal
from aipro.risk import RiskManager
from aipro.storage import Storage
from aipro.strategy import MomentumStrategy

LOGGER = logging.getLogger(__name__)


class TradingApplication:
    STATE_KEY = "trading_application"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.storage = Storage(settings.db_path)
        self.market = DemoMarketData()
        self.strategy = MomentumStrategy()
        self.risk = RiskManager(settings.daily_loss_limit_pct)
        self.order_guard = OrderGuard()
        self.controller = Controller()
        self.broker = PaperBroker(float(settings.initial_cash_krw))
        self.baseline_equity = float(settings.initial_cash_krw)
        self._restore_state()

    def _restore_state(self) -> None:
        state = self.storage.load_state(self.STATE_KEY)
        if not state:
            return
        self.broker = PaperBroker.restore(state["broker"])
        self.baseline_equity = float(state.get("baseline_equity", self.settings.initial_cash_krw))
        self.controller.mode = AppMode(state.get("controller_mode", AppMode.RUNNING.value))
        self.risk.halted = bool(state.get("risk_halted", self.controller.mode is AppMode.HALTED))

    def _persist_state(self) -> None:
        self.storage.save_state(
            self.STATE_KEY,
            {
                "broker": self.broker.snapshot(),
                "baseline_equity": self.baseline_equity,
                "controller_mode": self.controller.mode.value,
                "risk_halted": self.risk.halted,
            },
        )

    def _record_fill(self, fill: Fill | None) -> None:
        if fill is not None:
            self.storage.record("fill", json.dumps(asdict(fill), ensure_ascii=False))

    def pause(self) -> None:
        self.controller.pause()
        self.storage.record("controller", json.dumps({"mode": self.controller.mode.value}))
        self._persist_state()

    def resume(self) -> None:
        self.controller.resume()
        self.storage.record("controller", json.dumps({"mode": self.controller.mode.value}))
        self._persist_state()

    def halt(self) -> None:
        self.controller.halt()
        self.risk.halted = True
        self.storage.record("controller", json.dumps({"mode": self.controller.mode.value}))
        self._persist_state()

    def go(self) -> None:
        self.controller.go()
        self.risk.halted = False
        self.baseline_equity = self.broker.equity({})
        self.storage.record("controller", json.dumps({"mode": self.controller.mode.value}))
        self._persist_state()

    def status(self) -> dict[str, object]:
        return {
            "mode": self.controller.mode.value,
            "cash_krw": self.broker.cash_krw,
            "positions": len(self.broker.positions),
            "baseline_equity": self.baseline_equity,
        }

    def run_once(self) -> None:
        if not self.controller.can_trade:
            self.storage.record("cycle_skipped", json.dumps({"mode": self.controller.mode.value}))
            return

        snapshots = self.market.snapshots()
        prices = {item.symbol: item.price for item in snapshots}
        equity = self.broker.equity(prices)
        daily_return_pct = (equity / self.baseline_equity - 1) * 100
        if self.risk.evaluate(daily_return_pct):
            for symbol in list(self.broker.positions):
                self._record_fill(self.broker.sell_all(symbol, prices[symbol]))
            self.controller.halt()
            LOGGER.critical("HALTED: daily loss limit reached")
            self.storage.record("halt", json.dumps({"return_pct": daily_return_pct}))
            self._persist_state()
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
                if decision.symbol not in self.broker.positions and len(self.broker.positions) >= self.settings.max_positions:
                    self.storage.record("order_rejected", json.dumps({"reason": "max_positions", "symbol": decision.symbol}))
                    continue
                if not self.order_guard.allow(decision.symbol, "BUY"):
                    self.storage.record("order_rejected", json.dumps({"reason": "duplicate_order", "symbol": decision.symbol}))
                    continue
                amount = self.risk.position_size(
                    self.broker.cash_krw,
                    self.settings.max_position_pct,
                    self.settings.min_order_krw,
                )
                if amount:
                    self._record_fill(self.broker.buy(snapshot.symbol, snapshot.price, amount))
            elif decision.signal is Signal.SELL:
                if not self.order_guard.allow(decision.symbol, "SELL"):
                    self.storage.record("order_rejected", json.dumps({"reason": "duplicate_order", "symbol": decision.symbol}))
                    continue
                self._record_fill(self.broker.sell_all(snapshot.symbol, snapshot.price))

        self._persist_state()
        LOGGER.info(
            "cycle complete mode=%s cash=%.0f equity=%.0f positions=%d",
            self.settings.mode,
            self.broker.cash_krw,
            self.broker.equity(prices),
            len(self.broker.positions),
        )
