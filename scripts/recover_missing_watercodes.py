#!/usr/bin/env python3
"""Find official Atlas watercodes for only the waters that are missing them.

This is deliberately isolated from the normal stocking and species pipeline:

* records that already contain ``watercode`` are never queried or changed;
* the default mode is report-only and does not modify ``waters.json``;
* ``--apply`` accepts only unique, high-confidence matches;
* ambiguous or weak candidates remain unchanged for manual review.

The script queries the official Colorado Fishing Atlas Watercode Waterbodies and
Watercode Streams layers by the stored latitude/longitude.  An accepted code can
then be consumed by the existing ``enrich_atlas_species.py`` script without any
change to its established behavior for the other waters.
"""
from __future__ import annotations

import argparse
import json
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


def name_score(water: dict[str, Any], attributes: dict[str, Any]) -> float:
    left = [normalize_name(name) for name in water_names(water)]
    right = [normalize_name(name) for name in candidate_names(attributes)]
    left = [name for name in left if name]
    right = [name for name in right if name]
    if not left or not right:
        return 0.0

    best = 0.0
    for source in left:
        for target in right:
            if source == target:
                return 1.0
            if source in target or target in source:
                best = max(best, 0.92)
            best = max(best, SequenceMatcher(None, source, target).ratio())
    return round(best, 4)


def query_layer(
    session: requests.Session,
    *,
    layer_id: int,
    lat: float,
    lng: float,
    distance_m: int | None,
    timeout: int = 45,
) -> list[dict[str, Any]]:
    params: dict[str, Any] = {
        "f": "json",
        "where": "1=1",
        "geometry": f"{lng},{lat}",
        "geometryType": "esriGeometryPoint",
        "inSR": "4326",
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": OUT_FIELDS,
        "returnGeometry": "false",
        "returnDistinctValues": "true",
    }
    if distance_m:
        params["distance"] = distance_m
        params["units"] = "esriSRUnit_Meter"

    response = session.get(
        f"{ATLAS_SERVICE}/{layer_id}/query",
        params=params,
        timeout=timeout,
    )
    response.raise_for_status()
    payload = response.json()
    if payload.get("error"):
        raise RuntimeError(
            f"Atlas layer {layer_id} returned an error: {payload['error']}"
        )
    return [
        feature.get("attributes", {})
        for feature in payload.get("features", [])
        if isinstance(feature, dict) and isinstance(feature.get("attributes"), dict)
    ]


def unique_candidates(features: list[dict[str, Any]]) -> list[dict[str, Any]]:
    unique: dict[tuple[str, str], dict[str, Any]] = {}
    for attributes in features:
        primary = str(attributes.get("WATERCODE") or "").strip()
        alternate = str(attributes.get("ALT_WATERCODE") or "").strip()
        if not primary and not alternate:
            continue
        unique[(primary, alternate)] = attributes
    return list(unique.values())


def classify_match(
    water: dict[str, Any],
    features: list[dict[str, Any]],
    *,
    layer_name: str,
    search_mode: str,
) -> dict[str, Any]:
    candidates = []
    for attributes in unique_candidates(features):
        primary = str(attributes.get("WATERCODE") or "").strip()
        alternate = str(attributes.get("ALT_WATERCODE") or "").strip()
        candidates.append(
            {
                "watercode": primary or alternate,
                "primary_watercode": primary or None,
                "alternate_watercode": alternate or None,
                "names": candidate_names(attributes),
                "name_score": name_score(water, attributes),
            }
        )
    candidates.sort(key=lambda item: item["name_score"], reverse=True)

    accepted = None
    confidence = "none"
    reason = "No Atlas candidate was found near the stored coordinates."
    if len(candidates) == 1:
        top = candidates[0]
        score = top["name_score"]
        if search_mode == "intersects" and score >= 0.65:
            accepted = top
            confidence = "high"
            reason = "One intersecting Atlas feature with a compatible name."
        elif score >= 0.82:
            accepted = top
            confidence = "high"
            reason = "One nearby Atlas feature with a strong name match."
        else:
            confidence = "review"
            reason = "One nearby feature was found, but its name match is weak."
    elif len(candidates) > 1:
        top = candidates[0]
        runner_up = candidates[1]
        if top["name_score"] >= 0.9 and top["name_score"] - runner_up["name_score"] >= 0.18:
            accepted = top
            confidence = "high"
            reason = "The leading candidate has a clearly stronger name match."
        else:
            confidence = "ambiguous"
            reason = "Multiple plausible Atlas features require manual review."

    return {
        "layer": layer_name,
        "search_mode": search_mode,
        "confidence": confidence,
        "reason": reason,
        "accepted_candidate": accepted,
        "candidates": candidates,
    }


