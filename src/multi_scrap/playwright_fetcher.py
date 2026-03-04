from __future__ import annotations

from dataclasses import dataclass

from multi_scrap.settings import Settings


@dataclass(slots=True)
class RenderResult:
    html: str = ""
    final_url: str = ""
    ok: bool = False
    error: str = ""


def render_html_with_playwright(url: str, settings: Settings) -> RenderResult:
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:  # noqa: BLE001
        return RenderResult(ok=False, error=f"Playwright not available: {exc}")

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(user_agent=settings.user_agent)
            page.goto(url, wait_until="domcontentloaded", timeout=settings.playwright_timeout_ms)
            page.wait_for_timeout(1500)
            html = page.content()
            final_url = page.url
            browser.close()
        return RenderResult(html=html, final_url=final_url, ok=True)
    except Exception as exc:  # noqa: BLE001
        return RenderResult(ok=False, error=str(exc))
