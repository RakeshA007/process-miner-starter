"""
generate_sample_data.py

Creates a realistic, messy "order-to-cash" event log — the kind of raw export
you'd actually get from a business system, with intentionally inconsistent
column names, some rework loops, and some skipped steps. This is the input
Phase 1 of the build route starts from.

Run:  python src/generate_sample_data.py
Output: data/sample_orders.csv
"""

import csv
import random
from datetime import datetime, timedelta

random.seed(42)  # reproducible output — same data every time you run this

# The "happy path" for an order-to-cash process
HAPPY_PATH = [
    "Create Order",
    "Check Credit",
    "Approve Order",
    "Pick Items",
    "Pack Items",
    "Ship Order",
    "Send Invoice",
    "Receive Payment",
    "Close Order",
]

EMPLOYEES = ["A. Sharma", "R. Iyer", "M. Fernandes", "K. Rao", "S. Nair", "P. Verma"]

N_CASES = 600  # ~600 orders is enough to produce ~5,000-6,000 rows and real variant diversity


def build_case(order_id, start_time):
    """Builds one order's event sequence, with realistic variation."""
    steps = list(HAPPY_PATH)
    roll = random.random()

    if roll < 0.12:
        # Credit check fails once, gets rechecked (a rework loop)
        idx = steps.index("Check Credit")
        steps.insert(idx + 1, "Check Credit")
    elif roll < 0.20:
        # Small orders skip the approval step entirely
        steps.remove("Approve Order")
    elif roll < 0.28:
        # Payment is late enough that a reminder step is inserted
        idx = steps.index("Receive Payment")
        steps.insert(idx, "Send Payment Reminder")
    elif roll < 0.33:
        # Packing gets redone (damaged item, etc.)
        idx = steps.index("Pack Items")
        steps.insert(idx + 1, "Pack Items")

    events = []
    t = start_time
    for step in steps:
        t += timedelta(hours=random.uniform(0.5, 30))  # variable gaps between steps
        events.append({
            "OrderID": order_id,
            "Step": step,
            "EventTime": t.strftime("%Y-%m-%d %H:%M:%S"),
            "Employee": random.choice(EMPLOYEES),
        })
    return events


def main():
    base_time = datetime(2026, 1, 5, 8, 0, 0)
    rows = []
    for i in range(1, N_CASES + 1):
        order_id = f"ORD-{i:05d}"
        case_start = base_time + timedelta(hours=random.uniform(0, 24 * 60))
        rows.extend(build_case(order_id, case_start))

    out_path = "data/sample_orders.csv"
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["OrderID", "Step", "EventTime", "Employee"])
        writer.writeheader()
        writer.writerows(rows)

    print(f"Wrote {len(rows)} rows across {N_CASES} orders to {out_path}")


if __name__ == "__main__":
    main()
