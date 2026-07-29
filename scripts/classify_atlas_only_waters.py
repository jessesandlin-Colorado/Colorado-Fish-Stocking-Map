#!/usr/bin/env python3
"""Apply conservative, review-oriented classifications to Atlas-only waters.

This post-processes data/atlas-inventory-comparison.json.  The initial comparison
identifies records whose WATERCODE is absent from the stocking-derived project;
this script determines whether each record is a strong public import candidate,
a likely alias/duplicate, private or restricted, or in need of manual review.
"""
from __future__ import annotations

import csv
import json
import math
import re
from collections import Counter
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

ROOT = Path(__file__).parents[1]
DATA = ROOT / "data"
PLACEHOLDERS = {
    "", "purposely left blank", "unknown", "unnamed", "n a", "na", "none",
    "not available", "tbd", "no name",
}
PRIVATE_TERMS = (
    "private", "club", "hoa", "homeowners", "golf", "country club", "ranch",
    "resort", "members only", "no public access",
)
RESTRICTED_TERMS = (
    "closed", "restricted", "permit required", "reservation only", "youth only",
    "disabled only", "special regulation access",
)


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def norm(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def display_name(record: dict[str, Any]) -> str:
    primary = str(record.get("name") or "").strip()
    alternate = str(record.get("alternate_name") or "").strip()
    if norm(primary) in PLACEHOLDERS and norm(alternate) not in PLACEHOLDERS:
        return alternate
    return primary or alternate


def coordinates(record: dict[str, Any]) -> tuple[float | None, float | None]:
    lat = record.get("lat")
    lng = record.get("lng")
    try:
        return float(lat), float(lng)
    except (TypeError, ValueError):
        location = record.get("location") or {}
        try:
            return float(location.get("lat")), float(location.get("lng"))
        except (TypeError, ValueError, AttributeError):
            return None, None


def miles(a_lat: float, a_lng: float, b_lat: float, b_lng: float) -> float:
    radius = 3958.7613
    p1, p2 = math.radians(a_lat), math.radians(b_lat)
    dp = math.radians(b_lat - a_lat)
    dl = math.radians(b_lng - a_lng)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * radius * math.asin(math.sqrt(h))


def existing_index(project_waters: list[dict[str, Any]]) -> tuple[dict[str, list[dict[str, Any]]], list[dict[str, Any]]]:
    names: dict[str, list[dict[str, Any]]] = {}
    rows: list[dict[str, Any]] = []
    for water in project_waters:
        candidate_names = {
            norm(water.get("name")), norm(water.get("normalized_name")),
            *(norm(v) for v in (water.get("alternate_names") or []) if v),
        }
        candidate_names.discard("")
        row = dict(water)
        row["_names"] = candidate_names
        row["_lat"], row["_lng"] = coordinates(water)
        rows.append(row)
        for name in candidate_names:
            names.setdefault(name, []).append(row)
    return names, rows


def duplicate_candidate(record: dict[str, Any], exact_names: dict[str, list[dict[str, Any]]], existing: list[dict[str, Any]]) -> tuple[str, str, float | None]:
    candidate_names = {norm(display_name(record)), norm(record.get("name")), norm(record.get("alternate_name"))}
    candidate_names.discard("")
    lat, lng = coordinates(record)

    for name in candidate_names:
        if name in exact_names:
            match = exact_names[name][0]
            distance = None
            if lat is not None and lng is not None and match.get("_lat") is not None:
                distance = miles(lat, lng, match["_lat"], match["_lng"])
            return "exact-name", str(match.get("name") or ""), distance

    if lat is None or lng is None:
        return "", "", None

    best: tuple[float, float, dict[str, Any]] | None = None
    for water in existing:
        wlat, wlng = water.get("_lat"), water.get("_lng")
        if wlat is None or wlng is None:
            continue
        distance = miles(lat, lng, wlat, wlng)
        if distance > 3.0:
            continue
        similarity = max(
            (SequenceMatcher(None, name, existing_name).ratio() for name in candidate_names for existing_name in water.get("_names", set())),
            default=0.0,
        )
        score = similarity - min(distance / 30.0, 0.1)
        if best is None or score > best[0]:
            best = (score, distance, water)

    if best:
        score, distance, water = best
        similarity = score + min(distance / 30.0, 0.1)
        if similarity >= 0.90 and distance <= 3.0:
            return "near-name-near-coordinate", str(water.get("name") or ""), distance
        if similarity >= 0.78 and distance <= 0.35:
            return "near-coordinate-possible-alias", str(water.get("name") or ""), distance
    return "", "", None


def classify(record: dict[str, Any], duplicate_kind: str) -> tuple[str, str]:
    name = display_name(record)
    text = norm(" ".join(str(record.get(k) or "") for k in (
        "name", "alternate_name", "property_name", "access_basis", "special_opportunity",
    )))
    access = str(record.get("access_class") or "")
    species = record.get("species") or []
    lat, lng = coordinates(record)

    if duplicate_kind:
        return "hold-likely-existing-water", "Likely alias or coordinate/name match to a water already in the project"
    if any(term in text for term in PRIVATE_TERMS) or access == "private-indicated":
        return "exclude-private-review", "Private-access indicator requires proof of lawful public fishing access"
    if any(term in text for term in RESTRICTED_TERMS):
        return "hold-restricted-access", "Restricted or conditional access requires manual verification"
    if norm(name) in PLACEHOLDERS:
        return "hold-name-cleanup", "No usable public display name after alternate-name fallback"
    if lat is None or lng is None:
        return "hold-missing-location", "Missing usable map coordinates"
    if not species:
        return "hold-no-species", "No official species relationship was returned"
    if access == "public-indicated":
        if record.get("property_url") or record.get("survey_url") or norm(record.get("property_name")):
            return "import-public-confirmed", "Public indicator plus official property, survey, or land-manager context"
        return "import-public-provisional", "Public indicator present, but supporting access metadata is limited"
    if access == "access-indicated":
        return "hold-access-verification", "Atlas rates access but does not establish public ownership or permission"
    return "hold-access-unknown", "Atlas metadata does not establish lawful public access"


def main() -> None:
    comparison = load(DATA / "atlas-inventory-comparison.json")
    project = load(DATA / "waters.json")
    records = comparison.get("atlas_only_waters", [])
    project_waters = project.get("waters", [])
    exact_names, existing = existing_index(project_waters)

    for record in records:
        record["display_name"] = display_name(record)
        duplicate_kind, duplicate_name, duplicate_distance = duplicate_candidate(record, exact_names, existing)
        record["possible_existing_match_type"] = duplicate_kind
        record["possible_existing_water"] = duplicate_name
        record["possible_existing_distance_miles"] = round(duplicate_distance, 3) if duplicate_distance is not None else None
        classification, reason = classify(record, duplicate_kind)
        record["review_classification"] = classification
        record["review_reason"] = reason

    order = {
        "import-public-confirmed": 0,
        "import-public-provisional": 1,
        "hold-likely-existing-water": 2,
        "hold-access-verification": 3,
        "hold-access-unknown": 4,
        "hold-name-cleanup": 5,
        "hold-no-species": 6,
        "hold-missing-location": 7,
        "hold-restricted-access": 8,
        "exclude-private-review": 9,
    }
    records.sort(key=lambda r: (order.get(r["review_classification"], 99), str(r.get("display_name") or "").casefold()))
    counts = Counter(r["review_classification"] for r in records)

    fields = [
        "review_classification", "review_reason", "display_name", "name", "alternate_name",
        "watercode", "atlas_id", "county", "location_type", "fishery_type", "access_class",
        "access_basis", "species", "property_name", "property_url", "survey_url", "access_ease",
        "fishing_pressure", "family_friendly", "ice_fishing", "boating", "gold_medal",
        "special_opportunity", "lat", "lng", "possible_existing_match_type",
        "possible_existing_water", "possible_existing_distance_miles", "duplicate_atlas_records",
        "stocking_status",
    ]
    with (DATA / "atlas-only-waters-classified.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for record in records:
            row = dict(record)
            if isinstance(row.get("species"), list):
                row["species"] = " | ".join(row["species"])
            writer.writerow(row)

    comparison["atlas_only_waters"] = records
    comparison["classification_summary"] = dict(sorted(counts.items()))
    (DATA / "atlas-inventory-classified.json").write_text(
        json.dumps(comparison, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    importable = counts["import-public-confirmed"] + counts["import-public-provisional"]
    lines = [
        "# Atlas-only water classification", "",
        "This is a conservative second-pass review of waters absent by WATERCODE from the stocking-derived project.",
        "Name and coordinate matching is used to catch likely aliases; access classifications remain screening decisions, not legal determinations.", "",
        f"- Atlas-only records reviewed: **{len(records):,}**",
        f"- Public import candidates: **{importable:,}**", "",
        "## Classification counts", "", "| Classification | Count |", "|---|---:|",
    ]
    for key, value in sorted(counts.items(), key=lambda item: (order.get(item[0], 99), item[0])):
        lines.append(f"| {key} | {value:,} |")
    lines += [
        "", "## Recommended policy", "",
        "1. Import `import-public-confirmed` after a final coordinate spot-check.",
        "2. Review `import-public-provisional` in batches, prioritizing named public properties and official links.",
        "3. Do not import `hold-likely-existing-water` until aliases or WATERCODE mismatches are resolved.",
        "4. Hold all unknown, restricted, unnamed, or no-species records.",
        "5. Exclude private-indicated records unless public fishing access is independently confirmed.",
        "6. Label imported records: **Stocking history unknown — no matching record found in this project's historical stocking database.**", "",
    ]
    (DATA / "atlas-only-classification-report.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps(dict(sorted(counts.items())), indent=2))


if __name__ == "__main__":
    main()
