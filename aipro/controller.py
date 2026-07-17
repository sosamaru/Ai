from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class AppMode(str, Enum):
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    HALTED = "HALTED"


@dataclass(slots=True)
class Controller:
    mode: AppMode = AppMode.RUNNING

    def pause(self) -> None:
        if self.mode is not AppMode.HALTED:
            self.mode = AppMode.PAUSED

    def resume(self) -> None:
        if self.mode is not AppMode.HALTED:
            self.mode = AppMode.RUNNING

    def halt(self) -> None:
        self.mode = AppMode.HALTED

    def go(self) -> None:
        self.mode = AppMode.RUNNING

    @property
    def can_trade(self) -> bool:
        return self.mode is AppMode.RUNNING
