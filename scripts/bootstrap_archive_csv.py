#!/usr/bin/env python3
"""Bootstrap the CPW archive from every published Google Sheets tab.

The archive supplies the stocking date, displayed water name, and an official
Fishing Atlas hyperlink. The hyperlink's ``value`` query parameter is retained
as ``atlas_id`` so coordinates and water metadata continue to come from the
Fishing Atlas rather than being inferred from archive text.
"""
from __future__ import annotations

import argparse
import html as html_lib
import json
import re
import sqlite3
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

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


def clean(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def atlas_id_from_url(url: str) -> int | None:
    """Extract the Fishing Atlas ``value`` parameter from a link."""
    try:
        return int(parse_qs(urlparse(html_lib.unescape(url)).query).get("value", [None])[0])
    except (TypeError, ValueError):
        return None


def single_sheet_url(published_url: str, gid: str) -> str:
    """Return the published HTML view for exactly one numeric sheet gid."""
    parsed = urlparse(published_url)
    query = parse_qs(parsed.query)
    query.update({"gid": [str(gid)], "single": ["true"]})
    return urlunparse(parsed._replace(query=urlencode(query, doseq=True)))


def discover_sheet_gids(index_html: str) -> list[tuple[str, str]]:
    """Discover published tab gids without assuming tab names.

    Google has used several different wrappers for published workbooks. This
    parser handles ordinary navigation links, ``sheet-button-<gid>`` elements,
    and gids embedded in the page's JavaScript configuration.
    """
    soup = BeautifulSoup(index_html, "html.parser")
    discovered: dict[str, str] = {}

    for tag in soup.find_all(True):
        href = html_lib.unescape(str(tag.get("href", "")))
        tag_id = str(tag.get("id", ""))
        onclick = html_lib.unescape(str(tag.get("onclick", "")))
        combined = " ".join((href, tag_id, onclick))
        matches = re.findall(r"(?:#|[?&]|\b)gid(?:=|%3D|[-_])['\"]?(\d+)", combined, flags=re.I)
        matches += re.findall(r"sheet-button-(\d+)", combined, flags=re.I)
        for gid in matches:
            label = clean(tag.get_text(" ", strip=True)) or f"gid-{gid}"
            discovered.setdefault(gid, label)

    raw = html_lib.unescape(index_html)
    patterns = (
        r"(?:#|[?&])gid=(\d+)",
        r"sheet-button-(\d+)",
        r"[\"']gid[\"']\s*:\s*[\"']?(\d+)",
        r"\bgid\s*=\s*[\"'](\d+)[\"']",
        r"gid%3D(\d+)",
    )
    for pattern in patterns:
        for gid in re.findall(pattern, raw, flags=re.I):
            discovered.setdefault(gid, f"gid-{gid}")

    # Google commonly uses gid 0 for the first published tab. Include it as a
    # safe fallback; duplicate rows are removed by the canonical event key.
    discovered.setdefault("0", "gid-0")
    return list(discovered.items())


def parse_year_sheet(html: str, source_gid: str) -> list[tuple[StockingEvent, int, dict, int, str]]:
    """Extract archive rows while preserving the official Atlas link and ID."""
    soup = BeautifulSoup(html, "html.parser")
    extracted: list[tuple[StockingEvent, int, dict, int, str]] = []

    for row_number, row in enumerate(soup.select("tr"), start=1):
        cells = [clean(cell.get_text(" ", strip=True)) for cell in row.find_all(["td", "th"])]
        row_text = " | ".join(cells)
        date_match = DATE_RE.search(row_text)
        if not date_match:
            continue

        anchor = next(
            (
                item
                for item in row.select("a[href]")
                if atlas_id_from_url(item.get("href", "")) is not None
            ),
            None,
        )
        if anchor is None:
            continue

        atlas_url = html_lib.unescape(anchor.get("href", ""))
        atlas_id = atlas_id_from_url(atlas_url)
        water_name = clean(anchor.get_text(" ", strip=True))
        if not water_name or atlas_id is None:
            continue

        stocking_date = datetime.strptime(date_match.group(1), "%m/%d/%Y").date().isoformat()
        year = int(stocking_date[:4])
        region = next((cell.lower() for cell in cells if cell.lower() in REGIONS), None)
        event = StockingEvent(water_name=water_name, stocking_date=stocking_date, region=region)
        raw = {
            "archive_year": year,
            "source_gid": source_gid,
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

    index_response = session.get(published_url, timeout=120)
    index_response.raise_for_status()
    sheets = discover_sheet_gids(index_response.text)
    if not sheets:
        raise RuntimeError("Published workbook exposed no sheet gids")

    sheet_rows: list[tuple[str, str, str, list[tuple[StockingEvent, int, dict, int, str]]]] = []
    sheet_errors: list[str] = []
    seen_payloads: set[tuple[tuple[str, str, int], ...]] = set()

    for gid, title in sheets:
        source_url = single_sheet_url(published_url, gid)
        try:
            response = session.get(source_url, timeout=120)
            response.raise_for_status()
            rows = parse_year_sheet(response.text, gid)
            if not rows:
                sheet_errors.append(f"{title} (gid {gid}): no rows with both a stocking date and Atlas link")
                continue

            # Some Google wrappers expose the same first tab through more than
            # one gid-like token. Avoid importing an identical rendered sheet twice.
            signature = tuple(
                sorted((event.stocking_date, event.water_name, atlas_id) for event, _, _, atlas_id, _ in rows)
            )
            if signature in seen_payloads:
                continue
            seen_payloads.add(signature)
            sheet_rows.append((gid, title, source_url, rows))
        except requests.RequestException as exc:
            sheet_errors.append(f"{title} (gid {gid}): {type(exc).__name__}: {exc}")

    if not sheet_rows:
        raise RuntimeError("No published archive tabs produced recognizable rows: " + "; ".join(sheet_errors))

    years_imported = sorted(
        {int(event.stocking_date[:4]) for _, _, _, rows in sheet_rows for event, _, _, _, _ in rows}
    )
    if not years_imported or years_imported[0] > FIRST_ARCHIVE_YEAR:
        raise RuntimeError(
            f"Archive is incomplete: earliest imported year is "
            f"{years_imported[0] if years_imported else None}, expected {FIRST_ARCHIVE_YEAR}. "
            f"Discovered gids: {[gid for gid, _ in sheets]}. Details: {'; '.join(sheet_errors)}"
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
        for gid, title, source_url, rows in sheet_rows:
            sheet_years = sorted({event.stocking_date[:4] for event, _, _, _, _ in rows})
            source_sheet = title if not title.startswith("gid-") else ",".join(sheet_years)
            for event, row_number, raw, atlas_id, atlas_url in rows:
                rows_seen += 1
                if upsert(
                    conn,
                    event,
                    source_kind="archive",
                    source_url=source_url,
                    source_sheet=source_sheet,
                    source_gid=gid,
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
        "gids_discovered": [gid for gid, _ in sheets],
        "tabs_imported": len(sheet_rows),
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
