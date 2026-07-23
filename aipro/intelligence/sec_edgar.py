from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Callable, Iterable
from urllib import request


class FilingEventType(StrEnum):
    EARNINGS = "earnings"
    ANNUAL_REPORT = "annual_report"
    QUARTERLY_REPORT = "quarterly_report"
    MATERIAL_EVENT = "material_event"
    INSIDER_TRANSACTION = "insider_transaction"
    BENEFICIAL_OWNERSHIP = "beneficial_ownership"
    SECURITIES_OFFERING = "securities_offering"
    PROXY = "proxy"
    OTHER = "other"


_FORM_EVENT_MAP: dict[str, FilingEventType] = {
    "10-K": FilingEventType.ANNUAL_REPORT,
    "10-K/A": FilingEventType.ANNUAL_REPORT,
    "10-Q": FilingEventType.QUARTERLY_REPORT,
    "10-Q/A": FilingEventType.QUARTERLY_REPORT,
    "8-K": FilingEventType.MATERIAL_EVENT,
    "8-K/A": FilingEventType.MATERIAL_EVENT,
    "4": FilingEventType.INSIDER_TRANSACTION,
    "3": FilingEventType.INSIDER_TRANSACTION,
    "5": FilingEventType.INSIDER_TRANSACTION,
    "SC 13D": FilingEventType.BENEFICIAL_OWNERSHIP,
    "SC 13D/A": FilingEventType.BENEFICIAL_OWNERSHIP,
    "SC 13G": FilingEventType.BENEFICIAL_OWNERSHIP,
    "SC 13G/A": FilingEventType.BENEFICIAL_OWNERSHIP,
    "S-1": FilingEventType.SECURITIES_OFFERING,
    "S-1/A": FilingEventType.SECURITIES_OFFERING,
    "S-3": FilingEventType.SECURITIES_OFFERING,
    "S-3/A": FilingEventType.SECURITIES_OFFERING,
    "424B2": FilingEventType.SECURITIES_OFFERING,
    "424B3": FilingEventType.SECURITIES_OFFERING,
    "424B5": FilingEventType.SECURITIES_OFFERING,
    "DEF 14A": FilingEventType.PROXY,
}


