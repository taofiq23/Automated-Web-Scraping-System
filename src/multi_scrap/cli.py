from __future__ import annotations

import argparse
import logging
from datetime import date, datetime, timezone
from pathlib import Path

from multi_scrap.dedup import deduplicate_events
from multi_scrap.exporters import export_events_to_csv
from multi_scrap.pipeline import ScraperPipeline
from multi_scrap.settings import build_settings
from multi_scrap.sheets import GoogleSheetsWriter
from multi_scrap.source_loader import load_sources_from_csv, load_sources_from_yaml
from multi_scrap.utils.dates import monday_sunday_bounds
from multi_scrap.week_filter import filter_events_for_week


logger = logging.getLogger(__name__)


def _parse_week_start(value: str | None) -> date | None:
    if not value:
        return None
    return datetime.strptime(value, "%Y-%m-%d").date()


def _week_tab_name(prefix: str, week_start: date, week_end: date) -> str:
    clean_prefix = prefix.strip() or "Week"
    return f"{clean_prefix} {week_start.isoformat()} to {week_end.isoformat()}"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Weekly multi-source events scraping pipeline")
    sub = parser.add_subparsers(dest="command", required=True)

    analyze_cmd = sub.add_parser("analyze", help="Analyze feasibility for all sources")
    analyze_cmd.add_argument("--input-csv", required=True)
    analyze_cmd.add_argument("--output-csv", default="output/source_analysis.csv")
    analyze_cmd.add_argument("--output-md", default="docs/FEASIBILITY_MATRIX.md")
    analyze_cmd.add_argument("--output-config-yaml", default="config/sources.yml")

    run_cmd = sub.add_parser("run-weekly", help="Scrape events and publish weekly sheet")
    run_cmd.add_argument("--sources-csv", default="JM_clubes_scrappinglistxlsxclubs.csv")
    run_cmd.add_argument("--sources-yaml", default="config/sources.yml")
    run_cmd.add_argument("--week-start", default="", help="Week start date yyyy-mm-dd")
    run_cmd.add_argument(
        "--current-week",
        action="store_true",
        help="Use current week instead of upcoming week",
    )
    run_cmd.add_argument("--publish-gsheets", action="store_true")
    return parser.parse_args()


def run_weekly(args: argparse.Namespace) -> None:
    settings = build_settings()
    yaml_path = Path(args.sources_yaml)
    if yaml_path.exists():
        sources = load_sources_from_yaml(yaml_path)
    else:
        sources = load_sources_from_csv(args.sources_csv)

    pipeline = ScraperPipeline(settings=settings)
    result = pipeline.run(sources)
    deduped = deduplicate_events(result.events)

    week_start = _parse_week_start(args.week_start)
    if week_start is None:
        week_start, week_end = monday_sunday_bounds(upcoming=not args.current_week)
    else:
        week_end = week_start.fromordinal(week_start.toordinal() + 6)

    weekly_events = filter_events_for_week(deduped, week_start, week_end)
    weekly_events.sort(key=lambda event: (event.date, event.time, event.venue, event.event_name))

    all_events_path = settings.output_dir / "all_events_deduped.csv"
    weekly_path = settings.output_dir / f"weekly_events_{week_start.isoformat()}_{week_end.isoformat()}.csv"
    export_events_to_csv(all_events_path, deduped)
    export_events_to_csv(weekly_path, weekly_events)

    summary_path = settings.output_dir / f"run_summary_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.txt"
    summary_lines = [
        f"Total sources configured: {len(sources)}",
        f"Total source runs: {len(result.source_summaries)}",
        f"Total events extracted (pre-dedup): {len(result.events)}",
        f"Total events after dedup: {len(deduped)}",
        f"Weekly window: {week_start.isoformat()} -> {week_end.isoformat()}",
        f"Weekly events count: {len(weekly_events)}",
        f"CSV (all deduped): {all_events_path}",
        f"CSV (weekly): {weekly_path}",
        "",
        "Per-source summary:",
    ]
    for source_summary in result.source_summaries:
        err = "; ".join(source_summary.errors) if source_summary.errors else "-"
        summary_lines.append(
            f"{source_summary.source_id} | pages={source_summary.fetched_pages} | "
            f"events={source_summary.extracted_events} | errors={err}"
        )
    summary_path.write_text("\n".join(summary_lines), encoding="utf-8")

    print(f"Run complete. Weekly events: {len(weekly_events)}")
    print(f"All events CSV: {all_events_path}")
    print(f"Weekly events CSV: {weekly_path}")
    print(f"Run summary: {summary_path}")

    if args.publish_gsheets:
        if not settings.google_service_account_file or not settings.google_spreadsheet_id:
            raise RuntimeError(
                "GOOGLE_SERVICE_ACCOUNT_FILE and GOOGLE_SPREADSHEET_ID are required for --publish-gsheets"
            )
        title = _week_tab_name(settings.google_sheet_prefix, week_start, week_end)
        writer = GoogleSheetsWriter(
            service_account_file=settings.google_service_account_file,
            spreadsheet_id=settings.google_spreadsheet_id,
            price_currency_label=settings.google_price_currency_label,
        )
        rows_written = writer.write_events(title, weekly_events)
        logger.info(
            "Weekly publish summary | sheet_id=%s | tab=%s | rows_written=%s",
            settings.google_spreadsheet_id,
            title,
            rows_written,
        )
        print(f"Google Sheet updated: {title}")


def run_analysis(args: argparse.Namespace) -> None:
    from multi_scrap.source_analysis import (
        analyze_sources,
        build_source_config_from_analysis,
        write_analysis_csv,
        write_analysis_markdown,
    )
    from multi_scrap.source_loader import dump_sources_yaml, load_sources_from_csv

    sources = load_sources_from_csv(args.input_csv)
    rows = analyze_sources(sources)
    write_analysis_csv(args.output_csv, rows)
    write_analysis_markdown(args.output_md, rows)
    configured = build_source_config_from_analysis(sources, rows)
    dump_sources_yaml(args.output_config_yaml, configured)
    print(f"Analysis completed for {len(rows)} sources")
    print(f"CSV report: {args.output_csv}")
    print(f"Markdown report: {args.output_md}")
    print(f"Config YAML: {args.output_config_yaml}")


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    args = parse_args()
    if args.command == "analyze":
        run_analysis(args)
        return
    if args.command == "run-weekly":
        run_weekly(args)
        return
    raise RuntimeError(f"Unknown command: {args.command}")


if __name__ == "__main__":
    main()
