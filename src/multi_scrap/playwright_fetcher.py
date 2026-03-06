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
            page = browser.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=settings.playwright_timeout_ms)
            try:
                page.wait_for_load_state("networkidle", timeout=10000)
            except Exception:  # noqa: BLE001
                pass
            page.wait_for_timeout(1500)
            html = ""
            content_error = ""
            for _ in range(3):
                try:
                    html = page.content()
                    content_error = ""
                    break
                except Exception as exc:  # noqa: BLE001
                    content_error = str(exc)
                    page.wait_for_timeout(1500)
            if not html:
                browser.close()
                return RenderResult(ok=False, error=content_error or "Failed to capture rendered HTML")
            final_url = page.url
            browser.close()
        return RenderResult(html=html, final_url=final_url, ok=True)
    except Exception as exc:  # noqa: BLE001
        return RenderResult(ok=False, error=str(exc))
