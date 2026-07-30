#!/usr/bin/env python3
"""Merge the fixed archive snapshot into the website's Atlas-enriched waters dataset."""
from __future__ import annotations

import argparse
import hashlib
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


def water_names(water: dict[str, Any]) -> set[str]:
    """Return all usable normalized names for an Atlas-enriched water."""
    names = {
        normalized_name(water.get("name") or ""),
        normalized_name(water.get("canonical_name") or ""),
        normalized_name(water.get("atlas_name") or ""),
        clean(water.get("normalized_name") or ""),
    }
    return {name for name in names if name}


def site_event(event: dict[str, Any], source_kind: str = "archive") -> dict[str, Any]:
    """Keep the canonical event fields the website can display."""
    return {
        key: value
        for key, value in {
            "event_id": event.get("event_id"),
            "stocking_date": event.get("stocking_date") or event.get("report_date"),
            "species": event.get("species"),
            "quantity": event.get("quantity"),
            "length_inches": event.get("length_inches"),
            "county": event.get("county"),
            "region": event.get("region"),
            "water_name": event_name(event),
            "source_kind": source_kind,
        }.items()
        if value not in (None, "")
    }


def merged_events(
    uid: int,
    archive_events: list[dict[str, Any]],
    current_dates: list[str],
    water_name: str,
) -> list[dict[str, Any]]:
    """Preserve canonical archive rows and add only genuinely newer live dates."""
    events = [site_event(event) for event in archive_events]
    archived_dates = {event.get("stocking_date") for event in events}
    for stocking_date in current_dates:
        if stocking_date and stocking_date not in archived_dates:
            events.append(
                {
                    "event_id": f"current-{uid}-{stocking_date}",
                    "stocking_date": stocking_date,
                    "water_name": water_name,
                    "source_kind": "current-report",
                }
            )
    return sorted(
        events,
        key=lambda event: (
            event.get("stocking_date") or "",
            event.get("species") or "",
            event.get("event_id") or "",
        ),
        reverse=True,
    )


def unmapped_water(name: str, events: list[dict[str, Any]], reason: str) -> dict[str, Any]:
    """Expose valid database events in the list even when no map point is known."""
    public_events = [site_event(event) for event in events]
    dates = sorted(
        {event["stocking_date"] for event in public_events if event.get("stocking_date")},
        reverse=True,
    )
    digest = hashlib.sha1(f"{reason}|{normalized_name(name)}".encode("utf-8")).hexdigest()[:12]
    counties = {event.get("county") for event in public_events if event.get("county")}
    species = sorted(
        {event.get("species") for event in public_events if event.get("species")},
        key=str.casefold,
    )
    return {
        "key": f"unmapped-{digest}",
        "atlas_id": None,
        "name": name,
        "canonical_name": name,
        "normalized_name": normalized_name(name),
        "atlas_url": None,
        "latest_report_date": dates[0],
        "stocking_dates": dates,
        "stocking_events": public_events,
        "current_event_count": 0,
        "historical_event_count": len(public_events),
        "archive_event_count": len(public_events),
        "archive_first_date": dates[-1],
        "archive_last_date": dates[0],
        "species": species,
        "county": next(iter(counties)) if len(counties) == 1 else None,
        "lat": None,
        "lng": None,
        "stocking_status": "location-not-matched",
        "match_method": reason,
        "location_warning": (
            "These official stocking events are included, but this water has not "
            "yet been matched to a unique Fishing Atlas location."
        ),
    }


