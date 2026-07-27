# CPW Stocking Archive Database

This upgrade replaces the live-report snapshot as the historical stocking source while retaining the live CPW report for weekly incremental updates.

## Sources

- Official CPW published Google Sheets archive: 2014-present historical reports.
- Current CPW stocking report: weekly incremental additions.
- Fishing Atlas and reviewed overrides: continue to provide locations, water identities, and verified species metadata through the existing pipeline.

## Data model

- `stocking_events`: canonical, deduplicated events.
- `event_sources`: every original archive or live source row, preserving provenance.
- `import_runs`: counts, errors, and audit history for each run.

The event identity is based on normalized water name, stocking date, species, quantity, and average length. Missing fields are not inferred. Identical source rows collapse to one canonical event while remaining traceable through `event_sources`.

## Commands

```bash
python -m pip install -r requirements.txt
python scripts/stocking_database.py bootstrap
python scripts/stocking_database.py weekly
python scripts/stocking_database.py all
python -m pytest -q
```

- `bootstrap` imports the complete published archive.
- `weekly` reads the current report and inserts only new canonical events.
- `all` runs both operations and regenerates `data/stocking_events.json`.

The existing Saturday GitHub Actions refresh now runs the Atlas/current-data pipeline, archive import, weekly incremental import, and tests before committing generated outputs.

## Integration notes

The map should ultimately read historical events from `data/stocking_events.json`. Historical rows must pass through the repository's reviewed water-name and Atlas matching workflow before they are attached to coordinates. Do not infer coordinates, species, or water identities directly from archive text.

The first live bootstrap should produce substantially more than the current 91-event snapshot and should include dates beginning in 2014. Review `import_runs.errors_json` if Google changes the published-sheet markup or introduces unfamiliar column labels.
