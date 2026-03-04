from __future__ import annotations

import argparse
import csv
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from multi_scrap.models import SourceConfig
from multi_scrap.settings import build_settings
from multi_scrap.source_loader import dump_sources_yaml, load_sources_from_csv
from multi_scrap.utils.http import build_session, fetch_html


@dataclass(slots=True)
class SourceAnalysis:
    source_id: str
    venue_name: str
    source_url: str
    status_code: int
    platform: str
    has_event_json_ld: bool
    event_keyword_hits: int
    js_heavy: bool
    recommendation: str
    feasibility: str
    note: str = ""


EVENT_HINT_RE = re.compile(r"(?i)(event|agenda|programaci[oó]n|show|ticket|entrada|concierto|live)")


def detect_platform(url: str, html: str) -> str:
    host = urlparse(url).netloc.lower()
    html_lower = html.lower()
    if "wordpress" in html_lower or "wp-content" in html_lower or "/wp-json/" in html_lower:
        return "wordpress"
    if "blogspot.com" in host:
        return "blogspot"
    if "alternativateatral.com" in host:
        return "alternativateatral"
    if "negocio.site" in host:
        return "google_business_site"
    if "gob.ar" in host:
        return "government_portal"
    if "wix" in html_lower:
        return "wix"
    if "__next" in html_lower:
        return "nextjs"
    return "custom"


def estimate_js_heavy(html: str) -> bool:
    soup = BeautifulSoup(html, "html.parser")
    body_text_len = len((soup.body.get_text(" ", strip=True) if soup.body else "").strip())
    has_app_root = bool(soup.select_one("#__next, #root"))
    script_count = len(soup.select("script[src]"))
    return has_app_root and script_count >= 5 and body_text_len < 800


def find_event_json_ld(html: str) -> bool:
    soup = BeautifulSoup(html, "html.parser")
    scripts = soup.select("script[type='application/ld+json']")
    for node in scripts:
        text = (node.string or node.get_text() or "").lower()
        if '"@type"' in text and "event" in text:
            return True
    return False


def score_feasibility(status_code: int, has_event_json_ld: bool, keyword_hits: int, js_heavy: bool) -> tuple[str, str]:
    if status_code < 200 or status_code >= 400:
        return "manual_review", "low"
    if has_event_json_ld:
        return "static", "high"
    if js_heavy:
        return "playwright", "medium"
    if keyword_hits >= 5:
        return "static", "medium"
    return "playwright", "medium"


def analyze_sources(sources: list[SourceConfig]) -> list[SourceAnalysis]:
    settings = build_settings()
    session = build_session(settings)
    results: list[SourceAnalysis] = []
    for source in sources:
        fetched = fetch_html(session, source.source_url, timeout_seconds=settings.request_timeout_seconds)
        html = fetched.html or ""
        platform = detect_platform(source.source_url, html) if fetched.ok else "unknown"
        has_jsonld = find_event_json_ld(html) if fetched.ok else False
        keyword_hits = len(EVENT_HINT_RE.findall(html)) if fetched.ok else 0
        js_heavy = estimate_js_heavy(html) if fetched.ok else False
        recommendation, feasibility = score_feasibility(fetched.status_code, has_jsonld, keyword_hits, js_heavy)
        note = ""
        if platform in {"alternativateatral", "government_portal", "google_business_site"}:
            note = "third_party_platform"
        results.append(
            SourceAnalysis(
                source_id=source.source_id,
                venue_name=source.venue_name,
                source_url=source.source_url,
                status_code=fetched.status_code,
                platform=platform,
                has_event_json_ld=has_jsonld,
                event_keyword_hits=keyword_hits,
                js_heavy=js_heavy,
                recommendation=recommendation,
                feasibility=feasibility,
                note=note,
            )
        )
    return results


