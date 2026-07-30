import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BATHYMETRY = ROOT / "data" / "bathymetry"


def test_bathymetry_files_have_valid_colorado_contours():
    files = sorted(BATHYMETRY.glob("*.geojson"))
    assert len(files) >= 5

    for path in files:
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload["type"] == "FeatureCollection"
        assert payload["features"]
        assert payload["metadata"]["source"] == "U.S. Bureau of Reclamation"

        for feature in payload["features"]:
            properties = feature["properties"]
            assert properties["depth_ft"] > 0
            assert feature["geometry"]["type"] == "LineString"
            for longitude, latitude in feature["geometry"]["coordinates"]:
                assert -110 < longitude < -102
                assert 36 < latitude < 42
