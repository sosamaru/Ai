from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
import json
from pathlib import Path
import sqlite3

import pytest

from aipro.config import Settings
from aipro.sqlite_utils import connect
from aipro.us_stocks.portfolio_application import TradingApplication
from aipro.us_stocks.portfolio_ledger import PortfolioLedger, validate_accounting
from aipro.us_stocks.portfolio_market import FileMarketData, MarketFrame
from aipro.us_stocks.portfolio_policy import PortfolioPolicy
from aipro.us_stocks.portfolio_replay import demo_frame, demo_frames, load_jsonl, replay
from telegram import TelegramCommandRouter

D = Decimal
START = datetime(2026, 9, 14, 14, 30, tzinfo=UTC)


def application(tmp_path, policy=None):
    now = [START]
    app = TradingApplication(Settings(), policy=policy, db_path=tmp_path / "us.db", clock=lambda: now[0])
    return app, now


def cycle(app, now, *, minutes=0, short="10.46", long="25", transform=None):
    now[0] = START + timedelta(minutes=minutes)
    frame = demo_frame(now[0], short_price=short, long_price=long)
    if transform:
        frame = transform(frame)
    return app.process_frame(frame)


def buys(result, sleeve=None):
    return [fill for fill in result["fills"] if fill["side"] == "BUY" and (sleeve is None or fill["sleeve"] == sleeve)]


def test_fixed_funding_and_restart_never_refund_losses(tmp_path):
    app, now = application(tmp_path)
    cycle(app, now)
    cycle(app, now, minutes=1, short="9.60")
    state = app.ledger.read()
    restarted = TradingApplication(Settings(), db_path=tmp_path / "us.db", clock=lambda: now[0])
    assert restarted.ledger.read() == state
    assert state["external_contributed_krw"] == "1000000"
    assert D(state["sleeves"]["short"]["realized_pnl"]) < 0
    with pytest.raises(RuntimeError, match="deposits disabled"):
        restarted.ledger.contribute(D(1))


@pytest.mark.parametrize("cash", [999999, 1000001, 10000000])
def test_wrong_external_budget_rejected(tmp_path, cash):
    with pytest.raises(ValueError, match="exactly"):
        TradingApplication(Settings(initial_cash_krw=cash), db_path=tmp_path / "us.db")


def test_crypto_database_cannot_fund_us_portfolio(tmp_path):
    path = tmp_path / "shared.db"
    with connect(path) as db:
        db.execute("CREATE TABLE state(key TEXT, value TEXT)")
    with pytest.raises(RuntimeError, match="dedicated"):
        TradingApplication(Settings(), db_path=path)


def test_missing_state_cannot_silently_refund_existing_portfolio(tmp_path):
    app, _ = application(tmp_path)
    with connect(app.ledger.path) as db:
        db.execute("DELETE FROM us_dual_state")
    with pytest.raises(RuntimeError, match="refusing to refund"):
        PortfolioLedger(app.ledger.path, app.policy)


def test_costs_and_risk_sizing_are_charged_to_separate_cash_books(tmp_path):
    app, now = application(tmp_path)
    result = cycle(app, now)
    assert {fill["sleeve"] for fill in buys(result)} == {"short", "long"}
    for name, allocation in (("short", D(200000)), ("long", D(800000))):
        book = app.ledger.read()["sleeves"][name]
        costs = -sum(D(fill["cash_change_krw"]) for fill in buys(result, name))
        assert D(book["cash"]) == allocation - costs
        assert D(book["cash"]) >= allocation * D("0.05")
        assert all(D(fill["costs_krw"]) > 0 for fill in buys(result, name))
    validate_accounting(app.ledger.read(), app.policy)


def test_short_loss_does_not_draw_from_long_sleeve(tmp_path):
    app, now = application(tmp_path)
    cycle(app, now)
    long_before = app.ledger.read()["sleeves"]["long"]
    result = cycle(app, now, minutes=1, short="9.60")
    state = app.ledger.read()
    assert state["sleeves"]["short"]["halt"] == "daily_loss"
    assert state["sleeves"]["long"] == long_before
    assert not state["sleeves"]["short"]["positions"]
    assert all(fill["sleeve"] == "short" for fill in result["fills"])
    with pytest.raises(RuntimeError, match="loss gate"):
        app.resume()


