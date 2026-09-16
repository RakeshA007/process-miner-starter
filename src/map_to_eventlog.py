"""
map_to_eventlog.py

Phase 1, step 2 of the build route: map a raw export into the standard
process-mining event log shape (Case ID, Activity, Timestamp, Resource),
then store it in a local SQLite file — no server, no setup.

This is deliberately written as a config you'd change per data source,
not hard-coded logic — swap COLUMN_MAP for a new CSV and nothing else
in this file needs to change.

Run:  python src/map_to_eventlog.py
Input:  data/sample_orders.csv
Output: data/eventlog.db  (SQLite, table "event_log")
"""

import sqlite3
import pandas as pd

# --- This is the only part you edit when pointing at a different source file ---
INPUT_CSV = "data/sample_orders.csv"
COLUMN_MAP = {
    "OrderID": "case_id",
    "Step": "activity",
    "EventTime": "timestamp",
    "Employee": "resource",
}
# ---------------------------------------------------------------------------

DB_PATH = "data/eventlog.db"


def main():
    raw = pd.read_csv(INPUT_CSV)
    missing = [c for c in COLUMN_MAP if c not in raw.columns]
    if missing:
        raise ValueError(f"Expected columns not found in {INPUT_CSV}: {missing}")

    log = raw.rename(columns=COLUMN_MAP)[list(COLUMN_MAP.values())]
    log["timestamp"] = pd.to_datetime(log["timestamp"])

    # The single most important rule in process mining data prep:
    # every case's events must be in chronological order.
    log = log.sort_values(["case_id", "timestamp"]).reset_index(drop=True)

    conn = sqlite3.connect(DB_PATH)
    log.to_sql("event_log", conn, if_exists="replace", index=False)
    conn.close()

    print(f"Mapped {len(log)} events across {log['case_id'].nunique()} cases -> {DB_PATH}")
    print("\nPreview:")
    print(log.head(8).to_string(index=False))


if __name__ == "__main__":
    main()
