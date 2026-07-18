"""Backward-compatible crypto strategy imports.

New code should import from :mod:`aipro.crypto.strategy`.
"""

from aipro.crypto.strategy import MomentumStrategy

__all__ = ["MomentumStrategy"]
