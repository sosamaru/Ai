"""Failure injections only; no network, real funds, or market performance claims."""
from copy import deepcopy
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from io import BytesIO
import json
from urllib.error import HTTPError
from urllib.request import Request

import pytest

from aipro.config import Settings
from aipro.core.execution_gate import LiveExecutionInputs, evaluate_live_execution
from aipro.core.secure_http import NoCredentialRedirect, read_bounded
from aipro.crypto.application import TradingApplication
from aipro.crypto.broker import PAPER_ACCOUNT_STATE_KEY, PaperBroker
from aipro.crypto.market_health import MarketDataHealthError
from aipro.models import MarketSnapshot
from aipro.risk import RiskManager
from aipro.storage import Storage
from aipro.us_stocks.model_artifact import validate_artifact
from aipro.us_stocks.model_dataset import fingerprint
from aipro.us_stocks.model_training import train_model
from test_us_model_pipeline import synthetic_dataset


def settings(tmp_path):
    return Settings(db_path=tmp_path / "crypto.db", log_dir=tmp_path / "logs")


@pytest.mark.parametrize("raw", ['{broken', 'null', '{"cash_krw":NaN}',
    '{"cash_krw":-1,"positions":{},"orders":{}}'])
def test_corrupt_restart_preserves_exact_source_and_never_refunds(tmp_path, raw):
    store = Storage(tmp_path / "state.db")
    store.set_state(PAPER_ACCOUNT_STATE_KEY, raw)
    with pytest.raises(RuntimeError, match="corrupt"):
        PaperBroker.restore(1_000_000, store)
    assert store.get_state(PAPER_ACCOUNT_STATE_KEY) == raw


def test_missing_account_with_history_cannot_create_new_funding(tmp_path):
    store = Storage(tmp_path / "state.db")
    broker = PaperBroker.restore(1_000_000, store)
    broker.submit_buy("one", "KRW-BTC", 100, 5000)
    with store._connect() as db:
        db.execute("DELETE FROM application_state WHERE key='paper_account'")
    with pytest.raises(RuntimeError, match="refusing to refund"):
        PaperBroker.restore(1_000_000, store)


def test_stale_process_cannot_overwrite_account_or_continue_after_save_failure(tmp_path):
    store = Storage(tmp_path / "state.db")
    first = PaperBroker.restore(100000, store)
    stale = PaperBroker.restore(100000, store)
    first.submit_buy("first", "KRW-BTC", 100, 5000)
    expected = store.get_state(PAPER_ACCOUNT_STATE_KEY)
    with pytest.raises(RuntimeError, match="changed"):
        stale.submit_buy("second", "KRW-BTC", 100, 5000)
    assert store.get_state(PAPER_ACCOUNT_STATE_KEY) == expected
    with pytest.raises(RuntimeError, match="persistence failed"):
        stale.submit_sell_all("third", "KRW-BTC", 100)
    with store._connect() as db:
        assert db.execute("SELECT COUNT(*) FROM events WHERE event_type='paper_order_filled'").fetchone()[0] == 1


def test_reconciliation_mismatch_blocks_both_cycle_and_resume(tmp_path):
    app = TradingApplication(settings(tmp_path))
    app.broker.cash_krw -= 1
    for operation in (app.run_once, app.resume):
        with pytest.raises(RuntimeError, match="reconciliation"):
            operation()
    assert app.broker.orders == {}
    assert app.storage.get_state("halted") == "1"


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -1])
def test_invalid_snapshot_never_reaches_strategy(tmp_path, value):
    app = TradingApplication(settings(tmp_path))
    class Source:
        def snapshots(self):
            return [MarketSnapshot("KRW-BTC", value, 5., 2.)]
    app.market = Source()
    with pytest.raises(MarketDataHealthError):
        app.run_once()
    assert app.broker.orders == {}


def test_missing_held_quote_blocks_entries_and_cannot_clear_halt(tmp_path):
    app = TradingApplication(settings(tmp_path))
    app.broker.submit_buy("seed", "KRW-MISSING", 100, 5000)
    before = len(app.broker.orders)
    app.risk.halt(); app._persist_halted(True)
    with pytest.raises(MarketDataHealthError, match="missing"):
        app.resume()
    assert app.risk.halted and len(app.broker.orders) == before


@pytest.mark.parametrize("invalid", ["false", "true", 1, 0, None])
def test_live_gate_requires_actual_booleans_in_every_flag(invalid):
    now = datetime.now(UTC)
    fields = {name: True for name in LiveExecutionInputs.__dataclass_fields__}
    fields.update(kill_switch_active=False, authorization_expires_at_utc=(now + timedelta(minutes=1)).isoformat())
    original = LiveExecutionInputs(**fields)
    assert evaluate_live_execution(original, now_utc=now).allowed
    for name in fields.keys() - {"authorization_expires_at_utc"}:
        assert not evaluate_live_execution(replace(original, **{name: invalid}), now_utc=now).allowed


def test_nan_loss_halts_instead_of_bypassing_comparison():
    risk = RiskManager(-10)
    assert risk.evaluate(float("nan")) and risk.halted


def test_order_cap_applies_to_new_crypto_intents(tmp_path):
    app = TradingApplication(replace(settings(tmp_path), max_order_krw=10000))
    app.run_once()
    assert all(order.amount_krw <= 10000 for order in app.broker.orders.values())


def test_credential_redirects_and_oversized_payloads_fail_closed():
    req = Request("https://paper-api.alpaca.markets/v2/account", headers={"APCA-API-KEY-ID": "TEST_ONLY"})
    with pytest.raises(HTTPError, match="redirect blocked"):
        NoCredentialRedirect().redirect_request(req, None, 302, "", {}, "https://foreign.invalid/")
    with pytest.raises(ValueError, match="byte limit"):
        read_bounded(BytesIO(b"12345"), 4)


def test_statistical_rejection_is_binding_even_with_positive_point_estimate():
    artifact = train_model(synthetic_dataset()).artifact
    body = deepcopy(artifact.payload)
    body["robustness"]["net_ev_lower_bound"] = -.001
    with pytest.raises(ValueError, match="qualification"):
        validate_artifact({"artifact": body, "fingerprint": fingerprint(body)})
    body["qualified"] = False
    body["blockers"].append("positive_EV_lower_bound_not_established")
    rejected = validate_artifact({"artifact": body, "fingerprint": fingerprint(body)})
    assert not rejected.payload["qualified"]


def test_uncalibrated_fit_remains_research_only():
    result = train_model(synthetic_dataset(), calibration_method=None)
    assert not result.artifact.payload["qualified"]
    assert "separate_probability_calibration_required" in result.report["blockers"]
