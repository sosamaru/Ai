from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class PaperEvidenceSnapshot:
    captured_at_utc: str
    account: dict[str, Any]
    orders: tuple[dict[str, Any], ...]

    @property
    def fingerprint(self) -> str:
        payload = json.dumps(asdict(self), sort_keys=True, separators=(",", ":"), default=str)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class PaperEvidenceStore:
    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        with sqlite3.connect(self.path) as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS paper_evidence (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    captured_at_utc TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    fingerprint TEXT NOT NULL UNIQUE
                );
                CREATE TRIGGER IF NOT EXISTS paper_evidence_no_update
                BEFORE UPDATE ON paper_evidence BEGIN SELECT RAISE(ABORT, 'append only'); END;
                CREATE TRIGGER IF NOT EXISTS paper_evidence_no_delete
                BEFORE DELETE ON paper_evidence BEGIN SELECT RAISE(ABORT, 'append only'); END;
                """
            )

    def append(self, snapshot: PaperEvidenceSnapshot) -> str:
        parsed = datetime.fromisoformat(snapshot.captured_at_utc)
        if parsed.tzinfo is None:
            raise ValueError("captured_at_utc must be timezone-aware")
        payload = json.dumps(asdict(snapshot), sort_keys=True, separators=(",", ":"), default=str)
        with sqlite3.connect(self.path) as db:
            db.execute(
                "INSERT INTO paper_evidence(captured_at_utc,payload_json,fingerprint) VALUES(?,?,?)",
                (snapshot.captured_at_utc, payload, snapshot.fingerprint),
            )
        return snapshot.fingerprint


class AlpacaPaperEvidenceCollector:
    def __init__(self, client: Any, store: PaperEvidenceStore) -> None:
        self.client = client
        self.store = store

    def collect(self, *, captured_at_utc: datetime) -> PaperEvidenceSnapshot:
        if captured_at_utc.tzinfo is None:
            raise ValueError("captured_at_utc must be timezone-aware")
        snapshot = PaperEvidenceSnapshot(
            captured_at_utc=captured_at_utc.isoformat(),
            account=self.client.get_account(),
            orders=self.client.list_orders(status="all", limit=500),
        )
        self.store.append(snapshot)
        return snapshot


__all__ = ["AlpacaPaperEvidenceCollector", "PaperEvidenceSnapshot", "PaperEvidenceStore"]
