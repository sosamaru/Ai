# PAPER Trading Readiness Gate

AiPro evaluates crypto and US-stock readiness separately. A PASS for one asset class never enables or approves another asset class.

## Default criteria

- At least 500 validated historical rows
- At least 20 closed trades
- Fee- and slippage-adjusted total return of at least 0%
- Maximum drawdown no worse than -15%
- Closed-trade win rate of at least 35%
- Average capital exposure no higher than 85%
- At least three distinct market regimes
- Out-of-sample validation completed

These values are minimum engineering gates, not claims of profitability. A PASS allows progression to supervised PAPER evaluation only. It does not authorize LIVE trading.

## Evidence

The readiness report records:

- asset class (`crypto` or `us_stocks`)
- PASS or FAIL status
- every individual check and its actual/required value
- all failure codes
- optional SHA-256 fingerprint of the validated dataset

The report can be exported as a dictionary or human-readable text.

## Limitations

- The current backtest uses fixed fees and slippage and does not model order-book depth.
- Regime classification and out-of-sample selection are supplied as evidence; automatic regime detection and walk-forward splitting remain future work.
- Open positions remain marked to their latest supplied price at the end of a backtest.
- Passing this gate does not bypass PAPER monitoring, account reconciliation, HALTED behavior, or explicit LIVE approval controls.
