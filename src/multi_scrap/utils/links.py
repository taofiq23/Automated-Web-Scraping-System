from __future__ import annotations

import re
from urllib.parse import urldefrag, urljoin, urlparse

from bs4 import BeautifulSoup

from multi_scrap.utils.text import clean_text


EVENT_HINT_RE = re.compile(
    r"(?i)(event|events|agenda|programaci[oó]n|show|shows|ticket|tickets|entrada|entradas|concierto|live)"
)
TRUSTED_EVENT_DOMAINS = {
    "livepass.com.ar",
    "alternativateatral.com",
    "entradasonline.com.ar",
    "eventbrite.com",
    "ticketek.com.ar",
    "passline.com",
    "tuentrada.com",
}


def same_domain(url_a: str, url_b: str) -> bool:
    return urlparse(url_a).netloc == urlparse(url_b).netloc


def is_trusted_event_domain(url: str) -> bool:
    host = urlparse(url).netloc.lower()
    return any(host == domain or host.endswith(f".{domain}") for domain in TRUSTED_EVENT_DOMAINS)


def extract_candidate_event_links(
    html: str,
    base_url: str,
    include_patterns: list[str] | None = None,
    exclude_patterns: list[str] | None = None,
    same_domain_only: bool = True,
    max_links: int = 60,
) -> list[str]:
    include_patterns = include_patterns or []
    exclude_patterns = exclude_patterns or []
    soup = BeautifulSoup(html, "html.parser")

    links: list[str] = []
    seen: set[str] = set()
    for anchor in soup.select("a[href]"):
        href = anchor.get("href", "").strip()
        text = clean_text(anchor.get_text(" ", strip=True))
        if not href:
            continue
        absolute = urldefrag(urljoin(base_url, href))[0]
        if not absolute.startswith(("http://", "https://")):
            continue
        if same_domain_only and not same_domain(absolute, base_url) and not is_trusted_event_domain(absolute):
            continue
        haystack = f"{absolute} {text}"
        if include_patterns and not any(re.search(p, haystack, re.IGNORECASE) for p in include_patterns):
            continue
        if exclude_patterns and any(re.search(p, haystack, re.IGNORECASE) for p in exclude_patterns):
            continue
        if not include_patterns and not EVENT_HINT_RE.search(haystack):
            continue
        if absolute in seen:
            continue
        seen.add(absolute)
        links.append(absolute)
        if len(links) >= max_links:
            break
    return links
