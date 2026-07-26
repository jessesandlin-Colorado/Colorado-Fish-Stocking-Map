# Version 5 — Species and exploration release

## Highlights
- Atlas species extraction runs by default.
- Reads species-like ArcGIS fields and official Atlas-linked detail pages.
- Retains prior verified species during temporary outages.
- Supports reviewed corrections in `config/species_overrides.json`.
- Warns when species coverage is empty or unexpectedly low.
- Adds species, county, boating, recency, family, ice-fishing, and access filters.
- Adds marker clustering, canonical names, full water details, links, and stocking summaries.

## Refresh
```bash
python scripts/update_data.py --strict
```

The updater never infers species from habitat or water type. Empty species means the official source did not expose a verifiable name during that run.
