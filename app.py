"""
app.py

Phase 2 of the build route: the same mining logic from src/discover.py,
now wrapped so a real person can use it through a browser instead of a
terminal. This is the file that turns "code I run" into "a tool someone
else can click through."

Run:  streamlit run app.py
Then open the URL it prints (usually http://localhost:8501).
"""

import os
import sys

import pandas as pd
import streamlit as st

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))
from discover import build_cases, directly_follows_graph, build_graph, compute_variants, compute_kpis  # noqa: E402
import extract_from_db  # noqa: E402

st.set_page_config(page_title="Process Miner", layout="wide")
st.title("Process Miner")
st.caption("Phase 2 — the Phase 1 mining logic, wrapped for a real user instead of a terminal.")


def run_mining(mapped_log: pd.DataFrame):
    """Takes an already-mapped event log (case_id, activity, timestamp,
    resource columns) and renders the full analysis. This is the exact
    same three-function pipeline as src/discover.py's main()."""
    mapped_log = mapped_log.sort_values(["case_id", "timestamp"])
    cases = build_cases(mapped_log)
    node_counts, edge_counts, start_counts, end_counts = directly_follows_graph(cases)
    dot = build_graph(node_counts, edge_counts, start_counts, end_counts)
    kpis = compute_kpis(mapped_log, cases)
    variants_df = compute_variants(cases)

    st.subheader("Process map")
    st.graphviz_chart(dot, use_container_width=True)

    st.subheader("KPIs")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Cases", kpis["case_count"])
    c2.metric("Events", kpis["event_count"])
    c3.metric("Avg case duration (hrs)", kpis["avg_case_duration_hours"])
    c4.metric("Distinct variants", kpis["distinct_variants"])

    left, right = st.columns([3, 2])
    with left:
        st.subheader("Top variants")
        st.dataframe(variants_df.head(10), use_container_width=True, hide_index=True)
    with right:
        st.subheader("Top variant")
        st.write(f"**{kpis['top_variant_pct']}%** of cases ({kpis['top_variant_case_count']} of {kpis['case_count']}) follow:")
        st.code(kpis["top_variant"].replace(" -> ", "\n-> "))


st.sidebar.header("1. Choose a data source")
source = st.sidebar.radio(
    "Data source",
    ["Upload a CSV", "Use the Phase 1 sample data", "Sync from the demo source database"],
)

if source == "Sync from the demo source database":
    st.sidebar.caption("This runs the real incremental connector (src/extract_from_db.py) "
                        "and reads whatever's already in data/eventlog.db.")
    if st.sidebar.button("Run sync now"):
        with st.spinner("Syncing..."):
            status, rows = extract_from_db.sync_once()
        st.sidebar.success(f"Sync {status}: {rows} new events")

    if os.path.exists(extract_from_db.TARGET_DB):
        import sqlite3
        conn = sqlite3.connect(extract_from_db.TARGET_DB)
        tables = pd.read_sql("SELECT name FROM sqlite_master WHERE type='table'", conn)["name"].tolist()
        if "event_log" in tables:
            mapped = pd.read_sql("SELECT * FROM event_log", conn, parse_dates=["timestamp"])
            conn.close()
            if len(mapped):
                st.info(f"Showing {len(mapped)} events currently in data/eventlog.db.")
                run_mining(mapped)
            else:
                st.warning("event_log table exists but is empty — click 'Run sync now' in the sidebar.")
        else:
            conn.close()
            st.warning("No event_log table yet — click 'Run sync now' in the sidebar first.")
    else:
        st.warning("No database yet — click 'Run sync now' in the sidebar first.")

else:
    df = None
    if source == "Upload a CSV":
        uploaded = st.sidebar.file_uploader("Upload an event log CSV", type="csv")
        if uploaded is not None:
            df = pd.read_csv(uploaded)
    else:
        sample_path = os.path.join("data", "sample_orders.csv")
        if os.path.exists(sample_path):
            df = pd.read_csv(sample_path)
            st.sidebar.success(f"Loaded {len(df)} rows from data/sample_orders.csv")
        else:
            st.sidebar.error("data/sample_orders.csv not found — run "
                              "'python src/generate_sample_data.py' first.")

    if df is not None:
        st.subheader("Raw data preview")
        st.dataframe(df.head(8), use_container_width=True)

        st.sidebar.header("2. Map your columns")
        st.sidebar.caption("Tell it which of your columns is which — this is the "
                            "same mapping concept as src/map_to_eventlog.py's COLUMN_MAP.")
        cols = list(df.columns)
        case_col = st.sidebar.selectbox("Case ID column", cols, index=0)
        activity_col = st.sidebar.selectbox("Activity column", cols, index=min(1, len(cols) - 1))
        timestamp_col = st.sidebar.selectbox("Timestamp column", cols, index=min(2, len(cols) - 1))
        resource_options = ["(none)"] + cols
        resource_col = st.sidebar.selectbox("Resource column (optional)", resource_options,
                                             index=min(4, len(resource_options) - 1))

        if st.sidebar.button("Run process mining", type="primary"):
            try:
                mapped = pd.DataFrame({
                    "case_id": df[case_col].astype(str),
                    "activity": df[activity_col].astype(str),
                    "timestamp": pd.to_datetime(df[timestamp_col]),
                    "resource": df[resource_col] if resource_col != "(none)" else "",
                })
            except Exception as e:
                st.error(f"Couldn't map those columns: {e}")
            else:
                run_mining(mapped)
    else:
        st.info("Choose a data source in the sidebar to get started.")