def test_daily_target_is_net_of_exit_costs_and_latches_across_restart(tmp_path):
    app, now = application(tmp_path)
    cycle(app, now)
    result = cycle(app, now, minutes=1, short="11.60")
    book = result["status"]["sleeves"]["short"]
    assert book["profit_stop"]
    assert D(book["net_realized_pnl_krw"]) >= 4000
    assert not book["positions"]
    app = TradingApplication(Settings(), db_path=tmp_path / "us.db", clock=lambda: now[0])
    app.resume()  # May clear a manual halt but must not clear the target or baseline.
    result = cycle(app, now, minutes=2)
    assert not buys(result, "short")
    assert result["status"]["sleeves"]["short"]["profit_stop"]


def test_unsettled_sale_proceeds_unavailable_until_supplied_settlement(tmp_path):
    app, now = application(tmp_path)
    cycle(app, now)
    cash_before = D(app.ledger.read()["sleeves"]["short"]["cash"])
    cycle(app, now, minutes=1, short="10.80", transform=lambda f: replace(f, settlement_at_utc=START.replace(day=15, hour=13)))
    book = app.ledger.read()["sleeves"]["short"]
    assert D(book["cash"]) == cash_before
    proceeds = D(book["pending"][0]["amount"])
    now[0] = START + timedelta(days=1)
    frame = demo_frame(now[0])
    frame = replace(frame, quotes=tuple(replace(q, tradable=False) for q in frame.quotes))
    app.process_frame(frame)
    after = app.ledger.read()["sleeves"]["short"]
    assert not after["pending"]
    assert D(after["cash"]) == cash_before + proceeds
    assert D(after["cash"]) > cash_before


def test_duplicate_frame_atomic_under_concurrent_workers(tmp_path):
    app, _ = application(tmp_path)
    second = TradingApplication(Settings(), db_path=app.ledger.path, clock=lambda: START)
    frame = demo_frame()
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(lambda engine: engine.process_frame(frame), (app, second)))
    assert sum(result["processed"] for result in outcomes) == 1
    assert sum(event["kind"] == "CYCLE" for event in app.ledger.events()) == 1
    validate_accounting(app.ledger.read(), app.policy)


def test_failed_cycle_rolls_back_cash_positions_and_audit(tmp_path, monkeypatch):
    app, _ = application(tmp_path)
    before = app.ledger.read()
    real_record = app.ledger.record
    def fail_record(db, key, kind, payload):
        if kind == "CYCLE":
            raise RuntimeError("simulated process failure")
        real_record(db, key, kind, payload)
    monkeypatch.setattr(app.ledger, "record", fail_record)
    with pytest.raises(RuntimeError, match="process failure"):
        app.process_frame(demo_frame())
    assert app.ledger.read() == before
    assert len(app.ledger.events()) == 1
    monkeypatch.setattr(app.ledger, "record", real_record)
    assert app.process_frame(demo_frame())["processed"]


@pytest.mark.parametrize("change,reason", [
    (lambda f: replace(f, as_of_utc=START - timedelta(minutes=2)), "stale_or_future_frame"),
    (lambda f: replace(f, as_of_utc=START + timedelta(seconds=1)), "stale_or_future_frame"),
    (lambda f: replace(f, fx_as_of_utc=START - timedelta(minutes=6)), "stale_or_future_fx"),
    (lambda f: replace(f, quotes=tuple(replace(q, as_of_utc=START + timedelta(seconds=1)) for q in f.quotes)), "stale_or_future_quote"),
])
def test_invalid_market_timing_never_changes_capital(tmp_path, change, reason):
    app, _ = application(tmp_path)
    before = app.ledger.read()
    result = app.process_frame(change(demo_frame()))
    assert result["reason"] == reason
    assert app.ledger.read() == before


