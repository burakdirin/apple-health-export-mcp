"""Query-logic self-checks: aggregation, sleep stage math, night attribution."""

import sqlite3

from apple_health_export_mcp import queries
from apple_health_export_mcp.db import init_schema


def _db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_schema(conn)
    return conn


def _rec(conn, type, value, start, end):
    conn.execute(
        "INSERT INTO record(key,type,value,start,end,local_date) VALUES (?,?,?,?,?,?)",
        (f"{type}{start}{value}".encode(), type, value, start, end, start[:10]),
    )


def _src(conn, type, source, value, start):
    conn.execute(
        "INSERT INTO record(key,type,source,value,start,local_date) VALUES (?,?,?,?,?,?)",
        (f"{type}{source}{start}{value}".encode(), type, source, value, start, start[:10]),
    )


def test_quantity_sum_and_avg_by_day():
    conn = _db()
    t = "HKQuantityTypeIdentifierStepCount"
    _rec(conn, t, "1000", "2026-06-18 08:00:00 +0300", "2026-06-18 08:01:00 +0300")
    _rec(conn, t, "500", "2026-06-18 18:00:00 +0300", "2026-06-18 18:01:00 +0300")
    _rec(conn, t, "300", "2026-06-19 09:00:00 +0300", "2026-06-19 09:01:00 +0300")
    conn.commit()

    s = queries.quantity(conn, t, "2026-06-18", "2026-06-19", "sum", "day")
    assert [(r.period, r.value) for r in s] == [("2026-06-18", 1500.0), ("2026-06-19", 300.0)]
    a = queries.quantity(conn, t, "2026-06-18", "2026-06-18", "avg", "all")
    assert a[0].value == 750.0 and a[0].period == "all"


def test_sum_dedupes_parallel_sources_by_dominant_per_day():
    """Watch + iPhone log the same day in parallel; sum must not double-count (ADR-0010)."""
    conn = _db()
    t = "HKQuantityTypeIdentifierStepCount"
    # Day 1: Watch (3 records, 6000) dominates iPhone (2 records, 5800) -> use Watch's 6000.
    for v, s in [("2000", "07:00"), ("2000", "12:00"), ("2000", "18:00")]:
        _src(conn, t, "Apple Watch", v, f"2026-06-18 {s}:00 +0300")
    for v, s in [("2900", "08:00"), ("2900", "19:00")]:
        _src(conn, t, "BurakD iPhone", v, f"2026-06-18 {s}:00 +0300")
    # Day 2: only an old Huawei source -> era preserved, not dropped.
    _src(conn, t, "HUAWEI Sağlık", "4321", "2026-06-19 10:00:00 +0300")
    conn.commit()

    out = queries.quantity(conn, t, "2026-06-18", "2026-06-19", "sum", "day")
    by_day = {r.period: r.value for r in out}
    assert by_day["2026-06-18"] == 6000.0  # Watch only, NOT 6000+5800
    assert by_day["2026-06-19"] == 4321.0  # Huawei era kept

    # Escape hatch: forcing iPhone gives its own sum.
    forced = queries.quantity(conn, t, "2026-06-18", "2026-06-18", "sum", "day", source="BurakD iPhone")
    assert forced[0].value == 5800.0
    # avg is NOT deduped (all 6 samples count) — sanity that non-sum path is untouched.
    avg = queries.quantity(conn, t, "2026-06-18", "2026-06-18", "avg", "all")
    assert avg[0].n == 5


def test_sleep_stage_durations_attributed_to_wake_day():
    conn = _db()
    t = "HKCategoryTypeIdentifierSleepAnalysis"
    # Night of 2026-06-19: fell asleep before midnight on the 18th, woke on the 19th.
    _rec(
        conn, t, "HKCategoryValueSleepAnalysisAsleepCore", "2026-06-18 23:00:00 +0300", "2026-06-19 01:00:00 +0300"
    )  # 120 min, wake-day 19
    _rec(
        conn, t, "HKCategoryValueSleepAnalysisAsleepDeep", "2026-06-19 01:00:00 +0300", "2026-06-19 01:30:00 +0300"
    )  # 30 min
    _rec(
        conn, t, "HKCategoryValueSleepAnalysisAwake", "2026-06-19 01:30:00 +0300", "2026-06-19 01:40:00 +0300"
    )  # 10 min awake
    conn.commit()

    out = queries.sleep(conn, "2026-06-19", "2026-06-19")
    assert len(out) == 1
    night = out[0]
    assert night.night == "2026-06-19"
    assert night.asleep_min == 150.0  # core 120 + deep 30
    assert night.deep_min == 30.0
    assert night.awake_min == 10.0
