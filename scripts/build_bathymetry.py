#!/usr/bin/env python3
"""Convert the Reclamation Blue Mesa survey raster to compact web contours.

Example:
    python scripts/build_bathymetry.py source.tif \
      data/bathymetry/blue-mesa-2019.geojson
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import contourpy
import numpy as np
import rasterio
from pyproj import Transformer
from rasterio.enums import Resampling
from shapely.geometry import LineString, mapping
from shapely.ops import transform

FULL_POOL_FT = 7519
DEPTHS_FT = range(25, 326, 25)
SOURCE_URL = (
    "https://www.usbr.gov/tsc/techreferences/reservoir/"
    "BlueMesaReservoir2019GISSurface.tif.zip"
)


def build_features(source: Path) -> list[dict]:
    with rasterio.open(source) as raster:
        factor = 6
        height, width = raster.height // factor, raster.width // factor
        elevations = raster.read(
            1,
            out_shape=(height, width),
            resampling=Resampling.average,
            masked=True,
        ).filled(np.nan)
        matrix = raster.transform * raster.transform.scale(
            raster.width / width, raster.height / height
        )
        source_crs = raster.crs

    elevations[(elevations > FULL_POOL_FT) | (elevations < 7180)] = np.nan
    x_coords = matrix.c + (np.arange(width) + 0.5) * matrix.a
    y_coords = matrix.f + (np.arange(height) + 0.5) * matrix.e
    contours = contourpy.contour_generator(
        x=x_coords, y=y_coords, z=elevations, name="serial", corner_mask=True
    )
    to_wgs84 = Transformer.from_crs(source_crs, "EPSG:4326", always_xy=True).transform

    features = []
    for depth_ft in DEPTHS_FT:
        elevation_ft = FULL_POOL_FT - depth_ft
        for points in contours.lines(elevation_ft):
            if len(points) < 3:
                continue
            line = LineString(points).simplify(40, preserve_topology=False)
            if line.length < 300:
                continue
            features.append(
                {
                    "type": "Feature",
                    "properties": {
                        "depth_ft": depth_ft,
                        "elevation_ft": elevation_ft,
                        "major": depth_ft % 100 == 0,
                    },
                    "geometry": mapping(transform(to_wgs84, line)),
                }
            )
    return features


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    payload = {
        "type": "FeatureCollection",
        "name": "Blue Mesa Reservoir 2019 bathymetric contours",
        "metadata": {
            "water": "Blue Mesa Reservoir",
            "survey_year": 2019,
            "full_pool_elevation_ft": FULL_POOL_FT,
            "depth_reference": "Feet below the published full-pool elevation",
            "vertical_datum": "Reclamation Project Vertical Datum",
            "source": "U.S. Bureau of Reclamation",
            "source_url": SOURCE_URL,
            "disclaimer": (
                "Historical survey contours are for planning only and do not "
                "represent current depth or navigation hazards."
            ),
        },
        "features": build_features(args.source),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, separators=(",", ":")) + "\n", encoding="utf-8"
    )
    print(f"Wrote {len(payload['features'])} contours to {args.output}")


if __name__ == "__main__":
    main()