def merge_archive(
    waters_payload: dict[str, Any],
    archive_payload: dict[str, Any],
    client: PoliteHttpClient,
    overrides: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    archive_events = [
        event
        for event in archive_payload.get("events", [])
        if event.get("stocking_date") and event_name(event)
    ]

    existing = {
        int(water["atlas_id"]): dict(water)
        for water in waters_payload.get("waters", [])
        if water.get("atlas_id") is not None
    }

    # The provenance database intentionally stores canonical stocking facts only;
    # it does not have an atlas_id column.  Older generated snapshots sometimes
    # carried Atlas IDs, but a fresh export does not.  Build an exact normalized
    # name index so those events can still be merged into the live Atlas waters.
    name_to_ids: dict[str, set[int]] = defaultdict(set)
    for uid, water in existing.items():
        for name in water_names(water):
            name_to_ids[name].add(uid)

    by_atlas: dict[int, list[dict[str, Any]]] = defaultdict(list)
    unmatched_name_events: dict[str, list[dict[str, Any]]] = defaultdict(list)
    ambiguous_name_events: dict[str, list[dict[str, Any]]] = defaultdict(list)
    matched_by_id = 0
    matched_by_name = 0

    for event in archive_events:
        raw_uid = event.get("atlas_id")
        if raw_uid is not None:
            try:
                uid = int(raw_uid)
            except (TypeError, ValueError):
                uid = None
            if uid is not None:
                by_atlas[uid].append(event)
                matched_by_id += 1
                continue

        key = normalized_name(event_name(event))
        candidates = name_to_ids.get(key, set())
        if len(candidates) == 1:
            uid = next(iter(candidates))
            by_atlas[uid].append(event)
            matched_by_name += 1
        elif len(candidates) > 1:
            ambiguous_name_events[key].append(event)
        else:
            unmatched_name_events[key].append(event)

    enriched_new = 0
    unresolved = []
    unresolved_event_groups: list[list[dict[str, Any]]] = []
    located_archive_events = 0
    for uid, events in sorted(by_atlas.items()):
        archive_dates = {event["stocking_date"] for event in events}
        names = sorted({event_name(event) for event in events if event_name(event)})
        atlas_url = next((event.get("atlas_url") for event in events if event.get("atlas_url")), "")

        if uid in existing:
            water = existing[uid]
            events_for_water = merged_events(
                uid,
                events,
                water.get("stocking_dates") or [],
                water.get("name") or names[0],
            )
            dates = {event["stocking_date"] for event in events_for_water}
            water["stocking_dates"] = sorted(dates, reverse=True)
            water["stocking_events"] = events_for_water
            water["latest_report_date"] = max(dates)
            water["historical_event_count"] = len(events_for_water)
            water["archive_event_count"] = len(events)
            water["archive_first_date"] = min(archive_dates)
            water["archive_last_date"] = max(archive_dates)
            existing[uid] = water
            located_archive_events += len(events)
            continue

        # This path remains available for any legacy events that still carry a
        # valid Atlas ID but refer to a water absent from the current report.
        info = query_atlas(client, uid, names, overrides.get(str(uid), {}))
        if not info or info.get("lat") is None or info.get("lng") is None:
            unresolved.append({"atlas_id": uid, "names": names, "event_count": len(events)})
            unresolved_event_groups.append(events)
            continue

        dates = sorted(archive_dates, reverse=True)
        events_for_water = merged_events(uid, events, [], names[0])
        canonical_name = info.get("atlas_name") or names[0]
        existing[uid] = {
            "key": f"atlas-{uid}",
            "atlas_id": uid,
            "name": names[0],
            "normalized_name": normalized_name(names[0]),
            "atlas_url": atlas_url,
            "latest_report_date": dates[0],
            "stocking_dates": dates,
            "stocking_events": events_for_water,
            "current_event_count": 0,
            "historical_event_count": len(events_for_water),
            "archive_event_count": len(events),
            "archive_first_date": dates[-1],
            "archive_last_date": dates[0],
            "species": [],
            "species_status": "not-queried-for-archive-only-water",
            "atlas_species_metadata": {"note": "Species enrichment is deferred until the water appears in a current report."},
            "canonical_name": canonical_name,
            **info,
        }
        enriched_new += 1
        located_archive_events += len(events)

    unmapped = [
        unmapped_water(event_name(events[0]), events, "unmatched-name")
        for events in unmatched_name_events.values()
    ] + [
        unmapped_water(event_name(events[0]), events, "ambiguous-name")
        for events in ambiguous_name_events.values()
    ] + [
        unmapped_water(event_name(events[0]), events, "atlas-id-unresolved")
        for events in unresolved_event_groups
    ]

    waters = sorted(
        [*existing.values(), *unmapped],
        key=lambda item: (item.get("latest_report_date") or "", item.get("name") or ""),
        reverse=True,
    )

    live_summary = dict(waters_payload.get("summary") or {})
    archive_summary = dict(archive_payload.get("summary") or {})
    live_rows = int(live_summary.get("stocking_events") or 0)
    displayed_events = sum(int(water.get("historical_event_count") or 0) for water in waters)

    summary = {
        **live_summary,
        "stocking_events": displayed_events,
        "current_report_events": live_rows,
        "archive_events": len(archive_events),
        "archive_events_matched": located_archive_events,
        "historical_events": displayed_events,
        "matched_waters": len(existing),
        "stocking_history_waters": len(waters),
        "unmapped_stocking_waters": len(unmapped),
        "archive_unique_atlas_ids": len(by_atlas),
        "archive_only_waters_added": enriched_new,
        "archive_unresolved_waters": len(unresolved),
        "archive_unmatched_names": len(unmatched_name_events),
        "archive_ambiguous_names": len(ambiguous_name_events),
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
        "archive_events_read": len(archive_events),
        "archive_events_matched": located_archive_events,
        "archive_events_matched_by_atlas_id": matched_by_id,
        "archive_events_matched_by_normalized_name": matched_by_name,
        "archive_unique_atlas_ids": len(by_atlas),
        "existing_live_waters": len(waters_payload.get("waters", [])),
        "archive_only_waters_added": enriched_new,
        "combined_waters": len(waters),
        "unmapped_waters_added": len(unmapped),
        "archive_events_displayed": located_archive_events + sum(
            len(events) for events in unmatched_name_events.values()
        ) + sum(len(events) for events in ambiguous_name_events.values()) + sum(
            len(events) for events in unresolved_event_groups
        ),
        "unmatched_names": [
            {
                "normalized_name": name,
                "sample_name": event_name(events[0]),
                "event_count": len(events),
            }
            for name, events in sorted(unmatched_name_events.items())
        ],
        "ambiguous_names": [
            {
                "normalized_name": name,
                "sample_name": event_name(events[0]),
                "event_count": len(events),
                "candidate_atlas_ids": sorted(name_to_ids.get(name, set())),
            }
            for name, events in sorted(ambiguous_name_events.items())
        ],
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
        raise RuntimeError("Archive merge read fewer than 500 historical events")
    if merged["summary"].get("archive_events_matched", 0) < 500:
        raise RuntimeError("Archive merge matched fewer than 500 historical events to Atlas waters")

    write_json(waters_path, merged)
    write_json(args.data_dir / "archive-merge-report.json", report)
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
