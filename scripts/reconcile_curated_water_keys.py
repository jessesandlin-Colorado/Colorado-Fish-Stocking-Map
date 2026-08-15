#!/usr/bin/env python3
"""Keep curated map metadata attached when generated water keys change."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).parents[1]
CONFIG_PATHS = (
    ROOT / "config" / "fishing_reports.json",
    ROOT / "config" / "gold_medal_waters.json",
)


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def identity(value: Any) -> str | None:
    text = str(value or "").strip()
    return text if text and text != "0" else None


def unique_index(waters: list[dict[str, Any]], field: str) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for water in waters:
        value = identity(water.get(field))
        if value:
            grouped.setdefault(value, []).append(water)
    return {value: rows[0] for value, rows in grouped.items() if len(rows) == 1}


def target_key(
    old_key: str,
    old_by_key: dict[str, dict[str, Any]],
    new_by_key: dict[str, dict[str, Any]],
    new_by_watercode: dict[str, dict[str, Any]],
    new_by_atlas_id: dict[str, dict[str, Any]],
) -> str | None:
    if old_key in new_by_key:
        return old_key

    old = old_by_key.get(old_key, {})
    watercode = identity(old.get("watercode"))
    atlas_id = identity(old.get("atlas_id"))
    if not watercode and old_key.startswith("atlas-watercode-"):
        watercode = identity(old_key.removeprefix("atlas-watercode-"))
    if not atlas_id and old_key.startswith("atlas-") and not old_key.startswith("atlas-watercode-"):
        atlas_id = identity(old_key.removeprefix("atlas-"))

    if watercode and watercode in new_by_watercode:
        return str(new_by_watercode[watercode]["key"])
    if atlas_id and atlas_id in new_by_atlas_id:
        return str(new_by_atlas_id[atlas_id]["key"])
    return None


def merge_value(existing: Any, incoming: Any, key: str) -> Any:
    if existing == incoming:
        return existing
    if isinstance(existing, list) and isinstance(incoming, list):
        combined = []
        seen = set()
        for item in [*existing, *incoming]:
            marker = json.dumps(item, sort_keys=True)
            if marker not in seen:
                seen.add(marker)
                combined.append(item)
        return combined
    raise RuntimeError(f"Conflicting curated values resolve to {key}")


def reconcile(prior_path: Path, current_path: Path, config_paths: tuple[Path, ...] = CONFIG_PATHS) -> dict[str, Any]:
    old_waters = load(prior_path).get("waters", [])
    new_waters = load(current_path).get("waters", [])
    old_by_key = {str(w["key"]): w for w in old_waters if w.get("key")}
    new_by_key = {str(w["key"]): w for w in new_waters if w.get("key")}
    new_by_watercode = unique_index(new_waters, "watercode")
    new_by_atlas_id = unique_index(new_waters, "atlas_id")
    report: dict[str, Any] = {"remapped": {}, "unchanged": 0}

    for path in config_paths:
        payload = load(path)
        curated = payload.get("waters", {})
        rewritten: dict[str, Any] = {}
        unresolved = []
        for old_key, value in curated.items():
            new_key = target_key(
                old_key, old_by_key, new_by_key, new_by_watercode, new_by_atlas_id
            )
            if not new_key:
                unresolved.append(old_key)
                continue
            if new_key != old_key:
                report["remapped"][old_key] = new_key
            else:
                report["unchanged"] += 1
            rewritten[new_key] = (
                merge_value(rewritten[new_key], value, new_key)
                if new_key in rewritten
                else value
            )
        if unresolved:
            raise RuntimeError(
                f"{path.name}: curated water keys could not be reconciled: "
                + ", ".join(sorted(unresolved))
            )
        payload["waters"] = rewritten
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prior", required=True)
    parser.add_argument("--current", default=str(ROOT / "data" / "waters.json"))
    args = parser.parse_args()
    report = reconcile(Path(args.prior), Path(args.current))
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
