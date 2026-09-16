"""
discover.py

Phase 1, steps 3-6 of the build route: this is the mathematical core of
"process discovery." It reads the mapped event log, computes a
directly-follows graph (which activity follows which, and how often),
renders it as an actual process map image, ranks the process variants
(the distinct end-to-end paths through the process), and computes three
baseline KPIs.

No PM4Py, no external mining library — this is simple enough to hand-write
and fully understand, which matters more than convenience at this stage.

Run:  python src/discover.py
Input:  data/eventlog.db
Output: output/process_map.png
        output/variants.csv
        output/kpis.json
"""

import json
import sqlite3
from collections import Counter, defaultdict

import pandas as pd
import graphviz

DB_PATH = "data/eventlog.db"
OUT_DIR = "output"


def load_event_log():
    conn = sqlite3.connect(DB_PATH)
    log = pd.read_sql("SELECT * FROM event_log", conn, parse_dates=["timestamp"])
    conn.close()
    return log


def build_cases(log):
    """Groups events into an ordered list of activities per case."""
    cases = {}
    for case_id, group in log.groupby("case_id"):
        g = group.sort_values("timestamp")
        cases[case_id] = list(g["activity"])
    return cases


def directly_follows_graph(cases):
    """
    Counts every (A -> B) pair that occurs back-to-back within a case.
    This single data structure is what "process discovery" produces —
    everything else (the map, conformance, variants) is built on top of it.
    """
    node_counts = Counter()
    edge_counts = Counter()
    start_counts = Counter()
    end_counts = Counter()

    for case_id, activities in cases.items():
        start_counts[activities[0]] += 1
        end_counts[activities[-1]] += 1
        for activity in activities:
            node_counts[activity] += 1
        for a, b in zip(activities, activities[1:]):
            edge_counts[(a, b)] += 1

    return node_counts, edge_counts, start_counts, end_counts


def build_graph(node_counts, edge_counts, start_counts, end_counts, min_edge_count=1):
    """
    Builds the process map as a graphviz Digraph object, without writing
    anything to disk. Kept separate from render_process_map() so the
    Streamlit app (app.py) can render this same picture directly in the
    browser, instead of round-tripping through a PNG file.

    min_edge_count: only draw a directly-follows edge if it happened at
    least this many times. On a process with thousands of distinct
    variants, drawing every single edge produces unreadable "spaghetti" --
    raising this is the standard declutter control every process mining
    tool offers. It only hides rare edges from the picture; it never
    changes the underlying counts, KPIs, or variant rankings.
    """
    dot = graphviz.Digraph("process_map")
    dot.attr(rankdir="TB", fontsize="11")
    dot.attr("node", shape="box", style="rounded,filled", fillcolor="#EAF1F6",
             color="#2B5D8C", fontname="Helvetica", fontsize="11")
    dot.attr("edge", color="#52697E", fontname="Helvetica", fontsize="9")

    dot.node("START", shape="circle", style="filled", fillcolor="#2F7A4F",
              fontcolor="white", width="0.5", label="")
    dot.node("END", shape="circle", style="filled", fillcolor="#B85E2A",
              fontcolor="white", width="0.5", label="")

    for activity, count in node_counts.items():
        dot.node(activity, label=f"{activity}\n({count})")

    for activity, count in start_counts.items():
        dot.edge("START", activity, label=str(count))
    for activity, count in end_counts.items():
        dot.edge(activity, "END", label=str(count))

    for (a, b), count in edge_counts.items():
        if count < min_edge_count:
            continue
        # Line thickness scales with frequency — the most common paths
        # visually stand out, exactly what you want a process map to show.
        penwidth = str(min(1 + count / 50, 6))
        dot.edge(a, b, label=str(count), penwidth=penwidth)

    return dot


def render_process_map(node_counts, edge_counts, start_counts, end_counts, out_path, min_edge_count=1):
    dot = build_graph(node_counts, edge_counts, start_counts, end_counts, min_edge_count=min_edge_count)
    dot.format = "png"
    dot.render(out_path, cleanup=True)


def compute_variants(cases):
    """
    A "variant" is one distinct end-to-end path through the process.
    Ranking these by frequency is usually the fastest way to spot both
    the normal way work happens and the exceptions worth investigating.
    """
    variant_counts = Counter(tuple(activities) for activities in cases.values())
    total = sum(variant_counts.values())
    rows = []
    for variants, count in variant_counts.most_common():
        rows.append({
            "variant": " -> ".join(variants),
            "case_count": count,
            "pct_of_cases": round(100 * count / total, 1),
        })
    return pd.DataFrame(rows)


def compute_kpis(log, cases):
    durations = []
    for case_id, group in log.groupby("case_id"):
        span = group["timestamp"].max() - group["timestamp"].min()
        durations.append(span.total_seconds() / 3600.0)  # hours

    variant_counts = Counter(tuple(a) for a in cases.values())
    top_variant, top_count = variant_counts.most_common(1)[0]

    return {
        "case_count": len(cases),
        "event_count": int(sum(len(a) for a in cases.values())),
        "avg_case_duration_hours": round(sum(durations) / len(durations), 1),
        "distinct_variants": len(variant_counts),
        "top_variant": " -> ".join(top_variant),
        "top_variant_case_count": top_count,
        "top_variant_pct": round(100 * top_count / len(cases), 1),
    }


def main():
    import os
    os.makedirs(OUT_DIR, exist_ok=True)

    log = load_event_log()
    cases = build_cases(log)

    node_counts, edge_counts, start_counts, end_counts = directly_follows_graph(cases)
    render_process_map(node_counts, edge_counts, start_counts, end_counts,
                        f"{OUT_DIR}/process_map")

    variants_df = compute_variants(cases)
    variants_df.to_csv(f"{OUT_DIR}/variants.csv", index=False)

    kpis = compute_kpis(log, cases)
    with open(f"{OUT_DIR}/kpis.json", "w") as f:
        json.dump(kpis, f, indent=2)

    print("Process map  -> output/process_map.png")
    print("Variants     -> output/variants.csv")
    print("KPIs         -> output/kpis.json\n")
    print("--- KPI summary ---")
    for k, v in kpis.items():
        print(f"{k}: {v}")
    print("\n--- Top 5 variants ---")
    print(variants_df.head(5).to_string(index=False))


if __name__ == "__main__":
    main()
