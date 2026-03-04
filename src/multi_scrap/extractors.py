from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from multi_scrap.models import RawEvent, SourceConfig
from multi_scrap.utils.dates import normalize_date, normalize_time, parse_date_time
from multi_scrap.utils.text import clean_text, extract_price, normalize_musicians


CARD_SELECTOR = (
    "[class*='event'], [class*='show'], [class*='agenda'], [class*='program'], "
    "article, .tribe-events-event, .event-card, .event-item"
)
DATE_HINT_RE = re.compile(
    r"(?i)\b(\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?|\d{1,2}\s+de\s+[a-záéíóú]+(?:\s+de\s+\d{4})?)\b"
)
TIME_HINT_RE = re.compile(r"(?i)\b([01]?\d|2[0-3])[:\.][0-5]\d\b")
GENERIC_EVENT_NAMES = {"principal", "home", "inicio", "events", "eventos"}
GENERIC_MUSICIAN_VALUES = {"organization", "person", "musicgroup", "performinggroup"}


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _is_event_type(type_value: Any) -> bool:
    values = _as_list(type_value)
    return any(str(item).strip().lower() == "event" for item in values)


def _flatten_json_ld(payload: Any) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    if isinstance(payload, list):
        for entry in payload:
            items.extend(_flatten_json_ld(entry))
        return items
    if not isinstance(payload, dict):
        return items
    if "@graph" in payload:
        items.extend(_flatten_json_ld(payload["@graph"]))
    items.append(payload)
    return items


def _build_event_from_schema(item: dict[str, Any], source: SourceConfig, page_url: str) -> RawEvent | None:
    if not _is_event_type(item.get("@type")):
        return None
    name = clean_text(item.get("name"))
    if not name or name.casefold() in GENERIC_EVENT_NAMES:
        return None
    start_date = clean_text(item.get("startDate"))
    date_value, time_value = parse_date_time(start_date)
    if not date_value:
        return None

    offers = item.get("offers", {})
    if isinstance(offers, list):
        offers = offers[0] if offers else {}
    price = clean_text(str(offers.get("price", ""))) if isinstance(offers, dict) else ""

    performer = item.get("performer", "")
    musician_items = []
    for entry in _as_list(performer):
        if isinstance(entry, dict):
            musician_items.append(clean_text(entry.get("name")))
        else:
            musician_items.append(clean_text(str(entry)))
    filtered_musicians = [
        value
        for value in musician_items
        if value and value.casefold() not in GENERIC_MUSICIAN_VALUES
    ]
    musicians = normalize_musicians(", ".join(filtered_musicians))

    url_value = clean_text(item.get("url")) or page_url
    return RawEvent(
        event_name=name,
        date=date_value,
        time=time_value,
        venue=source.venue_name,
        ticket_price=price,
        description=clean_text(item.get("description")),
        musicians=musicians,
        event_link=urljoin(page_url, url_value),
        source_url=source.source_url,
        source_id=source.source_id,
    )


def extract_json_ld_events(html: str, source: SourceConfig, page_url: str) -> list[RawEvent]:
    soup = BeautifulSoup(html, "html.parser")
    events: list[RawEvent] = []
    seen_links: set[str] = set()
    for node in soup.select("script[type='application/ld+json']"):
        raw_json = (node.string or node.get_text() or "").strip()
        if not raw_json:
            continue
        try:
            payload = json.loads(raw_json)
        except json.JSONDecodeError:
            continue
        for item in _flatten_json_ld(payload):
            event = _build_event_from_schema(item, source, page_url)
            if not event or not event.event_name:
                continue
            dedup_hint = event.event_link or f"{event.event_name}-{event.date}-{event.time}"
            if dedup_hint in seen_links:
                continue
            seen_links.add(dedup_hint)
            events.append(event)
    return events


def extract_heuristic_card_events(html: str, source: SourceConfig, page_url: str) -> list[RawEvent]:
    soup = BeautifulSoup(html, "html.parser")
    events: list[RawEvent] = []
    seen: set[tuple[str, str]] = set()
    for card in soup.select(CARD_SELECTOR):
        title_node = card.select_one("h1, h2, h3, h4, .title, [class*='title']")
        name = clean_text(title_node.get_text(" ", strip=True) if title_node else "")
        if len(name) < 4:
            continue

        full_text = clean_text(card.get_text(" ", strip=True))
        if len(full_text) < 10:
            continue
        date_match = DATE_HINT_RE.search(full_text)
        time_match = TIME_HINT_RE.search(full_text)
        date_value = normalize_date(date_match.group(1) if date_match else "")
        time_value = normalize_time(time_match.group(0) if time_match else "")
        if not date_value:
            continue

        link_node = card.select_one("a[href]")
        event_link = ""
        if link_node:
            event_link = urljoin(page_url, link_node.get("href", ""))
        if not event_link:
            event_link = page_url

        price = extract_price(full_text)
        event = RawEvent(
            event_name=name,
            date=date_value,
            time=time_value,
            venue=source.venue_name,
            ticket_price=price,
            description=full_text[:450],
            musicians="",
            event_link=event_link,
            source_url=source.source_url,
            source_id=source.source_id,
        )
        key = (event.event_name.casefold(), event.date)
        if key in seen:
            continue
        seen.add(key)
        events.append(event)
    return events


def extract_events_from_html(html: str, source: SourceConfig, page_url: str) -> list[RawEvent]:
    schema_events = extract_json_ld_events(html, source, page_url)
    if schema_events:
        return schema_events
    return extract_heuristic_card_events(html, source, page_url)
