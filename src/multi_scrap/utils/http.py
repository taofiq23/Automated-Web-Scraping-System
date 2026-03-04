from __future__ import annotations

from dataclasses import dataclass

import requests

from multi_scrap.settings import Settings


@dataclass(slots=True)
class FetchResult:
    url: str
    status_code: int
    html: str
    ok: bool
    error: str = ""


def build_session(settings: Settings) -> requests.Session:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": settings.user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.8,es;q=0.7",
        }
    )
    return session


def fetch_html(session: requests.Session, url: str, timeout_seconds: int) -> FetchResult:
    try:
        response = session.get(url, timeout=timeout_seconds)
        return FetchResult(
            url=response.url,
            status_code=response.status_code,
            html=response.text,
            ok=response.ok,
            error="" if response.ok else f"HTTP {response.status_code}",
        )
    except Exception as exc:  # noqa: BLE001
        return FetchResult(url=url, status_code=0, html="", ok=False, error=str(exc))