@dataclass(frozen=True, slots=True)
class SecFilingEvent:
    cik: str
    company_name: str
    accession_number: str
    form: str
    filed_at_utc: str
    report_date: str
    primary_document: str
    event_type: FilingEventType
    sec_url: str
    items: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        normalized_cik = self.cik.strip().lstrip("0") or "0"
        if not normalized_cik.isdigit():
            raise ValueError("CIK must contain digits only")
        if not self.company_name.strip() or not self.accession_number.strip() or not self.form.strip():
            raise ValueError("company, accession number, and form are required")
        filed = datetime.fromisoformat(self.filed_at_utc)
        if filed.tzinfo is None:
            raise ValueError("filed_at_utc must be timezone-aware")
        if not self.sec_url.startswith("https://www.sec.gov/Archives/"):
            raise ValueError("sec_url must target the SEC Archives domain")
        object.__setattr__(self, "cik", normalized_cik)
        object.__setattr__(self, "company_name", self.company_name.strip())
        object.__setattr__(self, "accession_number", self.accession_number.strip())
        object.__setattr__(self, "form", self.form.strip().upper())
        object.__setattr__(self, "items", tuple(sorted({item.strip() for item in self.items if item.strip()})))

    @property
    def fingerprint(self) -> str:
        payload = json.dumps(
            {
                **asdict(self),
                "event_type": self.event_type.value,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class FilingSnapshot:
    cik: str
    company_name: str
    as_of_utc: str
    events: tuple[SecFilingEvent, ...]
    newest_filing_at_utc: str | None
    eligible: bool
    ineligible_reason: str | None
    fingerprint: str


class SecEdgarClient:
    """Read-only SEC submissions client with explicit contact identification.

    The SEC asks automated clients to identify themselves. Callers must provide a
    descriptive user agent containing an application name and contact email.
    """

    BASE_URL = "https://data.sec.gov/submissions"

    def __init__(
        self,
        user_agent: str,
        *,
        timeout_seconds: float = 10.0,
        opener: Callable[..., Any] | None = None,
    ) -> None:
        normalized = user_agent.strip()
        if len(normalized) < 10 or "@" not in normalized:
            raise ValueError("SEC user agent must include an application name and contact email")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self.user_agent = normalized
        self.timeout_seconds = timeout_seconds
        self._opener = opener or request.urlopen

    @staticmethod
    def normalize_cik(cik: str | int) -> str:
        value = str(cik).strip()
        if not value.isdigit() or len(value) > 10:
            raise ValueError("CIK must be a numeric value up to 10 digits")
        return value.zfill(10)

    def fetch_submissions(self, cik: str | int) -> dict[str, Any]:
        padded = self.normalize_cik(cik)
        req = request.Request(
            f"{self.BASE_URL}/CIK{padded}.json",
            method="GET",
            headers={
                "User-Agent": self.user_agent,
                "Accept": "application/json",
                "Accept-Encoding": "gzip, deflate",
            },
        )
        with self._opener(req, timeout=self.timeout_seconds) as response:
            raw = response.read().decode("utf-8")
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise RuntimeError("SEC submissions response must be a JSON object")
        return payload


def classify_filing(form: str, items: Iterable[str] = ()) -> FilingEventType:
    normalized_form = form.strip().upper()
    if normalized_form in {"10-K", "10-K/A"}:
        return FilingEventType.EARNINGS if any(item.startswith("2.02") for item in items) else FilingEventType.ANNUAL_REPORT
    if normalized_form in {"10-Q", "10-Q/A"}:
        return FilingEventType.QUARTERLY_REPORT
    return _FORM_EVENT_MAP.get(normalized_form, FilingEventType.OTHER)


def _column(recent: dict[str, Any], name: str) -> list[Any]:
    value = recent.get(name, [])
    if not isinstance(value, list):
        raise RuntimeError(f"SEC recent filings column {name!r} must be a list")
    return value


def normalize_recent_filings(payload: dict[str, Any]) -> tuple[SecFilingEvent, ...]:
    cik = str(payload.get("cik", "")).strip()
    company_name = str(payload.get("name", "")).strip()
    filings = payload.get("filings")
    if not cik or not company_name or not isinstance(filings, dict):
        raise RuntimeError("SEC submissions payload is missing company metadata")
    recent = filings.get("recent")
    if not isinstance(recent, dict):
        raise RuntimeError("SEC submissions payload is missing recent filings")

    columns = {
        name: _column(recent, name)
        for name in ("accessionNumber", "filingDate", "reportDate", "form", "primaryDocument")
    }
    optional_items = _column(recent, "items") if "items" in recent else []
    lengths = {len(values) for values in columns.values()}
    if len(lengths) != 1:
        raise RuntimeError("SEC recent filing columns have inconsistent lengths")
    count = lengths.pop() if lengths else 0
    if optional_items and len(optional_items) != count:
        raise RuntimeError("SEC items column has an inconsistent length")

    normalized_cik = cik.lstrip("0") or "0"
    events: list[SecFilingEvent] = []
    for index in range(count):
        accession = str(columns["accessionNumber"][index]).strip()
        filing_date = str(columns["filingDate"][index]).strip()
        form = str(columns["form"][index]).strip().upper()
        primary_document = str(columns["primaryDocument"][index]).strip()
        if not accession or not filing_date or not form or not primary_document:
            continue
        try:
            filed_at = datetime.fromisoformat(f"{filing_date}T00:00:00+00:00")
        except ValueError:
            continue
        item_text = str(optional_items[index]).strip() if optional_items else ""
        items = tuple(part.strip() for part in item_text.split(",") if part.strip())
        compact_accession = accession.replace("-", "")
        sec_url = (
            f"https://www.sec.gov/Archives/edgar/data/{normalized_cik}/"
            f"{compact_accession}/{primary_document}"
        )
        events.append(
            SecFilingEvent(
                cik=normalized_cik,
                company_name=company_name,
                accession_number=accession,
                form=form,
                filed_at_utc=filed_at.isoformat(),
                report_date=str(columns["reportDate"][index]).strip(),
                primary_document=primary_document,
                event_type=classify_filing(form, items),
                sec_url=sec_url,
                items=items,
            )
        )
    return tuple(sorted(events, key=lambda item: item.filed_at_utc, reverse=True))


def build_filing_snapshot(
    payload: dict[str, Any],
    *,
    as_of_utc: datetime,
    maximum_age_days: int = 120,
    allowed_forms: Iterable[str] | None = None,
) -> FilingSnapshot:
    if as_of_utc.tzinfo is None:
        raise ValueError("as_of_utc must be timezone-aware")
    if maximum_age_days <= 0:
        raise ValueError("maximum_age_days must be positive")

    events = normalize_recent_filings(payload)
    allowed = {form.strip().upper() for form in allowed_forms or () if form.strip()}
    if allowed:
        events = tuple(event for event in events if event.form in allowed)

    newest = datetime.fromisoformat(events[0].filed_at_utc).astimezone(UTC) if events else None
    eligible = True
    reason: str | None = None
    if not events:
        eligible = False
        reason = "NO_RELEVANT_FILINGS"
    elif newest is None or (as_of_utc.astimezone(UTC) - newest).days > maximum_age_days:
        eligible = False
        reason = "STALE_FILINGS"

    canonical = {
        "cik": str(payload.get("cik", "")).strip().lstrip("0") or "0",
        "company_name": str(payload.get("name", "")).strip(),
        "as_of_utc": as_of_utc.astimezone(UTC).replace(microsecond=0).isoformat(),
        "event_fingerprints": [event.fingerprint for event in events],
        "maximum_age_days": maximum_age_days,
        "allowed_forms": sorted(allowed),
        "eligible": eligible,
        "ineligible_reason": reason,
    }
    fingerprint = hashlib.sha256(
        json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return FilingSnapshot(
        cik=canonical["cik"],
        company_name=canonical["company_name"],
        as_of_utc=canonical["as_of_utc"],
        events=events,
        newest_filing_at_utc=newest.isoformat() if newest else None,
        eligible=eligible,
        ineligible_reason=reason,
        fingerprint=fingerprint,
    )


__all__ = [
    "FilingEventType",
    "FilingSnapshot",
    "SecEdgarClient",
    "SecFilingEvent",
    "build_filing_snapshot",
    "classify_filing",
    "normalize_recent_filings",
]
