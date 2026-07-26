# Version 4 — Data Foundation

Version 4 keeps the existing live map architecture while strengthening the data pipeline.

## Included

- Permanent `stocking-history.json` archive
- `import-history.json` audit trail for automated runs
- Multi-layer Fishing Atlas ID matching
- Richer location and access attributes
- Explicit match status and confidence on historical events
- Validation for report-size drops, missing coordinates, locations outside Colorado, unknown regions, and unmatched events
- Strict GitHub Actions validation before automatic publication
- Species data is included only when the official Atlas service explicitly returns a species name

## Local test

```cmd
python -m pip install -r requirements.txt
python scripts\update_data.py
python -m http.server 8000
```

Open `http://localhost:8000` and review `data/validation-report.html`.

Run a second import and confirm `historical_events` does not increase unless CPW has added a new report date.

## Generated files

- `data/waters.json`
- `data/stocking-history.json`
- `data/import-history.json`
- `data/species.json`
- `data/unmatched.json`
- `data/validation.json`
- `data/validation-report.html`
- `data/match-report.html`

## Version 4.1 reliability update

- Adds 300–500 ms spacing between external requests.
- Retries temporary failures up to three times with exponential backoff.
- Caches Atlas JSON responses for 24 hours under `.cache/atlas/`.
- GitHub Actions restores the cache between scheduled runs.
- Uses stale cached Atlas responses when the service is temporarily unavailable.
- Retains previously published water attributes when no cached Atlas response is available.
- Separates the updater into six clearly logged stages.
- Adds latest-report counts for the future “What’s new this week?” interface.
- Hides the species row unless verified species names exist.
- Disables experimental species probing by default. It can be run manually with
  `--enable-species-probe`, but should not be used for production until the
  official source is confirmed.
