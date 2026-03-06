from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import re
from typing import Any
import unicodedata


DEDUP_TEXT_RE = re.compile(r"[^a-z0-9]+")


def _dedup_canonical(value: str) -> str:
    text = (value or "").strip().casefold()
    if "ã" in text or "â" in text:
        try:
            text = text.encode("latin-1").decode("utf-8")
        except UnicodeError:
            pass
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = DEDUP_TEXT_RE.sub(" ", text).strip()
    return text


@dataclass(slots=True)
class SourceConfig:
    source_id: str
    venue_name: str
    source_url: str
    instagram_handle: str = ""
    enabled: bool = True
    mode: str = "auto"  # auto | static | playwright
    include_link_patterns: list[str] = field(default_factory=list)
    exclude_link_patterns: list[str] = field(default_factory=list)
    list_url: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class RawEvent:
    event_name: str = ""
    date: str = ""
    time: str = ""
    venue: str = ""
    ticket_price: str = ""
    description: str = ""
    musicians: str = ""
    event_link: str = ""
    source_url: str = ""
    source_id: str = ""
    scraped_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def score(self) -> int:
        return sum(
            1
            for value in [
                self.event_name,
                self.date,
                self.time,
                self.ticket_price,
                self.description,
                self.musicians,
                self.event_link,
            ]
            if value
        )

    def dedup_key(self) -> tuple[str, str, str]:
        return (
            _dedup_canonical(self.event_name),
            self.date.strip(),
            _dedup_canonical(self.venue),
        )

    def as_sheet_row(self) -> list[str]:
        return [
            self.event_name,
            self.date,
            self.time,
            self.venue,
            self.ticket_price,
            self.description,
            self.musicians,
            self.event_link,
            self.source_url,
        ]


SHEET_HEADER_ES = [
    "Nombre del evento",
    "Fecha",
    "Hora",
    "Recinto/Bar",
    "Precio de entrada",
    "Descripcion",
    "Musicos",
    "Enlace del evento",
    "URL fuente",
]

SHEET_HEADER_EN = [
    "Event Name",
    "Date",
    "Time",
    "Venue/Bar",
    "Ticket Price",
    "Description",
    "Musicians",
    "Event Link",
    "Source URL",
]

# Backward-compatible default.
SHEET_HEADER = SHEET_HEADER_ES


def sheet_header_for_language(language: str) -> list[str]:
    normalized = (language or "es").strip().lower()
    if normalized.startswith("en"):
        return SHEET_HEADER_EN.copy()
    return SHEET_HEADER_ES.copy()
