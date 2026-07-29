#!/usr/bin/env python3
"""Compare the complete Colorado Fishing Atlas inventory with published map waters.

Outputs a detailed JSON dataset, a CSV review sheet, and a Markdown summary. Atlas
records are matched to the project by WATERCODE; Atlas-only records are enriched
with the official Fishing Atlas species relationship and assigned transparent
classification and import-priority fields.
"""
from __future__ import annotations

import csv
import json
import random
import re
import time
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

PROJECT_ROOT = Path(__file__).parents[1]
DATA_DIR = PROJECT_ROOT / "data"
ATLAS_LAYER = "https://ndismaps.nrel.colostate.edu/arcgis/rest/services/FishingAtlas/FishingAtlas_Data/MapServer/2/query"
SPECIES_ENDPOINT = "https://ndismaps.nrel.colostate.edu/FishingAtlas/IdentifyFishingPlacesDB.aspx"
PAGE_SIZE = 1000

COLDWATER_TERMS = (
    "trout", "salmon", "kokanee", "grayling", "char", "whitefish",
)
WARMWATER_TERMS = (
    "bass", "walleye", "saugeye", "sauger", "perch", "crappie", "bluegill",
    "sunfish", "catfish", "bullhead", "pike", "muskie", "carp", "drum",
)
PUBLIC_TERMS = (
    "state wildlife area", "swa", "state park", "national forest", "national park",
    "city of", "town of", "county", "open space", "blm", "bureau of land",
    "recreation district", "reservoir", "wildlife refuge",
)
PRIVATE_TERMS = (
    "private", "club", "hoa", "homeowners", "golf", "ranch", "resort",
)
SPORTFISH_TERMS = COLDWATER_TERMS + WARMWATER_TERMS


