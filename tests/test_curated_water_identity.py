import importlib.util
import json
from pathlib import Path

SCRIPT = Path(__file__).parents[1] / "scripts" / "reconcile_curated_water_keys.py"
spec = importlib.util.spec_from_file_location("reconcile_curated_water_keys", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def write(path, payload):
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_reconciles_by_watercode_before_atlas_id(tmp_path):
    prior = tmp_path / "prior.json"
    current = tmp_path / "current.json"
    reports = tmp_path / "reports.json"
    medals = tmp_path / "medals.json"
    write(prior, {"waters": [{"key": "atlas-watercode-42", "watercode": 42, "atlas_id": 10}]})
    write(current, {"waters": [{"key": "atlas-99", "watercode": 42, "atlas_id": 99}]})
    write(reports, {"waters": {"atlas-watercode-42": [{"source": "Local"}]}})
    write(medals, {"waters": {"atlas-watercode-42": "Section"}})

    result = module.reconcile(prior, current, (reports, medals))

    assert result["remapped"] == {"atlas-watercode-42": "atlas-99"}
    assert "atlas-99" in json.loads(reports.read_text())["waters"]
    assert "atlas-99" in json.loads(medals.read_text())["waters"]


def test_reconciliation_rejects_unresolved_curated_key(tmp_path):
    prior = tmp_path / "prior.json"
    current = tmp_path / "current.json"
    config = tmp_path / "config.json"
    write(prior, {"waters": []})
    write(current, {"waters": []})
    write(config, {"waters": {"atlas-404": "Missing"}})

    try:
        module.reconcile(prior, current, (config,))
    except RuntimeError as exc:
        assert "atlas-404" in str(exc)
    else:
        raise AssertionError("Expected unresolved curated key to fail")
