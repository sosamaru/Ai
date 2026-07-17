from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")


@dataclass(slots=True)
class DailySession:
    session_date: str

    @classmethod
    def current(cls, now: datetime | None = None) -> "DailySession":
        moment = now or datetime.now(tz=KST)
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=KST)
        return cls(moment.astimezone(KST).date().isoformat())

    def roll_if_needed(self, now: datetime | None = None) -> bool:
        latest = self.current(now).session_date
        if latest == self.session_date:
            return False
        self.session_date = latest
        return True
