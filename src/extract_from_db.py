"""
extract_from_db.py

A real incremental connector, built around four rules that are the actual
answer to "accurate, smooth, without delays and lags":

  1. NEVER re-read the whole source table. Track a watermark (a column that
     only ever increases, like `updated_at`) and only ask the source for
     rows changed since last time. This is what keeps each sync fast and
     keeps load on the source system low, no matter how big it eventually gets.

  2. Page large pulls. Even an incremental batch can be big after a source
     system has been offline a while (or on the very first backfill) --
     pulling it in chunks avoids one giant slow query and lets you see
     progress instead of staring at a frozen terminal.

  3. Make writes idempotent. If a sync is interrupted and reruns, or if you
     rerun it manually while debugging, it must be safe -- no duplicate
     events, nothing double-counted. This script enforces that with a
     database-level UNIQUE constraint, not just "hope the code doesn't bug out."

  4. Only advance the watermark after a successful write. If anything fails
     mid-batch, the next run resumes from the last confirmed-good point --
     never silently skips data because of an error.

Run:  python src/extract_from_db.py            (one sync cycle -- what you'd
                                                  schedule to run every few minutes)
      python src/extract_from_db.py --backfill  (ignore saved state, pull everything --
                                                  use this once, the first time)
"""

import argparse
import json
import sqlite3
import time
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError

# --- Change these four things to point at your real source ---
SOURCE_DB_URL = "sqlite:///data/source_system.db"
# Real examples you'd swap in later:
#   Postgres:   "postgresql+psycopg2://user:password@host:5432/dbname"
#   SQL Server: "mssql+pyodbc://user:password@host/dbname?driver=ODBC+Driver+17+for+SQL+Server"
#   MySQL:      "mysql+pymysql://user:password@host:3306/dbname"
SOURCE_TABLE = "orders_raw"
WATERMARK_COLUMN = "updated_at"
COLUMN_MAP = {
    "order_id": "case_id",
    "status": "activity",
    "status_changed_at": "timestamp",
    "handled_by": "resource",
}
# ---------------------------------------------------------------

TARGET_DB = "data/eventlog.db"
STATE_FILE = "data/sync_state.json"
BATCH_SIZE = 2000
MAX_RETRIES = 4
RETRY_BACKOFF_SECONDS = 2  # doubles each retry: 2s, 4s, 8s, 16s


def load_watermark():
    if Path(STATE_FILE).exists():
        return json.loads(Path(STATE_FILE).read_text()).get("last_watermark", "1900-01-01")
    return "1900-01-01"  # far enough back that the first run pulls everything


def save_watermark(value):
    Path(STATE_FILE).write_text(json.dumps({"last_watermark": value}))


def ensure_target_schema(conn):
    # The UNIQUE constraint is what makes re-running this script safe.
    # If a batch gets written twice for any reason, the duplicate rows
    # are silently ignored instead of double-counting events.
    conn.execute("""
        CREATE TABLE IF NOT EXISTS event_log (
            case_id TEXT NOT NULL,
            activity TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            resource TEXT,
            UNIQUE(case_id, activity, timestamp, resource)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sync_log (
            run_started_at TEXT,
            run_finished_at TEXT,
            rows_pulled INTEGER,
            watermark_before TEXT,
            watermark_after TEXT,
            status TEXT,
            error_message TEXT
        )
    """)
    conn.commit()


def fetch_batch_with_retry(engine, since, offset):
    query = text(f"""
        SELECT * FROM {SOURCE_TABLE}
        WHERE {WATERMARK_COLUMN} > :since
        ORDER BY {WATERMARK_COLUMN}
        LIMIT :limit OFFSET :offset
    """)
    last_error = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            with engine.connect() as conn:
                return pd.read_sql(query, conn, params={"since": since, "limit": BATCH_SIZE, "offset": offset})
        except OperationalError as e:
            # Transient issues -- a momentary lock, a network blip -- are common
            # against a live production database. Back off and try again rather
            # than letting one hiccup kill the whole sync.
            last_error = e
            wait = RETRY_BACKOFF_SECONDS * (2 ** (attempt - 1))
            print(f"  [retry {attempt}/{MAX_RETRIES}] source query failed, retrying in {wait}s: {e}")
            time.sleep(wait)
    raise last_error


def upsert_batch(target_conn, df):
    mapped = df.rename(columns=COLUMN_MAP)[list(COLUMN_MAP.values())]
    rows = list(mapped.itertuples(index=False, name=None))
    target_conn.executemany(
        "INSERT OR IGNORE INTO event_log (case_id, activity, timestamp, resource) VALUES (?, ?, ?, ?)",
        rows,
    )
    target_conn.commit()
    return len(rows)


def sync_once(backfill=False):
    run_started = pd.Timestamp.now('UTC').isoformat()
    watermark_before = "1900-01-01" if backfill else load_watermark()
    print(f"Sync starting. Watermark: {watermark_before}{' (backfill: ignoring saved state)' if backfill else ''}")

    engine = create_engine(SOURCE_DB_URL)
    target_conn = sqlite3.connect(TARGET_DB)
    ensure_target_schema(target_conn)

    total_rows = 0
    max_watermark_seen = watermark_before
    offset = 0
    error_message = None

    try:
        while True:
            batch = fetch_batch_with_retry(engine, watermark_before, offset)
            if batch.empty:
                break

            written = upsert_batch(target_conn, batch)
            total_rows += written
            max_watermark_seen = max(max_watermark_seen, str(batch[WATERMARK_COLUMN].max()))
            print(f"  pulled batch of {len(batch)} rows (offset {offset}), {written} new events written")

            if len(batch) < BATCH_SIZE:
                break
            offset += BATCH_SIZE

        # Watermark only advances here -- after every batch in this run has
        # been successfully written. If the loop above raised partway through,
        # this line never runs, and the next sync safely resumes from
        # watermark_before instead of skipping the rows that failed.
        save_watermark(max_watermark_seen)
        status = "success"

    except Exception as e:
        error_message = str(e)
        status = "failed"
        print(f"Sync FAILED: {error_message}")
        print("Watermark was not advanced -- next run will retry from the same point.")

    run_finished = pd.Timestamp.now('UTC').isoformat()
    target_conn.execute(
        "INSERT INTO sync_log VALUES (?, ?, ?, ?, ?, ?, ?)",
        (run_started, run_finished, total_rows, watermark_before, max_watermark_seen, status, error_message),
    )
    target_conn.commit()
    target_conn.close()

    print(f"Sync {status}. {total_rows} new events written. Watermark now: {max_watermark_seen}\n")
    return status, total_rows


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--backfill", action="store_true", help="ignore saved watermark, pull all history")
    args = parser.parse_args()
    sync_once(backfill=args.backfill)
