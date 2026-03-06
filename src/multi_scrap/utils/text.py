from __future__ import annotations

import html
import re
import unicodedata

from bs4 import BeautifulSoup


WHITESPACE_RE = re.compile(r"\s+")
AMOUNT_RE_FRAGMENT = r"(?:\d{1,3}(?:[.,\s]\d{3})+|\d+)(?:[.,]\d{2})?"
PRICE_RE = re.compile(
    rf"(?i)(?:"
    rf"(?:desde|entrada|ticket|tickets|precio|valor|preventa)\s*[:\-]?\s*"
    rf"(?:\$|ars|usd|u\$s)?\s*{AMOUNT_RE_FRAGMENT}"
    rf"|(?:\$|ars|usd|u\$s)\s*{AMOUNT_RE_FRAGMENT}"
    rf")"
)
FREE_ENTRY_RE = re.compile(r"(?i)\b(?:free\s*entry|entrada\s+libre|gratis|sin\s+cargo)\b")
CSS_BLOCK_RE = re.compile(r"[.#]?[a-zA-Z0-9\-_]+\s*\{[^{}]*\}")
COMMENT_RE = re.compile(r"/\*.*?\*/", flags=re.DOTALL)
PERSON_NAME_RE = re.compile(
    r"\b([A-Z\u00C0-\u00FF][A-Za-z\u00C0-\u00FF'\-]+(?:\s+[A-Z\u00C0-\u00FF][A-Za-z\u00C0-\u00FF'\-]+){1,2})\b"
)
PERSON_STOPWORDS = {
    "jazz",
    "club",
    "band",
    "trio",
    "quartet",
    "cuarteto",
    "quinteto",
    "quintet",
    "sexteto",
    "sextet",
    "orquesta",
    "orchestra",
    "presenta",
    "present",
    "show",
    "noche",
    "cafe",
    "café",
    "free",
    "entry",
    "january",
    "february",
    "march",
    "april",
    "may",
    "june",
    "july",
    "august",
    "september",
    "october",
    "november",
    "december",
}


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
    text = clean_text(value)
    if not text:
        return ""
    if FREE_ENTRY_RE.search(text):
        return "Free entry"

    match = PRICE_RE.search(text)
    if not match:
        return ""

    price = clean_text(match.group(0))
    # Keep the monetary fragment only, removing label prefixes like "Desde" or "Entrada:".
    money_match = re.search(rf"(?i)(?:\$|ars|usd|u\$s)\s*{AMOUNT_RE_FRAGMENT}", price)
    if money_match:
        price = clean_text(money_match.group(0))
    else:
        amount_match = re.search(AMOUNT_RE_FRAGMENT, price)
        if amount_match:
            price = clean_text(amount_match.group(0))
    return price.rstrip(".*")


def normalize_musicians(value: str | None) -> str:
    if not value:
        return ""
    text = clean_text(value)
    if not text:
        return ""
    parts = re.split(r"\s*(?:,|;|/|\||\sy\s|\sand\s| & )\s*", text, flags=re.IGNORECASE)
    cleaned = [clean_text(item) for item in parts if clean_text(item)]
    return ", ".join(dict.fromkeys(cleaned))


def infer_musicians_from_text(value: str | None) -> str:
    text = clean_text(value)
    if not text:
        return ""
    names: list[str] = []
    for match in PERSON_NAME_RE.finditer(text):
        candidate = clean_text(match.group(1))
        if not candidate:
            continue
        tokens = {token.casefold() for token in candidate.split()}
        if tokens & PERSON_STOPWORDS:
            continue
        names.append(candidate)
    return normalize_musicians(", ".join(names))


def sanitize_description(value: str | None, max_length: int = 800) -> str:
    text = clean_text(value)
    if not text:
        return ""
    # Remove common inline CSS/comment noise that appears in some schema descriptions.
    text = COMMENT_RE.sub(" ", text)
    text = CSS_BLOCK_RE.sub(" ", text)
    text = clean_text(text)
    return text[:max_length]
