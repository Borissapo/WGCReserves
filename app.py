import pathlib
import subprocess
import sys

import streamlit as st
import pandas as pd
import plotly.express as px

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Central Bank Gold Reserves Monitor",
    page_icon="🥇",
    layout="wide",
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
TONNES_TO_MILLION_OZ = 1 / 31.1034768  # 1 tonne ~ 0.03215 M troy oz

_HERE = pathlib.Path(__file__).resolve().parent

# Scraped CSV (produced by wgc_scraper.py) is the primary source.
# The sample-generated CSV is kept as a secondary fallback.
SCRAPED_CSV = _HERE / "data" / "wgc_reserves.csv"
FALLBACK_CSV = _HERE / "data" / "gold_reserves.csv"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _enrich(df: pd.DataFrame) -> pd.DataFrame:
    """Add derived columns (unit conversions, rolling diffs)."""
    df = df.copy()

    # Normalise the date column
    date_col = next(
        (c for c in ("Date", "Period") if c in df.columns), None
    )
    if date_col is None or "Country" not in df.columns or "Tonnes" not in df.columns:
        return pd.DataFrame()

    df["Date"] = pd.to_datetime(df[date_col], format="%Y-%m")
    df["Tonnes"] = pd.to_numeric(df["Tonnes"], errors="coerce")
    df.dropna(subset=["Tonnes"], inplace=True)
    df.sort_values(["Country", "Date"], inplace=True)

    # Derived units
    df["MillionOz"] = df["Tonnes"] * TONNES_TO_MILLION_OZ
    df["Ounces"] = df["MillionOz"] * 1_000_000

    # Rolling differences (net change in Tonnes) per country
    # WGC data is quarterly, so diff(1)=QoQ, diff(2)=6M, diff(4)=YoY
    grouped = df.groupby("Country")["Tonnes"]
    df["QoQ_Change"] = grouped.diff(1)
    df["6M_Change"] = grouped.diff(2)
    df["YoY_Change"] = grouped.diff(4)

    df.reset_index(drop=True, inplace=True)
    return df


# ---------------------------------------------------------------------------
# Data loading (cached)
# ---------------------------------------------------------------------------
@st.cache_data(show_spinner="Loading gold reserves data ...")
def load_data() -> pd.DataFrame:
    # ------ 1. Primary: scraped CSV from wgc_scraper.py ---------------------
    if SCRAPED_CSV.exists():
        df = pd.read_csv(SCRAPED_CSV)
        if not df.empty:
            return _enrich(df)

    # ------ 2. Fallback: sample-generated CSV -------------------------------
    if FALLBACK_CSV.exists():
        st.warning(
            "Scraped data not found.  Run **`python wgc_scraper.py`** first "
            "to download fresh WGC data.  Showing sample data for now."
        )
        df = pd.read_csv(FALLBACK_CSV)
        if not df.empty:
            return _enrich(df)

    return pd.DataFrame()


# ---------------------------------------------------------------------------
# Load data
# ---------------------------------------------------------------------------
df = load_data()

if df.empty:
    st.error(
        "No data found. Please run  **`python wgc_scraper.py`**  to "
        "download gold reserves data from the World Gold Council, then reload."
    )
    st.stop()

# ---------------------------------------------------------------------------
# Sidebar - country selector
# ---------------------------------------------------------------------------
countries_sorted = sorted(df["Country"].unique())

st.sidebar.header("Country Selection")
selected_country = st.sidebar.selectbox(
    "Choose a country",
    options=countries_sorted,
    index=countries_sorted.index("China") if "China" in countries_sorted else 0,
)
country_df = df[df["Country"] == selected_country].copy()

# Show data freshness in the sidebar
latest_date = df["Date"].max()
st.sidebar.markdown("---")
st.sidebar.metric("Data through", f"{latest_date:%B %Y}")
st.sidebar.caption(
    "To refresh, run:  `python wgc_scraper.py`  then reload."
)

# ---------------------------------------------------------------------------
# Sidebar - WGC data update button (local only)
# ---------------------------------------------------------------------------
_SCRAPER = _HERE / "wgc_scraper.py"
if _SCRAPER.exists():
    st.sidebar.markdown("---")
    if st.sidebar.button("Update WGC Data", use_container_width=True):
        with st.sidebar:
            with st.spinner("Running WGC scraper (this may take a few minutes)..."):
                result = subprocess.run(
                    [sys.executable, str(_SCRAPER)],
                    capture_output=True,
                    text=True,
                    timeout=600,
                )
            if result.returncode == 0 and SCRAPED_CSV.exists():
                st.success("Data updated! Reloading...")
                st.cache_data.clear()
                st.rerun()
            else:
                st.error("Scraper failed. See details below.")
                st.code(result.stdout + result.stderr, language="text")

