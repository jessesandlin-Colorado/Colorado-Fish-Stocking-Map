#!/usr/bin/env python3
"""Bootstrap the CPW historical archive from Google Sheets' published CSV export."""
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


def csv_export_url(published_url: str) -> str:
    base = published_url.split("?", 1)[0]
    if base.endswith("/pubhtml"):
        base = base[: -len("/pubhtml")] + "/pub"
    elif not base.endswith("/pub"):
        base = base.rstrip("/") + "/pub"
    return f"{base}?output=csv"


def bootstrap(db: Path, published_url: str) -> dict:
    source_url = csv_export_url(published_url)
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    response = session.get(source_url, timeout=120)
    response.raise_for_status()

    content_type = response.headers.get("content-type", "").lower()
    body = response.text
    if not body.strip():
        raise RuntimeError("Google Sheets CSV export returned an empty response")
    if "text/html" in content_type and body.lstrip().lower().startswith("<!doctype html"):
        raise RuntimeError("Google Sheets returned HTML instead of the published CSV export")

    frame = pd.read_csv(StringIO(body))
    extracted = dataframe_to_events(frame)
    if not extracted:
        raise RuntimeError(
            "CSV export contained no recognizable stocking rows; "
            f"columns were: {list(map(str, frame.columns))}"
        )

    db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db)
    init_db(conn)
    observed = utc_now()
    run_id = conn.execute(
        "INSERT INTO import_runs(started_at,source_kind,source_url) VALUES(?,?,?)",
        (observed, "archive", source_url),
    ).lastrowid
    new_events = 0
    try:
        for event, row_number, raw in extracted:
            if upsert(
                conn,
                event,
                source_kind="archive",
                source_url=source_url,
                source_sheet="published-csv",
                source_gid="default",
                source_row=row_number,
                raw=raw,
                observed_at=observed,
            ):
                new_events += 1
        conn.execute(
            """UPDATE import_runs SET finished_at=?,rows_seen=?,canonical_events_seen=?,
               new_events=?,duplicate_events=?,errors_json=? WHERE run_id=?""",
            (
                utc_now(),
                len(extracted),
                len(extracted),
                new_events,
                len(extracted) - new_events,
                "[]",
                run_id,
            ),
        )
        conn.commit()
    except Exception as exc:
        conn.execute(
            "UPDATE import_runs SET finished_at=?,errors_json=? WHERE run_id=?",
            (utc_now(), json.dumps([f"{type(exc).__name__}: {exc}"]), run_id),
        )
        conn.commit()
        raise
    finally:
        conn.close()

    return {
        "source": "archive",
        "source_url": source_url,
        "rows_seen": len(extracted),
        "events_seen": len(extracted),
        "new_events": new_events,
        "duplicates": len(extracted) - new_events,
        "errors": [],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, default=Path("data/stocking.sqlite3"))
    parser.add_argument("--json", type=Path, default=Path("data/stocking_events.json"))
    parser.add_argument("--archive-url", default=ARCHIVE_URL)
    args = parser.parse_args()

    result = bootstrap(args.db, args.archive_url)
    summary = export_json(args.db, args.json)
    print(json.dumps([result, {"export": summary}], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
