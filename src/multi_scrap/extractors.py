from __future__ import annotations

import json
import re
from io import BytesIO
from datetime import date
from typing import Any
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from multi_scrap.models import RawEvent, SourceConfig
from multi_scrap.utils.dates import normalize_date, normalize_time, parse_date_time
from multi_scrap.utils.text import clean_text, extract_price, normalize_musicians


CARD_SELECTOR = (
    "[class*='event'], [class*='show'], [class*='agenda'], [class*='program'], "
    "article, .tribe-events-event, .event-card, .event-item"
)
DATE_HINT_RE = re.compile(
    r"(?i)\b("
    r"\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?"
    r"|\d{1,2}\s+de\s+[A-Za-zÁÉÍÓÚáéíóúÑñ]+(?:\s+de\s+\d{4})?"
    r"|\d{1,2}\s+[A-Za-zÁÉÍÓÚáéíóúÑñ]+(?:\s+\d{4})?"
    r"|[A-Za-zÁÉÍÓÚáéíóúÑñ]+\s+\d{1,2}(?:\s+\d{4})?"
    r")\b"
)
TIME_HINT_RE = re.compile(r"(?i)\b([01]?\d|2[0-3])[:\.][0-5]\d\b")
URL_DATE_RE = re.compile(r"(\d{2})(\d{2})(\d{4})$")
AGENDA_TEXT_EVENT_RE = re.compile(
    r"(?i)(?:jazz|show|m[uú]sica|evento)?\s*-\s*"
    r"(?:lunes|martes|mi[eé]rcoles|miercoles|jueves|viernes|s[áa]bado|sabado|domingo)\s+"
    r"(\d{1,2})\s+([A-Za-zÁÉÍÓÚáéíóúÑñ]+)\s+(\d{4})\s+(\d{1,2})\s+(\d{2})\s+hs\.?\s+"
    r"(.+?)\s+Entrada:\s*\$?\s*([\d\.,]+)"
)
WEEKDAY_BLOCK_RE = re.compile(
    r"(?i)(lunes|martes|mi[eé]rcoles|miercoles|jueves|viernes|s[áa]bado|sabado|domingo)\s+"
    r"(\d{1,2})\s+([A-Za-zÁÉÍÓÚáéíóúÑñ]+)\s+(.+?)(?="
    r"(?:lunes|martes|mi[eé]rcoles|miercoles|jueves|viernes|s[áa]bado|sabado|domingo)\s+\d{1,2}\s+[A-Za-zÁÉÍÓÚáéíóúÑñ]+|$)"
)
NEMPLA_SCHEDULE_RE = re.compile(
    r"(?i)([A-Za-z\u00C0-\u00FF\u00D1\u00F1]+)\s+(\d{1,2})\s*-\s*"
    r"(\d{1,2}:\d{2}\s*(?:am|pm))\s*-\s*\d{1,2}:\d{2}\s*(?:am|pm)\s+"
    r"(.+?)(?=\s+(?:QUIERO\s+IR|VER\s+AGENDA|[A-Za-z\u00C0-\u00FF\u00D1\u00F1]+\s+\d{1,2}\s*-\s*\d{1,2}:\d{2}\s*(?:am|pm)\s*-\s*\d{1,2}:\d{2}\s*(?:am|pm)|$))"
)
ALT_TITLE_DATE_RE = re.compile(r"(.+?)\((\d{1,2}/\d{1,2}/\d{2,4})\)")
POMPAS_CONTEXT_RE = re.compile(
    r"(?i)(\d{1,2}\s+[A-Za-zÁÉÍÓÚáéíóúÑñ]+)\s+(?:lunes|martes|mi[eé]rcoles|miercoles|jueves|viernes|s[áa]bado|sabado|domingo)\s+"
    r"(.+?)(?:Ver detalle|Semanalmente|$)"
)

GENERIC_EVENT_NAMES = {"principal", "home", "inicio", "events", "eventos"}
GENERIC_CARD_NAMES = {"comprar", "buy", "tickets", "entradas", "reservar", "ver detalle", "shows"}
GENERIC_MUSICIAN_VALUES = {"organization", "person", "musicgroup", "performinggroup"}
TRAILING_DATE_IN_TITLE_RE = re.compile(r"\s+\d{1,2}/\d{1,2}/\d{4}\s*$")

