from __future__ import annotations

import csv
import hashlib
import io
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from aipro.backtest import BacktestBar

REQUIRED_COLUMNS = (
    "timestamp",
    "symbol",
    "price",
    "change_1h_pct",
    "volatility_pct",
)


@dataclass(frozen=True, slots=True)
class BacktestDataset:
    bars: tuple[BacktestBar, ...]
    row_count: int
    symbols: tuple[str, ...]
    start_timestamp: datetime
    end_timestamp: datetime
    sha256: str


class BacktestCsvError(ValueError):
    pass


def load_backtest_csv(path: str | Path) -> BacktestDataset:
    csv_path = Path(path)
    try:
        raw = csv_path.read_bytes()
    except OSError as exc:
        raise BacktestCsvError(f"unable to read CSV: {csv_path}") from exc
    return parse_backtest_csv(raw.decode("utf-8-sig"), source_name=str(csv_path))


def parse_backtest_csv(text: str, *, source_name: str = "<memory>") -> BacktestDataset:
    if not text.strip():
        raise BacktestCsvError(f"CSV is empty: {source_name}")

    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None:
        raise BacktestCsvError(f"CSV header is missing: {source_name}")

    fieldnames = tuple(name.strip() for name in reader.fieldnames if name is not None)
    missing = [name for name in REQUIRED_COLUMNS if name not in fieldnames]
    extra = [name for name in fieldnames if name not in REQUIRED_COLUMNS]
    if missing or extra:
        raise BacktestCsvError(
            f"invalid CSV schema: missing={missing or []}, extra={extra or []}"
        )

    bars: list[BacktestBar] = []
    seen: set[tuple[datetime, str]] = set()

    for row_number, row in enumerate(reader, start=2):
        try:
            timestamp = _parse_timestamp(row["timestamp"])
            symbol = row["symbol"].strip().upper()
            price = _parse_finite_float(row["price"], "price")
            change_1h_pct = _parse_finite_float(row["change_1h_pct"], "change_1h_pct")
            volatility_pct = _parse_finite_float(row["volatility_pct"], "volatility_pct")
        except (KeyError, TypeError, ValueError) as exc:
            raise BacktestCsvError(f"invalid row {row_number}: {exc}") from exc

        if volatility_pct < 0:
            raise BacktestCsvError(
                f"invalid row {row_number}: volatility_pct must be non-negative"
            )

        key = (timestamp, symbol)
        if key in seen:
            raise BacktestCsvError(
                f"duplicate row {row_number}: timestamp={timestamp.isoformat()} symbol={symbol}"
            )
        seen.add(key)

        try:
            bars.append(
                BacktestBar(
                    timestamp=timestamp,
                    symbol=symbol,
                    price=price,
                    change_1h_pct=change_1h_pct,
                    volatility_pct=volatility_pct,
                )
            )
        except ValueError as exc:
            raise BacktestCsvError(f"invalid row {row_number}: {exc}") from exc

    if not bars:
        raise BacktestCsvError(f"CSV contains no data rows: {source_name}")

    ordered = tuple(sorted(bars, key=lambda bar: (bar.timestamp, bar.symbol)))
    canonical = "\n".join(
        ",".join(
            (
                bar.timestamp.isoformat(),
                bar.symbol,
                format(bar.price, ".17g"),
                format(bar.change_1h_pct, ".17g"),
                format(bar.volatility_pct, ".17g"),
            )
        )
        for bar in ordered
    ).encode("utf-8")

    return BacktestDataset(
        bars=ordered,
        row_count=len(ordered),
        symbols=tuple(sorted({bar.symbol for bar in ordered})),
        start_timestamp=ordered[0].timestamp,
        end_timestamp=ordered[-1].timestamp,
        sha256=hashlib.sha256(canonical).hexdigest(),
    )


def _parse_timestamp(raw: str | None) -> datetime:
    if raw is None or not raw.strip():
        raise ValueError("timestamp is required")
    value = raw.strip()
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError("timestamp must include a timezone offset")
    return parsed


def _parse_finite_float(raw: str | None, name: str) -> float:
    if raw is None or not raw.strip():
        raise ValueError(f"{name} is required")
    value = float(raw)
    if value != value or value in (float("inf"), float("-inf")):
        raise ValueError(f"{name} must be finite")
    return value


__all__ = [
    "BacktestCsvError",
    "BacktestDataset",
    "REQUIRED_COLUMNS",
    "load_backtest_csv",
    "parse_backtest_csv",
]