def test_missing_held_quote_and_backward_timestamp_fail_closed(tmp_path):
    app, now = application(tmp_path)
    cycle(app, now)
    result = cycle(app, now, minutes=1, transform=lambda f: replace(f, quotes=(f.quotes[0],)))
    assert result["reason"] == "missing_held_position_quote"
    result = cycle(app, now, short="10.47")
    assert result["reason"] == "non_increasing_frame_time"


def test_no_live_mode_even_if_legacy_live_guards_enabled(tmp_path):
    with pytest.raises(RuntimeError, match="PAPER execution only"):
        TradingApplication(Settings(mode="LIVE", live_confirm="YES", enable_live_trading=True), db_path=tmp_path / "us.db")


def test_partial_exit_remains_pending_and_retries_on_next_fresh_frame(tmp_path):
    app, now = application(tmp_path)
    cycle(app, now)
    result = cycle(app, now, minutes=1, short="9.60", transform=lambda f:
        replace(f, quotes=tuple(replace(q, bid_size=D(1)) if q.symbol == "SIMS" else q for q in f.quotes)))
    short_sale = next(fill for fill in result["fills"] if fill["sleeve"] == "short")
    assert short_sale["partial"]
    assert D(app.ledger.read()["sleeves"]["short"]["positions"]["SIMS"]["qty"]) == 2
    result = cycle(app, now, minutes=2, short="9.60")
    assert not result["status"]["sleeves"]["short"]["positions"]
    assert not buys(result, "short")
    validate_accounting(app.ledger.read(), app.policy)


def test_partial_profit_exit_does_not_vanish_after_price_reverses(tmp_path):
    app, now = application(tmp_path)
    cycle(app, now)
    first = cycle(app, now, minutes=1, short="10.80", transform=lambda f:
        replace(f, quotes=tuple(replace(q, bid_size=D(1)) if q.symbol == "SIMS" else q for q in f.quotes)))
    assert any(fill["reason"] == "take_profit" and fill["partial"] for fill in first["fills"])
    second = cycle(app, now, minutes=2, short="10.50")
    assert any(fill["reason"] == "take_profit" for fill in second["fills"])
    assert not second["status"]["sleeves"]["short"]["positions"]


def test_same_symbol_two_sleeves_share_visible_depth_without_mixing_books(tmp_path):
    app, _ = application(tmp_path)
    frame = demo_frame()
    # Build a single liquid candidate eligible for both strategies, but only 4
    # shares displayed. Both books must not each consume the same 4 shares.
    short, long = frame.quotes
    scale = float(short.mid / long.mid)
    daily = tuple(replace(b, open=b.open * scale, high=b.high * scale,
                          low=b.low * scale, close=b.close * scale) for b in long.daily_bars)
    quote = replace(short, daily_bars=daily, ask_size=D(4))
    result = app.process_frame(replace(frame, quotes=(quote,)))
    assert sum(D(fill["qty"]) for fill in buys(result)) == 4
    assert all(fill["client_order_id"].startswith("us-dual:") for fill in result["fills"])
    validate_accounting(app.ledger.read(), app.policy)


def test_manual_halt_sells_only_when_session_and_liquidity_allow(tmp_path):
    app, now = application(tmp_path)
    cycle(app, now)
    app.halt()
    assert app.status()["global_halt"] == "manual_halt"
    blocked = cycle(app, now, minutes=1, transform=lambda f: replace(f, quotes=tuple(replace(q, tradable=False) for q in f.quotes)))
    assert not blocked["fills"]
    sold = cycle(app, now, minutes=2)
    assert {fill["side"] for fill in sold["fills"]} == {"SELL"}
    assert all(not b["positions"] for b in app.ledger.read()["sleeves"].values())


def test_drawdown_latch_persists_over_day_roll_and_cannot_be_resumed_away(tmp_path):
    app, now = application(tmp_path)
    cycle(app, now)
    cycle(app, now, minutes=1, short="5", long="5")
    assert app.status()["global_halt"] == "total_drawdown"
    now[0] = START + timedelta(days=1)
    app.process_frame(demo_frame(now[0]))
    assert app.status()["global_halt"] == "total_drawdown"
    with pytest.raises(RuntimeError, match="drawdown"):
        app.resume()