PASSLINE_CARD_SELECTOR = ".masonry-item"
PASSLINE_LINK_SELECTOR = "a[href*='eventos-ficha-dvm'], a[href*='sitio-evento']"
PASSLINE_TITLE_SELECTOR = ".descripcion-evento .h4, .descripcion-evento span.h4"
PASSLINE_DATE_SELECTOR = "li.fecha-site"
PASSLINE_VENUE_SELECTOR = "li.lugar-site"
PASSLINE_LIST_DATE_LINE_RE = re.compile(
    r"(?i)^\*?\s*(\d{1,2}\s+de\s+[A-Za-z\u00C0-\u00FF\u00D1\u00F1]+\s+\d{4}\s+a\s+las\s+\d{1,2}:\d{2})\s*$"
)
PASSLINE_DETAIL_DATE_RE = re.compile(
    r"(?i)(?:lunes|martes|mi[eé]rcoles|miercoles|jueves|viernes|s[áa]bado|sabado|domingo)\s+"
    r"\d{1,2}\s+de\s+[A-Za-z\u00C0-\u00FF\u00D1\u00F1]+\s+\d{4}\s*-\s*\d{1,2}:\d{2}\s*(?:hrs|hs)\.?"
)
PASSLINE_SKIP_LINES = {
    "home",
    "eventos",
    "nuestros eventos",
    "funciones disponibles",
    "adquirir",
    "comprar",
    "agotadas",
    "sold out",
    "image",
}
MUSICIAN_DASH_RE = re.compile(
    r"([A-Z\u00C0-\u00FF][A-Za-z\u00C0-\u00FF'\.-]+(?:\s+[A-Z\u00C0-\u00FF][A-Za-z\u00C0-\u00FF'\.-]+)+)\s*[--\u2014]\s*"
)
CCNU_CLASS_DATE_RE = re.compile(r"\b(\d{2})-(\d{2})-(\d{4})\b")
CCNU_SUBTITLE_RE = re.compile(
    r"(?i)(?:lunes|martes|mi[eÃ©]rcoles|miercoles|jueves|viernes|s[Ã¡a]bado|sabado|domingo)\s+"
    r"(\d{1,2})\s+([A-Za-z\u00C0-\u00FF\u00D1\u00F1]+)(?:,?\s+(\d{4}))?,?\s+(\d{1,2}:\d{2})"
)
BORGES_DATE_TIME_RE = re.compile(r"(\d{2}-\d{2}-\d{4})\s+(\d{1,2}[:\s]\d{2})\s*hs\.?", flags=re.IGNORECASE)
BORGES_PRICE_RE = re.compile(r"\$\s*[\d\.,]+")
BORGES_SKIP_TITLES = {"shows", "reservar", "ingresar", "share", "back"}
VIRASORO_FECHA_RE = re.compile(
    r"(?i)(?:jazz|show|evento)?\s*-\s*"
    r"(?:lunes|martes|mi[eÃ©]rcoles|miercoles|jueves|viernes|s[Ã¡a]bado|sabado|domingo)\s+"
    r"(\d{1,2})\s+([A-Za-z\u00C0-\u00FF\u00D1\u00F1]+)\s+(\d{4})\s+(\d{1,2})\s+(\d{2})\s+hs\.?"
)
MUSICIAN_PAREN_RE = re.compile(
    r"([A-Z\u00C0-\u00FF][A-Za-z\u00C0-\u00FF'\.-]+(?:\s+[A-Z\u00C0-\u00FF][A-Za-z\u00C0-\u00FF'\.-]+)+)\s*\([^)]+\)"
)
CCOM_TIME_RE = re.compile(r"(?i)\b(\d{1,2})(?::(\d{2}))?\s*hs\b")
PDF_DATE_RE = re.compile(
    r"(?i)\b(\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?|\d{1,2}\s+de\s+[A-Za-z\u00C0-\u00FF\u00D1\u00F1]+(?:\s+de\s+\d{4})?)\b"
)
PDF_TIME_RE = re.compile(r"(?i)\b([01]?\d|2[0-3])[:\.]([0-5]\d)\s*(?:hs|hrs)?\b|\b([01]?\d|2[0-3])\s*hs\b")


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


