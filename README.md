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
