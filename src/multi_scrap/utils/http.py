from __future__ import annotations

from dataclasses import dataclass
import re
from urllib.parse import urljoin

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
    session.trust_env = False
    session.headers.update(
        {
            "User-Agent": settings.user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "es-AR,es;q=0.9,en;q=0.8",
        }
    )
    return session


def _is_challenge_page(text: str) -> bool:
    lowered = (text or "").casefold()
    return (
        "just a moment" in lowered
        or "verifying" in lowered
        or "verify you are human" in lowered
        or "checking your browser" in lowered
        or "please wait while your request is being verified" in lowered
        or "cf-chl" in lowered
        or "captcha" in lowered
    )


def _is_soft_ok(status_code: int, html: str) -> bool:
    return status_code in {403, 406, 415} and len(html or "") >= 1200 and not _is_challenge_page(html)


def _extract_client_redirect(html: str, base_url: str) -> str:
    text = html or ""

    # Meta refresh redirects.
    meta_match = re.search(
        r'(?is)<meta[^>]+http-equiv=["\']?refresh["\']?[^>]+content=["\'][^"\']*url=([^"\';>]+)',
        text,
    )
    if meta_match:
        return urljoin(base_url, meta_match.group(1).strip())

    # JavaScript redirects (setTimeout/location.href/location.replace).
    js_patterns = [
        r"""(?is)location\.href\s*=\s*["']([^"']+)["']""",
        r"""(?is)window\.location\s*=\s*["']([^"']+)["']""",
        r"""(?is)window\.location\.href\s*=\s*["']([^"']+)["']""",
        r"""(?is)location\.replace\(\s*["']([^"']+)["']\s*\)""",
    ]
    for pattern in js_patterns:
        match = re.search(pattern, text)
        if match:
            return urljoin(base_url, match.group(1).strip())
    return ""


def fetch_html(session: requests.Session, url: str, timeout_seconds: int) -> FetchResult:
    attempts = [
        {},
        {
            "Upgrade-Insecure-Requests": "1",
            "Pragma": "no-cache",
            "Cache-Control": "no-cache",
            "Referer": url,
        },
    ]
    last_error = ""
    timeout = max(timeout_seconds, 5)

    for headers in attempts:
        try:
            response = session.get(url, timeout=timeout, headers=headers, allow_redirects=True)
        except requests.RequestException as exc:
            last_error = str(exc)
            continue

        html = response.text or ""
        if response.ok or _is_soft_ok(response.status_code, html):
            redirect_url = _extract_client_redirect(html, response.url)
            if redirect_url and redirect_url != response.url:
                try:
                    redirected = session.get(redirect_url, timeout=timeout, headers=headers, allow_redirects=True)
                    if redirected.ok:
                        return FetchResult(
                            url=redirected.url,
                            status_code=redirected.status_code,
                            html=redirected.text or "",
                            ok=True,
                            error="",
                        )
                except requests.RequestException:
                    pass
            return FetchResult(
                url=response.url,
                status_code=response.status_code,
                html=html,
                ok=True,
                error="",
            )

        last_error = f"HTTP {response.status_code}"
        if response.status_code not in {403, 406, 415, 429, 500, 502, 503, 504}:
            return FetchResult(
                url=response.url,
                status_code=response.status_code,
                html=html,
                ok=False,
                error=last_error,
            )

    return FetchResult(url=url, status_code=0, html="", ok=False, error=last_error or "request failed")
