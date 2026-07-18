from __future__ import annotations

import json
import logging
from collections.abc import Callable
from datetime import date, datetime
from zoneinfo import ZoneInfo

from aipro.broker import PaperBroker
from aipro.config import Settings
from aipro.market import DemoMarketData
from aipro.models import Signal
from aipro.risk import RiskManager
from aipro.storage import Storage
from aipro.strategy import MomentumStrategy

LOGGER = logging.getLogger(__name__)
KST = ZoneInfo("Asia/Seoul")
ACTIVE_CYCLE_STATE_KEY = "active_cycle_id"
CYCLE_SEQUENCE_STATE_KEY = "cycle_sequence"


class TradingApplication:
    def __init__(
        self,
        settings: Settings,
        date_provider: Callable[[], date] | None = None,
    ) -> None:
        self.settings = settings
        self.storage = Storage(settings.db_path)
        self.market = DemoMarketData()
        self.strategy = MomentumStrategy()
        self.broker = PaperBroker.restore(float(settings.initial_cash_krw), self.storage)
        self._date_provider = date_provider or (lambda: datetime.now(KST).date())

        persisted_halt = self.storage.get_state("halted") == "1"
        self.risk = RiskManager(settings.daily_loss_limit_pct, halted=persisted_halt)
        self.baseline_equity = self._load_baseline()

    def _today(self) -> str:
        return self._date_provider().isoformat()

    def _load_baseline(self) -> float:
        stored = self.storage.get_state("baseline_equity")
        if stored is None:
            return float(self.settings.initial_cash_krw)
        try:
            baseline = float(stored)
        except ValueError:
            LOGGER.error("Invalid persisted baseline; restoring initial cash baseline")
            return float(self.settings.initial_cash_krw)
        return baseline if baseline > 0 else float(self.settings.initial_cash_krw)

    def _persist_daily_baseline(self, trading_date: str, equity: float) -> None:
        self.baseline_equity = equity
        self.storage.set_state("trading_date", trading_date)
        self.storage.set_state("baseline_equity", str(equity))
        self.storage.record(
            "baseline_reset",
            json.dumps({"trading_date": trading_date, "equity": equity}),
        )

    def _sync_daily_baseline(self, equity: float) -> None:
        today = self._today()
        stored_date = self.storage.get_state("trading_date")
        if stored_date != today:
            self._persist_daily_baseline(today, equity)
            return

        stored_baseline = self.storage.get_state("baseline_equity")
        if stored_baseline is None:
            self._persist_daily_baseline(today, equity)

    def _persist_halted(self, halted: bool) -> None:
        self.storage.set_state("halted", "1" if halted else "0")

    def _load_cycle_sequence(self) -> int:
        raw = self.storage.get_state(CYCLE_SEQUENCE_STATE_KEY)
        if raw is None:
            return 0
        try:
            sequence = int(raw)
        except ValueError:
            LOGGER.error("Invalid cycle sequence; resetting to zero")
            return 0
        return sequence if sequence >= 0 else 0

    def _begin_cycle(self) -> str:
        active = self.storage.get_state(ACTIVE_CYCLE_STATE_KEY)
        if active:
            return active

        sequence = self._load_cycle_sequence() + 1
        cycle_id = f"{self._today()}-{sequence:08d}"
        self.storage.set_state(CYCLE_SEQUENCE_STATE_KEY, str(sequence))
        self.storage.set_state(ACTIVE_CYCLE_STATE_KEY, cycle_id)
        self.storage.record(
            "cycle_started",
            json.dumps({"cycle_id": cycle_id, "sequence": sequence}, sort_keys=True),
        )
        return cycle_id

    def _finish_cycle(self, cycle_id: str) -> None:
        active = self.storage.get_state(ACTIVE_CYCLE_STATE_KEY)
        if active != cycle_id:
            raise RuntimeError("active cycle changed unexpectedly")
        self.storage.set_state(ACTIVE_CYCLE_STATE_KEY, "")
        self.storage.record(
            "cycle_completed",
            json.dumps({"cycle_id": cycle_id}, sort_keys=True),
        )

    @staticmethod
    def _order_id(cycle_id: str, side: str, symbol: str) -> str:
        normalized_symbol = symbol.strip().upper().replace("/", "-")
        if not normalized_symbol:
            raise ValueError("symbol is required for order id")
        return f"paper:{cycle_id}:{side.lower()}:{normalized_symbol}"

    def status(self) -> dict[str, object]:
        snapshots = self.market.snapshots()
        prices = {item.symbol: item.price for item in snapshots}
        equity = self.broker.equity(prices)
        self._sync_daily_baseline(equity)
        daily_return_pct = (equity / self.baseline_equity - 1) * 100
        return {
            "mode": self.settings.mode,
            "halted": self.risk.halted,
            "trading_date": self._today(),
            "cash_krw": round(self.broker.cash_krw, 2),
            "equity_krw": round(equity, 2),
            "baseline_equity_krw": round(self.baseline_equity, 2),
            "daily_return_pct": round(daily_return_pct, 4),
            "positions": len(self.broker.positions),
            "active_cycle_id": self.storage.get_state(ACTIVE_CYCLE_STATE_KEY) or None,
            "cycle_sequence": self._load_cycle_sequence(),
        }

    def resume(self) -> None:
        snapshots = self.market.snapshots()
        prices = {item.symbol: item.price for item in snapshots}
        equity = self.broker.equity(prices)
        self.risk.resume()
        self._persist_halted(False)
        self._persist_daily_baseline(self._today(), equity)
        self.storage.record("resume", json.dumps({"equity": equity}))
        LOGGER.warning("Trading resumed explicitly with a new daily baseline")

    def run_once(self) -> None:
        cycle_id = self._begin_cycle()
        snapshots = self.market.snapshots()
        prices = {item.symbol: item.price for item in snapshots}
        equity = self.broker.equity(prices)
        self._sync_daily_baseline(equity)

        daily_return_pct = (equity / self.baseline_equity - 1) * 100
        was_halted = self.risk.halted
        if self.risk.evaluate(daily_return_pct):
            for symbol in list(self.broker.positions):
                price = prices.get(symbol)
                if price is None:
                    LOGGER.error("Cannot liquidate %s: current price unavailable", symbol)
                    continue
                self.broker.submit_sell_all(
                    self._order_id(cycle_id, "liquidate", symbol),
                    symbol,
                    price,
                )
            self._persist_halted(True)
            LOGGER.critical("HALTED: daily loss limit reached or latch already active")
            if not was_halted:
                self.storage.record(
                    "halt",
                    json.dumps({"return_pct": daily_return_pct}),
                )
            self._finish_cycle(cycle_id)
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
                        "cycle_id": cycle_id,
                        "symbol": decision.symbol,
                        "signal": decision.signal.value,
                        "confidence": decision.confidence,
                        "reason": decision.reason,
                    }
                ),
            )
            if decision.signal is Signal.BUY:
                is_new_position = snapshot.symbol not in self.broker.positions
                if is_new_position and len(self.broker.positions) >= self.settings.max_positions:
                    continue
                amount = self.risk.position_size(
                    self.broker.cash_krw,
                    self.settings.max_position_pct,
                    self.settings.min_order_krw,
                )
                if amount:
                    self.broker.submit_buy(
                        self._order_id(cycle_id, "buy", snapshot.symbol),
                        snapshot.symbol,
                        snapshot.price,
                        amount,
                    )
            elif decision.signal is Signal.SELL:
                self.broker.submit_sell_all(
                    self._order_id(cycle_id, "sell", snapshot.symbol),
                    snapshot.symbol,
                    snapshot.price,
                )

        LOGGER.info(
            "cycle complete id=%s mode=%s cash=%.0f equity=%.0f positions=%d",
            cycle_id,
            self.settings.mode,
            self.broker.cash_krw,
            self.broker.equity(prices),
            len(self.broker.positions),
        )
        self._finish_cycle(cycle_id)
