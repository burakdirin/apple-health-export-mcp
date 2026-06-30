# Glossary

Domain terms for Apple Health export ingestion. Keep entries one or two lines.

- **export.zip** — The archive produced by iOS *Settings → Health → (profile) → Export All Health Data*. Contains the full health history; the only export path Apple offers.
- **export.xml** — The main data file inside the zip. One giant XML document of `<Record>`, `<Workout>`, `<Correlation>`, etc. 100 MB–1 GB+.
- **export_cda.xml** — A clinical (CDA) summary file. Mostly redundant for our purposes; ignored.
- **Record** — A single health datapoint: `type`, `sourceName`, `startDate`, `endDate`, `value`, `unit`. The atom of the export.
- **Quantity type** — `HKQuantityTypeIdentifier*` (e.g. `…StepCount`, `…HeartRate`, `…BodyMass`). `value` is numeric.
- **Category type** — `HKCategoryTypeIdentifier*` (e.g. `…SleepAnalysis`). `value` is a string enum.
- **Sleep stages** — Category values on `HKCategoryTypeIdentifierSleepAnalysis`: `…InBed`, `…AsleepCore`, `…AsleepDeep`, `…AsleepREM`, `…Awake`. Sleep duration = summed durations of the `Asleep*` intervals.
- **Workout** — A separate `<Workout>` element (activity type, duration, energy, distance). Its own table.
- **Correlation** — A `<Correlation>` element wrapping multiple Records (e.g. blood pressure = systolic + diastolic; food entries). Out of v1 scope.
- **sourceName** — The app/device that wrote the record (iPhone, Apple Watch, a 3rd-party app). Multiple sources write the *same* metric → duplicates; dedup/filter by source.
- **Ingest** — The one-time CLI step that parses `export.xml` into SQLite. Idempotent (ADR-0005).
- **Content hash key** — Synthetic `UNIQUE` key = hash of a record's fields, used for idempotent upsert since records carry no UUID.
- **Aggregation** — The only output shape tools return (ADR-0008): per-day/week sum/avg/min/max, or summed sleep duration. Never raw rows.
- **Local day** — The calendar day in the record's own UTC offset (ADR-0009). The unit most health questions ("how did I sleep last night") actually mean.
