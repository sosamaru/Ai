from __future__ import annotations

import json
from typing import Protocol


class CommandTarget(Protocol):
    def pause(self) -> None: ...
    def resume(self) -> None: ...
    def halt(self) -> None: ...
    def go(self) -> None: ...
    def status(self) -> dict[str, object]: ...


class CommandProcessor:
    def __init__(self, target: CommandTarget) -> None:
        self.target = target

    def handle(self, raw_command: str) -> str:
        command = raw_command.strip().split(maxsplit=1)[0].lower()
        if command == "/status":
            return json.dumps(self.target.status(), ensure_ascii=False, sort_keys=True)
        if command == "/pause":
            self.target.pause()
            return "PAUSED"
        if command == "/resume":
            self.target.resume()
            return "RUNNING"
        if command == "/halt":
            self.target.halt()
            return "HALTED"
        if command == "/go":
            self.target.go()
            return "RUNNING"
        if command in {"/help", "/start"}:
            return "/status /pause /resume /halt /go"
        return "UNKNOWN_COMMAND"
