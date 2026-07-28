#!/usr/bin/env python3
"""Recover Atlas watercodes only for waters that do not already have one.

The default mode is report-only. Existing watercodes are never queried, replaced,
or otherwise changed. With ``--apply``, only unique high-confidence candidates are
written to ``data/waters.json``; ambiguous and weak matches remain untouched.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import time
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

import requests

PROJECT_ROOT = Path(__file__).parents[1]
DEFAULT_DATA_DIR = PROJECT_ROOT / "data"
DEFAULT_REPORT = "watercode-recovery-report.json"
ATLAS_SERVICE = (
    "https://ndismaps.nrel.colostate.edu/arcgis/rest/services/"
    "FishingAtlas/FishingAtlas_Data/MapServer"
)
LAYERS = (
    (16, "waterbody", 150),
    (15, "stream", 75),
)
OUT_FIELDS = "WATERCODE,ALT_WATERCODE,DOW_NAME,GNIS_Name"


def read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def write_json(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def normalize_name(value: Any) -> str:
    text = str(value or "").casefold()
    text = re.sub(r"\b(reservoir|lake|pond|river|creek|number|no)\b", " ", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


def candidate_names(attributes: dict[str, Any]) -> list[str]:
    names: list[str] = []
    for field in ("DOW_NAME", "GNIS_Name"):
        value = attributes.get(field)
        if value and str(value).strip() and str(value).strip() not in names:
            names.append(str(value).strip())
    return names


def water_names(water: dict[str, Any]) -> list[str]:
    names: list[str] = []
    for field in ("name", "canonical_name", "atlas_name", "alternate_name"):
        value = water.get(field)
        if value and str(value).strip() and str(value).strip() not in names:
            names.append(str(value).strip())
    return names


def get_coordinates(water: dict[str, Any]) -> tuple[float, float] | None:
    coordinate_pairs = (
        (water.get("longitude"), water.get("latitude")),
        (water.get("lon"), water.get("lat")),
        (water.get("lng"), water.get("lat")),
    )
    for lon, lat in coordinate_pairs:
        try:
            lon_f, lat_f = float(lon), float(lat)
        except (TypeError, ValueError):
            continue
        if -110 <= lon_f <= -101 and 36 <= lat_f <= 42:
            return lon_f, lat_f

    coordinates = water.get("coordinates")
    if isinstance(coordinates, (list, tuple)) and len(coordinates) >= 2:
        try:
            lon_f, lat_f = float(coordinates[0]), float(coordinates[1])
        except (TypeError, ValueError):
            return None
        if -110 <= lon_f <= -101 and 36 <= lat_f <= 42:
            return lon_f, lat_f
    return None


def name_similarity(water: dict[str, Any], attributes: dict[str, Any]) -> float:
    left = [normalize_name(name) for name in water_names(water)]
    right = [normalize_name(name) for name in candidate_names(attributes)]
    scores = [
        SequenceMatcher(None, a, b).ratio()
        for a in left
        for b in right
        if a and b
    ]
    return max(scores, default=0.0)


def haversine_meters(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    radius = 6_371_000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * radius * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def query_layer(
    session: requests.Session,
    layer_id: int,
    layer_name: str,
    radius_m: int,
    lon: float,
    lat: float,
) -> list[dict[str, Any]]:
    url = f"{ATLAS_SERVICE}/{layer_id}/query"
    params = {
        "f": "json",
        "geometry": f"{lon},{lat}",
        "geometryType": "esriGeometryPoint",
        "inSR": "4326",
        "spatialRel": "esriSpatialRelIntersects",
        "distance": str(radius_m),
        "units": "esriSRUnit_Meter",
        "outFields": OUT_FIELDS,
        "returnGeometry": "true",
        "outSR": "4326",
    }
    response = session.get(url, params=params, timeout=45)
    response.raise_for_status()
    payload = response.json()
    if payload.get("error"):
        raise RuntimeError(f"Atlas layer {layer_id} error: {payload['error']}")

    results: list[dict[str, Any]] = []
    for feature in payload.get("features", []):
        attributes = feature.get("attributes") or {}
        geometry = feature.get("geometry") or {}
        distance = 0.0
        if "x" in geometry and "y" in geometry:
            distance = haversine_meters(lon, lat, float(geometry["x"]), float(geometry["y"]))
        results.append(
            {
                "layer": layer_name,
                "layer_id": layer_id,
                "search_radius_m": radius_m,
                "attributes": attributes,
                "distance_m": round(distance, 1),
            }
        )
    return results


def choose_candidate(water: dict[str, Any], candidates: list[dict[str, Any]]) -> dict[str, Any]:
    scored: list[dict[str, Any]] = []
    for candidate in candidates:
        attributes = candidate["attributes"]
        code = attributes.get("WATERCODE") or attributes.get("ALT_WATERCODE")
        similarity = name_similarity(water, attributes)
        distance = float(candidate.get("distance_m") or 0)
        radius = float(candidate.get("search_radius_m") or 1)
        distance_score = max(0.0, 1.0 - distance / radius)
        score = 0.8 * similarity + 0.2 * distance_score
        scored.append(
            {
                **candidate,
                "candidate_watercode": str(code).strip() if code not in (None, "") else None,
                "candidate_names": candidate_names(attributes),
                "name_similarity": round(similarity, 3),
                "score": round(score, 3),
            }
        )

    scored.sort(key=lambda item: (item["score"], item["name_similarity"]), reverse=True)
    valid = [item for item in scored if item["candidate_watercode"]]
    best = valid[0] if valid else None
    runner_up = valid[1] if len(valid) > 1 else None

    accepted = bool(
        best
        and best["name_similarity"] >= 0.85
        and best["score"] >= 0.82
        and (runner_up is None or best["score"] - runner_up["score"] >= 0.08)
    )
    if not best:
        reason = "no candidate with a watercode"
    elif best["name_similarity"] < 0.85:
        reason = "best candidate name similarity below 0.85"
    elif best["score"] < 0.82:
        reason = "best candidate confidence score below 0.82"
    elif runner_up and best["score"] - runner_up["score"] < 0.08:
        reason = "best candidate is not sufficiently distinct from runner-up"
    else:
        reason = "unique high-confidence match"

    return {
        "accepted": accepted,
        "reason": reason,
        "selected": best,
        "candidates": scored,
    }


def recover(data_dir: Path, report_path: Path, apply: bool = False) -> dict[str, Any]:
    waters_path = data_dir / "waters.json"
    payload = read_json(waters_path, {})
    waters = payload.get("waters", []) if isinstance(payload, dict) else []
    if not isinstance(waters, list):
        raise RuntimeError(f"Invalid waters payload in {waters_path}")

    session = requests.Session()
    session.headers["User-Agent"] = (
        "ColoradoFishMap/5.1 "
        "(+https://github.com/jessesandlin-Colorado/Colorado-Fish-Stocking-Map)"
    )

    report_entries: list[dict[str, Any]] = []
    applied = 0
    skipped_existing = 0

    for water in waters:
        if water.get("watercode") not in (None, ""):
            skipped_existing += 1
            continue

        label = water.get("name") or water.get("atlas_name") or water.get("atlas_id")
        coordinates = get_coordinates(water)
        entry: dict[str, Any] = {
            "atlas_id": water.get("atlas_id"),
            "name": label,
            "stored_names": water_names(water),
            "coordinates": coordinates,
        }
        if coordinates is None:
            entry.update({"accepted": False, "reason": "missing usable coordinates", "candidates": []})
            report_entries.append(entry)
            continue

        lon, lat = coordinates
        candidates: list[dict[str, Any]] = []
        errors: list[str] = []
        for layer_id, layer_name, radius_m in LAYERS:
            try:
                candidates.extend(query_layer(session, layer_id, layer_name, radius_m, lon, lat))
                time.sleep(0.2)
            except (requests.RequestException, ValueError, RuntimeError) as exc:
                errors.append(f"{layer_name}: {exc}")

        decision = choose_candidate(water, candidates)
        entry.update(decision)
        if errors:
            entry["query_errors"] = errors

        selected = decision.get("selected") or {}
        if apply and decision["accepted"] and selected.get("candidate_watercode"):
            water["watercode"] = selected["candidate_watercode"]
            water["watercode_recovery_source"] = (
                f"Fishing Atlas layer {selected['layer_id']} ({selected['layer']})"
            )
            water["watercode_recovery_confidence"] = selected["score"]
            applied += 1

        report_entries.append(entry)
        print(f"{label}: {decision['reason']}")

    report = {
        "mode": "apply" if apply else "report-only",
        "waters_total": len(waters),
        "waters_skipped_existing_watercode": skipped_existing,
        "waters_missing_watercode_tested": len(report_entries),
        "high_confidence_matches": sum(1 for item in report_entries if item.get("accepted")),
        "watercodes_applied": applied,
        "entries": report_entries,
    }
    write_json(report_path, report)
    if apply and applied:
        write_json(waters_path, payload)
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", default=str(DEFAULT_DATA_DIR))
    parser.add_argument("--report", default=None)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    report_path = Path(args.report) if args.report else data_dir / DEFAULT_REPORT
    result = recover(data_dir, report_path, apply=args.apply)
    print(json.dumps({key: value for key, value in result.items() if key != "entries"}, indent=2))


if __name__ == "__main__":
    main()
