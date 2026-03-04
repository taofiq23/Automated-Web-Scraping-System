from __future__ import annotations

import html
import re
import unicodedata

from bs4 import BeautifulSoup


WHITESPACE_RE = re.compile(r"\s+")
PRICE_RE = re.compile(r"(?i)(?:\$|usd|ars|entrada|tickets?)\s*[:\-]?\s*[\d\.,]+")
CSS_BLOCK_RE = re.compile(r"[.#]?[a-zA-Z0-9\-_]+\s*\{[^{}]*\}")
COMMENT_RE = re.compile(r"/\*.*?\*/", flags=re.DOTALL)


def clean_text(value: str | None) -> str:
    if not value:
        return ""
    normalized = html.unescape(value)
    if "<" in normalized and ">" in normalized:
        normalized = BeautifulSoup(normalized, "html.parser").get_text(" ", strip=True)
    normalized = unicodedata.normalize("NFKC", normalized)
    normalized = WHITESPACE_RE.sub(" ", normalized).strip()
    return normalized


def normalize_name(value: str | None) -> str:
    return clean_text(value).casefold()


def extract_price(value: str | None) -> str:
    if not value:
        return ""
    match = PRICE_RE.search(value)
    return clean_text(match.group(0)) if match else ""


def normalize_musicians(value: str | None) -> str:
    if not value:
        return ""
    text = clean_text(value)
    if not text:
        return ""
    parts = re.split(r"\s*(?:,|;|/|\||\sy\s|\sand\s| & )\s*", text, flags=re.IGNORECASE)
    cleaned = [clean_text(item) for item in parts if clean_text(item)]
    return ", ".join(dict.fromkeys(cleaned))


def sanitize_description(value: str | None, max_length: int = 800) -> str:
    text = clean_text(value)
    if not text:
        return ""
    # Remove common inline CSS/comment noise that appears in some schema descriptions.
    text = COMMENT_RE.sub(" ", text)
    text = CSS_BLOCK_RE.sub(" ", text)
    text = clean_text(text)
    return text[:max_length]
