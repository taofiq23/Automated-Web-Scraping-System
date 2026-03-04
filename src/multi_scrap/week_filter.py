from __future__ import annotations

from datetime import date

from multi_scrap.models import RawEvent
from multi_scrap.utils.dates import in_date_range


def filter_events_for_week(events: list[RawEvent], week_start: date, week_end: date) -> list[RawEvent]:
    return [event for event in events if in_date_range(event.date, week_start, week_end)]