def test_kst_daily_reset_preserves_overnight_gap_and_long_capital(tmp_path):
    app, now = application(tmp_path)
    cycle(app, now)
    previous = app.status()
    result = cycle(app, now, minutes=31, short="9.50")
    short = result["status"]["sleeves"]["short"]
    assert short["trading_date"] == "2026-09-15"
    assert short["baseline_equity_krw"] == previous["sleeves"]["short"]["equity_krw"]
    assert short["halt"]
    assert result["status"]["sleeves"]["long"]["baseline_equity_krw"] == previous["sleeves"]["long"]["equity_krw"]


def test_session_close_flattens_intraday_and_preserves_long_holdings(tmp_path):
    app, now = application(tmp_path)
    cycle(app, now)
    result = cycle(app, now, minutes=326)
    assert not result["status"]["sleeves"]["short"]["positions"]
    assert result["status"]["sleeves"]["long"]["positions"]
    assert any(fill["reason"] == "session_flatten" for fill in result["fills"])


@pytest.mark.parametrize("transform", [
    lambda q: replace(q, intelligence=None),
    lambda q: replace(q, intelligence=replace(q.intelligence, macro_risk_off=True)),
    lambda q: replace(q, intelligence=replace(q.intelligence, material_risk=True)),
    lambda q: replace(q, daily_dollar_volume=D(10)),
    lambda q: replace(q, ask=q.ask * D("1.02")),
])
def test_intelligence_and_liquidity_gates_block_new_entries(tmp_path, transform):
    app, now = application(tmp_path)
    result = cycle(app, now, transform=lambda f: replace(f, quotes=tuple(transform(q) for q in f.quotes)))
    assert not buys(result)


def test_missing_trained_forecast_never_falls_back_to_rule_when_model_selected(tmp_path):
    class MissingModel:
        def forecast(self, quote, feature_fingerprint):
            return None
    app, now = application(tmp_path)
    app.forecaster = MissingModel()
    result = cycle(app, now)
    assert not buys(result, "short")
    assert any(d["reason"] == "forecast_missing_or_lineage_mismatch" for d in result["decisions"])


@pytest.mark.parametrize("probability,expected_buy", [(0.7, True), (0.4, False)])
def test_optional_forecast_uses_existing_cost_aware_ev_pipeline(tmp_path, probability, expected_buy):
    from aipro.intelligence.paper_strategy_validation import ForecastEvidence
    class FixedTestForecast:
        def forecast(self, quote, feature_fingerprint):
            return ForecastEvidence(probability, 0.04, 0.03, 0.1, "TEST_ONLY_FORECAST", feature_fingerprint,
                                    probability_calibrated=True)
    app, now = application(tmp_path)
    app.forecaster = FixedTestForecast()
    result = cycle(app, now)
    assert bool(buys(result, "short")) is expected_buy
    assert any(d["model_id"] == "TEST_ONLY_FORECAST" for d in result["decisions"])


def test_unaffordable_whole_share_is_skipped_and_fractional_is_explicit(tmp_path):
    app, now = application(tmp_path)
    frame = demo_frame()
    def expensive(q):
        if q.symbol != "SIML":
            return replace(q, tradable=False)
        return replace(q, bid=q.bid * 100, ask=q.ask * 100, fractionable=True,
            daily_bars=tuple(replace(b, open=b.open * 100, high=b.high * 100, low=b.low * 100, close=b.close * 100) for b in q.daily_bars))
    frame = replace(frame, quotes=tuple(expensive(q) for q in frame.quotes))
    assert not buys(app.process_frame(frame))
    fractional = TradingApplication(Settings(), db_path=tmp_path / "fractional.db", clock=lambda: START,
        policy=PortfolioPolicy(allow_fractional=True))
    result = fractional.process_frame(frame)
    assert D(buys(result)[0]["qty"]) < 1


