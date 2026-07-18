"""Crypto runtime configuration ownership boundary.

``Settings`` remains an alias during the compatibility phase so environment names,
validation, and callers keep their existing behavior.
"""

from aipro.config import Settings

CryptoSettings = Settings

__all__ = ["CryptoSettings", "Settings"]