def _simplify_text(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", clean_text(value).casefold())


def _venue_matches_source(extracted_venue: str, source_venue: str) -> bool:
    venue = clean_text(extracted_venue)
    if not venue:
        return True
    extracted_key = _simplify_text(venue)
    source_key = _simplify_text(source_venue)
    if not extracted_key or not source_key:
        return True
    if extracted_key in source_key or source_key in extracted_key:
        return True
    source_tokens = [token for token in re.findall(r"[a-z0-9]+", source_key) if len(token) >= 5]
    return any(token in extracted_key for token in source_tokens)


def _extract_musicians_from_text(text: str) -> str:
    names: list[str] = []
    for pattern in (MUSICIAN_DASH_RE, MUSICIAN_PAREN_RE):
        names.extend(match.group(1) for match in pattern.finditer(text))
    return normalize_musicians(", ".join(names))


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
        title_node = card.select_one(
            "h1, h2, h3, h4, h5, .h4, .title, .event-title, [class*='title'], [class*='name']"
        )
        name = clean_text(title_node.get_text(" ", strip=True) if title_node else "")
        if len(name) < 4 or name.casefold() in GENERIC_CARD_NAMES:
            continue

        full_text = clean_text(card.get_text(" ", strip=True))
        if len(full_text) < 10:
            continue
        date_match = DATE_HINT_RE.search(full_text)
        time_match = TIME_HINT_RE.search(full_text)
        date_value = normalize_date(date_match.group(1) if date_match else "")
        time_value = normalize_time(time_match.group(0) if time_match else "")

        link_node = card.select_one("a[href]")
        event_link = ""
        if link_node:
            event_link = urljoin(page_url, link_node.get("href", ""))
        if not event_link:
            event_link = page_url

        if not date_value:
            candidate = event_link.rstrip("/").split("-")[-1]
            url_date_match = URL_DATE_RE.search(candidate)
            if url_date_match:
                dd, mm, yyyy = url_date_match.groups()
                date_value = f"{yyyy}-{mm}-{dd}"
        if not date_value:
            continue

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
    host = urlparse(page_url).netloc.lower()

    if "festivalesba.org" in host:
        festivales_events = extract_festivalesba_pdf_events(html, source, page_url)
        if festivales_events:
            return festivales_events

    if "virasorobar.com.ar" in host:
        virasoro_events = extract_virasoro_events(html, source, page_url)
        if virasoro_events:
            return virasoro_events
        virasoro_events = extract_agenda_text_events(html, source, page_url)
        if virasoro_events:
            return virasoro_events

    if "jazzvoyeur.com.ar" in host:
        jazzvoyeur_events = extract_jazzvoyeur_schedule_events(html, source, page_url)
        if jazzvoyeur_events:
            return jazzvoyeur_events

    if "lanempla.com" in host:
        nempla_events = extract_nempla_schedule_events(html, source, page_url)
        if nempla_events:
            return nempla_events

    if "ccnuevauriarte.com.ar" in host:
        ccnu_events = extract_ccnu_events(html, source, page_url)
        if ccnu_events:
            return ccnu_events

    if "borges1975.com" in host or "sibilanet.com" in host:
        borges_events = extract_borges_shows_events(html, source, page_url)
        if borges_events:
            return borges_events

    if "cafeberlinbuenosaires.com.ar" in host or ("livepass.com.ar" in host and source.source_id == "C0011"):
        cafeberlin_events = extract_cafeberlin_home_events(html, source, page_url)
        if cafeberlin_events:
            return cafeberlin_events

    if "ccomplejoartmedia.com.ar" in host:
        ccom_events = extract_ccomplejo_events(html, source, page_url)
        if ccom_events:
            return ccom_events

    if "pompapetriyasos.com.ar" in host:
        pompas_events = extract_pompas_context_events(html, source, page_url)
        if pompas_events:
            return pompas_events

    if "alternativateatral.com" in host and "espacio" in page_url:
        alt_events = extract_alternativateatral_space_events(html, source, page_url)
        if alt_events:
            return alt_events

    if "passline.com" in host:
        passline_events = extract_passline_list_events(html, source, page_url)
        if passline_events:
            return passline_events

    if "entradasonline.com.ar" in host:
        entradasonline_events = extract_entradasonline_events(html, source, page_url)
        if entradasonline_events:
            return entradasonline_events

    schema_events = extract_json_ld_events(html, source, page_url)
    if schema_events:
        return schema_events
    heuristic_events = extract_heuristic_card_events(html, source, page_url)
    if heuristic_events:
        return heuristic_events
    dated_anchor_events = extract_dated_anchor_events(html, source, page_url)
    if dated_anchor_events:
        return dated_anchor_events
    return extract_agenda_text_events(html, source, page_url)


def extract_cafeberlin_home_events(html: str, source: SourceConfig, page_url: str) -> list[RawEvent]:
    soup = BeautifulSoup(html, "html.parser")
    date_nodes = soup.select(".date-home")
    if not date_nodes:
        return []

    page_year = _infer_year_from_text(clean_text(soup.get_text(" ", strip=True)))
    events: list[RawEvent] = []
    seen: set[tuple[str, str, str]] = set()
    for date_node in date_nodes:
        raw_date = clean_text(date_node.get_text(" ", strip=True))
        if not raw_date:
            continue

        title_node = date_node.find_next(["h1", "h2", "h3"])
        event_name = clean_text(title_node.get_text(" ", strip=True) if title_node else "")
        if len(event_name) < 4 or event_name.casefold() in GENERIC_CARD_NAMES:
            continue

        date_value, time_value = parse_date_time(f"{raw_date} {page_year}")
        if not date_value:
            date_value, time_value = parse_date_time(raw_date)
        if not date_value:
            continue
        if not TIME_HINT_RE.search(raw_date):
            time_value = ""

        link_node = date_node.find_parent("a", href=True)
        if not link_node and date_node.parent:
            link_node = date_node.parent.find_parent("a", href=True)
        if not link_node and date_node.parent:
            link_node = date_node.parent.select_one("a[href]")
        event_link = urljoin(page_url, link_node.get("href", "").strip()) if link_node else page_url

        event = RawEvent(
            event_name=event_name,
            date=date_value,
            time=time_value,
            venue=source.venue_name,
            ticket_price="",
            description=raw_date,
            musicians="",
            event_link=event_link,
            source_url=source.source_url,
            source_id=source.source_id,
        )
        key = (event.event_name.casefold(), event.date, event.event_link)
        if key in seen:
            continue
        seen.add(key)
        events.append(event)
    return events


def _download_pdf_text(pdf_url: str) -> str:
    try:
        from pypdf import PdfReader
    except Exception:
        return ""

    try:
        session = requests.Session()
        session.trust_env = False
        session.headers.update(
            {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                "Accept": "application/pdf,*/*;q=0.8",
            }
        )
        response = session.get(pdf_url, timeout=40)
        if not response.ok or not response.content:
            return ""
        reader = PdfReader(BytesIO(response.content))
        chunks: list[str] = []
        for page in reader.pages:
            chunks.append(page.extract_text() or "")
        return "\n".join(chunks)
    except Exception:
        return ""


def extract_festivalesba_pdf_events(html: str, source: SourceConfig, page_url: str) -> list[RawEvent]:
    soup = BeautifulSoup(html, "html.parser")
    pdf_link = ""
    for anchor in soup.select("a[href]"):
        href = clean_text(anchor.get("href", "").strip())
        text = clean_text(anchor.get_text(" ", strip=True))
        if ".pdf" in href.lower() or "program" in text.casefold():
            pdf_link = urljoin(page_url, href)
            if ".pdf" in pdf_link.lower():
                break
    if not pdf_link:
        return []

    pdf_text = _download_pdf_text(pdf_link)
    if not pdf_text:
        return []

    lines = [clean_text(line) for line in pdf_text.replace("\r", "\n").split("\n")]
    lines = [line for line in lines if line]
    if not lines:
        return []

    year = _infer_year_from_text(" ".join(lines))
    events: list[RawEvent] = []
    seen: set[tuple[str, str, str]] = set()
    in_target_section = False
    current_date = ""

    for line in lines:
        lowered = line.casefold()
        if "bar conde" in lowered:
            in_target_section = True
        elif in_target_section and re.search(r"(?i)\bbar\s+[A-Za-z]", line) and "bar conde" not in lowered:
            in_target_section = False

        if not in_target_section:
            continue

        date_match = PDF_DATE_RE.search(line)
        if date_match:
            raw_date = date_match.group(1)
            date_value = normalize_date(raw_date)
            if not date_value:
                date_value, _ = parse_date_time(f"{raw_date} {year}")
            if date_value:
                current_date = date_value

        if not current_date:
            continue

        time_value = ""
        time_match = PDF_TIME_RE.search(line)
        if time_match:
            if time_match.group(1) and time_match.group(2):
                time_value = normalize_time(f"{time_match.group(1).zfill(2)}:{time_match.group(2)}")
            elif time_match.group(3):
                time_value = normalize_time(f"{time_match.group(3).zfill(2)}:00")

        name_line = line
        if date_match:
            name_line = name_line.replace(date_match.group(0), " ")
        if time_match:
            name_line = name_line.replace(time_match.group(0), " ")
        name_line = re.sub(r"(?i)\b(bar\s+conde|programaci[oó]n|programming|bares?\s+notables?)\b", " ", name_line)
        name_line = re.sub(r"(?i)\$\s*[\d\.,]+", " ", name_line)
        event_name = clean_text(name_line)
        if len(event_name) < 4 or event_name.casefold() in GENERIC_CARD_NAMES:
            continue

        event = RawEvent(
            event_name=event_name,
            date=current_date,
            time=time_value,
            venue=source.venue_name,
            ticket_price=extract_price(line),
            description=line[:450],
            musicians="",
            event_link=pdf_link,
            source_url=source.source_url,
            source_id=source.source_id,
        )
        key = (event.event_name.casefold(), event.date, event.time)
        if key in seen:
            continue
        seen.add(key)
        events.append(event)

    return events


def _extract_nearby_date_for_node(node: Any, page_year: int) -> tuple[str, str]:
    candidates: list[str] = []
    current = node
    for _ in range(4):
        if not current:
            break
        candidates.append(clean_text(current.get_text(" ", strip=True)))
        sibling = current.find_previous_sibling()
        if sibling:
            candidates.append(clean_text(sibling.get_text(" ", strip=True)))
        current = current.parent

    for text in candidates:
        if not text:
            continue
        date_value, time_value = parse_date_time(text)
        if date_value:
            return date_value, time_value
        date_match = DATE_HINT_RE.search(text)
        if not date_match:
            continue
        date_hint = date_match.group(1)
        date_value, time_value = parse_date_time(f"{date_hint} {page_year}")
        if date_value:
            return date_value, time_value
    return "", ""


def extract_ccomplejo_events(html: str, source: SourceConfig, page_url: str) -> list[RawEvent]:
    soup = BeautifulSoup(html, "html.parser")
    page_year = _infer_year_from_text(clean_text(soup.get_text(" ", strip=True)))
    events: list[RawEvent] = []
    seen: set[tuple[str, str, str]] = set()

    cards = []
    for div in soup.find_all("div"):
        classes = div.get("class", [])
        if not classes:
            continue
        class_text = " ".join(classes)
        if "ml-[20px]" in class_text and "flex" in classes and "flex-col" in classes:
            cards.append(div)

    for card in cards:
        card_text = clean_text(card.get_text(" ", strip=True))
        if len(card_text) < 8:
            continue

        title_node = card.find("p", class_=lambda c: c and "font-bold" in c and "leading-snug" in c)
        if not title_node:
            title_node = card.find("p", class_=lambda c: c and "text-[24px]" in c)
        event_name = clean_text(title_node.get_text(" ", strip=True) if title_node else "")
        if len(event_name) < 3 or event_name.casefold() in GENERIC_CARD_NAMES:
            continue

        date_value, _ = _extract_nearby_date_for_node(card, page_year)
        if not date_value:
            continue

        time_value = ""
        time_match = CCOM_TIME_RE.search(card_text)
        if time_match:
            hour = time_match.group(1).zfill(2)
            minute = (time_match.group(2) or "00").zfill(2)
            time_value = normalize_time(f"{hour}:{minute}")

        lowered = card_text.casefold()
        is_free = any(token in lowered for token in ("free", "free entry", "entrada libre", "gratis"))
        button_text = ""
        button_node = card.find("button")
        if button_node:
            button_text = clean_text(button_node.get_text(" ", strip=True))

        if is_free:
            price_value = "Free entry"
            event_link = page_url
        else:
            price_value = extract_price(card_text) or button_text
            link_node = card.find("a", href=True)
            event_link = urljoin(page_url, link_node.get("href", "").strip()) if link_node else page_url

        description_parts: list[str] = []
        for p_node in card.find_all("p"):
            line = clean_text(p_node.get_text(" ", strip=True))
            if not line or line == event_name:
                continue
            if line.casefold() in {"free", "free entry", "see more", "+see more"}:
                continue
            description_parts.append(line)
        description = clean_text(" ".join(description_parts))

        event = RawEvent(
            event_name=event_name,
            date=date_value,
            time=time_value,
            venue=source.venue_name,
            ticket_price=price_value,
            description=description[:450],
            musicians="",
            event_link=event_link,
            source_url=source.source_url,
            source_id=source.source_id,
        )
        key = (event.event_name.casefold(), event.date, event.time)
        if key in seen:
            continue
        seen.add(key)
        events.append(event)

    return events


def extract_ccnu_events(html: str, source: SourceConfig, page_url: str) -> list[RawEvent]:
    soup = BeautifulSoup(html, "html.parser")
    events: list[RawEvent] = []
    seen: set[tuple[str, str, str]] = set()

    for card in soup.select(".event-box"):
        link_node = card.select_one("a[href]")
        title_node = card.select_one("h1, h2, h3")
        if not link_node or not title_node:
            continue
        event_name = clean_text(title_node.get_text(" ", strip=True))
        if len(event_name) < 4 or event_name.casefold() in GENERIC_CARD_NAMES:
            continue

        date_value = ""
        class_match = CCNU_CLASS_DATE_RE.search(" ".join(card.get("class", [])))
        if class_match:
            day, month, year = class_match.groups()
            date_value = f"{year}-{month}-{day}"
        if not date_value:
            filter_date = clean_text(card.get("data-date-filter", ""))
            date_value = normalize_date(filter_date)
        if not date_value:
            continue

        event_link = urljoin(page_url, link_node.get("href", "").strip())
        date_node = card.select_one(".date-home")
        event = RawEvent(
            event_name=event_name,
            date=date_value,
            time="",
            venue=source.venue_name,
            ticket_price="",
            description=clean_text(date_node.get_text(" ", strip=True) if date_node else ""),
            musicians="",
            event_link=event_link,
            source_url=source.source_url,
            source_id=source.source_id,
        )
        key = (event.event_name.casefold(), event.date, event.event_link)
        if key in seen:
            continue
        seen.add(key)
        events.append(event)

    if events:
        return events

    title_node = soup.select_one(".title-event, .item-header .title-event, h2.title-event")
    subtitle_node = soup.select_one(".subtitle-event, h2.subtitle-event")
    if not title_node:
        return []

    event_name = clean_text(title_node.get_text(" ", strip=True))
    subtitle = clean_text(subtitle_node.get_text(" ", strip=True) if subtitle_node else "")
    date_value, time_value = parse_date_time(subtitle)
    if not date_value:
        match = CCNU_SUBTITLE_RE.search(subtitle)
        if match:
            day, month, year, hour = match.groups()
            parsed_year = year or str(_infer_year_from_text(clean_text(soup.get_text(" ", strip=True))))
            date_value, _ = parse_date_time(f"{day} {month} {parsed_year}")
            time_value = normalize_time(hour)
    if not date_value:
        return []

    venue_text = ""
    for p_node in soup.select("p"):
        line = clean_text(p_node.get_text(" ", strip=True))
        if line.casefold().startswith("recinto:"):
            venue_text = clean_text(line.split(":", 1)[1])
            break
    venue_value = venue_text or source.venue_name
    if not _venue_matches_source(venue_value, source.venue_name):
        venue_value = source.venue_name

    page_text = clean_text(soup.get_text(" ", strip=True))
    price_value = ""
    desde_node = soup.find(string=re.compile(r"(?i)desde\s+\$\s*[\d\.,]+"))
    if desde_node:
        price_value = clean_text(str(desde_node))
    if not price_value:
        price_value = extract_price(page_text)

    # Capture rich event synopsis from detail pages when available.
    desc_node = (
        soup.select_one("span[data-olk-copy-source]")
        or soup.select_one(".description-event, .event-description, .info-event span")
    )
    detail_desc = clean_text(desc_node.get_text(" ", strip=True) if desc_node else "")
    description_value = clean_text(" ".join(part for part in [subtitle, detail_desc] if part))

    event = RawEvent(
        event_name=event_name,
        date=date_value,
        time=time_value,
        venue=venue_value,
        ticket_price=price_value,
        description=description_value,
        musicians="",
        event_link=page_url,
        source_url=source.source_url,
        source_id=source.source_id,
    )
    return [event]


def extract_borges_shows_events(html: str, source: SourceConfig, page_url: str) -> list[RawEvent]:
    soup = BeautifulSoup(html, "html.parser")
    events: list[RawEvent] = []
    seen: set[tuple[str, str, str]] = set()

    for reserve_btn in soup.find_all("button"):
        btn_text = clean_text(reserve_btn.get_text(" ", strip=True))
        if "reservar" not in btn_text.casefold():
            continue

        container = reserve_btn
        for _ in range(8):
            container = container.parent
            if not container:
                break
            container_text = clean_text(container.get_text(" ", strip=True))
            if "reservar" in container_text.casefold() and BORGES_DATE_TIME_RE.search(container_text):
                break
        if not container:
            continue

        title_value = ""
        date_value = ""
        time_value = ""
        price_value = ""
        for bold in container.select("b"):
            text = clean_text(bold.get_text(" ", strip=True))
            if not text:
                continue
            lowered = text.casefold()
            if lowered in BORGES_SKIP_TITLES:
                continue
            if not date_value:
                dt_match = BORGES_DATE_TIME_RE.search(text)
                if dt_match:
                    date_part, time_part = dt_match.groups()
                    date_value = normalize_date(date_part)
                    time_value = normalize_time(time_part.replace(" ", ":"))
                    continue
            if not price_value and "$" in text:
                price_match = BORGES_PRICE_RE.search(text)
                if price_match:
                    price_value = clean_text(price_match.group(0))
                    continue
            if not title_value:
                title_value = text

        if not title_value or not date_value:
            continue

        description_node = container.select_one("p[align='justify'], p")
        description = clean_text(description_node.get_text(" ", strip=True) if description_node else "")
        musicians = _extract_musicians_from_text(description)

        link_node = (
            container.select_one("a[href*='passline']")
            or container.select_one("a[href*='product.php?id=']")
            or container.select_one("a[href*='show.php']")
            or container.select_one("a[href]")
        )
        event_link = urljoin(page_url, link_node.get("href", "").strip()) if link_node else page_url

        event = RawEvent(
            event_name=title_value,
            date=date_value,
            time=time_value,
            venue=source.venue_name,
            ticket_price=price_value,
            description=description[:450],
            musicians=musicians,
            event_link=event_link,
            source_url=source.source_url,
            source_id=source.source_id,
        )
        key = (event.event_name.casefold(), event.date, event.event_link)
        if key in seen:
            continue
        seen.add(key)
        events.append(event)

    if events:
        return events

    text = clean_text(soup.get_text(" ", strip=True))
    fallback_re = re.compile(
        r"(?i)([A-Z\u00C0-\u00FF0-9][A-Z\u00C0-\u00FF0-9/\-\s\.'\u2019]{3,}?)\s+reservar\s+"
        r"(\d{2}-\d{2}-\d{4})\s+(\d{1,2}[:\s]\d{2})\s*hs\.?\s+(\$\s*[\d\.,]+)"
    )
    for name, date_part, time_part, price in fallback_re.findall(text):
        event_name = clean_text(name)
        if event_name.casefold() in BORGES_SKIP_TITLES:
            continue
        date_value = normalize_date(date_part)
        time_value = normalize_time(time_part.replace(" ", ":"))
        if not date_value:
            continue
        event = RawEvent(
            event_name=event_name,
            date=date_value,
            time=time_value,
            venue=source.venue_name,
            ticket_price=clean_text(price),
            description="",
            musicians="",
            event_link=page_url,
            source_url=source.source_url,
            source_id=source.source_id,
        )
        key = (event.event_name.casefold(), event.date, event.event_link)
        if key in seen:
            continue
        seen.add(key)
        events.append(event)

    return events


def extract_entradasonline_events(html: str, source: SourceConfig, page_url: str) -> list[RawEvent]:
    soup = BeautifulSoup(html, "html.parser")
    cards = soup.select(".show-info")
    if not cards:
        # Detail pages can expose the same fields without wrapping .show-info.
        has_detail_markers = bool(
            soup.select_one("[itemprop='name']")
            and (soup.select_one("[itemprop='startDate']") or soup.find(string=re.compile(r"(?i)\d{1,2}\s+de\s+[A-Za-z\u00C0-\u00FF\u00D1\u00F1]+")))
        )
        if has_detail_markers:
            cards = [soup]
    if not cards:
        return []

    events: list[RawEvent] = []
    seen: set[tuple[str, str, str]] = set()
    for card in cards:
        name_node = card.select_one("[itemprop='name']")
        event_name = clean_text(name_node.get_text(" ", strip=True) if name_node else "")
        if len(event_name) < 4 or event_name.casefold() in GENERIC_CARD_NAMES:
            continue

        # Prefer machine-readable ISO value when present.
        start_node = card.select_one("[itemprop='startDate']")
        raw_start = clean_text(start_node.get("content", "") if start_node else "")
        if not raw_start:
            raw_start = clean_text(start_node.get_text(" ", strip=True) if start_node else "")
        date_value, time_value = parse_date_time(raw_start)

        if not date_value:
            date_line = ""
            for element in card.select("div, span"):
                text = clean_text(element.get_text(" ", strip=True))
                if DATE_HINT_RE.search(text):
                    date_line = text
                    break
            date_value = normalize_date(date_line)
            if not time_value:
                time_match = TIME_HINT_RE.search(date_line)
                time_value = normalize_time(time_match.group(0) if time_match else "")
        if not date_value:
            continue

        venue_node = card.select_one("[itemprop='location']")
        venue_value = clean_text(venue_node.get_text(" ", strip=True) if venue_node else "") or source.venue_name
        if not _venue_matches_source(venue_value, source.venue_name):
            continue

        price_node = card.select_one("[itemprop='price']")
        price_value = clean_text(price_node.get_text(" ", strip=True) if price_node else "")
        if not price_value:
            price_value = extract_price(clean_text(card.get_text(" ", strip=True)))

        description_node = card.select_one(".d-none, [itemprop='description']")
        description = clean_text(description_node.get_text(" ", strip=True) if description_node else "")
        musicians = _extract_musicians_from_text(description)

        link_node = card.select_one("a[href]")
        if not link_node:
            parent_link = card.find_parent("a", href=True)
            link_node = parent_link if parent_link else None
        event_link = urljoin(page_url, link_node.get("href", "").strip()) if link_node else page_url

        event = RawEvent(
            event_name=event_name,
            date=date_value,
            time=time_value,
            venue=venue_value,
            ticket_price=price_value,
            description=description[:450],
            musicians=musicians,
            event_link=event_link,
            source_url=source.source_url,
            source_id=source.source_id,
        )
        key = (event.event_name.casefold(), event.date, event.event_link)
        if key in seen:
            continue
        seen.add(key)
        events.append(event)
    return events


def extract_passline_list_events(html: str, source: SourceConfig, page_url: str) -> list[RawEvent]:
    soup = BeautifulSoup(html, "html.parser")
    cards = soup.select(PASSLINE_CARD_SELECTOR)
    events: list[RawEvent] = []
    seen: set[tuple[str, str, str]] = set()
    for card in cards:
        link_node = card.select_one(PASSLINE_LINK_SELECTOR)
        event_link = urljoin(page_url, link_node.get("href", "").strip()) if link_node else page_url

        title_node = card.select_one(PASSLINE_TITLE_SELECTOR)
        raw_title = clean_text(title_node.get_text(" ", strip=True) if title_node else "")
        event_name = clean_text(TRAILING_DATE_IN_TITLE_RE.sub("", raw_title))
        if not event_name or event_name.casefold() in GENERIC_CARD_NAMES:
            continue

        date_node = card.select_one(PASSLINE_DATE_SELECTOR)
        raw_date = clean_text(date_node.get_text(" ", strip=True) if date_node else "")
        date_value, time_value = parse_date_time(raw_date)
        if not date_value:
            continue

        venue_node = card.select_one(PASSLINE_VENUE_SELECTOR)
        venue_value = clean_text(venue_node.get_text(" ", strip=True) if venue_node else "") or source.venue_name
        event = RawEvent(
            event_name=event_name,
            date=date_value,
            time=time_value,
            venue=venue_value,
            ticket_price="",
            description=raw_title,
            musicians="",
            event_link=event_link,
            source_url=source.source_url,
            source_id=source.source_id,
        )
        key = (event.event_name.casefold(), event.date, event.event_link)
        if key in seen:
            continue
        seen.add(key)
        events.append(event)

    if events:
        return events

    text_lines = [
        clean_text(line.strip("* ").strip())
        for line in soup.get_text("\n", strip=True).splitlines()
        if clean_text(line)
    ]
    for idx, line in enumerate(text_lines):
        date_match = PASSLINE_LIST_DATE_LINE_RE.match(line)
        if not date_match:
            continue
        date_value, time_value = parse_date_time(date_match.group(1))
        if not date_value:
            continue

        event_name = ""
        for back in range(idx - 1, max(idx - 5, -1), -1):
            candidate = clean_text(text_lines[back].strip("* ").strip())
            lowered = candidate.casefold()
            if (
                not candidate
                or lowered in PASSLINE_SKIP_LINES
                or PASSLINE_LIST_DATE_LINE_RE.match(candidate)
                or "compra" in lowered
                or "adquir" in lowered
            ):
                continue
            event_name = candidate
            break
        if not event_name:
            continue

        venue_value = source.venue_name
        for forward in range(idx + 1, min(idx + 5, len(text_lines))):
            candidate = clean_text(text_lines[forward].strip("* ").strip())
            lowered = candidate.casefold()
            if not candidate or lowered in PASSLINE_SKIP_LINES or "compra" in lowered or "adquir" in lowered:
                continue
            if PASSLINE_LIST_DATE_LINE_RE.match(candidate):
                break
            venue_value = candidate
            break

        event = RawEvent(
            event_name=event_name,
            date=date_value,
            time=time_value,
            venue=venue_value,
            ticket_price="",
            description=f"{event_name} {date_match.group(1)}",
            musicians="",
            event_link=page_url,
            source_url=source.source_url,
            source_id=source.source_id,
        )
        key = (event.event_name.casefold(), event.date, event.event_link)
        if key in seen:
            continue
        seen.add(key)
        events.append(event)

    if events:
        return events

    return extract_passline_detail_events(html, source, page_url)


def extract_virasoro_events(html: str, source: SourceConfig, page_url: str) -> list[RawEvent]:
    soup = BeautifulSoup(html, "html.parser")
    blocks = soup.select("div#eventos")
    if not blocks:
        return []

    events: list[RawEvent] = []
    seen: set[tuple[str, str, str]] = set()
    for block in blocks:
        fecha_text = clean_text((block.select_one("div#fechas") or block.select_one(".fechas") or "").get_text(" ", strip=True))
        title_text = clean_text((block.select_one("div#titulos") or block.select_one(".titulos") or "").get_text(" ", strip=True))
        desc_text = clean_text((block.select_one("div#descripciones") or block.select_one(".descripciones") or "").get_text(" ", strip=True))
        price_text = clean_text((block.select_one("div#precios") or block.select_one(".precios") or "").get_text(" ", strip=True))

        if len(title_text) < 3:
            continue

        date_value = ""
        time_value = ""
        match = VIRASORO_FECHA_RE.search(fecha_text)
        if match:
            day, month, year, hour, minute = match.groups()
            date_value, _ = parse_date_time(f"{day} {month} {year}")
            time_value = normalize_time(f"{hour}:{minute}")
        else:
            date_value, time_value = parse_date_time(fecha_text)
        if not date_value:
            continue

        event = RawEvent(
            event_name=title_text,
            date=date_value,
            time=time_value,
            venue=source.venue_name,
            ticket_price=extract_price(price_text) or price_text,
            description=desc_text,
            musicians=normalize_musicians(desc_text),
            event_link=page_url,
            source_url=source.source_url,
            source_id=source.source_id,
        )
        key = (event.event_name.casefold(), event.date, event.event_link)
        if key in seen:
            continue
        seen.add(key)
        events.append(event)
    return events


def extract_passline_detail_events(html: str, source: SourceConfig, page_url: str) -> list[RawEvent]:
    soup = BeautifulSoup(html, "html.parser")
    title_node = soup.select_one("h1, h2")
    event_name = clean_text(title_node.get_text(" ", strip=True) if title_node else "")
    if len(event_name) < 3:
        return []

    page_text = clean_text(soup.get_text(" ", strip=True))
    raw_date = ""
    list_match = re.search(
        r"(?i)\d{1,2}\s+de\s+[A-Za-z\u00C0-\u00FF\u00D1\u00F1]+\s+\d{4}\s+a\s+las\s+\d{1,2}:\d{2}",
        page_text,
    )
    if list_match:
        raw_date = list_match.group(0)
    else:
        detail_match = PASSLINE_DETAIL_DATE_RE.search(page_text)
        if detail_match:
            raw_date = detail_match.group(0)
    if not raw_date:
        return []
    date_value, time_value = parse_date_time(raw_date)
    if not date_value:
        return []

    price = extract_price(page_text)
    event = RawEvent(
        event_name=event_name,
        date=date_value,
        time=time_value,
        venue=source.venue_name,
        ticket_price=price,
        description=page_text[:450],
        musicians="",
        event_link=page_url,
        source_url=source.source_url,
        source_id=source.source_id,
    )
    return [event]


def extract_agenda_text_events(html: str, source: SourceConfig, page_url: str) -> list[RawEvent]:
    text = clean_text(BeautifulSoup(html, "html.parser").get_text(" ", strip=True))
    if not text:
        return []

    events: list[RawEvent] = []
    seen: set[tuple[str, str]] = set()
    for match in AGENDA_TEXT_EVENT_RE.finditer(text):
        day, month, year, hour, minute, raw_name, raw_price = match.groups()
        event_name = clean_text(raw_name)
        if not event_name or event_name.casefold() in GENERIC_CARD_NAMES:
            continue
        date_value, _ = parse_date_time(f"{day} {month} {year}")
        if not date_value:
            continue
        time_value = normalize_time(f"{hour}:{minute}")
        price = clean_text(raw_price)
        event = RawEvent(
            event_name=event_name,
            date=date_value,
            time=time_value,
            venue=source.venue_name,
            ticket_price=price,
            description="",
            musicians="",
            event_link=page_url,
            source_url=source.source_url,
            source_id=source.source_id,
        )
        key = (event.event_name.casefold(), event.date)
        if key in seen:
            continue
        seen.add(key)
        events.append(event)
    return events


def extract_dated_anchor_events(html: str, source: SourceConfig, page_url: str) -> list[RawEvent]:
    soup = BeautifulSoup(html, "html.parser")
    events: list[RawEvent] = []
    seen: set[tuple[str, str, str]] = set()
    for anchor in soup.select("a[href]"):
        raw_text = clean_text(anchor.get_text(" ", strip=True))
        if len(raw_text) < 6:
            continue
        if raw_text.casefold() in GENERIC_CARD_NAMES:
            continue
        date_match = DATE_HINT_RE.search(raw_text)
        if not date_match:
            continue
        date_value = normalize_date(date_match.group(1))
        if not date_value:
            continue
        time_match = TIME_HINT_RE.search(raw_text)
        time_value = normalize_time(time_match.group(0) if time_match else "")
        event_name = clean_text(raw_text.replace(date_match.group(1), "").strip("() -:"))
        if len(event_name) < 4:
            continue
        event_link = urljoin(page_url, anchor.get("href", ""))
        event = RawEvent(
            event_name=event_name,
            date=date_value,
            time=time_value,
            venue=source.venue_name,
            ticket_price="",
            description=raw_text,
            musicians="",
            event_link=event_link,
            source_url=source.source_url,
            source_id=source.source_id,
        )
        dedup = (event.event_name.casefold(), event.date, event.event_link)
        if dedup in seen:
            continue
        seen.add(dedup)
        events.append(event)
    return events


def _infer_year_from_text(text: str) -> int:
    years = [int(value) for value in re.findall(r"\b(20\d{2})\b", text)]
    if years:
        return max(years)
    return date.today().year


def extract_jazzvoyeur_schedule_events(html: str, source: SourceConfig, page_url: str) -> list[RawEvent]:
    text = clean_text(BeautifulSoup(html, "html.parser").get_text(" ", strip=True))
    if "próximos shows".casefold() not in text.casefold() and "proximos shows" not in text.casefold():
        return []

    year = _infer_year_from_text(text)
    default_time = "21:00" if "show 21:00" in text.casefold() else ""
    events: list[RawEvent] = []
    seen: set[tuple[str, str]] = set()
    for _, day, month, raw_name in WEEKDAY_BLOCK_RE.findall(text):
        event_name = clean_text(raw_name.replace("QUIERO IR", "").strip(" -:"))
        if len(event_name) < 3 or event_name.casefold() in GENERIC_CARD_NAMES:
            continue
        date_value, _ = parse_date_time(f"{day} {month} {year}")
        if not date_value:
            continue
        event = RawEvent(
            event_name=event_name,
            date=date_value,
            time=default_time,
            venue=source.venue_name,
            ticket_price="",
            description="",
            musicians="",
            event_link=page_url,
            source_url=source.source_url,
            source_id=source.source_id,
        )
        key = (event.event_name.casefold(), event.date)
        if key in seen:
            continue
        seen.add(key)
        events.append(event)
    return events


def extract_nempla_schedule_events(html: str, source: SourceConfig, page_url: str) -> list[RawEvent]:
    text = clean_text(BeautifulSoup(html, "html.parser").get_text(" ", strip=True))
    lowered_text = text.casefold()
    if "agenda" not in lowered_text and "quiero ir" not in lowered_text:
        return []

    year = _infer_year_from_text(text)
    events: list[RawEvent] = []
    seen: set[tuple[str, str]] = set()
    for month, day, start_time, raw_name in NEMPLA_SCHEDULE_RE.findall(text):
        event_name = clean_text(re.sub(r"(?i)\b(?:QUIERO\s+IR|VER\s+AGENDA)\b.*$", "", raw_name))
        event_name = clean_text(event_name.strip(" -:#"))
        if len(event_name) < 3 or event_name.casefold() in GENERIC_CARD_NAMES:
            continue
        date_value, _ = parse_date_time(f"{day} {month} {year}")
        time_value = normalize_time(start_time)
        if not date_value:
            continue
        event = RawEvent(
            event_name=event_name,
            date=date_value,
            time=time_value,
            venue=source.venue_name,
            ticket_price="",
            description="",
            musicians="",
            event_link=page_url,
            source_url=source.source_url,
            source_id=source.source_id,
        )
        key = (event.event_name.casefold(), event.date)
        if key in seen:
            continue
        seen.add(key)
        events.append(event)
    return events


def extract_alternativateatral_space_events(html: str, source: SourceConfig, page_url: str) -> list[RawEvent]:
    soup = BeautifulSoup(html, "html.parser")
    page_text = clean_text(soup.get_text(" ", strip=True))
    year = _infer_year_from_text(page_text)

    events: list[RawEvent] = []
    seen: set[tuple[str, str, str]] = set()
    for anchor in soup.select("a[href*='obra']"):
        raw_text = clean_text(anchor.get_text(" ", strip=True))
        if len(raw_text) < 4:
            continue
        match = ALT_TITLE_DATE_RE.search(raw_text)
        if not match:
            continue
        raw_name, date_part = match.groups()
        event_name = clean_text(raw_name)
        date_value, _ = parse_date_time(date_part)
        if not date_value:
            continue
        event_link = urljoin(page_url, anchor.get("href", ""))
        event = RawEvent(
            event_name=event_name,
            date=date_value,
            time="",
            venue=source.venue_name,
            ticket_price="",
            description=raw_text,
            musicians="",
            event_link=event_link,
            source_url=source.source_url,
            source_id=source.source_id,
        )
        key = (event.event_name.casefold(), event.date, event.event_link)
        if key in seen:
            continue
        seen.add(key)
        events.append(event)

    # Fallback: parse "jueves 21:00 hs A destiempo $ 15.000,00" style fragments.
    schedule_re = re.compile(
        r"(?i)(lunes|martes|mi[eé]rcoles|miercoles|jueves|viernes|s[áa]bado|sabado|domingo)\s+"
        r"(\d{1,2}:\d{2})\s+hs\.?\s+(.+?)\s+\$\s*([\d\.,]+)"
    )
    for weekday, hour, raw_name, price in schedule_re.findall(page_text):
        event_name = clean_text(raw_name)
        if len(event_name) < 3:
            continue
        event = RawEvent(
            event_name=event_name,
            date="",
            time=normalize_time(hour),
            venue=source.venue_name,
            ticket_price=price,
            description=f"{weekday} {hour}",
            musicians="",
            event_link=page_url,
            source_url=source.source_url,
            source_id=source.source_id,
        )
        events.append(event)
    # Remove rows without date for this project requirement.
    return [event for event in events if event.date]


def extract_pompas_context_events(html: str, source: SourceConfig, page_url: str) -> list[RawEvent]:
    soup = BeautifulSoup(html, "html.parser")
    year = _infer_year_from_text(clean_text(soup.get_text(" ", strip=True)))
    events: list[RawEvent] = []
    seen: set[tuple[str, str, str]] = set()
    for anchor in soup.select("a[href*='publico.alternativateatral.com/entradas']"):
        event_link = urljoin(page_url, anchor.get("href", ""))
        parent = anchor
        context = ""
        for _ in range(4):
            parent = parent.parent if parent else None
            if not parent:
                break
            candidate = clean_text(parent.get_text(" ", strip=True))
            if 20 < len(candidate) < 260 and re.search(r"\d{1,2}\s+[A-Za-zÁÉÍÓÚáéíóúÑñ]+", candidate):
                context = candidate
                break
        if not context:
            continue
        match = POMPAS_CONTEXT_RE.search(context)
        if not match:
            continue
        date_part, raw_name = match.groups()
        event_name = clean_text(raw_name)
        if len(event_name) < 3:
            continue
        date_value, _ = parse_date_time(f"{date_part} {year}")
        if not date_value:
            continue
        event = RawEvent(
            event_name=event_name,
            date=date_value,
            time="",
            venue=source.venue_name,
            ticket_price="",
            description=context,
            musicians="",
            event_link=event_link,
            source_url=source.source_url,
            source_id=source.source_id,
        )
        key = (event.event_name.casefold(), event.date, event.event_link)
        if key in seen:
            continue
        seen.add(key)
        events.append(event)
    return events
