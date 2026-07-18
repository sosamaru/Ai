from __future__ import annotations

import json

from aipro.broker import PAPER_ACCOUNT_STATE_KEY as LEGACY_STATE_KEY
from aipro.broker import PaperBroker as LegacyPaperBroker
from aipro.crypto.broker import PAPER_ACCOUNT_STATE_KEY, PaperBroker


class MemoryStore:
    def __init__(self) -> None:
        self.state: dict[str, str] = {}
        self.events: list[tuple[str, str]] = []

    def get_state(self, key: str) -> str | None:
        return self.state.get(key)

    def set_state(self, key: str, value: str) -> None:
        self.state[key] = value

    def record(self, event_type: str, payload: str) -> None:
        self.events.append((event_type, payload))


def test_legacy_module_reexports_crypto_broker() -> None:
    assert LegacyPaperBroker is PaperBroker
    assert LEGACY_STATE_KEY == PAPER_ACCOUNT_STATE_KEY == "paper_account"


def test_restart_restores_account_and_preserves_idempotency() -> None:
    storage = MemoryStore()
    broker = PaperBroker.restore(1_000_000, storage)
    first = broker.submit_buy("cycle-1:buy:KRW-BTC", "KRW-BTC", 100_000, 200_000)

    restored = PaperBroker.restore(1_000_000, storage)
    duplicate = restored.submit_buy("cycle-1:buy:KRW-BTC", "KRW-BTC", 120_000, 200_000)

    assert duplicate == first
    assert restored.cash_krw == 800_000
    assert restored.positions["KRW-BTC"].quantity == 2.0
    persisted = json.loads(storage.state[PAPER_ACCOUNT_STATE_KEY])
    assert list(persisted["orders"]) == ["cycle-1:buy:KRW-BTC"]
