import importlib.util
from pathlib import Path

PATH=Path(__file__).parents[1]/"scripts"/"update_data.py"
spec=importlib.util.spec_from_file_location("update_data",PATH)
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

def test_species_from_named_fields():
    features=[{"attributes":{"SPECIES":"Rainbow trout; Brown trout","FA_NAME":"Example"}}]
    names,meta=m._species_from_attributes(features)
    assert names==["Brown trout","Rainbow trout"]
    assert "SPECIES" in meta["fields_examined"]

def test_species_from_official_html_vocabulary():
    html="<div><b>Fish species:</b> Rainbow Trout, Kokanee Salmon and Lake Trout</div>"
    assert m._species_from_html(html)==["Kokanee salmon","Lake trout","Rainbow trout"]

def test_no_habitat_inference():
    html="<p>Cold high mountain lake stocked with catchables.</p>"
    assert m._species_from_html(html)==[]
