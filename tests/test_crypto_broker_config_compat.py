from aipro.broker import PAPER_ACCOUNT_STATE_KEY as LEGACY_ACCOUNT_KEY
from aipro.broker import PaperBroker as LegacyPaperBroker
from aipro.config import Settings as LegacySettings
from aipro.crypto import CryptoSettings, PAPER_ACCOUNT_STATE_KEY, PaperBroker, Settings


def test_crypto_broker_boundary_preserves_legacy_class_and_state_key() -> None:
    assert PaperBroker is LegacyPaperBroker
    assert PAPER_ACCOUNT_STATE_KEY == LEGACY_ACCOUNT_KEY == "paper_account"


def test_crypto_settings_boundary_preserves_environment_contract() -> None:
    assert Settings is LegacySettings
    assert CryptoSettings is LegacySettings
    assert CryptoSettings().mode == "PAPER"
