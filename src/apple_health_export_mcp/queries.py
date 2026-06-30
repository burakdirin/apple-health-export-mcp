"""Pure SQLite query helpers — no FastMCP dependency, so they're unit-testable.

All return aggregates only (ADR-0008). Dates are local-day strings 'YYYY-MM-DD'
compared against record.local_date (ADR-0009). Durations strip the " +HHMM"
offset before julianday(); start/end share an offset so the diff is correct.
"""

from __future__ import annotations

import sqlite3

_BUCKET = {
    "day": "local_date",
    "week": "strftime('%Y-W%W', local_date)",
    "month": "substr(local_date,1,7)",
    "all": "'all'",
}
_AGG = {"sum", "avg", "min", "max", "count"}
# Stages that count as actually asleep (vs InBed/Awake).
_ASLEEP = (
    "HKCategoryValueSleepAnalysisAsleepCore",
    "HKCategoryValueSleepAnalysisAsleepDeep",
    "HKCategoryValueSleepAnalysisAsleepREM",
    "HKCategoryValueSleepAnalysisAsleepUnspecified",
)


def list_types(conn: sqlite3.Connection) -> list[dict]:
    """Discover which metrics exist in this data (ADR-0004): type, count, date span."""
    rows = conn.execute(
        "SELECT type, COUNT(*) n, MIN(local_date) first, MAX(local_date) last FROM record GROUP BY type ORDER BY n DESC"
    ).fetchall()
    out = [dict(r) for r in rows]
    wk = conn.execute("SELECT COUNT(*) n FROM workout").fetchone()["n"]
    if wk:
        out.append({"type": "Workout", "n": wk, "first": None, "last": None})
    return out


def quantity(
    conn: sqlite3.Connection,
    type: str,
    start: str,
    end: str,
    agg: str = "sum",
    bucket: str = "day",
    source: str | None = None,
) -> list[dict]:
    """Aggregate a numeric metric over a date range.

    `sum` is de-duplicated: the same activity is logged in parallel by multiple
    devices (Watch + iPhone + 3rd-party), so a naive SUM over-counts (~40% on
    real data). We mirror Apple's "one source per interval" merge offline by
    picking, per local day, the single dominant source (most records that day =
    the device actually in use) and summing only it. This is era-robust (old
    Huawei/Zepp days pick those sources) and locale-proof (no source-name match).
    avg/min/max/count are NOT deduped — extra samples don't inflate them.
    Pass `source` to force one source (the HKStatistics `separateBySource` escape
    hatch). ADR-0010.
    """
    if agg not in _AGG:
        raise ValueError(f"agg must be one of {sorted(_AGG)}")
    if bucket not in _BUCKET:
        raise ValueError(f"bucket must be one of {sorted(_BUCKET)}")
    b = _BUCKET[bucket]
    src_filter = " AND source=?" if source else ""
    src_arg = (source,) if source else ()

    if agg == "sum" and source is None:
        # ponytail: per-day dominant-source pick; upgrade to per-interval union
        # (Apple's exact merge) only if single-source days measurably undercount.
        rows = conn.execute(
            f"""
            WITH per_src AS (
                SELECT local_date, source, COUNT(*) n, SUM(CAST(value AS REAL)) s
                FROM record WHERE type=? AND local_date BETWEEN ? AND ?
                GROUP BY local_date, source),
            best AS (
                SELECT local_date, s,
                       ROW_NUMBER() OVER (PARTITION BY local_date ORDER BY n DESC, s DESC) rn
                FROM per_src)
            SELECT {b} period, ROUND(SUM(s), 2) value, COUNT(*) n
            FROM best WHERE rn=1 GROUP BY {b} ORDER BY period
            """,
            (type, start, end),
        ).fetchall()
        return [dict(r) for r in rows]

    expr = "COUNT(*)" if agg == "count" else f"{agg}(CAST(value AS REAL))"
    rows = conn.execute(
        f"SELECT {b} period, {expr} value, COUNT(*) n "
        f"FROM record WHERE type=? AND local_date BETWEEN ? AND ?{src_filter} "
        f"GROUP BY {b} ORDER BY period",
        (type, start, end, *src_arg),
    ).fetchall()
    return [dict(r) for r in rows]


def list_sources(conn: sqlite3.Connection, type: str) -> list[dict]:
    """Which sources wrote a given type, with counts — for transparency / `source=` use."""
    rows = conn.execute(
        "SELECT source, COUNT(*) n, MIN(local_date) first, MAX(local_date) last "
        "FROM record WHERE type=? GROUP BY source ORDER BY n DESC",
        (type,),
    ).fetchall()
    return [dict(r) for r in rows]


def sleep(conn: sqlite3.Connection, start: str, end: str) -> list[dict]:
    """Per-night sleep, attributed to the wake-up local day (end date).

    Reports minutes per stage. Legacy nights may only have InBed (older devices),
    so in_bed_min is surfaced as a fallback when asleep_min is 0.
    """
    asleep_in = ",".join("?" * len(_ASLEEP))
    rows = conn.execute(
        f"""
        SELECT substr(end,1,10) night,
               SUM(CASE WHEN value IN ({asleep_in}) THEN dur ELSE 0 END) asleep_min,
               SUM(CASE WHEN value='HKCategoryValueSleepAnalysisAsleepREM'  THEN dur ELSE 0 END) rem_min,
               SUM(CASE WHEN value='HKCategoryValueSleepAnalysisAsleepDeep' THEN dur ELSE 0 END) deep_min,
               SUM(CASE WHEN value='HKCategoryValueSleepAnalysisAsleepCore' THEN dur ELSE 0 END) core_min,
               SUM(CASE WHEN value='HKCategoryValueSleepAnalysisAwake'      THEN dur ELSE 0 END) awake_min,
               SUM(CASE WHEN value='HKCategoryValueSleepAnalysisInBed'      THEN dur ELSE 0 END) in_bed_min
        FROM (
            SELECT value, end,
                   (julianday(substr(end,1,19)) - julianday(substr(start,1,19)))*1440 dur
            FROM record
            WHERE type='HKCategoryTypeIdentifierSleepAnalysis'
              AND substr(end,1,10) BETWEEN ? AND ?
        )
        GROUP BY night ORDER BY night
        """,
        (*_ASLEEP, start, end),
    ).fetchall()
    return [{k: (round(v, 1) if isinstance(v, float) else v) for k, v in dict(r).items()} for r in rows]


def workouts(conn: sqlite3.Connection, start: str, end: str) -> list[dict]:
    """Per-activity workout summary in range: count, total & avg minutes."""
    rows = conn.execute(
        """
        SELECT activity, COUNT(*) n,
               ROUND(SUM(duration), 1) total_min,
               ROUND(AVG(duration), 1) avg_min
        FROM workout WHERE local_date BETWEEN ? AND ?
        GROUP BY activity ORDER BY n DESC
        """,
        (start, end),
    ).fetchall()
    return [dict(r) for r in rows]
