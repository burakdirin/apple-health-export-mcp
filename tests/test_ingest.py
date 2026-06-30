"""Parser self-check: locale-independent XML discovery, parsing, idempotency.

Uses a tiny synthetic zip mirroring the real tr_TR export quirks (main XML named
in Turkish, English type ids, localized sourceName, offset timestamps).
"""

import zipfile

from apple_health_export_mcp.db import connect, init_schema
from apple_health_export_mcp.ingest import ingest

SAMPLE_XML = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE HealthData [<!ELEMENT HealthData ANY>]>
<HealthData locale="tr_TR">
 <ExportDate value="2026-06-26 19:00:04 +0300"/>
 <Record type="HKQuantityTypeIdentifierStepCount" sourceName="Saat" unit="count" startDate="2026-06-18 23:13:35 +0300" endDate="2026-06-18 23:14:35 +0300" value="1432"/>
 <Record type="HKQuantityTypeIdentifierStepCount" sourceName="Saat" unit="count" startDate="2026-06-19 08:00:00 +0300" endDate="2026-06-19 08:05:00 +0300" value="900"/>
 <Record type="HKCategoryTypeIdentifierSleepAnalysis" sourceName="Saat" startDate="2026-06-19 02:00:00 +0300" endDate="2026-06-19 05:00:00 +0300" value="HKCategoryValueSleepAnalysisAsleepCore">
  <MetadataEntry key="x" value="y"/>
 </Record>
 <Workout workoutActivityType="HKWorkoutActivityTypeElliptical" duration="5.38" durationUnit="min" sourceName="Burak Apple Watch’u" startDate="2026-06-19 21:00:19 +0300" endDate="2026-06-19 21:05:42 +0300"/>
</HealthData>
"""


def _make_zip(path):
    with zipfile.ZipFile(path, "w") as zf:
        # Turkish export filename + a CDA decoy that must be ignored.
        zf.writestr("apple_health_export/export_cda.xml", "<ClinicalDocument/>")
        zf.writestr("apple_health_export/dışa aktarılan.xml", SAMPLE_XML)


def test_ingest_parses_and_is_idempotent(tmp_path):
    zip_path = tmp_path / "export.zip"
    db = tmp_path / "health.db"
    _make_zip(zip_path)

    counts = ingest(zip_path, db, progress=lambda *_: None)
    assert counts == {"record": 3, "workout": 1}

    conn = connect(db, create=False)
    # local_date is the first 10 chars of the offset-local timestamp (ADR-0009).
    steps = conn.execute(
        "SELECT local_date, CAST(value AS REAL) v FROM record "
        "WHERE type='HKQuantityTypeIdentifierStepCount' ORDER BY local_date"
    ).fetchall()
    assert [(r["local_date"], r["v"]) for r in steps] == [
        ("2026-06-18", 1432.0),
        ("2026-06-19", 900.0),
    ]
    # Sleep record kept its English enum despite tr_TR locale.
    sleep = conn.execute("SELECT value FROM record WHERE type='HKCategoryTypeIdentifierSleepAnalysis'").fetchone()
    assert sleep["value"] == "HKCategoryValueSleepAnalysisAsleepCore"
    wk = conn.execute("SELECT activity, duration FROM workout").fetchone()
    assert wk["activity"] == "HKWorkoutActivityTypeElliptical" and abs(wk["duration"] - 5.38) < 1e-9
    conn.close()

    # Re-ingest the same archive → no duplicates (content-hash key, ADR-0005).
    init_schema(connect(db, create=False))
    ingest(zip_path, db, progress=lambda *_: None)
    conn = connect(db, create=False)
    assert conn.execute("SELECT COUNT(*) c FROM record").fetchone()["c"] == 3
    assert conn.execute("SELECT COUNT(*) c FROM workout").fetchone()["c"] == 1
    conn.close()
