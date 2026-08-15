import csv,json,subprocess,sys
from scripts.update_streamflow import candidate_matches,choose_matches,distance_miles,name_similarity

def water(name="Cache la Poudre River",lat=40.59,lng=-105.14,key="poudre"):
    return {"key":key,"name":name,"canonical_name":name,"location_type":"Stream or River","lat":lat,"lng":lng}
def station(name="CACHE LA POUDRE RIVER AT CANYON MOUTH",source="Cache la Poudre River",lat=40.59,lng=-105.14,abbrev="CLAFTCCO"):
    return {"abbrev":abbrev,"stationName":name,"waterSource":source,"latitude":lat,"longitude":lng,"stationType":"Stream Gage","parameter":"DISCHRG","units":"CFS","measValue":321}
def test_distance_and_name_matching():
    assert distance_miles(40.59,-105.14,40.60,-105.14)<1
    assert name_similarity(water(),station())>=.9
def test_auto_match_requires_name_and_proximity():
    candidates=candidate_matches([water()],[station(),station(name="BIG THOMPSON RIVER NEAR DRAKE",source="Big Thompson River",abbrev="WRONG")])
    assert choose_matches(candidates)["poudre"]["station_abbrev"]=="CLAFTCCO"
    assert all(item["station_abbrev"]!="WRONG" for item in candidates)
def test_ambiguous_high_matches_are_held_for_review():
    options=candidate_matches([water()],[station(abbrev="ONE"),station(lat=40.591,abbrev="TWO")])
    assert "poudre" not in choose_matches(options)
    assert choose_matches(options,{"poudre":"ONE"})["poudre"]["confidence"]=="manual-approved"
def test_exact_name_can_match_farther_access_point():
    farther=station(lat=40.68)
    candidates=candidate_matches([water()],[farther])
    assert candidates[0]["distance_miles"]>3
    assert choose_matches(candidates)["poudre"]["station_abbrev"]=="CLAFTCCO"
def test_fork_mismatch_is_not_auto_approved_at_longer_distance():
    main=water(name="Cache la Poudre River")
    north=station(name="NORTH FORK CACHE LA POUDRE RIVER",source="North Fork Cache la Poudre River",lat=40.68)
    assert choose_matches(candidate_matches([main],[north]))=={}
def test_diversion_structures_are_not_published_as_stream_flow():
    diversion=station(name="DENVER WATER CONDUIT NO 20",source="Cache la Poudre River")
    diversion["stationType"]="Diversion Structure"
    assert candidate_matches([water()],[diversion])==[]
def test_frontend_bundle_and_loader_are_present():
    assert "streamflowScript.src = 'streamflow.js'" in open("share-links.js",encoding="utf-8").read()
    bundle=open("streamflow.js",encoding="utf-8").read()
    assert "30-day stream flow trend" in bundle
    assert "View official DWR station" in bundle
    catalog=open("catalog-map-style.js",encoding="utf-8").read()
    assert "flow-gauge" in catalog
    assert "flow-available-badge" in catalog
def test_full_map_legend_explains_marker_colors_and_gauge():
    legend=open("map-symbol-legend.js",encoding="utf-8").read()
    for label in ("Green · 0–14 days","Yellow · 15–30 days","Red · 31–60 days","Gray · 61+ days","Blue pointer · lake or pond","Green pointer · river or stream","Gold ring · Gold Medal Water","Gauge · stream-flow data"):
        assert label in legend

def test_gold_medal_sections_have_map_treatment_and_reports():
    medal=json.load(open("config/gold_medal_waters.json",encoding="utf-8"))["waters"]
    reports=json.load(open("config/fishing_reports.json",encoding="utf-8"))["waters"]
    waters={item["key"]:item for item in json.load(open("data/waters.json",encoding="utf-8"))["waters"]}
    dream=json.load(open("data/dream-stream.json",encoding="utf-8"))
    waters[dream["key"]]=dream
    assert medal
    assert set(medal).issubset(waters)
    assert set(medal).issubset(reports)
    assert all(reports[key] for key in medal)
    catalog=open("catalog-map-style.js",encoding="utf-8").read()
    assert "gold-medal-water" in catalog
    assert "gold-medal-badge" in catalog
    assert dream["atlas_id"]==689
    assert dream["watercode"]=="30851"
    assert dream["property_name"]=="Charlie Meyers SWA"
def test_fixture_build_writes_public_data_and_review_report(tmp_path):
    waters,stations,daily,output,report=[tmp_path/name for name in ("waters.json","stations.json","daily.json","streamflow.json","report.csv")]
    waters.write_text(json.dumps({"waters":[water()]}),encoding="utf-8")
    stations.write_text(json.dumps([station()]),encoding="utf-8")
    daily.write_text(json.dumps([{"abbrev":"CLAFTCCO","measDate":"2026-08-01","measValue":300}]),encoding="utf-8")
    subprocess.run([sys.executable,"scripts/update_streamflow.py","--waters",str(waters),"--stations-fixture",str(stations),"--daily-fixture",str(daily),"--output",str(output),"--report",str(report)],check=True)
    payload=json.loads(output.read_text(encoding="utf-8"))
    assert payload["waters"]["poudre"]["current"]["value"]==321
    assert payload["waters"]["poudre"]["trend"][0]["value"]==300
    with report.open(encoding="utf-8") as handle: assert next(csv.DictReader(handle))["published"]=="True"
