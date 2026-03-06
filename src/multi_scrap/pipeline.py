from __future__ import annotations

from collections import deque
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Iterable

from multi_scrap.extractors import extract_events_from_html
from multi_scrap.models import RawEvent, SourceConfig
from multi_scrap.normalize import drop_invalid, normalize_event
from multi_scrap.playwright_fetcher import render_html_with_playwright
from multi_scrap.settings import Settings
from multi_scrap.utils.diagnostics import format_error, format_info
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
            futures = {pool.submit(self.scrape_source, source): source for source in enabled_sources}
            for future in as_completed(futures):
                source = futures[future]
                try:
                    events, summary = future.result()
                except Exception as exc:  # noqa: BLE001
                    summary = SourceRunSummary(
                        source_id=source.source_id,
                        source_url=source.source_url,
                        mode=source.mode,
                        fetched_pages=0,
                        extracted_events=0,
                        errors=[format_error(source.source_url, f"Unhandled source exception: {exc}")],
                    )
                    events = []
                all_events.extend(events)
                summaries.append(summary)
        return PipelineResult(events=all_events, source_summaries=summaries)

    def scrape_source(self, source: SourceConfig) -> tuple[list[RawEvent], SourceRunSummary]:
        summary = SourceRunSummary(source_id=source.source_id, source_url=source.source_url, mode=source.mode)
        session = build_session(self.settings)
        base_url = source.list_url or source.source_url
        events: list[RawEvent] = []
        queue: deque[tuple[str, int]] = deque([(base_url, 0)])
        visited: set[str] = set()
        tried_source_fallback = False

        while queue and summary.fetched_pages < self.settings.max_pages_per_source:
            url, depth = queue.popleft()
            if url in visited:
                continue
            visited.add(url)

            fetched = fetch_html(session, url, timeout_seconds=self.settings.request_timeout_seconds)
            summary.fetched_pages += 1
            if not fetched.ok:
                if depth == 0:
                    summary.errors.append(format_error(url, fetched.error))
                    can_fallback = (
                        bool(source.source_url)
                        and source.source_url != url
                        and not tried_source_fallback
                        and source.source_url not in visited
                    )
                    if can_fallback:
                        tried_source_fallback = True
                        queue.appendleft((source.source_url, 0))
                continue

            events.extend(extract_events_from_html(fetched.html, source, fetched.url))
            if depth >= self.settings.link_crawl_depth:
                continue

            candidate_links = extract_candidate_event_links(
                fetched.html,
                base_url=fetched.url,
                include_patterns=source.include_link_patterns,
                exclude_patterns=source.exclude_link_patterns,
                max_links=self.settings.max_event_links_per_source,
            )
            for link in candidate_links:
                if link in visited:
                    continue
                queue.append((link, depth + 1))

        has_valid_static_events = any(event.event_name and event.date for event in events)
        should_try_playwright = self.settings.enable_playwright and not has_valid_static_events
        if should_try_playwright:
            playwright_target = source.source_url or base_url
            rendered = render_html_with_playwright(playwright_target, self.settings)
            if not rendered.ok:
                summary.errors.append(format_error("playwright", rendered.error))
            else:
                summary.fetched_pages += 1
                rendered_base = rendered.final_url or playwright_target
                events.extend(extract_events_from_html(rendered.html, source, rendered_base))

                rendered_links = extract_candidate_event_links(
                    rendered.html,
                    base_url=rendered_base,
                    include_patterns=source.include_link_patterns,
                    exclude_patterns=source.exclude_link_patterns,
                    max_links=self.settings.max_event_links_per_source,
                )
                for link in rendered_links:
                    if link in visited:
                        continue
                    if summary.fetched_pages >= self.settings.max_pages_per_source:
                        break
                    visited.add(link)
                    fetched = fetch_html(session, link, timeout_seconds=self.settings.request_timeout_seconds)
                    summary.fetched_pages += 1
                    if not fetched.ok:
                        continue
                    events.extend(extract_events_from_html(fetched.html, source, fetched.url))

        normalized = [normalize_event(event, source) for event in events]
        valid_events = drop_invalid(normalized)
        if normalized and not valid_events:
            summary.errors.append(
                format_info(
                    "VALIDATION_DROP_ALL",
                    source.source_id,
                    detail=f"candidate_events={len(normalized)}; valid_events=0",
                )
            )
        elif not normalized and not summary.errors:
            summary.errors.append(format_info("EXTRACTION_EMPTY", source.source_id))
        summary.extracted_events = len(valid_events)
        return valid_events, summary
