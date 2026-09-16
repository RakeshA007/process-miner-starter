"""
setup_demo_source_db.py

Stands in for "a real source system" so we can build and test a real
incremental connector without needing your actual database yet. It creates
a SQLite file that looks like a typical transactional table you'd find in
almost any business system: an orders table with a status, who last touched
it, and — critically — an `updated_at` column that changes every time a row
changes. That column is the single most important thing a source table can
have for reliable integration; see extract_from_db.py for why.

Run modes:
  python src/setup_demo_source_db.py            -> create the table, seed 300 orders
  python src/setup_demo_source_db.py --simulate  -> pretend more work happened
                                                     (updates some existing orders,
                                                     inserts new ones) -- run this
                                                     between two syncs to see the
                                                     connector pull only the delta
"""

import argparse
import random
import sqlite3
from datetime import datetime, timedelta

DB_PATH = "data/source_system.db"
STATUSES = ["Created", "Credit Checked", "Approved", "Picked", "Packed", "Shipped", "Invoiced", "Paid", "Closed"]
EMPLOYEES = ["A. Sharma", "R. Iyer", "M. Fernandes", "K. Rao", "S. Nair"]


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS orders_raw (
            row_id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id TEXT NOT NULL,
            status TEXT NOT NULL,
            status_changed_at TEXT NOT NULL,
            handled_by TEXT,
            updated_at TEXT NOT NULL
        )
    """)
    # This index is what makes "only fetch rows changed since X" a fast,
    # cheap query instead of a full table scan on every sync.
    conn.execute("CREATE INDEX IF NOT EXISTS idx_orders_updated_at ON orders_raw(updated_at)")
    return conn


def insert_status_event(conn, order_id, status, when):
    now = datetime.utcnow().isoformat()
    conn.execute(
        "INSERT INTO orders_raw (order_id, status, status_changed_at, handled_by, updated_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (order_id, status, when.isoformat(), random.choice(EMPLOYEES), now),
    )


def seed(n_orders=300):
    conn = get_conn()
    base = datetime(2026, 3, 1, 8, 0, 0)
    for i in range(1, n_orders + 1):
        order_id = f"ORD-{i:05d}"
        t = base + timedelta(hours=random.uniform(0, 24 * 30))
        n_steps = random.randint(4, len(STATUSES))
        for status in STATUSES[:n_steps]:
            t += timedelta(hours=random.uniform(1, 20))
            insert_status_event(conn, order_id, status, t)
    conn.commit()
    n = conn.execute("SELECT COUNT(*) FROM orders_raw").fetchone()[0]
    conn.close()
    print(f"Seeded source system: {n} status events across {n_orders} orders in {DB_PATH}")


def simulate_new_activity(n_new_orders=15, n_updates=25):
    """Pretends time has passed in the source system: some brand-new orders
    arrive, and some in-flight orders move to their next status. Every one
    of these writes gets a fresh updated_at — this is what your connector
    should pick up on its next run, and nothing else."""
    conn = get_conn()
    now = datetime.utcnow()

    existing_ids = [r[0] for r in conn.execute("SELECT DISTINCT order_id FROM orders_raw").fetchall()]
    for order_id in random.sample(existing_ids, min(n_updates, len(existing_ids))):
        current = conn.execute(
            "SELECT status FROM orders_raw WHERE order_id = ? ORDER BY status_changed_at DESC LIMIT 1",
            (order_id,),
        ).fetchone()
        if current and current[0] in STATUSES and STATUSES.index(current[0]) < len(STATUSES) - 1:
            next_status = STATUSES[STATUSES.index(current[0]) + 1]
            insert_status_event(conn, order_id, next_status, now)

    next_num = max(int(oid.split("-")[1]) for oid in existing_ids) + 1
    for i in range(n_new_orders):
        order_id = f"ORD-{next_num + i:05d}"
        insert_status_event(conn, order_id, "Created", now)

    conn.commit()
    conn.close()
    print(f"Simulated activity: {n_updates} orders advanced a step, {n_new_orders} new orders created.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--simulate", action="store_true", help="simulate new activity instead of seeding")
    args = parser.parse_args()

    if args.simulate:
        simulate_new_activity()
    else:
        seed()
