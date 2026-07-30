#!/usr/bin/env python3
"""Merge reviewed public Fishing Atlas waters into data/waters.json.

Imports confirmed public Atlas-only records, merges likely aliases into existing
waters where possible, and leaves private-indicated records out of the public map.
The script is idempotent and is intended to run after comparison/classification.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).parents[1]
DATA = ROOT / "data"


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def norm(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def clean_name(record: dict[str, Any]) -> str:
    return str(record.get("display_name") or record.get("alternate_name") or record.get("name") or "").strip()


def atlas_url(atlas_id: Any) -> str | None:
    if atlas_id in (None, ""):
        return None
    return f"https://ndismaps.nrel.colostate.edu/fishingatlas/index.aspx?keyword=fspot&value={atlas_id}"


def merge_missing(target: dict[str, Any], source: dict[str, Any]) -> None:
    mapping = {
        "watercode": "watercode",
        "atlas_id": "atlas_id",
        "county": "county",
        "location_type": "location_type",
        "fishery_type": "fishery_type",
        "property_name": "property_name",
        "property_url": "property_url",
        "survey_url": "survey_url",
        "driving_url": "driving_url",
        "elevation_ft": "elevation_ft",
        "access_ease": "access_ease",
        "fishing_pressure": "fishing_pressure",
        "family_friendly": "family_friendly",
        "rustic": "rustic",
        "ice_fishing": "ice_fishing",
        "accessible_pier": "accessible_pier",
        "boating": "boating",
        "atlas_stocked_description": "stocked_description",
        "special_opportunity": "special_opportunity",
        "lat": "lat",
        "lng": "lng",
    }
    for source_key, target_key in mapping.items():
        value = source.get(source_key)
        if value not in (None, "", []) and target.get(target_key) in (None, "", []):
            target[target_key] = value
    if source.get("species"):
        target["species"] = sorted(set(target.get("species") or []) | set(source["species"]), key=str.casefold)
    if not target.get("atlas_url"):
        target["atlas_url"] = atlas_url(source.get("atlas_id"))
    if (
        target.get("atlas_id") not in (None, "")
        and target.get("lat") not in (None, "")
        and target.get("lng") not in (None, "")
    ):
        # A reviewed catalog match supersedes an earlier unresolved-location
        # classification. Do not leave a mapped water carrying a stale warning.
        target.pop("location_warning", None)
        target["stocking_status"] = "matched-to-fishing-atlas"
        if target.get("match_method") in {
            None,
            "",
            "unmatched-name",
            "ambiguous-name",
            "atlas-id-unresolved",
        }:
            target["match_method"] = "atlas-catalog-exact-name"


def make_water(record: dict[str, Any]) -> dict[str, Any]:
    name = clean_name(record)
    watercode = str(record.get("watercode") or "").strip()
    atlas_id = record.get("atlas_id")
    return {
        "key": f"atlas-watercode-{watercode}" if watercode else f"atlas-{atlas_id}",
        "atlas_id": atlas_id,
        "watercode": watercode or None,
        "name": name,
        "canonical_name": name,
        "atlas_name": name,
        "alternate_name": record.get("alternate_name"),
        "normalized_name": norm(name),
        "atlas_url": atlas_url(atlas_id),
        "latest_report_date": None,
        "stocking_dates": [],
        "stocking_events": [],
        "historical_event_count": 0,
        "stocking_status": "no-project-stocking-record-found",
        "catalog_source": "Colorado Fishing Atlas",
        "county": record.get("county"),
        "location_type": record.get("location_type"),
        "fishery_type": record.get("fishery_type"),
        "species": record.get("species") or [],
        "property_name": record.get("property_name"),
        "property_url": record.get("property_url"),
        "survey_url": record.get("survey_url"),
        "driving_url": record.get("driving_url"),
        "elevation_ft": record.get("elevation_ft"),
        "access_ease": record.get("access_ease"),
        "fishing_pressure": record.get("fishing_pressure"),
        "family_friendly": record.get("family_friendly"),
        "rustic": record.get("rustic"),
        "ice_fishing": record.get("ice_fishing"),
        "accessible_pier": record.get("accessible_pier"),
        "boating": record.get("boating"),
        "stocked_description": record.get("atlas_stocked_description"),
        "gold_medal": bool(record.get("gold_medal")),
        "special_opportunity": record.get("special_opportunity"),
        "lat": record.get("lat"),
        "lng": record.get("lng"),
        "public_catalog_classification": record.get("review_classification"),
    }


def main() -> None:
    project = load(DATA / "waters.json")
    classified = load(DATA / "atlas-inventory-classified.json")
    waters = project.get("waters", [])
    records = classified.get("atlas_only_waters", [])

    # Remove prior generated Atlas-only imports so reruns rebuild them cleanly.
    waters = [w for w in waters if w.get("stocking_status") != "no-project-stocking-record-found"]
    by_name = {norm(w.get("name")): w for w in waters if norm(w.get("name"))}

    imported = 0
    aliases_merged = 0
    excluded_private = 0
    held = 0

    for record in records:
        classification = record.get("review_classification")
        if classification in {"import-public-confirmed", "import-public-provisional"}:
            waters.append(make_water(record))
            imported += 1
        elif classification == "hold-likely-existing-water":
            match = by_name.get(norm(record.get("possible_existing_water")))
            if match:
                merge_missing(match, record)
                aliases_merged += 1
            else:
                held += 1
        elif classification == "exclude-private-review":
            excluded_private += 1
        else:
            held += 1

    waters.sort(key=lambda w: str(w.get("canonical_name") or w.get("name") or "").casefold())
    project["waters"] = waters
    summary = project.setdefault("summary", {})
    summary["matched_waters"] = sum(
        w.get("lat") is not None and w.get("lng") is not None for w in waters
    )
    summary["total_waters"] = len(waters)
    summary["stocking_history_waters"] = sum(bool(w.get("stocking_dates")) for w in waters)
    summary["unmapped_stocking_waters"] = sum(
        w.get("stocking_status") == "location-not-matched" for w in waters
    )
    summary["atlas_catalog_only_waters"] = sum(w.get("stocking_status") == "no-project-stocking-record-found" for w in waters)
    summary["atlas_aliases_merged"] = aliases_merged
    summary["atlas_private_records_excluded"] = excluded_private
    summary["atlas_records_held"] = held
    project["schema_version"] = max(int(project.get("schema_version") or 0), 6)

    (DATA / "waters.json").write_text(json.dumps(project, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    report = {
        "catalog_waters": len(waters),
        "stocking_history_waters": summary["stocking_history_waters"],
        "atlas_catalog_only_imported": imported,
        "likely_aliases_merged": aliases_merged,
        "private_records_excluded": excluded_private,
        "other_records_held": held,
    }
    (DATA / "atlas-catalog-import-report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