def find_match(session: requests.Session, water: dict[str, Any]) -> dict[str, Any]:
    lat = water.get("lat")
    lng = water.get("lng")
    if not isinstance(lat, (int, float)) or not isinstance(lng, (int, float)):
        return {
            "confidence": "none",
            "reason": "The record does not have usable coordinates.",
            "accepted_candidate": None,
            "candidates": [],
        }

    attempts: list[dict[str, Any]] = []
    for layer_id, layer_name, distance_m in LAYERS:
        exact = query_layer(
            session,
            layer_id=layer_id,
            lat=float(lat),
            lng=float(lng),
            distance_m=None,
        )
        result = classify_match(
            water,
            exact,
            layer_name=layer_name,
            search_mode="intersects",
        )
        attempts.append(result)
        if result.get("confidence") == "high":
            result["attempts"] = attempts
            return result

        nearby = query_layer(
            session,
            layer_id=layer_id,
            lat=float(lat),
            lng=float(lng),
            distance_m=distance_m,
        )
        result = classify_match(
            water,
            nearby,
            layer_name=layer_name,
            search_mode=f"within-{distance_m}m",
        )
        attempts.append(result)
        if result.get("confidence") == "high":
            result["attempts"] = attempts
            return result
        time.sleep(0.15)

    review_attempts = [
        attempt for attempt in attempts if attempt.get("candidates")
    ]
    if review_attempts:
        best = max(
            review_attempts,
            key=lambda attempt: attempt["candidates"][0]["name_score"],
        )
        best = dict(best)
        best["attempts"] = attempts
        return best

    return {
        "confidence": "none",
        "reason": "No waterbody or stream feature was found within the safe search distances.",
        "accepted_candidate": None,
        "candidates": [],
        "attempts": attempts,
    }


def recover(data_dir: Path, *, apply: bool, report_path: Path) -> dict[str, Any]:
    waters_path = data_dir / "waters.json"
    payload = read_json(waters_path, {})
    waters = payload.get("waters", []) if isinstance(payload, dict) else []
    if not isinstance(waters, list):
        raise RuntimeError(f"Invalid waters payload in {waters_path}")

    missing = [water for water in waters if water.get("watercode") in (None, "")]
    session = requests.Session()
    session.headers["User-Agent"] = (
        "ColoradoFishMap/5.1 "
        "(+https://github.com/jessesandlin-Colorado/Colorado-Fish-Stocking-Map)"
    )

    results: list[dict[str, Any]] = []
    applied = 0
    for index, water in enumerate(missing, start=1):
        label = water.get("name") or water.get("atlas_name") or water.get("key")
        try:
            match = find_match(session, water)
        except (requests.RequestException, ValueError, RuntimeError) as exc:
            match = {
                "confidence": "error",
                "reason": str(exc),
                "accepted_candidate": None,
                "candidates": [],
            }

        accepted = match.get("accepted_candidate")
        did_apply = False
        if apply and match.get("confidence") == "high" and accepted:
            # Re-check the invariant immediately before writing.
            if water.get("watercode") in (None, ""):
                code = str(accepted["watercode"])
                water["watercode"] = code
                water["watercode_recovery"] = {
                    "source": "Colorado Fishing Atlas Watercode spatial fallback",
                    "layer": match.get("layer"),
                    "search_mode": match.get("search_mode"),
                    "name_score": accepted.get("name_score"),
                }
                did_apply = True
                applied += 1

        results.append(
            {
                "key": water.get("key"),
                "atlas_id": water.get("atlas_id"),
                "name": label,
                "county": water.get("county"),
                "lat": water.get("lat"),
                "lng": water.get("lng"),
                "applied": did_apply,
                **match,
            }
        )
        print(
            f"[{index}/{len(missing)}] {label}: "
            f"{match.get('confidence')}"
            + (f" -> {accepted.get('watercode')}" if accepted else "")
        )
        time.sleep(0.20)

    report = {
        "mode": "apply" if apply else "report-only",
        "source": ATLAS_SERVICE,
        "waters_total": len(waters),
        "waters_already_with_watercode": len(waters) - len(missing),
        "waters_missing_watercode": len(missing),
        "high_confidence_matches": sum(
            1 for result in results if result.get("confidence") == "high"
        ),
        "applied": applied,
        "results": results,
    }
    write_json(report_path, report)
    if apply and applied:
        write_json(waters_path, payload)
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", default=str(DEFAULT_DATA_DIR))
    parser.add_argument(
        "--report",
        help="Report path; defaults to <data-dir>/watercode-recovery-report.json",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write only unique high-confidence matches into waters.json.",
    )
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    report_path = Path(args.report) if args.report else data_dir / DEFAULT_REPORT
    result = recover(data_dir, apply=args.apply, report_path=report_path)
    print(json.dumps({key: value for key, value in result.items() if key != "results"}, indent=2))


if __name__ == "__main__":
    main()
