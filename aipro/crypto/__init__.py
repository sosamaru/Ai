"""Crypto-specific configuration, adapters, and strategies.

Existing AiPro runtime behavior remains crypto-first while modules are migrated into
this package incrementally without breaking run.py -> telegram.py -> main.py.
"""

from aipro.crypto.domain import CRYPTO_DOMAIN

__all__ = ["CRYPTO_DOMAIN"]
