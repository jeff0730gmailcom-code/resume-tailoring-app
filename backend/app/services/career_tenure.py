"""Career tenure from master-CV employment dates.

Years of experience in the tailored Professional Summary must come from
the earliest job start date through the latest job end date — never from
an AI guess like '8+ years'. Present/current roles use today's date.
Future-dated end months are capped at today so unworked time is not counted.
Overlapping jobs are not double-counted: this is a calendar span, not a sum.
"""
from __future__ import annotations

import re
from datetime import date
from typing import Any

_RANGE_SPLIT_RE = re.compile(r"\s*(?:[-–—]|to)\s*", re.IGNORECASE)
_PRESENT_RE = re.compile(r"^(present|current|now|ongoing)$", re.IGNORECASE)
_NUMERIC_DATE_RE = re.compile(r"^(0?[1-9]|1[0-2])/((?:19|20)\d{2})$")
_YEAR_ONLY_RE = re.compile(r"^((?:19|20)\d{2})$")
_NAMED_MONTH_RE = re.compile(
    r"^(Jan(?:uary)?|Feb(?:ruary|urary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|"
    r"Dec(?:ember)?)[a-z]*\.?\s+((?:19|20)\d{2})$",
    re.IGNORECASE,
)
_MONTH_NUM = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}
# Invented "8+ years" / "over 10 yrs" spans — replace the count only, keep
# any following "of experience" prose intact.
_YEARS_SPAN_RE = re.compile(
    r"(?i)(?:(?:over|more than|nearly|about|around|approximately)\s+)?"
    r"\d+\+?\s*(?:years?|yrs)"
)


def _month_start_today() -> date:
    today = date.today()
    return date(today.year, today.month, 1)


def _parse_month_year(token: str, *, end: bool) -> date | None:
    raw = (token or "").strip(" .")
    if not raw:
        return None
    if _PRESENT_RE.match(raw):
        return _month_start_today()
    numeric = _NUMERIC_DATE_RE.match(raw)
    if numeric:
        month, year = int(numeric.group(1)), int(numeric.group(2))
        return date(year, month, 1)
    named = _NAMED_MONTH_RE.match(raw)
    if named:
        month = _MONTH_NUM[named.group(1)[:3].lower()]
        year = int(named.group(2))
        return date(year, month, 1)
    year_only = _YEAR_ONLY_RE.match(raw)
    if year_only:
        year = int(year_only.group(1))
        return date(year, 12 if end else 1, 1)
    return None


def parse_job_date_range(dates: str) -> tuple[date, date] | None:
    """Return (start, end) month dates from a CV employment period string."""
    text = " ".join((dates or "").replace("\n", " ").split())
    if not text:
        return None
    parts = _RANGE_SPLIT_RE.split(text, maxsplit=1)
    if len(parts) != 2:
        return None
    start = _parse_month_year(parts[0], end=False)
    end = _parse_month_year(parts[1], end=True)
    if start is None or end is None:
        return None
    if end < start:
        start, end = end, start
    return start, end


def _career_span(experience: Any) -> tuple[date, date] | None:
    """Earliest start month through latest end month (end capped at today)."""
    starts: list[date] = []
    ends: list[date] = []
    for entry in experience or []:
        parsed = parse_job_date_range(getattr(entry, "dates", "") or "")
        if parsed is None:
            continue
        starts.append(parsed[0])
        ends.append(parsed[1])
    if not starts:
        return None
    start, end = min(starts), max(ends)
    today = _month_start_today()
    if end > today:
        end = today
    if end < start:
        return None
    return start, end


def _span_months(experience: Any) -> int | None:
    span = _career_span(experience)
    if span is None:
        return None
    start, end = span
    # Inclusive of the end month: "Jan 2020 – Dec 2023" is 4 years, not 3+.
    return (end.year - start.year) * 12 + (end.month - start.month) + 1


def career_span_years(experience: Any) -> int | None:
    """Whole years from the earliest start month to the latest end month."""
    months = _span_months(experience)
    if months is None:
        return None
    return months // 12


def career_tenure_phrase(experience: Any) -> str | None:
    """Display form for the summary, e.g. '12 years' or '12+ years'."""
    months = _span_months(experience)
    if months is None:
        return None
    years, leftover = divmod(months, 12)
    if years <= 0:
        return "under 1 year"
    if leftover:
        return f"{years}+ years"
    return f"{years} years"


def apply_career_years_to_summary(summary: str, experience: Any) -> str:
    """Replace an invented year count with the CV-derived career span."""
    phrase = career_tenure_phrase(experience)
    if not phrase:
        return summary or ""
    text = (summary or "").strip()
    if not text:
        return text
    if _YEARS_SPAN_RE.search(text):
        return _YEARS_SPAN_RE.sub(phrase, text, count=1)
    first, sep, rest = text.partition(". ")
    if re.search(r"(?i)\bwith\b", first):
        patched = re.sub(
            r"(?i)\bwith\b",
            f"with {phrase} of experience,",
            first,
            count=1,
        )
        return f"{patched}. {rest}".strip() if rest else patched
    injection = f"with {phrase} of experience"
    if re.search(r"(?i)\b(?:engineer|developer|lead|manager|architect|analyst)\b", first):
        first = re.sub(
            r"(?i)(\b(?:engineer|developer|lead|manager|architect|analyst)\b)",
            rf"\1 {injection}",
            first,
            count=1,
        )
        return f"{first}. {rest}".strip() if rest else first
    if sep:
        return f"{first.rstrip('.')} {injection}. {rest}".strip()
    return f"{text.rstrip('.')} {injection}."
