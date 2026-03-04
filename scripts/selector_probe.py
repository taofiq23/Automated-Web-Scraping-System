import argparse

import requests
from bs4 import BeautifulSoup


def static_probe(url: str, selectors: list[str]) -> None:
    response = requests.get(url, timeout=25)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    print(f"Static HTML fetched: {response.url} (status={response.status_code})")
    for selector in selectors:
        nodes = soup.select(selector)
        print(f"[static] {selector} -> {len(nodes)} matches")
        if nodes:
            sample = nodes[0].get_text(" ", strip=True)
            print(f"  sample: {sample[:150]}")


def playwright_probe(url: str, selectors: list[str]) -> None:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=45000)
        page.wait_for_timeout(1500)
        print(f"Playwright page loaded: {page.url}")
        for selector in selectors:
            locator = page.locator(selector)
            count = locator.count()
            print(f"[playwright] {selector} -> {count} matches")
            if count:
                sample = locator.first.inner_text(timeout=10000).strip()
                print(f"  sample: {sample[:150]}")
        browser.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify selectors against a URL")
    parser.add_argument("--url", required=True)
    parser.add_argument("--selector", dest="selectors", action="append", required=True)
    parser.add_argument("--playwright", action="store_true", help="Also validate selector against JS-rendered DOM")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    static_probe(args.url, args.selectors)
    if args.playwright:
        playwright_probe(args.url, args.selectors)


if __name__ == "__main__":
    main()
