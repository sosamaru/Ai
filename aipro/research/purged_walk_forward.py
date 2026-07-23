from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from typing import Iterable, Sequence


@dataclass(frozen=True)
class Observation:
    index: int
    label_start: int
    label_end: int
    domain: str


@dataclass(frozen=True)
class Fold:
    train_indices: tuple[int, ...]
    test_indices: tuple[int, ...]
    purged_indices: tuple[int, ...]
    embargoed_indices: tuple[int, ...]
    domain: str
    fingerprint: str


@dataclass(frozen=True)
class WalkForwardConfig:
    min_train_size: int
    test_size: int
    step_size: int
    embargo_size: int = 0
    max_train_size: int | None = None
    expanding: bool = True

    def validate(self) -> None:
        for name in ("min_train_size", "test_size", "step_size"):
            if getattr(self, name) <= 0:
                raise ValueError(f"{name} must be positive")
        if self.embargo_size < 0:
            raise ValueError("embargo_size must be non-negative")
        if self.max_train_size is not None and self.max_train_size < self.min_train_size:
            raise ValueError("max_train_size cannot be smaller than min_train_size")


class PurgedWalkForwardSplitter:
    """Deterministic PAPER-only splitter for overlapping financial labels."""

    def __init__(self, config: WalkForwardConfig) -> None:
        config.validate()
        self.config = config

    def split(self, observations: Sequence[Observation]) -> tuple[Fold, ...]:
        if not observations:
            raise ValueError("observations cannot be empty")
        ordered = tuple(sorted(observations, key=lambda item: item.index))
        if len({item.index for item in ordered}) != len(ordered):
            raise ValueError("observation indices must be unique")
        domains = {item.domain for item in ordered}
        if len(domains) != 1:
            raise ValueError("crypto and US-stock observations must not share a splitter")
        domain = next(iter(domains))
        if any(item.label_end < item.label_start for item in ordered):
            raise ValueError("label_end cannot precede label_start")

        folds: list[Fold] = []
        test_start = self.config.min_train_size
        while test_start + self.config.test_size <= len(ordered):
            test_stop = test_start + self.config.test_size
            test = ordered[test_start:test_stop]
            test_label_start = min(item.label_start for item in test)
            test_label_end = max(item.label_end for item in test)

            raw_train_start = 0 if self.config.expanding else max(0, test_start - self.config.min_train_size)
            if self.config.max_train_size is not None:
                raw_train_start = max(raw_train_start, test_start - self.config.max_train_size)
            raw_train = ordered[raw_train_start:test_start]

            train: list[int] = []
            purged: list[int] = []
            for item in raw_train:
                overlaps = item.label_start <= test_label_end and item.label_end >= test_label_start
                if overlaps:
                    purged.append(item.index)
                else:
                    train.append(item.index)

            embargo_stop = min(len(ordered), test_stop + self.config.embargo_size)
            embargoed = tuple(item.index for item in ordered[test_stop:embargo_stop])
            if len(train) < self.config.min_train_size - len(purged):
                raise ValueError("purging leaves insufficient training evidence")

            payload = {
                "domain": domain,
                "train": train,
                "test": [item.index for item in test],
                "purged": purged,
                "embargoed": embargoed,
            }
            fingerprint = sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
            folds.append(
                Fold(
                    train_indices=tuple(train),
                    test_indices=tuple(item.index for item in test),
                    purged_indices=tuple(purged),
                    embargoed_indices=embargoed,
                    domain=domain,
                    fingerprint=fingerprint,
                )
            )
            test_start += self.config.step_size

        if not folds:
            raise ValueError("configuration produces no validation folds")
        return tuple(folds)


def assert_no_leakage(fold: Fold, observations: Iterable[Observation]) -> None:
    by_index = {item.index: item for item in observations}
    test = [by_index[index] for index in fold.test_indices]
    test_start = min(item.label_start for item in test)
    test_end = max(item.label_end for item in test)
    for index in fold.train_indices:
        item = by_index[index]
        if item.label_start <= test_end and item.label_end >= test_start:
            raise AssertionError(f"leakage detected at observation {index}")
