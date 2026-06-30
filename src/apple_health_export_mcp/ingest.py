"""Stream-parse an Apple Health export.zip into SQLite. See ADR-0001/0003/0005/0006.

Validated against a real tr_TR export (HealthKit Export Version 14, ~2.4M records):
- main XML is NOT always "export.xml" — a Turkish export names it "dışa aktarılan.xml".
  We locate it by content (root <HealthData>), not by filename.
- type identifiers and category value enums are English regardless of locale.
- decimals use "." even in tr_TR; sourceName may be localized/personal.
"""

from __future__ import annotations

import hashlib
import zipfile
from collections.abc import Iterator
from pathlib import Path
from xml.etree import ElementTree as ET

from .db import connect, init_schema

BATCH = 10_000


def _find_main_xml(zf: zipfile.ZipFile) -> str:
    """Return the zip entry name of the main HealthData XML (locale-independent)."""
    xmls = [n for n in zf.namelist() if n.lower().endswith(".xml")]
    # export_cda.xml is the clinical summary — never the main file.
    candidates = [n for n in xmls if not n.lower().endswith("export_cda.xml")]
    for name in candidates or xmls:
        with zf.open(name) as f:
            head = f.read(512)
        if b"<HealthData" in head or b"DOCTYPE HealthData" in head:
            return name
    raise ValueError("No HealthData XML found in archive — is this an Apple Health export?")


def _key(*parts: str | None) -> bytes:
    """Content hash → idempotent upsert key (records carry no UUID). ADR-0005."""
    return hashlib.blake2b("|".join(p or "" for p in parts).encode(), digest_size=16).digest()


def _iter_rows(stream) -> Iterator[tuple[str, tuple]]:
    """Yield ('record'|'workout', row_tuple) for each relevant element, freeing memory."""
    for _event, elem in ET.iterparse(stream, events=("end",)):
        tag = elem.tag
        if tag == "Record":
            a = elem.attrib
            start = a.get("startDate", "")
            row = (
                _key(a.get("type"), a.get("sourceName"), start, a.get("endDate"), a.get("value"), a.get("unit")),
                a.get("type", ""),
                a.get("sourceName"),
                a.get("unit"),
                a.get("value"),
                start,
                a.get("endDate"),
                a.get("creationDate"),
                start[:10],
            )
            yield "record", row
            elem.clear()
        elif tag == "Workout":
            a = elem.attrib
            start = a.get("startDate", "")
            row = (
                _key(a.get("workoutActivityType"), a.get("sourceName"), start, a.get("endDate"), a.get("duration")),
                a.get("workoutActivityType", ""),
                float(a["duration"]) if a.get("duration") else None,
                a.get("durationUnit"),
                a.get("sourceName"),
                start,
                a.get("endDate"),
                a.get("creationDate"),
                start[:10],
            )
            yield "workout", row
            elem.clear()
        elif tag in ("Correlation", "ActivitySummary", "Me", "ExportDate"):
            elem.clear()  # not stored in v1; free memory


_REC_SQL = (
    "INSERT OR IGNORE INTO record(key,type,source,unit,value,start,end,created,local_date) VALUES (?,?,?,?,?,?,?,?,?)"
)
_WK_SQL = (
    "INSERT OR IGNORE INTO workout"
    "(key,activity,duration,duration_unit,source,start,end,created,local_date)"
    " VALUES (?,?,?,?,?,?,?,?,?)"
)


def ingest(zip_path: Path, db: Path | None = None, *, progress=print) -> dict[str, int]:
    zip_path = Path(zip_path).expanduser()
    conn = connect(db, create=True)
    init_schema(conn)
    # Ingest-only speedups; safe because it's a rebuildable derived store. ADR-0003.
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=OFF")

    counts = {"record": 0, "workout": 0}
    rec_batch: list[tuple] = []
    wk_batch: list[tuple] = []

    def flush() -> None:
        if rec_batch:
            conn.executemany(_REC_SQL, rec_batch)
            rec_batch.clear()
        if wk_batch:
            conn.executemany(_WK_SQL, wk_batch)
            wk_batch.clear()
        conn.commit()

    with zipfile.ZipFile(zip_path) as zf:
        main = _find_main_xml(zf)
        progress(f"Reading {main} ...")
        with zf.open(main) as stream:
            for kind, row in _iter_rows(stream):
                if kind == "record":
                    rec_batch.append(row)
                else:
                    wk_batch.append(row)
                counts[kind] += 1
                if (counts["record"] + counts["workout"]) % BATCH == 0:
                    flush()
                    progress(f"  {counts['record']:,} records, {counts['workout']:,} workouts")
    flush()
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("INSERT OR REPLACE INTO meta(k,v) VALUES('source_zip',?)", (str(zip_path),))
    conn.commit()
    conn.close()
    return counts
