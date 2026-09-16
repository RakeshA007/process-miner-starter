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

# Every KPI the app knows how to compute, keyed by the label shown on
# screen. Add a new metric here (and to compute_kpis in src/discover.py if
# it isn't already in the dict it returns) and it automatically becomes
# something the user can choose to display below.
KPI_CATALOG = {
    "Cases": "case_count",
    "Events": "event_count",
    "Avg case duration (hrs)": "avg_case_duration_hours",
    "Median case duration (hrs)": "median_case_duration_hours",
    "Min case duration (hrs)": "min_case_duration_hours",
    "Max case duration (hrs)": "max_case_duration_hours",
    "Distinct variants": "distinct_variants",
    "Distinct activities": "distinct_activities",
    "Avg events per case": "avg_events_per_case",
}
DEFAULT_KPIS = ["Cases", "Events", "Avg case duration (hrs)", "Distinct variants"]


def compute_mining_results(mapped_log: pd.DataFrame) -> dict:
    """The expensive, once-per-dataset work: build cases, the
    directly-follows graph, KPIs, and variants. Kept separate from
    rendering so a cheap, interactive control (like the process map's
    frequency slider) never has to re-run this from scratch -- only a
    fresh "Run process mining" click does."""
    mapped_log = mapped_log.sort_values(["case_id", "timestamp"])
    cases = build_cases(mapped_log)
    node_counts, edge_counts, start_counts, end_counts = directly_follows_graph(cases)
    return {
        "node_counts": node_counts,
        "edge_counts": edge_counts,
        "start_counts": start_counts,
        "end_counts": end_counts,
        "kpis": compute_kpis(mapped_log, cases),
        "variants_df": compute_variants(cases),
    }


def render_mining_results(results: dict):
    """Cheap rendering step. Streamlit reruns this whole script on every
    interaction -- including just dragging the slider below -- so this
    function deliberately does no heavy recomputation, only reads from
    the already-computed `results` dict."""
    node_counts = results["node_counts"]
    edge_counts = results["edge_counts"]
    start_counts = results["start_counts"]
    end_counts = results["end_counts"]
    kpis = results["kpis"]
    variants_df = results["variants_df"]

    st.subheader("Process map")
    max_edge_count = max(edge_counts.values()) if edge_counts else 1
    if max_edge_count > 1:
        min_edge_count = st.slider(
            "Minimum path frequency — hide paths that happened fewer times than this "
            "(raise this to declutter a tangled map; it only hides rare paths, the "
            "KPIs and variants below are unaffected)",
            min_value=1, max_value=int(max_edge_count), value=1,
        )
    else:
        min_edge_count = 1
    dot = build_graph(node_counts, edge_counts, start_counts, end_counts, min_edge_count=min_edge_count)
    shown = sum(1 for c in edge_counts.values() if c >= min_edge_count)
    hidden = len(edge_counts) - shown
    if hidden:
        st.caption(f"Showing {shown} of {len(edge_counts)} distinct paths "
                    f"({hidden} rarer path{'s' if hidden != 1 else ''} hidden below the threshold).")
    st.graphviz_chart(dot, use_container_width=True)

    st.subheader("KPIs")
    chosen = st.multiselect(
        "Choose which KPIs to show",
        options=list(KPI_CATALOG.keys()),
        default=DEFAULT_KPIS,
    )
    if chosen:
        # Lay chosen metrics out four to a row, however many are picked.
        for row_start in range(0, len(chosen), 4):
            row_labels = chosen[row_start:row_start + 4]
            row_cols = st.columns(len(row_labels))
            for col, label in zip(row_cols, row_labels):
                col.metric(label, kpis[KPI_CATALOG[label]])
    else:
        st.caption("No KPIs selected — pick at least one above to see numbers here.")

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

# Switching data source starts fresh, so you're never looking at a stale
# map computed from a different file.
if st.session_state.get("mining_source") != source:
    st.session_state.pop("mining_results", None)
    st.session_state["mining_source"] = source

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
                with st.spinner("Running process mining..."):
                    results = compute_mining_results(mapped)
                render_mining_results(results)
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

        # Two-step "disable, then crunch" so the button visibly greys out
        # the instant you click it, instead of sitting there looking
        # unresponsive while a big file is processed. Streamlit reruns the
        # whole script on every interaction, so this takes two reruns: one
        # to show the disabled button, one to do the actual work.
        run_clicked = st.sidebar.button(
            "Run process mining", type="primary",
            disabled=st.session_state.get("mining_running", False),
        )
        if run_clicked:
            try:
                mapped = pd.DataFrame({
                    "case_id": df[case_col].astype(str),
                    "activity": df[activity_col].astype(str),
                    "timestamp": pd.to_datetime(df[timestamp_col]),
                    "resource": df[resource_col] if resource_col != "(none)" else "",
                })
            except Exception as e:
                st.sidebar.error(f"Couldn't map those columns: {e}")
            else:
                st.session_state["pending_mapped_log"] = mapped
                st.session_state["mining_running"] = True
                st.rerun()

        if st.session_state.get("mining_running"):
            st.info("⏳ Running process mining — this can take a little while on large "
                    "files. The button in the sidebar is greyed out until this finishes, "
                    "so a single click is enough.")
            with st.spinner("Crunching the event log..."):
                mapped = st.session_state.pop("pending_mapped_log")
                st.session_state["mining_results"] = compute_mining_results(mapped)
            st.session_state["mining_running"] = False
            st.rerun()

        if "mining_results" in st.session_state:
            render_mining_results(st.session_state["mining_results"])
    else:
        st.info("Choose a data source in the sidebar to get started.")
