from __future__ import annotations

import re
from datetime import date, datetime, timedelta

import dateparser


ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
ISO_DATETIME_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2})?(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})?$")
TIME_RE = re.compile(r"^([01]?\d|2[0-3]):[0-5]\d$")


def parse_date_time(value: str | None) -> tuple[str, str]:
    if not value:
        return "", ""
    text = value.strip()
    if ISO_DATE_RE.match(text):
        parsed = datetime.strptime(text, "%Y-%m-%d")
        return parsed.date().isoformat(), ""
    if ISO_DATETIME_RE.match(text):
        iso_text = text[:-1] + "+00:00" if text.endswith("Z") else text
        try:
            parsed_dt = datetime.fromisoformat(iso_text)
            return parsed_dt.date().isoformat(), parsed_dt.strftime("%H:%M")
        except ValueError:
            pass
    if TIME_RE.match(text):
        parsed_time = datetime.strptime(text, "%H:%M")
        return "", parsed_time.strftime("%H:%M")
    normalized = text
    normalized = re.sub(r"(?i)\b(?:hrs?|hs)\.?\b", "", normalized)
    normalized = re.sub(r"(?i)\ba\s+las\b", " ", normalized)
    normalized = re.sub(r"\s*-\s*", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    has_explicit_time = bool(
        re.search(
            r"(?i)\b([01]?\d|2[0-3])[:\.][0-5]\d\b|\b([1-9]|1[0-2])\s*(am|pm)\b",
            normalized,
        )
    )

    dt = dateparser.parse(
        normalized,
        languages=["es", "en"],
        settings={
            "RETURN_AS_TIMEZONE_AWARE": False,
            "PREFER_DAY_OF_MONTH": "first",
            "DATE_ORDER": "DMY",
        },
    )
    if not dt:
        return "", ""
    return dt.date().isoformat(), dt.strftime("%H:%M") if has_explicit_time else ""


def normalize_date(value: str | None) -> str:
    date_value, _ = parse_date_time(value)
    return date_value


def normalize_time(value: str | None) -> str:
    _, time_value = parse_date_time(value)
    return time_value


def monday_sunday_bounds(reference_date: date | None = None, upcoming: bool = True) -> tuple[date, date]:
    ref = reference_date or date.today()
    this_monday = ref - timedelta(days=ref.weekday())
    monday = this_monday + timedelta(days=7) if upcoming else this_monday
    sunday = monday + timedelta(days=6)
    return monday, sunday


def in_date_range(date_str: str, start: date, end: date) -> bool:
    if not date_str:
        return False
    try:
        parsed = datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        return False
    return start <= parsed <= end
