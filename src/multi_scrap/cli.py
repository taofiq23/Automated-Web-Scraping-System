from __future__ import annotations

import argparse
import logging
import warnings
from dataclasses import replace
from datetime import date, datetime, timezone
from pathlib import Path

from bs4 import XMLParsedAsHTMLWarning

from multi_scrap.dedup import deduplicate_events
from multi_scrap.exporters import export_events_to_csv
from multi_scrap.pipeline import ScraperPipeline
from multi_scrap.settings import build_settings
from multi_scrap.sheets import GoogleSheetsWriter
from multi_scrap.models import SourceConfig, sheet_header_for_language
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
    run_cmd.add_argument(
        "--include-disabled",
        action="store_true",
        help="Try sources even if disabled in config (automatic recovery pass)",
    )
    run_cmd.add_argument(
        "--force-auto-mode",
        action="store_true",
        help="Force all sources to auto mode (requests + Playwright fallback)",
    )
    return parser.parse_args()


def _build_effective_sources(
    sources: list[SourceConfig],
    include_disabled: bool,
    force_auto_mode: bool,
) -> list[SourceConfig]:
    effective: list[SourceConfig] = []
    for source in sources:
        enabled = source.enabled or include_disabled
        mode = "auto" if force_auto_mode else source.mode
        effective.append(
            replace(
                source,
                enabled=enabled,
                mode=mode,
            )
        )
    return effective


def run_weekly(args: argparse.Namespace) -> None:
    settings = build_settings()
    yaml_path = Path(args.sources_yaml)
    if yaml_path.exists():
        sources = load_sources_from_yaml(yaml_path)
    else:
        sources = load_sources_from_csv(args.sources_csv)

    effective_sources = _build_effective_sources(
        sources=sources,
        include_disabled=args.include_disabled,
        force_auto_mode=args.force_auto_mode,
    )

    pipeline = ScraperPipeline(settings=settings)
    result = pipeline.run(effective_sources)
    deduped = deduplicate_events(result.events)
    sheet_header = sheet_header_for_language(settings.sheet_header_language)

    week_start = _parse_week_start(args.week_start)
    if week_start is None:
        week_start, week_end = monday_sunday_bounds(upcoming=not args.current_week)
    else:
        week_end = week_start.fromordinal(week_start.toordinal() + 6)

    weekly_events = filter_events_for_week(deduped, week_start, week_end)
    weekly_events.sort(key=lambda event: (event.date, event.time, event.venue, event.event_name))

    all_events_path = settings.output_dir / "all_events_deduped.csv"
    weekly_path = settings.output_dir / f"weekly_events_{week_start.isoformat()}_{week_end.isoformat()}.csv"
    export_events_to_csv(all_events_path, deduped, header=sheet_header)
    export_events_to_csv(weekly_path, weekly_events, header=sheet_header)

    total_configured = len(sources)
    total_eligible = sum(1 for source in effective_sources if source.enabled)
    total_inactive = total_configured - total_eligible
    contributing_sources = sum(1 for row in result.source_summaries if row.extracted_events > 0)
    reviewed_no_additions = max(total_eligible - contributing_sources, 0)
    publish_tab = _week_tab_name(settings.google_sheet_prefix, week_start, week_end)
    rows_written_to_sheet = 0

    summary_path = settings.output_dir / f"run_summary_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.txt"
    summary_lines = [
        f"Total sources configured: {total_configured}",
        f"Total sources active this run: {total_eligible}",
        f"Sources inactive by configuration: {total_inactive}",
        f"Sources contributing events: {contributing_sources}",
        f"Sources reviewed with no event additions: {reviewed_no_additions}",
        f"Automatic override include-disabled: {args.include_disabled}",
        f"Automatic override force-auto-mode: {args.force_auto_mode}",
        f"Total source runs: {len(result.source_summaries)}",
        f"Total events extracted (pre-dedup): {len(result.events)}",
        f"Total events after dedup: {len(deduped)}",
        f"Weekly window: {week_start.isoformat()} -> {week_end.isoformat()}",
        f"Weekly events count: {len(weekly_events)}",
        f"CSV (all deduped): {all_events_path}",
        f"CSV (weekly): {weekly_path}",
        f"Google sheet tab: {publish_tab}",
        "Rows written to Google Sheets: 0",
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
        writer = GoogleSheetsWriter(
            service_account_file=settings.google_service_account_file,
            spreadsheet_id=settings.google_spreadsheet_id,
            price_currency_label=settings.google_price_currency_label,
            header=sheet_header,
        )
        rows_written_to_sheet = writer.write_events(publish_tab, weekly_events)
        logger.info(
            "Weekly publish summary | sheet_id=%s | tab=%s | rows_written=%s",
            settings.google_spreadsheet_id,
            publish_tab,
            rows_written_to_sheet,
        )
        summary_lines = [
            line if not line.startswith("Rows written to Google Sheets:") else f"Rows written to Google Sheets: {rows_written_to_sheet}"
            for line in summary_lines
        ]
        summary_path.write_text("\n".join(summary_lines), encoding="utf-8")
        print(f"Google Sheet updated: {publish_tab}")

    logger.info(
        "Run overview | active_sources=%s/%s | contributing_sources=%s | reviewed_no_additions=%s | weekly_rows=%s | sheet_tab=%s | sheet_rows=%s",
        total_eligible,
        total_configured,
        contributing_sources,
        reviewed_no_additions,
        len(weekly_events),
        publish_tab,
        rows_written_to_sheet,
    )


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
    warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)
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
