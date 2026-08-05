#!/usr/bin/env python3
"""Match mapped stream waters to Colorado DWR telemetry stations.

Only high-confidence matches are published. All plausible candidates are
written to a review report so the proximity/name heuristic stays auditable.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import re
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

import requests

ROOT = Path(__file__).parents[1]
DEFAULT_OVERRIDES = ROOT / "config" / "streamflow_overrides.json"
STATIONS_URL = "https://dwr.state.co.us/Rest/GET/api/v2/telemetrystations/telemetrystation"
DAILY_URL = "https://dwr.state.co.us/Rest/GET/api/v2/telemetrystations/telemetrytimeseriesday"
FLOW_PARAMETERS = {"DISCHRG", "DISCHARGE", "FLOW", "STREAMFLOW"}
GENERIC_WORDS = {"river", "stream", "creek", "fork", "branch", "at", "above", "below", "near", "in", "the", "of", "number", "no", "station", "gage", "gauge"}


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def normalize_name(value: Any) -> str:
    text = str(value or "").lower().replace("&", " and ")
    text = re.sub(r"\b(?:river|stream|creek)\s+#?\d+\b", " ", text)
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", text)).strip()


def core_tokens(value: Any) -> set[str]:
    return {word for word in normalize_name(value).split() if word not in GENERIC_WORDS and len(word) > 1}


def name_similarity(water: dict[str, Any], station: dict[str, Any]) -> float:
    water_names = [water.get(field) for field in ("canonical_name", "atlas_name", "alternate_name", "name")]
    station_names = [station.get("waterSource"), station.get("stationName")]
    best = 0.0
    for left in filter(None, water_names):
        for right in filter(None, station_names):
            left_core, right_core = core_tokens(left), core_tokens(right)
            if not left_core or not right_core:
                continue
            overlap = len(left_core & right_core) / len(left_core | right_core)
            sequence = SequenceMatcher(None, " ".join(sorted(left_core)), " ".join(sorted(right_core))).ratio()
            best = max(best, overlap, sequence * 0.9)
    return round(best, 3)


def distance_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 3958.7613
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return radius * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def is_stream(water: dict[str, Any]) -> bool:
    return bool(re.search(r"stream|river|creek", str(water.get("location_type") or ""), re.I))


def is_flow_station(station: dict[str, Any]) -> bool:
    parameter = str(station.get("parameter") or "").upper()
    units = str(station.get("units") or "").lower()
    station_type = str(station.get("stationType") or "").lower()
    station_name = str(station.get("stationName") or "").lower()
    unsuitable = re.search(r"\b(?:seepage|impact point|ditch|tunnel|conduit|pipeline)\b", station_name)
    return not unsuitable and "stream gage" in station_type and (parameter in FLOW_PARAMETERS or "cfs" in units or "cubic feet" in units)


def classify_match(distance: float, similarity: float) -> tuple[str, float]:
    distance_score = max(0.0, 1.0 - distance / 10.0)
    score = round(similarity * 0.72 + distance_score * 0.28, 3)
    high = (distance <= 0.75 and similarity >= 0.72) or (distance <= 2.5 and similarity >= 0.90) or (distance <= 10.0 and similarity >= 0.99)
    possible = distance <= 10.0 and similarity >= 0.55
    return ("high" if high else "review" if possible else "rejected"), score


def candidate_matches(waters: list[dict[str, Any]], stations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    usable = [s for s in stations if is_flow_station(s) and s.get("latitude") is not None and s.get("longitude") is not None]
    for water in filter(is_stream, waters):
        if water.get("lat") is None or water.get("lng") is None:
            continue
        for station in usable:
            distance = distance_miles(float(water["lat"]), float(water["lng"]), float(station["latitude"]), float(station["longitude"]))
            if distance > 10.0:
                continue
            similarity = name_similarity(water, station)
            confidence, score = classify_match(distance, similarity)
            if confidence == "rejected":
                continue
            candidates.append({"water_key": water["key"], "water_name": water.get("canonical_name") or water.get("name"), "station_abbrev": station.get("abbrev"), "station_name": station.get("stationName"), "water_source": station.get("waterSource"), "distance_miles": round(distance, 2), "name_similarity": similarity, "match_score": score, "confidence": confidence, "station": station})
    return sorted(candidates, key=lambda item: (item["water_key"], -item["match_score"], item["distance_miles"]))


def choose_matches(candidates: list[dict[str, Any]], overrides: dict[str, str] | None = None) -> dict[str, dict[str, Any]]:
    overrides = overrides or {}
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for candidate in candidates:
        grouped[candidate["water_key"]].append(candidate)
    chosen = {}
    for water_key, options in grouped.items():
        approved_abbrev = overrides.get(water_key)
        if approved_abbrev:
            approved = next((option for option in options if option["station_abbrev"] == approved_abbrev), None)
            if approved:
                approved = {**approved, "confidence": "manual-approved", "match_score": 1.0}
                chosen[water_key] = approved
            continue
        high = [option for option in options if option["confidence"] == "high"]
        if not high:
            continue
        if len(high) > 1 and high[0]["match_score"] - high[1]["match_score"] < 0.08:
            continue
        chosen[water_key] = high[0]
    return chosen


def request_rows(url: str, params: dict[str, Any], api_key: str | None) -> list[dict[str, Any]]:
    headers = {"User-Agent": "COFish/1.0 (+https://cofish.app)"}
    if api_key:
        headers["ApiKey"] = api_key
    response = requests.get(url, params=params, headers=headers, timeout=90)
    response.raise_for_status()
    payload = response.json()
    return payload.get("ResultList", payload if isinstance(payload, list) else [])


def fetch_stations(api_key: str | None) -> list[dict[str, Any]]:
    return request_rows(STATIONS_URL, {"format": "json", "includeHistoric": "false", "includeThirdParty": "true", "pageSize": 10000}, api_key)


def fetch_daily(abbrevs: list[str], api_key: str | None, days: int = 30) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    start = (date.today() - timedelta(days=days - 1)).isoformat()
    for index in range(0, len(abbrevs), 75):
        rows.extend(request_rows(DAILY_URL, {"format": "jsonforced", "abbrev": ",".join(abbrevs[index:index + 75]), "parameter": "DISCHRG", "startDate": start, "endDate": date.today().isoformat(), "includeThirdParty": "true", "pageSize": 10000}, api_key))
    return rows


def write_review_report(path: Path, candidates: list[dict[str, Any]], chosen: dict[str, dict[str, Any]]) -> None:
    fields = ["published", "confidence", "water_key", "water_name", "station_abbrev", "station_name", "water_source", "distance_miles", "name_similarity", "match_score"]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for item in candidates:
            row = {key: item.get(key) for key in fields}
            row["published"] = item["water_key"] in chosen and chosen[item["water_key"]]["station_abbrev"] == item["station_abbrev"]
            writer.writerow(row)


def build_payload(chosen: dict[str, dict[str, Any]], daily_rows: list[dict[str, Any]]) -> dict[str, Any]:
    trends: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in daily_rows:
        abbrev, value = str(row.get("abbrev") or ""), row.get("measValue")
        if abbrev and value is not None:
            trends[abbrev].append({"date": str(row.get("measDate") or "")[:10], "value": value})
    waters = {}
    for key, match in chosen.items():
        station, abbrev = match["station"], str(match["station"].get("abbrev") or "")
        waters[key] = {"station": {"abbrev": abbrev, "name": station.get("stationName"), "water_source": station.get("waterSource"), "latitude": station.get("latitude"), "longitude": station.get("longitude"), "distance_miles": match["distance_miles"], "provider": station.get("dataSource"), "usgs_station_id": station.get("usgsStationId"), "official_url": station.get("moreInformation")}, "current": {"value": station.get("measValue"), "units": station.get("units") or "cfs", "measured_at": station.get("measDateTime"), "parameter": station.get("parameter"), "flag": station.get("flagA"), "review_status": station.get("flagB")}, "trend": sorted(trends.get(abbrev, []), key=lambda point: point["date"])[-30:], "match": {"confidence": match["confidence"], "score": match["match_score"], "name_similarity": match["name_similarity"]}}
    return {"generated_at": datetime.now(timezone.utc).isoformat(), "source": "Colorado Division of Water Resources HydroBase REST API", "source_url": "https://dwr.state.co.us/tools/stations", "summary": {"matched_waters": len(waters), "stations": len({v["station"]["abbrev"] for v in waters.values()})}, "waters": waters}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--waters", type=Path, default=ROOT / "data" / "waters.json")
    parser.add_argument("--stations-fixture", type=Path)
    parser.add_argument("--daily-fixture", type=Path)
    parser.add_argument("--overrides", type=Path, default=DEFAULT_OVERRIDES)
    parser.add_argument("--output", type=Path, default=ROOT / "data" / "streamflow.json")
    parser.add_argument("--report", type=Path, default=ROOT / "data" / "streamflow-match-report.csv")
    args = parser.parse_args()
    waters = read_json(args.waters).get("waters", [])
    api_key = os.getenv("DWR_API_KEY") or None
    stations = read_json(args.stations_fixture) if args.stations_fixture else fetch_stations(api_key)
    candidates = candidate_matches(waters, stations)
    overrides_payload = read_json(args.overrides) if args.overrides.exists() else {}
    chosen = choose_matches(candidates, overrides_payload.get("approved", {}))
    abbrevs = sorted({str(item["station_abbrev"]) for item in chosen.values() if item.get("station_abbrev")})
    daily = read_json(args.daily_fixture) if args.daily_fixture else fetch_daily(abbrevs, api_key)
    write_json(args.output, build_payload(chosen, daily))
    write_review_report(args.report, candidates, chosen)
    print(f"Matched {len(chosen)} of {sum(map(is_stream, waters))} mapped streams to {len(abbrevs)} stations")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
