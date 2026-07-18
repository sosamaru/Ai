"""Backward-compatible crypto market imports.

New code should import from :mod:`aipro.crypto.market`.
"""

from aipro.crypto.market import DemoMarketData

__all__ = ["DemoMarketData"]
