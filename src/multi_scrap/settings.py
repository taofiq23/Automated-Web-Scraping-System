from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


load_dotenv()


@dataclass(slots=True)
class Settings:
    request_timeout_seconds: int = int(os.getenv("REQUEST_TIMEOUT_SECONDS", "25"))
    user_agent: str = os.getenv(
        "SCRAPER_USER_AGENT",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    )
    max_event_links_per_source: int = int(os.getenv("MAX_EVENT_LINKS_PER_SOURCE", "25"))
    max_pages_per_source: int = int(os.getenv("MAX_PAGES_PER_SOURCE", "40"))
    link_crawl_depth: int = int(os.getenv("LINK_CRAWL_DEPTH", "2"))
    source_workers: int = int(os.getenv("SOURCE_WORKERS", "6"))
    enable_playwright: bool = os.getenv("ENABLE_PLAYWRIGHT", "true").strip().lower() == "true"
    playwright_timeout_ms: int = int(os.getenv("PLAYWRIGHT_TIMEOUT_MS", "45000"))
    output_dir: Path = Path(os.getenv("OUTPUT_DIR", "output"))
    google_service_account_file: str = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "")
    google_spreadsheet_id: str = os.getenv("GOOGLE_SPREADSHEET_ID", "")
    google_sheet_prefix: str = os.getenv("GOOGLE_SHEET_PREFIX", "Week")
    google_price_currency_label: str = os.getenv("GOOGLE_PRICE_CURRENCY_LABEL", "ARS")
    sheet_header_language: str = os.getenv("SHEET_HEADER_LANGUAGE", "es")


def build_settings() -> Settings:
    settings = Settings(
        request_timeout_seconds=int(os.getenv("REQUEST_TIMEOUT_SECONDS", "25")),
        user_agent=os.getenv(
            "SCRAPER_USER_AGENT",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        ),
        max_event_links_per_source=int(os.getenv("MAX_EVENT_LINKS_PER_SOURCE", "25")),
        max_pages_per_source=int(os.getenv("MAX_PAGES_PER_SOURCE", "40")),
        link_crawl_depth=int(os.getenv("LINK_CRAWL_DEPTH", "2")),
        source_workers=int(os.getenv("SOURCE_WORKERS", "6")),
        enable_playwright=os.getenv("ENABLE_PLAYWRIGHT", "true").strip().lower() == "true",
        playwright_timeout_ms=int(os.getenv("PLAYWRIGHT_TIMEOUT_MS", "45000")),
        output_dir=Path(os.getenv("OUTPUT_DIR", "output")),
        google_service_account_file=os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", ""),
        google_spreadsheet_id=os.getenv("GOOGLE_SPREADSHEET_ID", ""),
        google_sheet_prefix=os.getenv("GOOGLE_SHEET_PREFIX", "Week"),
        google_price_currency_label=os.getenv("GOOGLE_PRICE_CURRENCY_LABEL", "ARS"),
        sheet_header_language=os.getenv("SHEET_HEADER_LANGUAGE", "es"),
    )
    settings.output_dir.mkdir(parents=True, exist_ok=True)
    return settings
