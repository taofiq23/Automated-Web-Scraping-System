from __future__ import annotations

import csv
from pathlib import Path

from multi_scrap.models import RawEvent, SHEET_HEADER


def export_events_to_csv(path: str | Path, events: list[RawEvent]) -> Path:
    out_path = Path(path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(SHEET_HEADER)
        for event in events:
            writer.writerow(event.as_sheet_row())
    return out_path
