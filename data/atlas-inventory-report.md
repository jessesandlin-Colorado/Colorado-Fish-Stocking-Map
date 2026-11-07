# Colorado Fishing Atlas inventory comparison

Generated: 2026-11-07T18:22:08.735913+00:00

## Executive summary

- **1,287** visible Atlas fishing-point records were retrieved.
- They represent **1,201 unique WATERCODEs** after duplicate consolidation.
- **358** Atlas WATERCODEs are already represented in the project.
- **843** Atlas WATERCODEs are not represented in the project's stocking-derived group.
- Project coverage is **29.8%** of the Atlas inventory by WATERCODE.
- **831** Atlas-only waters are provisionally rated high or medium priority for import.
- **0** Atlas records lack a WATERCODE and require separate manual review.

> "Atlas-only" means no matching WATERCODE was found in the project's 2014-present stocking-derived dataset. It should be labeled **Stocking history unknown / no project stocking record found**, not "never stocked."

## Import recommendations

| Classification | Count |
|---|---:|
| exclude/private-review | 12 |
| import-high-priority | 831 |

## Fishery classifications

| Classification | Count |
|---|---:|
| Coldwater | 588 |
| Mixed coldwater/warmwater | 32 |
| Warmwater | 223 |

## Access indicators

| Classification | Count |
|---|---:|
| private-indicated | 12 |
| public-indicated | 831 |

Access classifications are screening indicators only. Users must still verify legal access, closures, and regulations with CPW and the land manager.

## Water types

| Classification | Count |
|---|---:|
| Stream or River | 307 |
| Water Body | 536 |

## Suggested import policy

1. Import **high-priority** records automatically after duplicate and coordinate validation.
2. Import **medium-priority** records if they have official species and no private-access indicator.
3. Hold **manual-review** records for access verification, duplicate resolution, or sparse metadata.
4. Exclude records flagged **private-review** until legal public access is confirmed.
5. Display every imported Atlas-only record as **Stocking history unknown — no matching record in the project's historical stocking database**.

## Review files

- `data/atlas-only-waters-review.csv`: ranked decision sheet for filtering and annotation.
- `data/atlas-inventory-comparison.json`: complete records, summaries, duplicates, and no-WATERCODE cases.
