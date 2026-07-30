#!/usr/bin/env python3
"""Import the 2026 worksheet from CPW's published stocking archive once.

Google's published ``pubhtml`` page is a JavaScript shell and no longer exposes
worksheet tables or gids in server-rendered HTML.  The worksheet-specific CSV
endpoint remains stable, so this importer intentionally targets only the 2026
sheet and merges those rows into the existing provenance-preserving database.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
from io import StringIO
from pathlib import Path

import pandas as pd
import requests

from stocking_database import (
    ARCHIVE_URL,
    USER_AGENT,
    dataframe_to_events,
    export_json,
    init_db,
    upsert,
    utc_now,
)

ARCHIVE_2026_CSV = ARCHIVE_URL.replace("/pubhtml", "/pub?output=csv&sheet=2026")


def read_2026_sheet(session: requests.Session, url: str) -> pd.DataFrame:
    response = session.get(url, timeout=60)
    response.raise_for_status()
    text = response.text.lstrip("\ufeff")
    if not text.strip():
        raise RuntimeError("The published 2026 worksheet returned an empty response")

    # The normal published CSV has its column names on the first row.  Try a few
    # leading rows as headers as a guard against a title/banner row being added.
    for header in range(5):
        frame = pd.read_csv(StringIO(text), header=header)
        if dataframe_to_events(frame):
            return frame
    raise RuntimeError("No recognizable stocking table was found in the 2026 CSV worksheet")


def import_2026(db: Path, output_json: Path, url: str) -> dict:
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    frame = read_2026_sheet(session, url)
    extracted = dataframe_to_events(frame)
    if not extracted:
        raise RuntimeError("The 2026 worksheet contained no recognizable stocking events")

    conn = sqlite3.connect(db)
    init_db(conn)
    observed = utc_now()
    new_events = 0
    try:
        for event, row_number, raw in extracted:
            if not event.stocking_date.startswith("2026-"):
                continue
            if upsert(
                conn,
                event,
                source_kind="archive",
                source_url=url,
                source_sheet="2026",
                source_gid="sheet-2026",
                source_row=row_number,
                raw=raw,
                observed_at=observed,
            ):
                new_events += 1
        conn.commit()
    finally:
        conn.close()

    summary = export_json(db, output_json)
    imported_2026 = int((summary.get("events_by_year") or {}).get("2026", 0))
    if imported_2026 == 0:
        raise RuntimeError("Import completed without producing any 2026 events")

    return {
        "source": url,
        "worksheet": "2026",
        "rows_recognized": len(extracted),
        "new_events": new_events,
        "database_2026_events": imported_2026,
        "database_latest_date": summary.get("latest_date"),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, default=Path("data/stocking.sqlite3"))
    parser.add_argument("--json", type=Path, default=Path("data/stocking_events.json"))
    parser.add_argument("--url", default=ARCHIVE_2026_CSV)
    args = parser.parse_args()
    args.db.parent.mkdir(parents=True, exist_ok=True)
    result = import_2026(args.db, args.json, args.url)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
