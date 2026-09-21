"""Train-independent sigmoid and isotonic probability calibration."""
from __future__ import annotations

from dataclasses import dataclass
from math import exp, log
from statistics import fmean

from aipro.core.evidence import finite, integer


def _pairs(probabilities, outcomes):
    p, y = tuple(probabilities), tuple(outcomes)
    if not p or len(p) != len(y) or len(p) > 20000:
        raise ValueError("aligned, bounded calibration observations required")
    for value in p:
        finite(value, "probability", 0, 1)
    if any(type(value) is not int or value not in (0, 1) for value in y):
        raise ValueError("binary outcomes required")
    return p, y


def reliability_report(probabilities, outcomes, bins=10):
    p, y = _pairs(probabilities, outcomes)
    integer(bins, "bins", 2, 50)
    buckets = []
    for i in range(bins):
        indices = [j for j, value in enumerate(p) if min(int(value * bins), bins - 1) == i]
        if indices:
            buckets.append({"lower": i / bins, "upper": (i + 1) / bins, "count": len(indices),
                            "mean_probability": fmean(p[j] for j in indices),
                            "observed_frequency": fmean(y[j] for j in indices)})
    return {"brier_score": fmean((a - b) ** 2 for a, b in zip(p, y)), "reliability_curve": buckets,
            "ece": sum(b["count"] * abs(b["mean_probability"] - b["observed_frequency"]) for b in buckets) / len(p),
            "observations": len(p), "note": "Brier combines reliability, resolution and uncertainty."}


def _sigmoid(value):
    return 1 / (1 + exp(-max(-40, min(40, value))))


@dataclass(frozen=True)
class Calibrator:
    method: str
    parameters: tuple

    def __post_init__(self):
        if self.method == "sigmoid":
            if len(self.parameters) != 2:
                raise ValueError("sigmoid requires slope and intercept")
            finite(self.parameters[0], "slope", 0, 100)
            finite(self.parameters[1], "intercept", -100, 100)
        elif self.method == "isotonic":
            if not self.parameters or len(self.parameters) > 20000:
                raise ValueError("invalid isotonic knots")
            previous = (-1, -1)
            for x, y in self.parameters:
                finite(x, "isotonic input", 0, 1)
                finite(y, "isotonic output", 0, 1)
                if x <= previous[0] or y < previous[1]:
                    raise ValueError("isotonic knots must be ordered and monotone")
                previous = (x, y)
        else:
            raise ValueError("unknown calibration method")

    def predict(self, probability):
        p = finite(probability, "probability", 0, 1)
        if self.method == "sigmoid":
            p = max(1e-6, min(1 - 1e-6, p))
            return _sigmoid(self.parameters[0] * log(p / (1 - p)) + self.parameters[1])
        for upper, value in self.parameters:
            if p <= upper:
                return value
        return self.parameters[-1][1]


def fit_calibrator(probabilities, outcomes, *, training_end: int, calibration_indices,
                   calibration_label_ends, test_start: int, method="sigmoid"):
    p, y = _pairs(probabilities, outcomes)
    indices, ends = tuple(calibration_indices), tuple(calibration_label_ends)
    if (len(indices) != len(p) or len(ends) != len(p) or not indices
            or any(type(v) is not int for v in (*indices, *ends, training_end, test_start))
            or any(b <= a for a, b in zip(indices, indices[1:]))
            or min(indices) <= training_end or max(ends) >= test_start
            or any(end < start for start, end in zip(indices, ends))):
        raise ValueError("calibration must follow resolved training labels and end before test predictions")
    minimum = 1000 if method == "isotonic" else 50
    if len(p) < minimum or set(y) != {0, 1}:
        raise ValueError("insufficient separate calibration data or missing class")
    if method == "sigmoid":
        x = [log(max(1e-6, min(1 - 1e-6, v)) / (1 - max(1e-6, min(1 - 1e-6, v)))) for v in p]
        slope, bias = 1.0, 0.0
        for _ in range(300):
            errors = [_sigmoid(slope * a + bias) - b for a, b in zip(x, y)]
            slope = max(0, min(100, slope - .05 * (fmean(e * a for e, a in zip(errors, x)) + .001 * slope)))
            bias = max(-100, min(100, bias - .05 * fmean(errors)))
        return Calibrator(method, (slope, bias))
    if method != "isotonic":
        raise ValueError("unknown calibration method")
    # Equal input values must be pooled before the pool-adjacent-violators pass.
    grouped = {}
    for a, b in zip(p, y):
        total, count = grouped.get(a, (0, 0))
        grouped[a] = (total + b, count + 1)
    blocks = []
    for upper, (total, count) in sorted(grouped.items()):
        blocks.append([upper, total, count])
        while len(blocks) >= 2 and blocks[-2][1] / blocks[-2][2] > blocks[-1][1] / blocks[-1][2]:
            right, left = blocks.pop(), blocks.pop()
            blocks.append([right[0], left[1] + right[1], left[2] + right[2]])
    return Calibrator(method, tuple((upper, total / count) for upper, total, count in blocks))
