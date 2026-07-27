#!/usr/bin/env python3
"""Merge the committed historical snapshot into the website-facing waters dataset.

This script does not download or rebuild the 2014-2025 archive. It treats
``data/stocking_events.json`` as a fixed, reviewed input and overlays its dates
and counts onto ``data/waters.json`` after the current CPW report is refreshed.
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

GENERIC_NAMES = {"atlas", "fishing atlas", "map", "link", "view"}


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def normalize_archive_events(payload: dict[str, Any]) -> list[dict[str, Any]]:
    events = payload.get("events", [])
    if not isinstance(events, list):
        raise RuntimeError("Historical snapshot is missing an events list")

    normalized: list[dict[str, Any]] = []
    for event in events:
        if not isinstance(event, dict):
            continue
        atlas_id = event.get("atlas_id")
        name = str(event.get("water_name") or "").strip()
        stocking_date = str(event.get("stocking_date") or "").strip()
        if not isinstance(atlas_id, int) or not name or not stocking_date:
            continue
        if name.casefold() in GENERIC_NAMES:
            raise RuntimeError(f"Historical snapshot contains generic water name {name!r}")
        normalized.append({"atlas_id": atlas_id, "water_name": name, "stocking_date": stocking_date})

    if not normalized:
        raise RuntimeError("Historical snapshot contains no usable Atlas-linked events")
    return normalized


def merge_payloads(waters_payload: dict[str, Any], archive_payload: dict[str, Any]) -> dict[str, Any]:
    archive_events = normalize_archive_events(archive_payload)
    archive_by_id: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for event in archive_events:
        archive_by_id[event["atlas_id"]].append(event)

    waters = waters_payload.get("waters", [])
    if not isinstance(waters, list):
        raise RuntimeError("Website dataset is missing a waters list")

    merged_event_keys: set[tuple[int, str]] = set()
    matched_archive_ids: set[int] = set()

    for water in waters:
        atlas_id = water.get("atlas_id")
        if not isinstance(atlas_id, int):
            continue

        historical = archive_by_id.get(atlas_id, [])
        if historical:
            matched_archive_ids.add(atlas_id)

        dates = {str(value) for value in water.get("stocking_dates", []) if value}
        for event in historical:
            dates.add(event["stocking_date"])
            merged_event_keys.add((atlas_id, event["stocking_date"]))

        sorted_dates = sorted(dates, reverse=True)
        water["stocking_dates"] = sorted_dates
        water["historical_event_count"] = len(sorted_dates)
        if sorted_dates:
            water["latest_report_date"] = sorted_dates[0]
        water["archive_event_count"] = len({event["stocking_date"] for event in historical})
        water["archive_first_date"] = min((event["stocking_date"] for event in historical), default=None)
        water["archive_last_date"] = max((event["stocking_date"] for event in historical), default=None)

    summary = waters_payload.setdefault("summary", {})
    summary["archive_snapshot_events"] = len(archive_events)
    summary["archive_snapshot_atlas_ids"] = len(archive_by_id)
    summary["archive_ids_matched_to_map"] = len(matched_archive_ids)
    summary["archive_ids_not_yet_enriched"] = len(set(archive_by_id) - matched_archive_ids)
    summary["combined_unique_stocking_dates"] = len(merged_event_keys)
    summary["historical_snapshot_generated_at"] = archive_payload.get("generated_at")

    waters_payload["historical_snapshot"] = {
        "source": "data/stocking_events.json",
        "generated_at": archive_payload.get("generated_at"),
        "events": len(archive_events),
        "atlas_ids": len(archive_by_id),
        "matched_atlas_ids": len(matched_archive_ids),
        "unmatched_atlas_ids": sorted(set(archive_by_id) - matched_archive_ids),
    }
    return waters_payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--waters", type=Path, default=Path("data/waters.json"))
    parser.add_argument("--archive", type=Path, default=Path("data/stocking_events.json"))
    args = parser.parse_args()

    merged = merge_payloads(read_json(args.waters), read_json(args.archive))
    write_json(args.waters, merged)
    print(json.dumps(merged.get("historical_snapshot", {}), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