def read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def normalize(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def clean_watercode(value: Any) -> str:
    text = str(value or "").strip()
    return text[:-2] if text.endswith(".0") else text


def request_json(session: requests.Session, url: str, params: dict[str, Any], retries: int = 4) -> dict[str, Any]:
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            response = session.get(url, params=params, timeout=60)
            response.raise_for_status()
            payload = response.json()
            if payload.get("error"):
                raise RuntimeError(payload["error"].get("message", "ArcGIS query failed"))
            return payload
        except (requests.RequestException, ValueError, RuntimeError) as exc:
            last_error = exc
            if attempt + 1 < retries:
                time.sleep((2 ** attempt) + random.uniform(0.1, 0.5))
    raise RuntimeError(f"Request failed: {last_error}")


def fetch_atlas_points(session: requests.Session) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    offset = 0
    while True:
        payload = request_json(
            session,
            ATLAS_LAYER,
            {
                "where": "SHOW = 1 OR SHOW IS NULL",
                "outFields": "*",
                "returnGeometry": "true",
                "outSR": "4326",
                "resultOffset": offset,
                "resultRecordCount": PAGE_SIZE,
                "orderByFields": "OBJECTID_12",
                "f": "json",
            },
        )
        features = payload.get("features", [])
        records.extend(features)
        if len(features) < PAGE_SIZE:
            break
        offset += len(features)
    return records


def parse_species(text: str) -> list[str]:
    root = ET.fromstring(text.lstrip("\ufeff"))
    return sorted(
        {
            node.text.strip()
            for node in root.findall(".//AtlasFish/linkname")
            if node.text and node.text.strip()
        },
        key=str.casefold,
    )


def fetch_species(session: requests.Session, watercode: str, retries: int = 3) -> tuple[list[str], str | None]:
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            response = session.get(
                SPECIES_ENDPOINT,
                params={"key": watercode, "filename": "tblMasterSpecies"},
                timeout=45,
            )
            response.raise_for_status()
            return parse_species(response.text), None
        except (requests.RequestException, ET.ParseError, ValueError) as exc:
            last_error = exc
            if attempt + 1 < retries:
                time.sleep((2 ** attempt) + random.uniform(0.1, 0.4))
    return [], str(last_error)


def fishery_type(species: list[str]) -> str:
    normalized = [normalize(item) for item in species]
    cold = any(any(term in item for term in COLDWATER_TERMS) for item in normalized)
    warm = any(any(term in item for term in WARMWATER_TERMS) for item in normalized)
    if cold and warm:
        return "Mixed coldwater/warmwater"
    if cold:
        return "Coldwater"
    if warm:
        return "Warmwater"
    return "Other/unknown"


def access_class(attrs: dict[str, Any]) -> tuple[str, str]:
    combined = normalize(" ".join(str(attrs.get(key) or "") for key in ("PROP_NAME", "PROP_URL", "FA_NAME", "FA_NAME2")))
    if any(term in combined for term in PRIVATE_TERMS):
        return "private-indicated", "Name or property text contains a private-access indicator"
    if any(term in combined for term in PUBLIC_TERMS) or attrs.get("PROP_URL"):
        return "public-indicated", "Public-land/property indicator or official property URL is present"
    if normalize(attrs.get("ACCESS_EASE")) in {"easy", "medium"}:
        return "access-indicated", "Atlas provides an Easy or Medium access rating"
    return "unknown", "Atlas attributes do not establish public access"


def water_type(attrs: dict[str, Any]) -> str:
    value = str(attrs.get("LOC_TYPE") or "").strip()
    if value:
        return value
    name = normalize(attrs.get("FA_NAME"))
    if any(word in name for word in ("river", "creek", "stream", "fork")):
        return "Stream/River (name-derived)"
    return "Water Body/Unknown"


def score_record(attrs: dict[str, Any], species: list[str], access: str) -> tuple[int, list[str]]:
    score = 0
    reasons: list[str] = []
    normalized_species = [normalize(item) for item in species]
    sportfish_count = sum(any(term in item for term in SPORTFISH_TERMS) for item in normalized_species)

    if species:
        score += 25
        reasons.append("official species list")
    else:
        score -= 20
        reasons.append("no species listed")
    if sportfish_count:
        score += 15
        reasons.append("sportfish present")
    if sportfish_count >= 3:
        score += 10
        reasons.append("three or more sportfish")
    if access == "public-indicated":
        score += 25
        reasons.append("public access indicated")
    elif access == "access-indicated":
        score += 12
        reasons.append("access rating available")
    elif access == "private-indicated":
        score -= 45
        reasons.append("private access indicated")
    if normalize(attrs.get("ACCESS_EASE")) == "easy":
        score += 8
        reasons.append("easy access")
    if normalize(attrs.get("OPP_FAMILY")) == "yes":
        score += 6
        reasons.append("family friendly")
    if attrs.get("SURVEY_URL") or attrs.get("REPORTS_URL"):
        score += 6
        reasons.append("survey/report available")
    if attrs.get("DRIVING_URL"):
        score += 3
        reasons.append("driving link available")
    if attrs.get("GoldMedal"):
        score += 10
        reasons.append("Gold Medal water")
    if attrs.get("SUP"):
        score += 5
        reasons.append("special opportunity")
    if not (attrs.get("FA_NAME") or attrs.get("DOW_NAME")):
        score -= 20
        reasons.append("missing display name")
    return max(0, min(100, score)), reasons


def recommendation(score: int, access: str, species: list[str]) -> str:
    if access == "private-indicated":
        return "exclude/private-review"
    if not species:
        return "manual-review/no-species"
    if score >= 70:
        return "import-high-priority"
    if score >= 50:
        return "import-medium-priority"
    if score >= 30:
        return "manual-review"
    return "exclude/low-information"


def feature_record(feature: dict[str, Any]) -> dict[str, Any]:
    attrs = feature.get("attributes", {})
    geometry = feature.get("geometry", {})
    return {
        "objectid": attrs.get("OBJECTID_12"),
        "atlas_id": attrs.get("UNI_ID"),
        "watercode": clean_watercode(attrs.get("WATERCODE")),
        "name": attrs.get("FA_NAME") or attrs.get("DOW_NAME"),
        "alternate_name": attrs.get("FA_NAME2"),
        "property_name": attrs.get("PROP_NAME"),
        "county": attrs.get("COUNTYNAME"),
        "location_type": water_type(attrs),
        "lat": geometry.get("y"),
        "lng": geometry.get("x"),
        "elevation_ft": attrs.get("ELEV_FT") or attrs.get("ELEV_FT_TXT"),
        "boating": attrs.get("BOATING"),
        "access_ease": attrs.get("ACCESS_EASE"),
        "fishing_pressure": attrs.get("FISH_PRESSURE"),
        "family_friendly": attrs.get("OPP_FAMILY"),
        "rustic": attrs.get("OPP_RUSTIC"),
        "ice_fishing": attrs.get("OPP_ICE"),
        "accessible_pier": attrs.get("HANDI_PIER"),
        "atlas_stocked_description": attrs.get("STOCKED"),
        "survey_url": attrs.get("SURVEY_URL") or attrs.get("REPORTS_URL"),
        "driving_url": attrs.get("DRIVING_URL"),
        "property_url": attrs.get("PROP_URL"),
        "gold_medal": bool(attrs.get("GoldMedal")),
        "special_opportunity": attrs.get("SUP_Desc") if attrs.get("SUP") else None,
        "show": attrs.get("SHOW"),
        "noshow_reason": attrs.get("NOSHOW_REASON"),
        "quality": attrs.get("Quality"),
        "spot_url": attrs.get("SpotURL"),
        "_attrs": attrs,
    }


def markdown_table(rows: list[tuple[str, Any]]) -> str:
    body = ["| Classification | Count |", "|---|---:|"]
    body.extend(f"| {label} | {value:,} |" for label, value in rows)
    return "\n".join(body)


def main() -> None:
    payload = read_json(DATA_DIR / "waters.json", {})
    project_waters = payload.get("waters", []) if isinstance(payload, dict) else []
    project_codes = {clean_watercode(w.get("watercode")) for w in project_waters if clean_watercode(w.get("watercode"))}

    session = requests.Session()
    session.headers["User-Agent"] = "ColoradoFishMap-AtlasInventory/1.0 (+https://github.com/jessesandlin-Colorado/Colorado-Fish-Stocking-Map)"
    features = fetch_atlas_points(session)
    raw_records = [feature_record(feature) for feature in features]

    by_code: dict[str, list[dict[str, Any]]] = defaultdict(list)
    no_code: list[dict[str, Any]] = []
    for record in raw_records:
        if record["watercode"]:
            by_code[record["watercode"]].append(record)
        else:
            no_code.append(record)

    unique_records: list[dict[str, Any]] = []
    duplicate_groups: list[dict[str, Any]] = []
    for code, records in by_code.items():
        records.sort(key=lambda r: (r.get("quality") or 0, bool(r.get("name"))), reverse=True)
        primary = records[0]
        primary["duplicate_atlas_records"] = len(records) - 1
        unique_records.append(primary)
        if len(records) > 1:
            duplicate_groups.append({
                "watercode": code,
                "count": len(records),
                "names": sorted({str(r.get("name") or "") for r in records}),
                "atlas_ids": sorted({r.get("atlas_id") for r in records if r.get("atlas_id") is not None}),
            })

    matched = [r for r in unique_records if r["watercode"] in project_codes]
    atlas_only = [r for r in unique_records if r["watercode"] not in project_codes]

    species_failures = 0
    for index, record in enumerate(atlas_only, start=1):
        species, error = fetch_species(session, record["watercode"])
        record["species"] = species
        record["species_error"] = error
        if error:
            species_failures += 1
        access, access_reason = access_class(record["_attrs"])
        record["access_class"] = access
        record["access_basis"] = access_reason
        record["fishery_type"] = fishery_type(species)
        score, score_reasons = score_record(record["_attrs"], species, access)
        record["import_score"] = score
        record["score_reasons"] = score_reasons
        record["recommendation"] = recommendation(score, access, species)
        record["stocking_status"] = "no-project-stocking-record-found"
        record.pop("_attrs", None)
        if index % 50 == 0:
            print(f"Species/classification: {index}/{len(atlas_only)}")
        time.sleep(random.uniform(0.10, 0.20))

    for record in matched:
        record.pop("_attrs", None)
    for record in no_code:
        record.pop("_attrs", None)

    atlas_only.sort(key=lambda r: (-r["import_score"], str(r.get("name") or "").casefold()))
    generated_at = datetime.now(timezone.utc).isoformat()
    rec_counts = Counter(r["recommendation"] for r in atlas_only)
    type_counts = Counter(r["location_type"] for r in atlas_only)
    fishery_counts = Counter(r["fishery_type"] for r in atlas_only)
    access_counts = Counter(r["access_class"] for r in atlas_only)
    county_counts = Counter(r.get("county") or "Unknown" for r in atlas_only)
    species_counts = Counter(species for r in atlas_only for species in r["species"])

    summary = {
        "generated_at": generated_at,
        "atlas_feature_records": len(raw_records),
        "atlas_unique_watercodes": len(unique_records),
        "project_waters": len(project_waters),
        "project_unique_watercodes": len(project_codes),
        "atlas_watercodes_already_in_project": len(matched),
        "atlas_only_unique_watercodes": len(atlas_only),
        "atlas_records_without_watercode": len(no_code),
        "duplicate_watercode_groups": len(duplicate_groups),
        "species_lookup_failures": species_failures,
        "project_coverage_of_atlas_percent": round((len(matched) / len(unique_records) * 100), 1) if unique_records else 0,
        "recommendations": dict(sorted(rec_counts.items())),
        "water_types": dict(sorted(type_counts.items())),
        "fishery_types": dict(sorted(fishery_counts.items())),
        "access_classes": dict(sorted(access_counts.items())),
        "top_counties": dict(county_counts.most_common(20)),
        "top_species": dict(species_counts.most_common(40)),
    }

    output = {
        "generated_at": generated_at,
        "sources": {
            "atlas_inventory": ATLAS_LAYER,
            "atlas_species": SPECIES_ENDPOINT,
            "project_dataset": "data/waters.json",
        },
        "methodology": {
            "inventory_filter": "SHOW = 1 OR SHOW IS NULL",
            "match_key": "WATERCODE",
            "stocking_interpretation": "Atlas-only means no matching WATERCODE in the project's 2014-present stocking-derived dataset; it does not prove the water was never stocked.",
            "access_caution": "Access classes are indicators from Atlas attributes and names, not legal access determinations.",
            "score": "0-100 transparent heuristic favoring official species, sportfish, public/access indicators, survey links, and family/access attributes; private indicators are penalized.",
        },
        "summary": summary,
        "atlas_only_waters": atlas_only,
        "matched_atlas_waters": matched,
        "duplicate_watercode_groups": duplicate_groups,
        "records_without_watercode": no_code,
    }
    (DATA_DIR / "atlas-inventory-comparison.json").write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    fields = [
        "recommendation", "import_score", "name", "alternate_name", "watercode", "atlas_id",
        "county", "location_type", "fishery_type", "access_class", "access_basis",
        "species", "property_name", "access_ease", "fishing_pressure", "family_friendly",
        "ice_fishing", "boating", "atlas_stocked_description", "gold_medal",
        "special_opportunity", "survey_url", "property_url", "driving_url", "lat", "lng",
        "duplicate_atlas_records", "species_error",
    ]
    with (DATA_DIR / "atlas-only-waters-review.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for record in atlas_only:
            row = dict(record)
            row["species"] = " | ".join(record["species"])
            writer.writerow(row)

    recommended = rec_counts.get("import-high-priority", 0) + rec_counts.get("import-medium-priority", 0)
    report = f"""# Colorado Fishing Atlas inventory comparison

Generated: {generated_at}

## Executive summary

- **{len(raw_records):,}** visible Atlas fishing-point records were retrieved.
- They represent **{len(unique_records):,} unique WATERCODEs** after duplicate consolidation.
- **{len(matched):,}** Atlas WATERCODEs are already represented in the project.
- **{len(atlas_only):,}** Atlas WATERCODEs are not represented in the project's stocking-derived group.
- Project coverage is **{summary['project_coverage_of_atlas_percent']:.1f}%** of the Atlas inventory by WATERCODE.
- **{recommended:,}** Atlas-only waters are provisionally rated high or medium priority for import.
- **{len(no_code):,}** Atlas records lack a WATERCODE and require separate manual review.

> "Atlas-only" means no matching WATERCODE was found in the project's 2014-present stocking-derived dataset. It should be labeled **Stocking history unknown / no project stocking record found**, not "never stocked."

## Import recommendations

{markdown_table(sorted(rec_counts.items()))}

## Fishery classifications

{markdown_table(sorted(fishery_counts.items()))}

## Access indicators

{markdown_table(sorted(access_counts.items()))}

Access classifications are screening indicators only. Users must still verify legal access, closures, and regulations with CPW and the land manager.

## Water types

{markdown_table(sorted(type_counts.items()))}

## Suggested import policy

1. Import **high-priority** records automatically after duplicate and coordinate validation.
2. Import **medium-priority** records if they have official species and no private-access indicator.
3. Hold **manual-review** records for access verification, duplicate resolution, or sparse metadata.
4. Exclude records flagged **private-review** until legal public access is confirmed.
5. Display every imported Atlas-only record as **Stocking history unknown — no matching record in the project's historical stocking database**.

## Review files

- `data/atlas-only-waters-review.csv`: ranked decision sheet for filtering and annotation.
- `data/atlas-inventory-comparison.json`: complete records, summaries, duplicates, and no-WATERCODE cases.
"""
    (DATA_DIR / "atlas-inventory-report.md").write_text(report, encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
