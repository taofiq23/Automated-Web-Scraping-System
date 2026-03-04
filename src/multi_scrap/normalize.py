from __future__ import annotations

from multi_scrap.models import RawEvent, SourceConfig
from multi_scrap.utils.dates import normalize_date, normalize_time
from multi_scrap.utils.text import clean_text, normalize_musicians, sanitize_description


def normalize_event(event: RawEvent, source: SourceConfig) -> RawEvent:
    event.event_name = clean_text(event.event_name)
    event.date = normalize_date(event.date) if event.date else ""
    event.time = normalize_time(event.time) if event.time else ""
    event.venue = clean_text(event.venue) or source.venue_name
    event.ticket_price = clean_text(event.ticket_price)
    event.description = sanitize_description(event.description)
    event.musicians = normalize_musicians(event.musicians)
    event.event_link = clean_text(event.event_link)
    event.source_url = clean_text(event.source_url) or source.source_url
    event.source_id = source.source_id
    return event


def drop_invalid(events: list[RawEvent]) -> list[RawEvent]:
    return [
        event
        for event in events
        if event.event_name
        and event.date
        and event.venue
    ]
