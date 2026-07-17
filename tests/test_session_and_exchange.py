from datetime import datetime
from zoneinfo import ZoneInfo

from aipro.broker import PaperBroker
from aipro.exchange import FakeExchange
from aipro.session import DailySession


def test_daily_session_rolls_at_kst_date_change():
    kst = ZoneInfo("Asia/Seoul")
    session = DailySession.current(datetime(2026, 7, 17, 23, 59, tzinfo=kst))
    assert session.session_date == "2026-07-17"
    assert session.roll_if_needed(datetime(2026, 7, 18, 0, 1, tzinfo=kst))
    assert session.session_date == "2026-07-18"
    assert not session.roll_if_needed(datetime(2026, 7, 18, 10, 0, tzinfo=kst))


def test_fake_exchange_contract_round_trip():
    exchange = FakeExchange(PaperBroker(100_000))
    buy = exchange.buy("KRW-BTC", 10_000, 20_000)
    assert buy.side == "BUY"
    assert exchange.equity({"KRW-BTC": 10_000}) > 99_000
    sell = exchange.sell_all("KRW-BTC", 11_000)
    assert sell is not None
    assert sell.side == "SELL"
    assert not exchange.broker.positions
