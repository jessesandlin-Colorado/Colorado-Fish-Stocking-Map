#!/usr/bin/env python3
"""Merge the fixed archive snapshot into the website's Atlas-enriched waters dataset."""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from update_data import (
    PROJECT_ROOT,
    PoliteHttpClient,
    clean,
    load_overrides,
    normalized_name,
    query_atlas,
)


def read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def event_name(event: dict[str, Any]) -> str:
    return clean(event.get("water_name") or event.get("name"))


def merge_archive(
    waters_payload: dict[str, Any],
    archive_payload: dict[str, Any],
    client: PoliteHttpClient,
    overrides: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    archive_events = [
        event for event in archive_payload.get("events", [])
        if event.get("atlas_id") is not None and event.get("stocking_date") and event_name(event)
    ]
    by_atlas: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for event in archive_events:
        by_atlas[int(event["atlas_id"])].append(event)

    existing = {
        int(water["atlas_id"]): dict(water)
        for water in waters_payload.get("waters", [])
        if water.get("atlas_id") is not None
    }

    enriched_new = 0
    unresolved = []
    for uid, events in sorted(by_atlas.items()):
        archive_dates = {event["stocking_date"] for event in events}
        names = sorted({event_name(event) for event in events if event_name(event)})
        atlas_url = next((event.get("atlas_url") for event in events if event.get("atlas_url")), "")

        if uid in existing:
            water = existing[uid]
            dates = set(water.get("stocking_dates") or []) | archive_dates
            water["stocking_dates"] = sorted(dates, reverse=True)
            water["latest_report_date"] = max(dates)
            water["historical_event_count"] = len(dates)
            water["archive_event_count"] = len(archive_dates)
            water["archive_first_date"] = min(archive_dates)
            water["archive_last_date"] = max(archive_dates)
            existing[uid] = water
            continue

        info = query_atlas(client, uid, names, overrides.get(str(uid), {}))
        if not info or info.get("lat") is None or info.get("lng") is None:
            unresolved.append({"atlas_id": uid, "names": names, "event_count": len(events)})
            continue

        dates = sorted(archive_dates, reverse=True)
        canonical_name = info.get("atlas_name") or names[0]
        existing[uid] = {
            "key": f"atlas-{uid}",
            "atlas_id": uid,
            "name": names[0],
            "normalized_name": normalized_name(names[0]),
            "atlas_url": atlas_url,
            "latest_report_date": dates[0],
            "stocking_dates": dates,
            "current_event_count": 0,
            "historical_event_count": len(dates),
            "archive_event_count": len(dates),
            "archive_first_date": dates[-1],
            "archive_last_date": dates[0],
            "species": [],
            "species_status": "not-queried-for-archive-only-water",
            "atlas_species_metadata": {"note": "Species enrichment is deferred until the water appears in a current report."},
            "canonical_name": canonical_name,
            **info,
        }
        enriched_new += 1

    waters = sorted(
        existing.values(),
        key=lambda item: (item.get("latest_report_date") or "", item.get("name") or ""),
        reverse=True,
    )

    live_summary = dict(waters_payload.get("summary") or {})
    archive_summary = dict(archive_payload.get("summary") or {})
    live_rows = int(live_summary.get("stocking_events") or 0)
    archive_rows = len(archive_events)
    combined_dates = {
        (event.get("atlas_id"), event.get("stocking_date"), event_name(event).casefold())
        for event in archive_events
    }
    for water in waters_payload.get("waters", []):
        for stocking_date in water.get("stocking_dates") or []:
            combined_dates.add((water.get("atlas_id"), stocking_date, clean(water.get("name")).casefold()))

    summary = {
        **live_summary,
        "stocking_events": len(combined_dates),
        "current_report_events": live_rows,
        "archive_events": archive_rows,
        "historical_events": len(combined_dates),
        "matched_waters": len(waters),
        "archive_unique_atlas_ids": len(by_atlas),
        "archive_only_waters_added": enriched_new,
        "archive_unresolved_waters": len(unresolved),
        "archive_earliest_date": archive_summary.get("earliest_date"),
        "archive_latest_date": archive_summary.get("latest_date"),
    }

    payload = {
        **waters_payload,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": summary,
        "waters": waters,
    }
    report = {
        "archive_events_read": archive_rows,
        "archive_unique_atlas_ids": len(by_atlas),
        "existing_live_waters": len(waters_payload.get("waters", [])),
        "archive_only_waters_added": enriched_new,
        "combined_waters": len(waters),
        "unresolved": unresolved,
    }
    return payload, report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    parser.add_argument("--overrides", type=Path, default=PROJECT_ROOT / "config" / "atlas_overrides.json")
    parser.add_argument("--cache-ttl-hours", type=int, default=24 * 365)
    args = parser.parse_args()

    waters_path = args.data_dir / "waters.json"
    archive_path = args.data_dir / "stocking_events.json"
    waters_payload = read_json(waters_path, {})
    archive_payload = read_json(archive_path, {})
    if not waters_payload.get("waters"):
        raise RuntimeError("data/waters.json contains no live Atlas-enriched waters")
    if not archive_payload.get("events"):
        raise RuntimeError("data/stocking_events.json contains no historical events")

    client = PoliteHttpClient(PROJECT_ROOT / ".cache", cache_ttl_hours=args.cache_ttl_hours)
    overrides = load_overrides(args.overrides)
    merged, report = merge_archive(waters_payload, archive_payload, client, overrides)

    if merged["summary"].get("archive_events", 0) < 500:
        raise RuntimeError("Archive merge produced fewer than 500 historical events")
    if merged["summary"].get("matched_waters", 0) <= len(waters_payload.get("waters", [])):
        raise RuntimeError("Archive merge did not add any historical-only waters")

    write_json(waters_path, merged)
    write_json(args.data_dir / "archive-merge-report.json", report)
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
