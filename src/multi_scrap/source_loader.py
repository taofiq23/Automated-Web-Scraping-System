from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

import yaml

from multi_scrap.models import SourceConfig


def _read_text_with_fallbacks(path: Path) -> str:
    raw = path.read_bytes()
    for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _repair_mojibake(value: str) -> str:
    # Common case: UTF-8 text decoded as latin-1/cp1252 (e.g. "CafÃ©" -> "Café")
    if "Ã" not in value and "Â" not in value:
        return value
    try:
        return value.encode("latin-1").decode("utf-8")
    except UnicodeError:
        return value


def load_sources_from_csv(path: str | Path) -> list[SourceConfig]:
    csv_path = Path(path)
    content = _read_text_with_fallbacks(csv_path)
    reader = csv.DictReader(content.splitlines())
    sources: list[SourceConfig] = []
    for row in reader:
        source_id = (row.get("club_id") or "").strip()
        venue_name = _repair_mojibake((row.get("nombre") or "").strip())
        web_url = (row.get("web_url") or "").strip()
        instagram = _repair_mojibake((row.get("instagram_handle") or "").strip())
        if not source_id or not web_url:
            continue
        sources.append(
            SourceConfig(
                source_id=source_id,
                venue_name=venue_name or source_id,
                source_url=web_url,
                instagram_handle=instagram,
                mode="auto",
            )
        )
    return sources


def load_sources_from_yaml(path: str | Path) -> list[SourceConfig]:
    yaml_path = Path(path)
    payload = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
    items = payload.get("sources", [])
    sources: list[SourceConfig] = []
    for item in items:
        source_id = (item.get("source_id") or "").strip()
        venue_name = _repair_mojibake((item.get("venue_name") or source_id).strip())
        source_url = (item.get("source_url") or "").strip()
        instagram_handle = _repair_mojibake((item.get("instagram_handle") or "").strip())
        list_url = (item.get("list_url") or "").strip()
        sources.append(
            SourceConfig(
                source_id=source_id,
                venue_name=venue_name or source_id,
                source_url=source_url,
                instagram_handle=instagram_handle,
                enabled=bool(item.get("enabled", True)),
                mode=item.get("mode", "auto"),
                include_link_patterns=item.get("include_link_patterns", []) or [],
                exclude_link_patterns=item.get("exclude_link_patterns", []) or [],
                list_url=list_url,
                metadata=item.get("metadata", {}) or {},
            )
        )
    return sources


def dump_sources_yaml(path: str | Path, sources: list[SourceConfig]) -> None:
    yaml_path = Path(path)
    yaml_path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {
        "sources": [
            {
                "source_id": source.source_id,
                "venue_name": source.venue_name,
                "source_url": source.source_url,
                "instagram_handle": source.instagram_handle,
                "enabled": source.enabled,
                "mode": source.mode,
                "list_url": source.list_url,
                "include_link_patterns": source.include_link_patterns,
                "exclude_link_patterns": source.exclude_link_patterns,
                "metadata": source.metadata,
            }
            for source in sources
        ]
    }
    yaml_path.write_text(yaml.safe_dump(payload, sort_keys=False, allow_unicode=True), encoding="utf-8")
