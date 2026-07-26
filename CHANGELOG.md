# Changelog

## 5.0.0
- Production species extraction and fallbacks
- Species coverage validation
- Species override configuration
- Rich filters, detail dialog, clustering, and historical summary
- Schema version 5


## 4.2 — Reviewed Atlas fallback matching

- Search all configured Atlas layers by authoritative `UNI_ID`.
- Add conservative exact-name alias fallback for reviewed exceptions.
- Add `config/atlas_overrides.json` for aliases and last-resort verified coordinates.
- Record `atlas-id`, `reviewed-name-alias`, or `manual-override` as the match method.
- Remove region parsing, region validation warnings, region filters, and region display.

# Changelog

## 4.1 — Reliability update

- Polite Atlas request throttling and bounded retries
- Persistent local response cache
- GitHub Actions cache restoration
- Stale-cache and prior-published-data fallbacks
- Six-stage importer logging
- Latest-report summary metrics
- Species display hidden until verified data exists
- Experimental species probing disabled by default
