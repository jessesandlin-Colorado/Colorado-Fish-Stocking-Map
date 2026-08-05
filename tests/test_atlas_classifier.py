from scripts.classify_atlas_only_waters import duplicate_candidate, existing_index


def mapped(name, lat, lng):
    return {"name": name, "lat": lat, "lng": lng}


def atlas(name, lat, lng):
    return {"name": name, "lat": lat, "lng": lng}


def test_distant_generic_exact_name_is_not_a_duplicate():
    names, existing = existing_index([mapped("South Platte River", 39.70, -105.20)])
    kind, match, distance = duplicate_candidate(
        atlas("South Platte River", 38.97, -105.59), names, existing
    )
    assert (kind, match, distance) == ("", "", None)


def test_nearest_exact_name_candidate_is_used():
    names, existing = existing_index([
        mapped("Blue Lake", 40.00, -105.00),
        mapped("Blue Lake", 39.01, -105.01),
    ])
    kind, match, distance = duplicate_candidate(
        atlas("Blue Lake", 39.00, -105.00), names, existing
    )
    assert kind == "exact-name"
    assert match == "Blue Lake"
    assert distance < 1


def test_exact_name_can_enrich_an_unmapped_stocking_record():
    names, existing = existing_index([{"name": "Avery Pond"}])
    kind, match, distance = duplicate_candidate(
        atlas("Avery Pond", 40.0, -105.0), names, existing
    )
    assert (kind, match, distance) == ("exact-name-unmapped", "Avery Pond", None)