# ---------------------------------------------------------------------------
# HEADER
# ---------------------------------------------------------------------------
st.title("Central Bank Gold Reserves Monitor")
st.caption("Source: World Gold Council - Gold Reserves by Country")

# ===================================================================
# TOP SECTION - Individual country charts
# ===================================================================
st.header(f"{selected_country}")

tab_total, tab_qoq, tab_yoy = st.tabs(
    [
        "Total Reserves (Tonnes)",
        "Quarter-over-Quarter Change",
        "Year-over-Year Change",
    ]
)

# --- Tab 1: Total reserves line chart -----------------------------------
with tab_total:
    fig1 = px.line(
        country_df,
        x="Date",
        y="Tonnes",
        title=f"{selected_country} - Total Gold Reserves (Metric Tonnes)",
        labels={"Tonnes": "Metric Tonnes", "Date": ""},
    )
    fig1.update_layout(hovermode="x unified")
    st.plotly_chart(fig1, use_container_width=True)

# --- Tab 2: QoQ bar chart (diverging) -----------------------------------
with tab_qoq:
    qoq_df = country_df.dropna(subset=["QoQ_Change"]).copy()
    qoq_df["Color"] = qoq_df["QoQ_Change"].apply(
        lambda x: "Bought" if x >= 0 else "Sold"
    )
    fig2 = px.bar(
        qoq_df,
        x="Date",
        y="QoQ_Change",
        color="Color",
        color_discrete_map={"Bought": "#22a867", "Sold": "#e0413d"},
        title=f"{selected_country} - Quarter-over-Quarter Change (Tonnes)",
        labels={"QoQ_Change": "Change (Tonnes)", "Date": ""},
    )
    fig2.update_layout(hovermode="x unified", showlegend=True)
    st.plotly_chart(fig2, use_container_width=True)

# --- Tab 3: YoY bar chart (diverging) -----------------------------------
with tab_yoy:
    yoy_df = country_df.dropna(subset=["YoY_Change"]).copy()
    yoy_df["Color"] = yoy_df["YoY_Change"].apply(
        lambda x: "Bought" if x >= 0 else "Sold"
    )
    fig3 = px.bar(
        yoy_df,
        x="Date",
        y="YoY_Change",
        color="Color",
        color_discrete_map={"Bought": "#22a867", "Sold": "#e0413d"},
        title=f"{selected_country} - Year-over-Year Change (Tonnes)",
        labels={"YoY_Change": "Change (Tonnes)", "Date": ""},
    )
    fig3.update_layout(hovermode="x unified", showlegend=True)
    st.plotly_chart(fig3, use_container_width=True)

# ===================================================================
# BOTTOM SECTION - Global Top Movers
# ===================================================================
st.divider()
st.header("Global Top Movers (Latest Quarter)")

latest_df = df[df["Date"] == latest_date].copy()
st.caption(f"Data as of **{latest_date:%B %Y}**")


def _top_table(
    source: pd.DataFrame, col: str, top_n: int = 5, ascending: bool = False
) -> pd.DataFrame:
    """Return a formatted top-N table for display."""
    subset = source.dropna(subset=[col])
    subset = subset.sort_values(col, ascending=ascending).head(top_n)
    out = subset[["Country", col]].copy()
    out.columns = ["Country", "Change (Tonnes)"]
    out["Change (Tonnes)"] = out["Change (Tonnes)"].round(2)
    out = out.reset_index(drop=True)
    out.index = out.index + 1  # 1-based ranking
    return out


col1, col2, col3 = st.columns(3)

with col1:
    st.subheader("Last Quarter")
    st.markdown("**Top 5 Buyers**")
    st.dataframe(
        _top_table(latest_df, "QoQ_Change", ascending=False),
        use_container_width=True,
    )
    st.markdown("**Top 5 Sellers**")
    st.dataframe(
        _top_table(latest_df, "QoQ_Change", ascending=True),
        use_container_width=True,
    )

with col2:
    st.subheader("Last 6 Months")
    st.markdown("**Top 5 Buyers**")
    st.dataframe(
        _top_table(latest_df, "6M_Change", ascending=False),
        use_container_width=True,
    )
    st.markdown("**Top 5 Sellers**")
    st.dataframe(
        _top_table(latest_df, "6M_Change", ascending=True),
        use_container_width=True,
    )

with col3:
    st.subheader("Last 12 Months")
    st.markdown("**Top 5 Buyers**")
    st.dataframe(
        _top_table(latest_df, "YoY_Change", ascending=False),
        use_container_width=True,
    )
    st.markdown("**Top 5 Sellers**")
    st.dataframe(
        _top_table(latest_df, "YoY_Change", ascending=True),
        use_container_width=True,
    )