def write_analysis_csv(path: str | Path, rows: list[SourceAnalysis]) -> Path:
    out_path = Path(path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "source_id",
                "venue_name",
                "source_url",
                "status_code",
                "platform",
                "has_event_json_ld",
                "event_keyword_hits",
                "js_heavy",
                "recommendation",
                "feasibility",
                "note",
            ]
        )
        for row in rows:
            writer.writerow(
                [
                    row.source_id,
                    row.venue_name,
                    row.source_url,
                    row.status_code,
                    row.platform,
                    row.has_event_json_ld,
                    row.event_keyword_hits,
                    row.js_heavy,
                    row.recommendation,
                    row.feasibility,
                    row.note,
                ]
            )
    return out_path


def write_analysis_markdown(path: str | Path, rows: list[SourceAnalysis]) -> Path:
    out_path = Path(path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Source Feasibility Matrix",
        "",
        "| ID | Venue | URL | HTTP | Platform | JSON-LD Event | JS Heavy | Recommended Method | Feasibility |",
        "|---|---|---|---:|---|---|---|---|---|",
    ]
    for row in rows:
        lines.append(
            "| {id} | {venue} | {url} | {status} | {platform} | {jsonld} | {js} | {rec} | {feas} |".format(
                id=row.source_id,
                venue=row.venue_name.replace("|", "/"),
                url=row.source_url,
                status=row.status_code,
                platform=row.platform,
                jsonld="yes" if row.has_event_json_ld else "no",
                js="yes" if row.js_heavy else "no",
                rec=row.recommendation,
                feas=row.feasibility,
            )
        )
    out_path.write_text("\n".join(lines), encoding="utf-8")
    return out_path


def build_source_config_from_analysis(sources: list[SourceConfig], analyses: list[SourceAnalysis]) -> list[SourceConfig]:
    by_id = {row.source_id: row for row in analyses}
    configured: list[SourceConfig] = []
    seen_urls: dict[str, str] = {}
    for source in sources:
        analysis = by_id.get(source.source_id)
        if not analysis:
            configured.append(source)
            continue
        normalized_url = source.source_url.strip().rstrip("/").casefold()
        duplicate_of = seen_urls.get(normalized_url)
        if duplicate_of is None:
            seen_urls[normalized_url] = source.source_id
        mode = analysis.recommendation if analysis.recommendation in {"static", "playwright"} else "auto"
        enabled = analysis.feasibility != "low" and duplicate_of is None
        configured.append(
            SourceConfig(
                source_id=source.source_id,
                venue_name=source.venue_name,
                source_url=source.source_url,
                instagram_handle=source.instagram_handle,
                enabled=enabled,
                mode=mode,
                include_link_patterns=[],
                exclude_link_patterns=[
                    r"instagram\.com",
                    r"facebook\.com",
                    r"whatsapp",
                    r"mailto:",
                ],
                metadata={
                    "platform": analysis.platform,
                    "feasibility": analysis.feasibility,
                    "analysis_note": analysis.note,
                    "duplicate_of_source_id": duplicate_of or "",
                },
            )
        )
    return configured


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze source scraping feasibility")
    parser.add_argument("--input-csv", required=True, help="Path to source CSV")
    parser.add_argument("--output-csv", default="output/source_analysis.csv", help="Output analysis CSV")
    parser.add_argument(
        "--output-md",
        default="docs/FEASIBILITY_MATRIX.md",
        help="Output markdown feasibility report",
    )
    parser.add_argument("--output-config-yaml", default="config/sources.yml", help="Generated source config YAML")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    sources = load_sources_from_csv(args.input_csv)
    analyses = analyze_sources(sources)
    write_analysis_csv(args.output_csv, analyses)
    write_analysis_markdown(args.output_md, analyses)
    configured_sources = build_source_config_from_analysis(sources, analyses)
    dump_sources_yaml(args.output_config_yaml, configured_sources)
    print(f"Analyzed {len(analyses)} sources")
    print(f"Analysis CSV: {args.output_csv}")
    print(f"Analysis Markdown: {args.output_md}")
    print(f"Generated source config: {args.output_config_yaml}")


if __name__ == "__main__":
    main()
