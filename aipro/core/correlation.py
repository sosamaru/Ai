"""Timestamp-aligned historical correlation; missing evidence is conservative."""
from statistics import fmean
import math

from aipro.core.evidence import finite, instant


def aligned_correlation(left, right, *, before, minimum=20):
    cutoff = instant(before)
    def returns(bars):
        values = {}
        previous = None
        for bar in bars:
            stamp = instant(bar.timestamp_utc)
            if stamp >= cutoff:
                raise ValueError("correlation cannot consume future or unfinished bars")
            close = finite(bar.close, "close", .000000001)
            if previous is not None:
                if stamp <= previous[0]:
                    raise ValueError("correlation history must increase")
                # Align both endpoints, so missing bars cannot pair a multi-bar
                # return with another asset's single-bar return.
                values[(previous[0], stamp)] = close / previous[1] - 1
            previous = stamp, close
        return values
    a, b = returns(left), returns(right)
    keys = sorted(a.keys() & b.keys())[-120:]
    if len(keys) < minimum:
        return 1.0, "insufficient_history_conservative_limit"
    x, y = [a[k] for k in keys], [b[k] for k in keys]
    mx, my = fmean(x), fmean(y)
    denominator = math.sqrt(sum((v - mx)**2 for v in x) * sum((v - my)**2 for v in y))
    if denominator <= 1e-20:
        return 1.0, "constant_history_conservative_limit"
    return max(-1, min(1, sum((u - mx) * (v - my) for u, v in zip(x, y)) / denominator)), "observed"
