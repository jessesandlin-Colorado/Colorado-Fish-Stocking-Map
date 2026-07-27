#!/usr/bin/env python3
"""Bootstrap the CPW archive from every annual Google Sheets tab.

The archive supplies the stocking date, displayed water name, and an official
Fishing Atlas hyperlink.  The hyperlink's ``value`` query parameter is retained
as ``atlas_id`` so coordinates and water metadata can continue to come from the
Fishing Atlas rather than being inferred from archive text.
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, quote, urlparse

import requests
from bs4 import BeautifulSoup

from stocking_database import (
    ARCHIVE_URL,
    USER_AGENT,
    StockingEvent,
    event_key,
    export_json,
    init_db,
    upsert,
    utc_now,
)

DATE_RE = re.compile(r"\b(\d{1,2}/\d{1,2}/\d{4})\b")
REGIONS = {"northeast", "northwest", "southeast", "southwest"}
FIRST_ARCHIVE_YEAR = 2014


def sheet_html_url(published_url: str, year: int) -> str:
    """Return a Google Visualization HTML export for a named annual tab."""
    base = published_url.split("?", 1)[0]
    if base.endswith("/pubhtml"):
        base = base[: -len("/pubhtml")]
    return f"{base}/gviz/tq?tqx=out:html&sheet={quote(str(year))}"


def atlas_id_from_url(url: str) -> int | None:
    try:
        return int(parse_qs(urlparse(url).query).get("value", [None])[0])
    except (TypeError, ValueError):
        return None


def clean(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def parse_year_sheet(html: str, year: int) -> list[tuple[StockingEvent, int, dict, int, str]]:
    """Extract archive rows while preserving the official Atlas link and ID."""
    soup = BeautifulSoup(html, "html.parser")
    extracted: list[tuple[StockingEvent, int, dict, int, str]] = []

    for row_number, row in enumerate(soup.select("tr"), start=1):
        cells = [clean(cell.get_text(" ", strip=True)) for cell in row.find_all(["td", "th"])]
        row_text = " | ".join(cells)
        date_match = DATE_RE.search(row_text)
        if not date_match:
            continue

        anchors = row.select('a[href*="value="]')
        anchor = next((item for item in anchors if atlas_id_from_url(item.get("href", "")) is not None), None)
        if anchor is None:
            continue

        atlas_url = anchor.get("href", "")
        atlas_id = atlas_id_from_url(atlas_url)
        water_name = clean(anchor.get_text(" ", strip=True))
        if not water_name or atlas_id is None:
            continue

        stocking_date = datetime.strptime(date_match.group(1), "%m/%d/%Y").date().isoformat()
        region = next((cell.lower() for cell in cells if cell.lower() in REGIONS), None)
        event = StockingEvent(
            water_name=water_name,
            stocking_date=stocking_date,
            region=region,
        )
        raw = {
            "archive_year": year,
            "cells": cells,
            "atlas_id": atlas_id,
            "atlas_url": atlas_url,
        }
        extracted.append((event, row_number, raw, atlas_id, atlas_url))

    return extracted


def ensure_atlas_columns(conn: sqlite3.Connection) -> None:
    existing = {row[1] for row in conn.execute("PRAGMA table_info(stocking_events)")}
    if "atlas_id" not in existing:
        conn.execute("ALTER TABLE stocking_events ADD COLUMN atlas_id INTEGER")
    if "atlas_url" not in existing:
        conn.execute("ALTER TABLE stocking_events ADD COLUMN atlas_url TEXT")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_stocking_atlas_id ON stocking_events(atlas_id)")


def bootstrap(db: Path, published_url: str) -> dict:
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})

    current_year = datetime.now(timezone.utc).year
    annual_rows: list[tuple[int, str, list[tuple[StockingEvent, int, dict, int, str]]]] = []
    sheet_errors: list[str] = []

    for year in range(FIRST_ARCHIVE_YEAR, current_year + 1):
        source_url = sheet_html_url(published_url, year)
        try:
            response = session.get(source_url, timeout=120)
            response.raise_for_status()
            rows = parse_year_sheet(response.text, year)
            if not rows:
                sheet_errors.append(f"{year}: no rows with both a stocking date and Atlas link")
                continue
            annual_rows.append((year, source_url, rows))
        except requests.RequestException as exc:
            sheet_errors.append(f"{year}: {type(exc).__name__}: {exc}")

    if not annual_rows:
        raise RuntimeError("No annual archive tabs produced recognizable rows: " + "; ".join(sheet_errors))

    years_imported = sorted(year for year, _, _ in annual_rows)
    if years_imported[0] > FIRST_ARCHIVE_YEAR:
        raise RuntimeError(
            f"Archive is incomplete: earliest imported year is {years_imported[0]}, "
            f"expected {FIRST_ARCHIVE_YEAR}. Details: {'; '.join(sheet_errors)}"
        )

    db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db)
    init_db(conn)
    ensure_atlas_columns(conn)
    observed = utc_now()
    run_id = conn.execute(
        "INSERT INTO import_runs(started_at,source_kind,source_url) VALUES(?,?,?)",
        (observed, "archive", published_url),
    ).lastrowid

    rows_seen = 0
    new_events = 0
    try:
        for year, source_url, rows in annual_rows:
            for event, row_number, raw, atlas_id, atlas_url in rows:
                rows_seen += 1
                if upsert(
                    conn,
                    event,
                    source_kind="archive",
                    source_url=source_url,
                    source_sheet=str(year),
                    source_gid=str(year),
                    source_row=row_number,
                    raw=raw,
                    observed_at=observed,
                ):
                    new_events += 1
                conn.execute(
                    "UPDATE stocking_events SET atlas_id=?, atlas_url=? WHERE event_id=?",
                    (atlas_id, atlas_url, event_key(event)),
                )

        conn.execute(
            """UPDATE import_runs SET finished_at=?,rows_seen=?,canonical_events_seen=?,
               new_events=?,duplicate_events=?,errors_json=? WHERE run_id=?""",
            (
                utc_now(), rows_seen, rows_seen, new_events, rows_seen - new_events,
                json.dumps(sheet_errors), run_id,
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
        "years_imported": years_imported,
        "rows_seen": rows_seen,
        "events_seen": rows_seen,
        "new_events": new_events,
        "duplicates": rows_seen - new_events,
        "sheet_warnings": sheet_errors,
    }


def validate_summary(summary: dict) -> None:
    earliest = summary.get("earliest_date")
    if not earliest or int(earliest[:4]) > FIRST_ARCHIVE_YEAR:
        raise RuntimeError(
            f"Historical coverage validation failed: earliest date is {earliest!r}; "
            f"expected a date in {FIRST_ARCHIVE_YEAR}."
        )
    if summary.get("stocking_events", 0) <= 514:
        raise RuntimeError(
            "Historical coverage validation failed: import did not exceed the prior "
            f"2026-only total (found {summary.get('stocking_events', 0)} events)."
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, default=Path("data/stocking.sqlite3"))
    parser.add_argument("--json", type=Path, default=Path("data/stocking_events.json"))
    parser.add_argument("--archive-url", default=ARCHIVE_URL)
    args = parser.parse_args()

    result = bootstrap(args.db, args.archive_url)
    summary = export_json(args.db, args.json)
    validate_summary(summary)
    print(json.dumps([result, {"export": summary}], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
