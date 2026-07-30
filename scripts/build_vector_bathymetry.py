#!/usr/bin/env python3
"""Convert Reclamation FileGDB contours into compact web GeoJSON."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pyogrio
from shapely import concave_hull, force_2d, union_all
from shapely.geometry import LineString, MultiLineString, mapping


def line_parts(geometry):
    if isinstance(geometry, LineString):
        yield geometry
    elif isinstance(geometry, MultiLineString):
        yield from geometry.geoms


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--layer", required=True)
    parser.add_argument("--clip-layer", action="append", default=[])
    parser.add_argument("--clip-buffer", type=float, default=100)
    parser.add_argument("--elevation-field", default="Z_MAX")
    parser.add_argument("--reference-elevation", type=float, required=True)
    parser.add_argument("--interval", type=int, default=10)
    parser.add_argument("--max-depth", type=int)
    parser.add_argument("--water", required=True)
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--datum", required=True)
    parser.add_argument("--source-url", required=True)
    args = parser.parse_args()

    contours = pyogrio.read_dataframe(args.source, layer=args.layer)
    if contours.crs is None:
        raise RuntimeError("Source contours have no coordinate reference system")
    if args.clip_layer:
        survey_points = [
            pyogrio.read_dataframe(args.source, layer=layer).geometry
            for layer in args.clip_layer
        ]
        point_union = union_all(
            [geometry for series in survey_points for geometry in series if geometry]
        )
        survey_area = concave_hull(point_union, ratio=0.15).buffer(args.clip_buffer)
        contours.geometry = contours.geometry.intersection(survey_area)
        contours = contours[~contours.geometry.is_empty]
    contours = contours.to_crs("EPSG:4326")
    available = sorted(
        {
            float(value)
            for value in contours[args.elevation_field].dropna().unique()
            if float(value) <= args.reference_elevation
        },
        reverse=True,
    )
    if not available:
        raise RuntimeError("No contours occur below the reference elevation")

    chosen: dict[float, int] = {}
    depth = args.interval
    maximum_depth = args.max_depth or (args.reference_elevation - min(available))
    while depth <= maximum_depth + args.interval / 2:
        target = args.reference_elevation - depth
        elevation = min(available, key=lambda value: abs(value - target))
        if abs(elevation - target) <= max(2, args.interval / 3):
            chosen[elevation] = round(args.reference_elevation - elevation)
        depth += args.interval

    features = []
    for _, row in contours.iterrows():
        elevation = float(row[args.elevation_field])
        if elevation not in chosen:
            continue
        depth_ft = chosen[elevation]
        for line in line_parts(row.geometry):
            line = line.simplify(0.000025, preserve_topology=False)
            if line.is_empty or len(line.coords) < 3:
                continue
            features.append(
                {
                    "type": "Feature",
                    "properties": {
                        "depth_ft": depth_ft,
                        "elevation_ft": round(elevation, 1),
                        "major": depth_ft % (args.interval * 5) == 0,
                    },
                    "geometry": mapping(force_2d(line)),
                }
            )

    payload = {
        "type": "FeatureCollection",
        "name": f"{args.water} {args.year} bathymetric contours",
        "metadata": {
            "water": args.water,
            "survey_year": args.year,
            "reference_elevation_ft": args.reference_elevation,
            "contour_interval_ft": args.interval,
            "depth_reference": "Feet below the documented reference elevation",
            "vertical_datum": args.datum,
            "source": "U.S. Bureau of Reclamation",
            "source_url": args.source_url,
            "disclaimer": (
                "Historical survey contours are for planning only and do not "
                "represent current depth or navigation hazards."
            ),
        },
        "features": features,
    }
    if not features:
        raise RuntimeError("No output contours were generated")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, separators=(",", ":")) + "\n", encoding="utf-8"
    )
    print(f"Wrote {len(features)} contours to {args.output}")


if __name__ == "__main__":
    main()
