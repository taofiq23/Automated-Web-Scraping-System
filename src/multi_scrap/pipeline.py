from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Iterable

from multi_scrap.extractors import extract_events_from_html
from multi_scrap.models import RawEvent, SourceConfig
from multi_scrap.normalize import drop_invalid, normalize_event
from multi_scrap.playwright_fetcher import render_html_with_playwright
from multi_scrap.settings import Settings
from multi_scrap.utils.http import build_session, fetch_html
from multi_scrap.utils.links import extract_candidate_event_links


@dataclass(slots=True)
class SourceRunSummary:
    source_id: str
    source_url: str
    mode: str
    fetched_pages: int = 0
    extracted_events: int = 0
    errors: list[str] = field(default_factory=list)


@dataclass(slots=True)
class PipelineResult:
    events: list[RawEvent]
    source_summaries: list[SourceRunSummary]


class ScraperPipeline:
    def __init__(self, settings: Settings):
        self.settings = settings

    def run(self, sources: Iterable[SourceConfig]) -> PipelineResult:
        all_events: list[RawEvent] = []
        summaries: list[SourceRunSummary] = []
        enabled_sources = [source for source in sources if source.enabled]
        with ThreadPoolExecutor(max_workers=max(self.settings.source_workers, 1)) as pool:
            futures = [pool.submit(self.scrape_source, source) for source in enabled_sources]
            for future in as_completed(futures):
                events, summary = future.result()
                all_events.extend(events)
                summaries.append(summary)
        return PipelineResult(events=all_events, source_summaries=summaries)

    def scrape_source(self, source: SourceConfig) -> tuple[list[RawEvent], SourceRunSummary]:
        summary = SourceRunSummary(source_id=source.source_id, source_url=source.source_url, mode=source.mode)
        session = build_session(self.settings)
        base_url = source.list_url or source.source_url
        events: list[RawEvent] = []

        main_fetch = fetch_html(session, base_url, timeout_seconds=self.settings.request_timeout_seconds)
        summary.fetched_pages += 1
        if not main_fetch.ok:
            summary.errors.append(f"{base_url} -> {main_fetch.error}")
        else:
            events.extend(extract_events_from_html(main_fetch.html, source, main_fetch.url))
            candidate_links = extract_candidate_event_links(
                main_fetch.html,
                base_url=main_fetch.url,
                include_patterns=source.include_link_patterns,
                exclude_patterns=source.exclude_link_patterns,
                max_links=self.settings.max_event_links_per_source,
            )
            for link in candidate_links:
                child_fetch = fetch_html(session, link, timeout_seconds=self.settings.request_timeout_seconds)
                summary.fetched_pages += 1
                if not child_fetch.ok:
                    continue
                events.extend(extract_events_from_html(child_fetch.html, source, child_fetch.url))

        should_try_playwright = (
            self.settings.enable_playwright and source.mode in {"auto", "playwright"} and len(events) == 0
        )
        if should_try_playwright:
            rendered = render_html_with_playwright(base_url, self.settings)
            if not rendered.ok:
                summary.errors.append(f"playwright -> {rendered.error}")
            else:
                summary.fetched_pages += 1
                events.extend(extract_events_from_html(rendered.html, source, rendered.final_url or base_url))

        normalized = [normalize_event(event, source) for event in events]
        valid_events = drop_invalid(normalized)
        summary.extracted_events = len(valid_events)
        return valid_events, summary
