# Colorado Fish Stocking Map — Version 3

A static, deployable map generated from the Colorado Parks and Wildlife stocking report and Fishing Atlas.

## Improvements in Version 3

- Queries all five scale-dependent Atlas catchable-water layers: 59, 61, 63, 65, and 67.
- Retains the layer that produced each successful location match.
- Includes GitHub Actions for weekly data refreshes.
- Includes GitHub Pages deployment.
- Keeps unmatched records and a match report for quality review.

## Run locally

```cmd
python -m pip install -r requirements.txt
python scripts\update_data.py
python -m http.server 8000
```

Open `http://localhost:8000`.

## Publish online

See `HOSTING.md` for exact GitHub and GitHub Pages instructions.

## Data outputs

- `data/waters.json`
- `data/unmatched.json`
- `data/match-report.html`

Official CPW information and regulations always control.

## Reliable and polite data refreshes

The Version 4.1 updater intentionally limits traffic to external services. Atlas
requests are spaced 300–500 milliseconds apart, retried no more than three times,
and cached for 24 hours in `.cache/`. If the Atlas is temporarily unavailable,
the updater can reuse stale cached responses or preserve previously published
water details instead of erasing them.

Run the normal production update with:

```bash
python scripts/update_data.py
```

Species probing is disabled by default because the currently identified public
layer does not reliably expose species names. The website therefore omits the
species line rather than presenting a technical error to every visitor.

## Reviewed Atlas matching fallbacks

The importer now resolves waters in this order:

1. Exact `UNI_ID` lookup across all configured Fishing Atlas layers.
2. Exact reviewed-name aliases from `config/atlas_overrides.json`.
3. A reviewed manual coordinate override, only when `lat` and `lng` have been explicitly added to that file.
4. Leave the event unmatched rather than guessing.

Region is intentionally not parsed, validated, filtered, or displayed; the map provides geographic context.


## Version 5
See `VERSION-5.md` for species extraction, filters, details, clustering, and validation behavior.
