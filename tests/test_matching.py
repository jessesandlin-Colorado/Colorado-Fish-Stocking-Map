import importlib.util
from pathlib import Path
import unittest

SCRIPT = Path(__file__).parents[1] / "scripts" / "update_data.py"
spec = importlib.util.spec_from_file_location("update_data", SCRIPT)
update_data = importlib.util.module_from_spec(spec)
spec.loader.exec_module(update_data)


class AtlasFallbackTests(unittest.TestCase):
    def test_reviewed_alias_fallback(self):
        original = update_data.arcgis_query

        def fake_query(client, service, layer, where, cache_key):
            if where.startswith("UNI_ID="):
                return [], "cache-fresh"
            if "Twin Lakes Reservoir" in where and layer == 63:
                return [{
                    "attributes": {"FA_NAME": "Twin Lakes Reservoir", "COUNTYNAME": "Lake"},
                    "geometry": {"x": -106.4, "y": 39.1},
                }], "network"
            return [], "network"

        try:
            update_data.arcgis_query = fake_query
            result = update_data.query_atlas(
                object(), 298, ["Twin Lakes Lower"], {"aliases": ["Twin Lakes Reservoir"]}
            )
        finally:
            update_data.arcgis_query = original

        self.assertEqual(result["match_method"], "reviewed-name-alias")
        self.assertEqual(result["atlas_layer"], 63)

    def test_manual_override_requires_coordinates(self):
        original = update_data.arcgis_query
        update_data.arcgis_query = lambda *args, **kwargs: ([], "network")
        try:
            missing = update_data.query_atlas(object(), 123, ["Test"], {"aliases": ["Test"]})
            manual = update_data.query_atlas(
                object(), 123, ["Test"], {"canonical_name": "Test", "lat": 39.0, "lng": -105.0}
            )
        finally:
            update_data.arcgis_query = original

        self.assertIsNone(missing)
        self.assertEqual(manual["match_method"], "manual-override")

    def test_verified_override_file_has_coordinates_for_all_eight_waters(self):
        overrides = update_data.load_overrides(Path(__file__).parents[1] / "config" / "atlas_overrides.json")
        expected_ids = {"396", "472", "271", "298", "804", "999", "771", "1432"}
        self.assertEqual(set(overrides), expected_ids)
        for atlas_id, override in overrides.items():
            self.assertIsInstance(override.get("lat"), (int, float), atlas_id)
            self.assertIsInstance(override.get("lng"), (int, float), atlas_id)
            self.assertTrue(override.get("canonical_name"), atlas_id)

    def test_region_is_not_published(self):
        page = '''<table><tr><td>Southwest</td><td>Test Lake</td><td>07/24/2026</td>
        <td><a href="https://ndismaps.nrel.colostate.edu/fishingatlas/index.aspx?keyword=fspot&value=123">Atlas</a></td>
        </tr></table>'''
        event = update_data.parse_report(page)[0]
        self.assertEqual(event["name"], "Test Lake")
        self.assertNotIn("region", event)


class ReportWindowValidationTests(unittest.TestCase):
    @staticmethod
    def _events(count, report_date):
        return [
            {
                "atlas_id": index,
                "name": f"Water {index}",
                "report_date": report_date,
            }
            for index in range(count)
        ]

    @staticmethod
    def _waters(count):
        return [
            {
                "atlas_id": index,
                "name": f"Water {index}",
                "lat": 39.0,
                "lng": -105.0,
                "species": ["Rainbow trout"],
            }
            for index in range(count)
        ]

    def test_current_fully_matched_window_reset_preserves_history(self):
        today = update_data.datetime.now(update_data.timezone.utc).date().isoformat()
        findings = update_data.validate(
            self._events(18, today),
            self._waters(18),
            [],
            prior_count=107,
            prior_history_count=106,
            history_count=124,
        )
        self.assertFalse(any(item["level"] == "critical" for item in findings))
        self.assertTrue(any(item["code"] == "rolling-window-reset" for item in findings))

    def test_window_drop_remains_critical_when_history_shrinks(self):
        today = update_data.datetime.now(update_data.timezone.utc).date().isoformat()
        findings = update_data.validate(
            self._events(18, today),
            self._waters(18),
            [],
            prior_count=107,
            prior_history_count=106,
            history_count=100,
        )
        self.assertTrue(any(item["code"] == "large-report-drop" for item in findings))

    def test_window_drop_remains_critical_when_report_is_stale(self):
        findings = update_data.validate(
            self._events(18, "2025-01-01"),
            self._waters(18),
            [],
            prior_count=107,
            prior_history_count=106,
            history_count=124,
        )
        self.assertTrue(any(item["code"] == "large-report-drop" for item in findings))


if __name__ == "__main__":
    unittest.main()
