"""US-stock-specific configuration, adapters, and strategies.

The domain is intentionally disabled until a broker, market-data adapter, tests,
and a paper-trading readiness gate are implemented.
"""

from aipro.us_stocks.domain import US_STOCK_DOMAIN, USStockCapitalPolicy

__all__ = ["US_STOCK_DOMAIN", "USStockCapitalPolicy"]
