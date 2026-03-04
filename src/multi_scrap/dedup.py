from __future__ import annotations

from multi_scrap.models import RawEvent


def deduplicate_events(events: list[RawEvent]) -> list[RawEvent]:
    best_by_key: dict[tuple[str, str, str], RawEvent] = {}
    for event in events:
        key = event.dedup_key()
        if key not in best_by_key:
            best_by_key[key] = event
            continue
        if event.score() > best_by_key[key].score():
            best_by_key[key] = event
    return list(best_by_key.values())
