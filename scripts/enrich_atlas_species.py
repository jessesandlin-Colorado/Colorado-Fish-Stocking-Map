#!/usr/bin/env python3
"""Enrich published waters with current species from the Colorado Fishing Atlas.

The Fishing Atlas identify service exposes its species relationship as XML when
queried with a water's WATERCODE under the parameter name ``key``. This script
runs after the normal stocking-data build, replaces inferred/legacy species
with the official current Atlas list when available, and republishes
``data/species.json`` from the same source.
"""
from __future__ import annotations

import argparse
import json
import random
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

PROJECT_ROOT = Path(__file__).parents[1]
DEFAULT_DATA_DIR = PROJECT_ROOT / "data"
SPECIES_ENDPOINT = "https://ndismaps.nrel.colostate.edu/FishingAtlas/IdentifyFishingPlacesDB.aspx"

# Reviewed matches recovered from the Colorado Fishing Atlas. The normal CPW
# stocking-data build may recreate these manual-override records without a
# WATERCODE, so restore the verified value immediately before species lookup.
RECOVERED_WATERCODES_BY_ATLAS_ID: dict[int, str] = {
    298: "80036",  # Twin Lakes Reservoir
    472: "92724",  # Trujillo Meadows Reservoir
    271: "89929",  # Rio Grande Reservoir
    396: "88511",  # Beaver Creek Reservoir
    804: "81531",  # Fairplay Kids Pond
    999: "70431",  # Berry Creek Pond
    771: "91746",  # Pitkin Kids Pond
}


def read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def apply_recovered_watercodes(waters: list[dict[str, Any]]) -> int:
    """Restore reviewed watercodes when the upstream build omitted them."""
    applied = 0
    for water in waters:
        atlas_id = water.get("atlas_id")
        recovered = RECOVERED_WATERCODES_BY_ATLAS_ID.get(atlas_id)
        if recovered and water.get("watercode") in (None, ""):
            water["watercode"] = recovered
            applied += 1
    return applied


def parse_species_xml(text: str) -> list[str]:
    """Return unique AtlasFish/linkname values in stable alphabetical order."""
    try:
        root = ET.fromstring(text.lstrip("\ufeff"))
    except ET.ParseError as exc:
        raise ValueError(f"Atlas species response was not valid XML: {exc}") from exc

    names = {
        element.text.strip()
        for element in root.findall(".//AtlasFish/linkname")
        if element.text and element.text.strip()
    }
    return sorted(names, key=str.casefold)


def get_official_species(
    session: requests.Session,
    watercode: str | int,
    *,
    retries: int = 3,
    timeout: int = 45,
) -> list[str]:
    """Fetch current species for one WATERCODE from the official Atlas service."""
    params = {"key": str(watercode), "filename": "tblMasterSpecies"}
    last_error: Exception | None = None

    for attempt in range(1, retries + 1):
        try:
            response = session.get(SPECIES_ENDPOINT, params=params, timeout=timeout)
            response.raise_for_status()
            body = response.text.strip()
            if body == "Missing parameter key.":
                raise RuntimeError("Atlas rejected the required key parameter")
            return parse_species_xml(response.text)
        except (requests.RequestException, RuntimeError, ValueError) as exc:
            last_error = exc
            if attempt < retries:
                time.sleep((2 ** (attempt - 1)) + random.uniform(0.1, 0.4))

    raise RuntimeError(f"Species lookup failed for WATERCODE {watercode}: {last_error}")


def enrich(data_dir: Path) -> dict[str, int]:
    waters_path = data_dir / "waters.json"
    payload = read_json(waters_path, {})
    waters = payload.get("waters", []) if isinstance(payload, dict) else []
    if not isinstance(waters, list):
        raise RuntimeError(f"Invalid waters payload in {waters_path}")

    recovered_watercodes_applied = apply_recovered_watercodes(waters)
    if recovered_watercodes_applied:
        print(f"Applied {recovered_watercodes_applied} recovered watercodes")

    session = requests.Session()
    session.headers["User-Agent"] = (
        "ColoradoFishMap/5.1 "
        "(+https://github.com/jessesandlin-Colorado/Colorado-Fish-Stocking-Map)"
    )

    cache: dict[str, list[str]] = {}
    fetched = 0
    available = 0
    missing_watercode = 0
    failed = 0

    for index, water in enumerate(waters, start=1):
        watercode = water.get("watercode")
        label = water.get("name") or water.get("atlas_name") or water.get("atlas_id")
        if watercode in (None, ""):
            missing_watercode += 1
            water.setdefault("species", [])
            water["species_status"] = "missing-watercode"
            continue

        key = str(watercode)
        try:
            if key not in cache:
                cache[key] = get_official_species(session, key)
                fetched += 1
                time.sleep(random.uniform(0.20, 0.40))
            species = cache[key]
            water["species"] = species
            water["species_status"] = "available" if species else "no-species-listed"
            water["species_data_source"] = "Colorado Fishing Atlas IdentifyFishingPlacesDB.aspx"
            water["species_watercode"] = key
            if species:
                available += 1
            print(f"[{index}/{len(waters)}] {label}: {len(species)} species")
        except RuntimeError as exc:
            failed += 1
            # Preserve previously published values during a temporary Atlas outage.
            water["species_status"] = "retained-prior-after-error"
            water["species_error"] = str(exc)
            print(f"[{index}/{len(waters)}] WARNING {label}: {exc}")

    generated_at = datetime.now(timezone.utc).isoformat()
    payload["generated_at"] = generated_at
    summary = payload.setdefault("summary", {})
    summary["waters_with_species"] = sum(1 for water in waters if water.get("species"))
    summary["unique_species"] = len(
        {species for water in waters for species in water.get("species", [])}
    )
    write_json(waters_path, payload)

    species_payload = {
        "generated_at": generated_at,
        "status": "available" if any(water.get("species") for water in waters) else "no-species-listed",
        "source": SPECIES_ENDPOINT,
        "note": (
            "Current species are read from the official Colorado Fishing Atlas "
            "using key=<WATERCODE>&filename=tblMasterSpecies."
        ),
        "waters_with_species": [
            {
                "atlas_id": water.get("atlas_id"),
                "watercode": water.get("watercode"),
                "name": water.get("name"),
                "species": water.get("species", []),
            }
            for water in waters
            if water.get("species")
        ],
    }
    write_json(data_dir / "species.json", species_payload)

    return {
        "waters": len(waters),
        "unique_watercodes_fetched": fetched,
        "waters_with_species": available,
        "missing_watercode": missing_watercode,
        "recovered_watercodes_applied": recovered_watercodes_applied,
        "failed": failed,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", default=str(DEFAULT_DATA_DIR))
    args = parser.parse_args()
    result = enrich(Path(args.data_dir))
    print(json.dumps(result, indent=2))

    # A total endpoint failure should fail the workflow rather than silently
    # publishing stale data, while isolated failures retain prior values.
    if result["unique_watercodes_fetched"] == 0 and result["failed"]:
        raise SystemExit("No Atlas species requests succeeded")


if __name__ == "__main__":
    main()
