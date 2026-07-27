#!/usr/bin/env python3
"""Build and incrementally update a provenance-preserving CPW stocking database.

Sources:
  * Official CPW published Google Sheets archive (2014-present)
  * Current CPW stocking report (weekly incremental updates)

No species or stocking information is inferred. Every canonical event retains one
or more source rows in event_sources.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path
from typing import Optional
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import pandas as pd
import requests
from bs4 import BeautifulSoup

ARCHIVE_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vSRURGSiGWRaPnJoz11cq0pTTaFPzIWGumsJONymkYmAmrGxYslI1f86qn2iad1R7iQzOhSlBV8rwWK/pubhtml"
LIVE_URL = "https://cpw.state.co.us/activities/fishing/fishing-awards-and-records/fish-stocking-report"
USER_AGENT = "ColoradoFishStockingMap/5.3 (+historical archive importer)"

COLUMN_ALIASES = {
    "water_name": {"water", "water name", "body of water", "lake", "location", "waterbody", "water body"},
    "stocking_date": {"date", "stock date", "stocking date", "date stocked", "report date"},
    "species": {"species", "fish", "fish species", "type", "species stocked"},
    "quantity": {"number", "quantity", "number stocked", "fish stocked", "count", "qty"},
    "length_inches": {"length", "average length", "avg length", "size", "length inches", "inches"},
    "county": {"county"},
    "region": {"region", "area"},
}


@dataclass(frozen=True)
class StockingEvent:
    water_name: str
    stocking_date: str
    species: Optional[str] = None
    quantity: Optional[int] = None
    length_inches: Optional[float] = None
    county: Optional[str] = None
    region: Optional[str] = None


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def clean_text(value: object) -> Optional[str]:
    if value is None or pd.isna(value):
        return None
    text = re.sub(r"\s+", " ", str(value)).strip()
    return text or None


def normalize_text(value: object) -> str:
    text = clean_text(value) or ""
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = text.casefold().replace("&", " and ")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def parse_date(value: object) -> Optional[str]:
    text = clean_text(value)
    if not text:
        return None
    parsed = pd.to_datetime(text, errors="coerce")
    if pd.isna(parsed):
        return None
    return parsed.date().isoformat()


def parse_int(value: object) -> Optional[int]:
    text = clean_text(value)
    if not text:
        return None
    match = re.search(r"-?[\d,]+", text)
    if not match:
        return None
    try:
        return int(match.group(0).replace(",", ""))
    except ValueError:
        return None


def parse_float(value: object) -> Optional[float]:
    text = clean_text(value)
    if not text:
        return None
    match = re.search(r"-?\d+(?:\.\d+)?", text.replace(",", ""))
    if not match:
        return None
    try:
        return float(match.group(0))
    except ValueError:
        return None


def canonical_columns(df: pd.DataFrame) -> dict[str, object]:
    found: dict[str, object] = {}
    for col in df.columns:
        label = normalize_text(" ".join(map(str, col)) if isinstance(col, tuple) else col)
        for canonical, aliases in COLUMN_ALIASES.items():
            if label in {normalize_text(alias) for alias in aliases}:
                found.setdefault(canonical, col)
    return found


def dataframe_to_events(df: pd.DataFrame) -> list[tuple[StockingEvent, int, dict]]:
    cols = canonical_columns(df)
    if "water_name" not in cols or "stocking_date" not in cols:
        return []
    events = []
    for idx, row in df.iterrows():
        name = clean_text(row.get(cols["water_name"]))
        date = parse_date(row.get(cols["stocking_date"]))
        if not name or not date:
            continue
        event = StockingEvent(
            water_name=name,
            stocking_date=date,
            species=clean_text(row.get(cols.get("species"))) if "species" in cols else None,
            quantity=parse_int(row.get(cols.get("quantity"))) if "quantity" in cols else None,
            length_inches=parse_float(row.get(cols.get("length_inches"))) if "length_inches" in cols else None,
            county=clean_text(row.get(cols.get("county"))) if "county" in cols else None,
            region=clean_text(row.get(cols.get("region"))) if "region" in cols else None,
        )
        raw = {str(key): None if pd.isna(value) else str(value) for key, value in row.to_dict().items()}
        row_number = int(idx) + 2 if isinstance(idx, int) else len(events) + 2
        events.append((event, row_number, raw))
    return events


def with_gid(url: str, gid: str) -> str:
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    query.update({"gid": [gid], "single": ["true"]})
    return urlunparse(parsed._replace(query=urlencode(query, doseq=True)))


def discover_archive_sheets(session: requests.Session, url: str) -> list[tuple[str, str, str]]:
    response = session.get(url, timeout=45)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    sheets: dict[str, tuple[str, str, str]] = {}
    for tag in soup.find_all(["a", "li"]):
        href = tag.get("href", "")
        gid_match = re.search(r"(?:[?&#]|gid=)(?:gid=)?(\d+)", href)
        if not gid_match:
            gid_match = re.search(r"gid[=:'\"\s]+(\d+)", tag.get("onclick", ""))
        if gid_match:
            gid = gid_match.group(1)
            title = clean_text(tag.get_text(" ", strip=True)) or f"gid-{gid}"
            sheets[gid] = (gid, title, with_gid(url, gid))
    if not sheets:
        sheets["default"] = ("default", "default", url)
    return list(sheets.values())


def read_html_tables(session: requests.Session, url: str) -> list[pd.DataFrame]:
    response = session.get(url, timeout=60)
    response.raise_for_status()
    return pd.read_html(StringIO(response.text), displayed_only=False)


def event_key(event: StockingEvent) -> str:
    fields = [
        normalize_text(event.water_name),
        event.stocking_date,
        normalize_text(event.species),
        str(event.quantity or ""),
        "" if event.length_inches is None else f"{event.length_inches:.4f}",
    ]
    return hashlib.sha256("|".join(fields).encode("utf-8")).hexdigest()[:24]


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript("""
    PRAGMA foreign_keys = ON;
    CREATE TABLE IF NOT EXISTS stocking_events (
      event_id TEXT PRIMARY KEY,
      water_name TEXT NOT NULL,
      normalized_water_name TEXT NOT NULL,
      stocking_date TEXT NOT NULL,
      species TEXT,
      normalized_species TEXT NOT NULL DEFAULT '',
      quantity INTEGER,
      length_inches REAL,
      county TEXT,
      region TEXT,
      first_seen_at TEXT NOT NULL,
      last_seen_at TEXT NOT NULL,
      CHECK(length(stocking_date) = 10)
    );
    CREATE INDEX IF NOT EXISTS idx_stocking_date ON stocking_events(stocking_date);
    CREATE INDEX IF NOT EXISTS idx_stocking_water ON stocking_events(normalized_water_name);
    CREATE TABLE IF NOT EXISTS event_sources (
      source_id INTEGER PRIMARY KEY AUTOINCREMENT,
      event_id TEXT NOT NULL REFERENCES stocking_events(event_id) ON DELETE CASCADE,
      source_kind TEXT NOT NULL,
      source_url TEXT NOT NULL,
      source_sheet TEXT,
      source_gid TEXT,
      source_row INTEGER,
      observed_at TEXT NOT NULL,
      raw_row_json TEXT NOT NULL,
      UNIQUE(source_kind, source_url, source_gid, source_row, raw_row_json)
    );
    CREATE TABLE IF NOT EXISTS import_runs (
      run_id INTEGER PRIMARY KEY AUTOINCREMENT,
      started_at TEXT NOT NULL,
      finished_at TEXT,
      source_kind TEXT NOT NULL,
      source_url TEXT NOT NULL,
      rows_seen INTEGER NOT NULL DEFAULT 0,
      canonical_events_seen INTEGER NOT NULL DEFAULT 0,
      new_events INTEGER NOT NULL DEFAULT 0,
      duplicate_events INTEGER NOT NULL DEFAULT 0,
      errors_json TEXT NOT NULL DEFAULT '[]'
    );
    """)
    conn.commit()


def upsert(
    conn: sqlite3.Connection,
    event: StockingEvent,
    *,
    source_kind: str,
    source_url: str,
    source_sheet: str,
    source_gid: str,
    source_row: int,
    raw: dict,
    observed_at: str,
) -> bool:
    key = event_key(event)
    exists = conn.execute("SELECT 1 FROM stocking_events WHERE event_id=?", (key,)).fetchone() is not None
    conn.execute("""
      INSERT INTO stocking_events(event_id, water_name, normalized_water_name, stocking_date,
        species, normalized_species, quantity, length_inches, county, region, first_seen_at, last_seen_at)
      VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
      ON CONFLICT(event_id) DO UPDATE SET
        last_seen_at=excluded.last_seen_at,
        county=COALESCE(stocking_events.county, excluded.county),
        region=COALESCE(stocking_events.region, excluded.region)
    """, (
        key,
        event.water_name,
        normalize_text(event.water_name),
        event.stocking_date,
        event.species,
        normalize_text(event.species),
        event.quantity,
        event.length_inches,
        event.county,
        event.region,
        observed_at,
        observed_at,
    ))
    conn.execute("""
      INSERT OR IGNORE INTO event_sources(event_id, source_kind, source_url, source_sheet,
        source_gid, source_row, observed_at, raw_row_json)
      VALUES(?,?,?,?,?,?,?,?)
    """, (
        key,
        source_kind,
        source_url,
        source_sheet,
        source_gid,
        source_row,
        observed_at,
        json.dumps(raw, sort_keys=True, ensure_ascii=False),
    ))
    return not exists


def import_source(db: Path, source_kind: str, source_url: str, *, fixture: Optional[Path] = None) -> dict:
    conn = sqlite3.connect(db)
    init_db(conn)
    observed = utc_now()
    run_id = conn.execute(
        "INSERT INTO import_runs(started_at,source_kind,source_url) VALUES(?,?,?)",
        (observed, source_kind, source_url),
    ).lastrowid
    rows_seen = canonical = new = 0
    errors: list[str] = []
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    try:
        if fixture:
            fixture = fixture.resolve()
            sheets = [("fixture", fixture.stem, fixture.as_uri())]
        elif source_kind == "archive":
            sheets = discover_archive_sheets(session, source_url)
        else:
            sheets = [("live", "current-report", source_url)]
        for gid, title, sheet_url in sheets:
            try:
                tables = (
                    pd.read_html(str(fixture), displayed_only=False)
                    if fixture
                    else read_html_tables(session, sheet_url)
                )
                sheet_had_events = False
                for table in tables:
                    extracted = dataframe_to_events(table)
                    if not extracted:
                        continue
                    sheet_had_events = True
                    for event, row_number, raw in extracted:
                        rows_seen += 1
                        canonical += 1
                        if upsert(
                            conn,
                            event,
                            source_kind=source_kind,
                            source_url=sheet_url,
                            source_sheet=title,
                            source_gid=gid,
                            source_row=row_number,
                            raw=raw,
                            observed_at=observed,
                        ):
                            new += 1
                if not sheet_had_events:
                    errors.append(f"No recognizable stocking table in sheet {title!r} ({gid}).")
            except Exception as exc:
                errors.append(f"{title} ({gid}): {type(exc).__name__}: {exc}")
        conn.commit()
    finally:
        finished = utc_now()
        conn.execute("""UPDATE import_runs SET finished_at=?,rows_seen=?,canonical_events_seen=?,
          new_events=?,duplicate_events=?,errors_json=? WHERE run_id=?""", (
            finished,
            rows_seen,
            canonical,
            new,
            canonical - new,
            json.dumps(errors),
            run_id,
        ))
        conn.commit()
        conn.close()
    return {
        "source": source_kind,
        "rows_seen": rows_seen,
        "events_seen": canonical,
        "new_events": new,
        "duplicates": canonical - new,
        "errors": errors,
    }


def export_json(db: Path, output: Path) -> dict:
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("""SELECT * FROM stocking_events
      ORDER BY stocking_date DESC, normalized_water_name, normalized_species""").fetchall()
    by_year = {
        str(row[0]): row[1]
        for row in conn.execute(
            "SELECT substr(stocking_date,1,4), count(*) FROM stocking_events GROUP BY 1 ORDER BY 1"
        )
    }
    payload = {
        "schema_version": 1,
        "generated_at": utc_now(),
        "sources": {"archive": ARCHIVE_URL, "live": LIVE_URL},
        "summary": {
            "stocking_events": len(rows),
            "unique_waters": conn.execute(
                "SELECT count(DISTINCT normalized_water_name) FROM stocking_events"
            ).fetchone()[0],
            "earliest_date": conn.execute("SELECT min(stocking_date) FROM stocking_events").fetchone()[0],
            "latest_date": conn.execute("SELECT max(stocking_date) FROM stocking_events").fetchone()[0],
            "events_by_year": by_year,
        },
        "events": [dict(row) for row in rows],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    conn.close()
    return payload["summary"]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["bootstrap", "weekly", "export", "all"])
    parser.add_argument("--db", type=Path, default=Path("data/stocking.sqlite3"))
    parser.add_argument("--json", type=Path, default=Path("data/stocking_events.json"))
    parser.add_argument("--archive-url", default=ARCHIVE_URL)
    parser.add_argument("--live-url", default=LIVE_URL)
    parser.add_argument("--fixture", type=Path)
    args = parser.parse_args()
    args.db.parent.mkdir(parents=True, exist_ok=True)
    results = []
    if args.command in {"bootstrap", "all"}:
        results.append(import_source(args.db, "archive", args.archive_url, fixture=args.fixture))
    if args.command in {"weekly", "all"}:
        results.append(import_source(args.db, "live", args.live_url, fixture=args.fixture))
    if args.command in {"export", "bootstrap", "weekly", "all"}:
        results.append({"export": export_json(args.db, args.json)})
    print(json.dumps(results, indent=2))
    return 1 if any(result.get("errors") for result in results if isinstance(result, dict)) else 0


if __name__ == "__main__":
    raise SystemExit(main())