def test_audit_is_append_only_and_state_corruption_rejected(tmp_path):
    app, _ = application(tmp_path)
    with connect(app.ledger.path) as db:
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            db.execute("DELETE FROM us_dual_events")
        db.execute("UPDATE us_dual_state SET payload='{}'")
    with pytest.raises(RuntimeError, match="corrupt"):
        app.status()


def test_policy_change_requires_migration_not_silent_budget_reset(tmp_path):
    app, _ = application(tmp_path)
    with pytest.raises(RuntimeError, match="migration"):
        PortfolioLedger(app.ledger.path, PortfolioPolicy(short_daily_loss=D("0.02")))


def test_market_frame_json_roundtrip_and_future_bar_rejection(tmp_path):
    frame = demo_frame()
    path = tmp_path / "input.json"
    path.write_text(json.dumps(frame.to_dict()), encoding="utf-8")
    assert FileMarketData(path).frame().fingerprint == frame.fingerprint
    q = frame.quotes[0]
    with pytest.raises(ValueError, match="observable"):
        replace(q, intraday_bars=(replace(q.intraday_bars[-1], timestamp_utc=(START + timedelta(minutes=1)).isoformat()),))


def test_synthetic_and_real_inputs_cannot_share_ledger(tmp_path):
    app, now = application(tmp_path)
    cycle(app, now)
    result = cycle(app, now, minutes=1, transform=lambda f: replace(f, synthetic=False))
    assert result["reason"] == "synthetic_and_market_data_cannot_share_ledger"


def test_replay_is_deterministic_and_never_creates_elapsed_paper_evidence(tmp_path):
    frames = demo_frames()
    first, second = replay(frames), replay(frames)
    assert first == second
    assert first["fills"] and not first["blocked_frames"]
    assert first["synthetic"]
    assert not first["live_ready"]
    assert not first["qualifies_as_elapsed_paper_evidence"]
    path = tmp_path / "data.jsonl"
    path.write_text("\n".join(json.dumps(f.to_dict()) for f in frames), encoding="utf-8")
    assert replay(load_jsonl(path)) == first
    with pytest.raises(ValueError, match="chronological"):
        replay(reversed(frames))


def test_canonical_entrypoint_constructs_isolated_us_application(tmp_path, monkeypatch):
    import main
    monkeypatch.setenv("AIPRO_RUNTIME", "US_DUAL")
    monkeypatch.setenv("AIPRO_MODE", "PAPER")
    monkeypatch.setenv("AIPRO_INITIAL_CASH_KRW", "1000000")
    monkeypatch.setenv("AIPRO_US_DUAL_DB_PATH", str(tmp_path / "us.db"))
    monkeypatch.setenv("AIPRO_LOG_DIR", str(tmp_path / "logs"))
    app = main.build_application()
    assert isinstance(app, TradingApplication)
    assert app.run_once()["reason"] == "configure_AIPRO_US_FRAME_PATH"
    assert not hasattr(app, "broker")  # No crypto broker or network order adapter.


def test_authenticated_telegram_controls_keep_domains_and_targets_separate(tmp_path):
    app, now = application(tmp_path)
    router = TelegramCommandRouter(app, frozenset({123}))
    assert router.approval is None
    assert router.handle(999, "/halt") == "권한이 없습니다."
    assert not app.status()["global_halt"]
    assert "미국 주식" in router.handle(123, "/status")
    assert "적용되지" in router.handle(123, "/ai_upbit_go")
    cycle(app, now)
    assert "중단" in router.handle(123, "/halt")
    assert app.status()["global_halt"]
    baseline = app.status()["sleeves"]["short"]["baseline_equity_krw"]
    assert "해제" in router.handle(123, "/go")
    assert app.status()["sleeves"]["short"]["baseline_equity_krw"] == baseline


@pytest.mark.parametrize("kwargs", [{"runtime": "OTHER"}, {"paper_interval_seconds": 61},
    {"runtime": "CRYPTO", "paper_interval_seconds": 10}])
def test_bad_runtime_and_loop_configuration_rejected(kwargs):
    with pytest.raises(ValueError):
        Settings(**kwargs).validate()
