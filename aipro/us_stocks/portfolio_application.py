"""Canonical US dual-portfolio PAPER application; no network order methods."""
from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal, ROUND_DOWN
from hashlib import sha256
import logging
import os
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

from aipro.config import Settings
from aipro.us_stocks.portfolio_ledger import PortfolioLedger
from aipro.us_stocks.portfolio_market import FileMarketData, MarketFrame, Quote, instant
from aipro.us_stocks.portfolio_policy import INITIAL_ALLOCATIONS, PortfolioPolicy, number
from aipro.us_stocks.portfolio_strategy import ForecastProvider, entry_decision

LOGGER = logging.getLogger(__name__)
KST = ZoneInfo("Asia/Seoul")
D = Decimal


class TradingApplication:
    asset_class = "us_stock"

    def __init__(self, settings: Settings, *, policy: PortfolioPolicy | None = None,
                 db_path: Path | None = None, market=None, clock=None,
                 forecaster: ForecastProvider | None = None) -> None:
        settings.validate()
        if settings.mode != "PAPER":
            raise RuntimeError("US dual portfolio supports local PAPER execution only")
        if settings.initial_cash_krw != 1_000_000:
            raise ValueError("US dual profile requires exactly KRW 1,000,000 initial funding")
        self.settings = settings
        self.policy = policy or PortfolioPolicy()
        self.clock = clock or (lambda: datetime.now(UTC))
        self.ledger = PortfolioLedger(db_path or Path(os.getenv("AIPRO_US_DUAL_DB_PATH", "data/us_dual_paper.sqlite3")), self.policy)
        self.market = market
        if self.market is None and os.getenv("AIPRO_US_FRAME_PATH"):
            self.market = FileMarketData(Path(os.environ["AIPRO_US_FRAME_PATH"]))
        self.forecaster = forecaster

    @staticmethod
    def _equity(book: dict, quotes: dict[str, Quote], fx: D) -> D:
        return (D(book["cash"]) + sum((D(item["amount"]) for item in book["pending"]), D(0))
                + sum((D(pos["qty"]) * quotes[symbol].mid * fx for symbol, pos in book["positions"].items()), D(0)))

    def _liquidation_equity(self, book: dict, quotes: dict[str, Quote], fx: D) -> D:
        costs = 1 - self.policy.fee_rate - self.policy.fx_cost_rate
        return (D(book["cash"]) + sum((D(item["amount"]) for item in book["pending"]), D(0))
                + sum((D(pos["qty"]) * quotes[symbol].bid * (1 - self.policy.slippage_rate) * fx * costs
                       for symbol, pos in book["positions"].items()), D(0)))

    def _blocked(self, db, state: dict, frame: MarketFrame, reason: str) -> dict:
        key = "blocked:" + frame.fingerprint + ":" + reason
        if db.execute("SELECT 1 FROM us_dual_events WHERE event_key=?", (key,)).fetchone() is None:
            self.ledger.record(db, key, "BLOCKED", {"reason": reason, "at": str(frame.as_of_utc)})
        return {"processed": False, "reason": reason, "paper_only": True}

    def process_frame(self, frame: MarketFrame) -> dict:
        now, stamp = instant(self.clock()), instant(frame.as_of_utc)
        quotes = {quote.symbol: quote for quote in frame.quotes}
        p = self.policy
        with self.ledger.transaction() as (db, state):
            cycle_key = "frame:" + frame.fingerprint
            if db.execute("SELECT 1 FROM us_dual_events WHERE event_key=?", (cycle_key,)).fetchone():
                return {"processed": False, "reason": "duplicate_frame", "paper_only": True}
            if not 0 <= (now - stamp).total_seconds() <= p.frame_max_age_seconds:
                return self._blocked(db, state, frame, "stale_or_future_frame")
            if not 0 <= (stamp - instant(frame.fx_as_of_utc)).total_seconds() <= 300:
                return self._blocked(db, state, frame, "stale_or_future_fx")
            if state["last_frame_utc"] and stamp <= instant(state["last_frame_utc"]):
                return self._blocked(db, state, frame, "non_increasing_frame_time")
            if state["last_source_synthetic"] is not None and state["last_source_synthetic"] != frame.synthetic:
                return self._blocked(db, state, frame, "synthetic_and_market_data_cannot_share_ledger")
            held = {s for book in state["sleeves"].values() for s in book["positions"]}
            if held - quotes.keys():
                return self._blocked(db, state, frame, "missing_held_position_quote")
            if any(not 0 <= (stamp - instant(q.as_of_utc)).total_seconds() <= p.quote_max_age_seconds for q in quotes.values()):
                return self._blocked(db, state, frame, "stale_or_future_quote")

            day = stamp.astimezone(KST).date().isoformat()
            bid_depth = {symbol: quote.bid_size for symbol, quote in quotes.items()}
            ask_depth = {symbol: quote.ask_size for symbol, quote in quotes.items()}
            can_execute = instant(frame.session_open_utc) <= stamp < instant(frame.session_close_utc)
            closing = stamp >= instant(frame.session_close_utc) - timedelta(seconds=p.flatten_before_close_seconds)
            equities = {}
            for name, book in state["sleeves"].items():
                available = [item for item in book["pending"] if instant(item["available_at"]) <= stamp]
                book["cash"] = str(D(book["cash"]) + sum((D(item["amount"]) for item in available), D(0)))
                book["pending"] = [item for item in book["pending"] if instant(item["available_at"]) > stamp]
                equity = self._equity(book, quotes, frame.usd_krw)
                if book["day"] != day:
                    # Carry forward the last observed close rather than hiding an
                    # overnight gap by resetting to the new quote. Exact midnight
                    # valuation still needs a continuously running data feed.
                    previous = state["last_status"].get("sleeves", {}).get(name, {}).get("equity_krw")
                    book.update(day=day, baseline=str(previous if previous is not None else INITIAL_ALLOCATIONS[name]),
                                entries_today=0, entered_symbols_today=[])
                book["peak"] = str(max(D(book["peak"]), equity))
                equities[name] = equity
            total = sum(equities.values())
            state["total_peak_krw"] = str(max(D(state["total_peak_krw"]), total))
            if total <= D(state["total_peak_krw"]) * (1 - p.total_max_drawdown):
                state["global_halt"] = "total_drawdown"
            short = state["sleeves"]["short"]
            if equities["short"] <= D(short["baseline"]) * (1 - p.short_daily_loss):
                short["halt"] = "daily_loss"
            if equities["short"] <= D(short["peak"]) * (1 - p.short_max_drawdown):
                short["halt"] = "short_drawdown"
            if self._liquidation_equity(short, quotes, frame.usd_krw) >= D(short["baseline"]) * (1 + p.short_daily_target):
                short["target_day"] = day

            decisions, fills = [], []
            for name, book in state["sleeves"].items():
                review_due = not book["last_review"] or stamp - instant(book["last_review"]) >= timedelta(days=p.long_review_days)
                for symbol, position in list(book["positions"].items()):
                    q = quotes[symbol]
                    position["peak_usd"] = str(max(D(position["peak_usd"]), q.mid))
                    change = q.bid / D(position["entry_usd"]) - 1
                    reason = position.get("exit_reason", "")
                    if state["global_halt"]:
                        reason = state["global_halt"]
                    elif name == "short" and not reason:
                        if book["halt"]:
                            reason = book["halt"]
                        elif book["target_day"] == day:
                            reason = "daily_target"
                        elif closing or instant(position["entry_at"]) < instant(frame.session_open_utc):
                            reason = "session_flatten"
                        elif change <= -p.short_stop:
                            reason = "position_stop"
                        elif change >= p.short_take_profit:
                            reason = "take_profit"
                        elif D(position["peak_usd"]) >= D(position["entry_usd"]) * (1 + p.short_take_profit / 2) and q.bid <= D(position["peak_usd"]) * (1 - p.short_trailing_stop):
                            reason = "trailing_stop"
                    elif name == "long" and not reason and change <= -p.long_position_stop:
                        reason = "long_position_stop"
                    elif name == "long" and not reason and q.intelligence and 0 <= (stamp - instant(q.intelligence.as_of_utc)).total_seconds() <= p.intelligence_max_age_seconds and q.intelligence.material_risk:
                        reason = "material_filing_risk"
                    elif name == "long" and not reason and review_due:
                        check = entry_decision(name, q, frame, p, equities[name])
                        if check.reason == "long_trend_not_positive":
                            reason = "long_trend_exit"
                    if reason:
                        position["exit_reason"] = reason
                        depth_quote = replace(q, bid_size=bid_depth[symbol])
                        step = D("0.000001") if D(position["qty"]) % 1 or p.allow_fractional else D(1)
                        if can_execute and q.tradable and depth_quote.bid_size >= step:
                            fill = self._sell(book, name, depth_quote, frame, reason, step)
                            fills.append(fill)
                            bid_depth[symbol] -= D(fill["qty"])
                        else:
                            decisions.append({"sleeve": name, "symbol": symbol, "reason": "exit_pending:" + reason})

                # Re-evaluate after actual simulated costs before any new entry.
                equity_after_exits = self._equity(book, quotes, frame.usd_krw)
                if name == "short" and equity_after_exits <= D(book["baseline"]) * (1 - p.short_daily_loss):
                    book["halt"] = "daily_loss"
                if (not can_execute or closing or state["global_halt"] or book["halt"]
                        or (name == "short" and book["target_day"] == day)
                        or (name == "long" and not review_due)):
                    continue
                ranked = []
                for q in quotes.values():
                    if q.symbol in book["positions"] or q.symbol in book["entered_symbols_today"]:
                        continue
                    if not q.tradable or q.ask_size <= 0 or q.spread_bps > p.max_spread_bps:
                        decisions.append({"sleeve": name, "symbol": q.symbol, "reason": "quote_liquidity_gate"})
                        continue
                    decision = entry_decision(name, q, frame, p, equity_after_exits, self.forecaster if name == "short" else None)
                    decisions.append({"sleeve": name, "symbol": q.symbol, "reason": decision.reason,
                                      "allowed": decision.allowed, "model_id": decision.model_id,
                                      "feature_fingerprint": decision.feature_fingerprint})
                    if decision.allowed:
                        ranked.append((decision.score, q.symbol, q, decision))
                for _, _, q, decision in sorted(ranked, key=lambda item: (-item[0], item[1])):
                    max_positions = p.short_max_positions if name == "short" else p.long_max_positions
                    if len(book["positions"]) >= max_positions:
                        break
                    if name == "short" and book["entries_today"] >= p.short_max_entries_per_day:
                        break
                    depth_quote = replace(q, ask_size=ask_depth[q.symbol])
                    fill = self._buy(book, name, depth_quote, frame, self._equity(book, quotes, frame.usd_krw), decision.notional_cap_krw)
                    if fill:
                        fills.append(fill)
                        ask_depth[q.symbol] -= D(fill["qty"])
                        if name == "short" and self._equity(book, quotes, frame.usd_krw) <= D(book["baseline"]) * (1 - p.short_daily_loss):
                            book["halt"] = "daily_loss"
                            break
                if name == "long" and (ranked or book["positions"]):
                    book["last_review"] = stamp.isoformat()

            state["last_frame_utc"] = stamp.isoformat()
            state["last_source_synthetic"] = frame.synthetic
            for index, fill in enumerate(fills):
                fill["client_order_id"] = "us-dual:" + sha256(f"{frame.fingerprint}:{index}:{fill['sleeve']}:{fill['symbol']}:{fill['side']}".encode()).hexdigest()[:40]
            status = self._make_status(state, quotes, frame)
            state["last_status"] = status
            result = {"processed": True, "paper_only": True, "synthetic": frame.synthetic,
                      "frame_fingerprint": frame.fingerprint, "fills": fills, "decisions": decisions, "status": status}
            self.ledger.record(db, cycle_key, "CYCLE", result)
            return result

    def _buy(self, book: dict, name: str, q: Quote, frame: MarketFrame, equity: D, model_cap: D | None) -> dict | None:
        p = self.policy
        realized_capital = INITIAL_ALLOCATIONS[name] + D(book["realized_pnl"])
        capital = max(D(0), min(realized_capital, equity))
        existing_cost = sum((D(pos["cost"]) for pos in book["positions"].values()), D(0))
        position_cap = capital * (p.short_position_fraction if name == "short" else p.long_position_fraction)
        budget = min(D(book["cash"]) - capital * p.cash_reserve_fraction,
                     capital * (1 - p.cash_reserve_fraction) - existing_cost, position_cap)
        if name == "short":
            round_trip_cost = 2 * (p.fee_rate + p.fx_cost_rate + p.slippage_rate) + q.spread_bps / 10000
            budget = min(budget, capital * p.short_risk_per_trade / (p.short_stop + round_trip_cost))
        if model_cap is not None:
            budget = min(budget, number(model_cap))
        price = q.ask * (1 + p.slippage_rate)
        unit_cost = price * frame.usd_krw * (1 + p.fee_rate + p.fx_cost_rate)
        if budget <= 0:
            return None
        step = D("0.000001") if p.allow_fractional and q.fractionable else D(1)
        quantity = (min(budget / unit_cost, q.ask_size) / step).to_integral_value(rounding=ROUND_DOWN) * step
        cost = quantity * unit_cost
        if quantity <= 0 or cost < p.minimum_order_krw:
            return None
        book["cash"] = str(D(book["cash"]) - cost)
        book["positions"][q.symbol] = {"qty": str(quantity), "cost": str(cost), "entry_usd": str(price),
            "entry_at": instant(frame.as_of_utc).isoformat(), "peak_usd": str(price)}
        book["entries_today"] += 1
        book["entered_symbols_today"].append(q.symbol)
        return {"sleeve": name, "symbol": q.symbol, "side": "BUY", "qty": str(quantity),
                "price_usd": str(price), "cash_change_krw": str(-cost), "reason": "strategy_entry",
                "costs_krw": str(quantity * price * frame.usd_krw * (p.fee_rate + p.fx_cost_rate))}

    def _sell(self, book: dict, name: str, q: Quote, frame: MarketFrame, reason: str, step: D) -> dict:
        position = book["positions"][q.symbol]
        quantity = (min(D(position["qty"]), q.bid_size) / step).to_integral_value(rounding=ROUND_DOWN) * step
        price = q.bid * (1 - self.policy.slippage_rate)
        gross = quantity * price * frame.usd_krw
        proceeds = gross * (1 - self.policy.fee_rate - self.policy.fx_cost_rate)
        released_cost = D(position["cost"]) * quantity / D(position["qty"])
        pnl = proceeds - released_cost
        book["realized_pnl"] = str(D(book["realized_pnl"]) + pnl)
        book["pending"].append({"amount": str(proceeds), "available_at": instant(frame.settlement_at_utc).isoformat()})
        remaining = D(position["qty"]) - quantity
        if remaining == 0:
            del book["positions"][q.symbol]
        else:
            position.update(qty=str(remaining), cost=str(D(position["cost"]) - released_cost))
        return {"sleeve": name, "symbol": q.symbol, "side": "SELL", "qty": str(quantity),
                "price_usd": str(price), "unsettled_proceeds_krw": str(proceeds), "realized_pnl_krw": str(pnl),
                "reason": reason, "partial": remaining > 0,
                "costs_krw": str(gross * (self.policy.fee_rate + self.policy.fx_cost_rate))}

    def _make_status(self, state: dict, quotes: dict[str, Quote], frame: MarketFrame) -> dict:
        sleeves = {}
        for name, book in state["sleeves"].items():
            equity = self._equity(book, quotes, frame.usd_krw)
            baseline = D(book["baseline"])
            sleeves[name] = {
                "cash_krw": book["cash"], "unsettled_krw": str(sum((D(item["amount"]) for item in book["pending"]), D(0))),
                "equity_krw": str(equity), "baseline_equity_krw": str(baseline),
                "daily_return_pct": str((equity / baseline - 1) * 100 if baseline > 0 else D(0)),
                "net_realized_pnl_krw": book["realized_pnl"], "positions": book["positions"],
                "halt": book["halt"], "profit_stop": book["target_day"] == book["day"],
                "entries_today": book["entries_today"], "trading_date": book["day"],
            }
        return {"asset_class": "us_stock", "mode": "PAPER", "execution": "LOCAL_SIMULATION",
                "as_of_utc": instant(frame.as_of_utc).isoformat(), "synthetic": frame.synthetic,
                "external_contributed_krw": "1000000", "remaining_external_funding_krw": "0",
                "total_equity_krw_reference_only": str(sum(D(item["equity_krw"]) for item in sleeves.values())),
                "global_halt": state["global_halt"], "sleeves": sleeves}

    def status(self) -> dict:
        state = self.ledger.read()
        status = dict(state["last_status"])
        if not status:
            return {"mode": "PAPER", "execution": "LOCAL_SIMULATION", "reason": "awaiting_market_frame",
                    "external_contributed_krw": "1000000", "remaining_external_funding_krw": "0",
                    "global_halt": state["global_halt"], "sleeves": {}}
        status["global_halt"] = state["global_halt"]
        status["stale"] = (instant(self.clock()) - instant(status["as_of_utc"])).total_seconds() > self.policy.frame_max_age_seconds
        for name in status["sleeves"]:
            status["sleeves"][name]["halt"] = state["sleeves"][name]["halt"]
        return status

    def halt(self) -> None:
        with self.ledger.transaction() as (db, state):
            state["global_halt"] = "manual_halt"
            self.ledger.record(db, "halt:" + str(uuid4()), "HALT", {"at": str(self.clock())})

    def resume(self) -> None:
        with self.ledger.transaction() as (db, state):
            now = instant(self.clock())
            if not state["last_frame_utc"] or not 0 <= (now - instant(state["last_frame_utc"])).total_seconds() <= self.policy.frame_max_age_seconds:
                raise RuntimeError("fresh portfolio valuation required before resume")
            status = state["last_status"]
            total = D(status["total_equity_krw_reference_only"])
            if total <= D(state["total_peak_krw"]) * (1 - self.policy.total_max_drawdown):
                raise RuntimeError("total drawdown gate is still active")
            book = state["sleeves"]["short"]
            eq = D(status["sleeves"]["short"]["equity_krw"])
            if eq <= D(book["peak"]) * (1 - self.policy.short_max_drawdown) or eq <= D(book["baseline"]) * (1 - self.policy.short_daily_loss):
                raise RuntimeError("short loss gate is still active; resume cannot reset a baseline")
            state["global_halt"] = ""
            book["halt"] = ""
            self.ledger.record(db, "resume:" + str(uuid4()), "RESUME", {"at": str(now), "baseline_reset": False})

    def run_once(self) -> dict:
        if self.market is None:
            result = {"processed": False, "reason": "configure_AIPRO_US_FRAME_PATH", "paper_only": True}
        else:
            result = self.process_frame(self.market.frame())
        LOGGER.info("US dual PAPER cycle: %s", result)
        return result
