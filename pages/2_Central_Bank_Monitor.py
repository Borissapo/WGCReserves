"""
Central Bank Monitor — direct scraper results.

Reads gold_history.csv produced by the gold_tracker scrapers and shows:
  1. Summary table with latest update per country.
  2. Per-country rolling reserves chart and period-over-period flow chart.
"""

import pathlib

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_HERE = pathlib.Path(__file__).resolve().parent.parent  # cb_imf/

# Primary: committed CSV inside the repo (works on Streamlit Cloud).
# Fallback: gold_tracker sibling directory (local dev with fresh scrapes).
_LOCAL_CSV = _HERE / "data" / "gold_history.csv"
_TRACKER_CSV = _HERE.parent / "gold_tracker" / "data" / "gold_history.csv"

LOGO_PATH = _HERE / "assets" / "logo.webp"

# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------
@st.cache_data(show_spinner="Loading Central Bank Monitor data ...")
def load_monitor_data() -> pd.DataFrame:
    csv_path = None
    if _TRACKER_CSV.exists():
        csv_path = _TRACKER_CSV
    elif _LOCAL_CSV.exists():
        csv_path = _LOCAL_CSV
    else:
        return pd.DataFrame()

    df = pd.read_csv(csv_path)
    if df.empty:
        return pd.DataFrame()

    df["Report_Date"] = pd.to_datetime(df["Report_Date"], errors="coerce")
    df["Gold_Tonnes"] = pd.to_numeric(df["Gold_Tonnes"], errors="coerce")
    df["Date_Scraped"] = pd.to_datetime(df["Date_Scraped"], errors="coerce")
    df.dropna(subset=["Report_Date", "Gold_Tonnes"], inplace=True)
    df.sort_values(["Country", "Report_Date"], inplace=True)
    df.reset_index(drop=True, inplace=True)
    return df


df = load_monitor_data()

if df.empty:
    st.error(
        "No data found. Ensure the gold_tracker has been run at least once "
        "so that `gold_tracker/data/gold_history.csv` exists."
    )
    st.stop()

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
if LOGO_PATH.exists():
    st.sidebar.image(str(LOGO_PATH), use_container_width=True)
    st.sidebar.markdown("---")

# ---------------------------------------------------------------------------
# HEADER
# ---------------------------------------------------------------------------
st.title("Central Bank Monitor")
st.caption("Source: Direct scraping of official central bank websites")

# ===================================================================
# SECTION 1 — Summary table: latest update per country
# ===================================================================
st.header("Latest Updates")


def build_summary(data: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for country, grp in data.groupby("Country"):
        grp = grp.sort_values("Report_Date")
        latest = grp.iloc[-1]
        latest_tonnes = latest["Gold_Tonnes"]
        latest_date = latest["Report_Date"]
        scraped = latest["Date_Scraped"]

        prev_tonnes = None
        delta = None
        pct = None
        if len(grp) >= 2:
            prev_tonnes = grp.iloc[-2]["Gold_Tonnes"]
            delta = latest_tonnes - prev_tonnes
            pct = (delta / prev_tonnes * 100) if prev_tonnes else None

        rows.append(
            {
                "Country": country,
                "Last Report": latest_date,
                "Gold (Tonnes)": latest_tonnes,
                "Previous (Tonnes)": prev_tonnes,
                "Change (Tonnes)": delta,
                "Change (%)": pct,
                "Data Points": len(grp),
                "Last Scraped": scraped,
            }
        )

    summary = pd.DataFrame(rows)
    summary.sort_values("Last Report", ascending=False, inplace=True)
    summary.reset_index(drop=True, inplace=True)
    summary.index = summary.index + 1
    return summary


summary_df = build_summary(df)

st.dataframe(
    summary_df.style.format(
        {
            "Last Report": lambda x: x.strftime("%Y-%m-%d") if pd.notna(x) else "",
            "Gold (Tonnes)": "{:,.2f}",
            "Previous (Tonnes)": lambda x: f"{x:,.2f}" if pd.notna(x) else "—",
            "Change (Tonnes)": lambda x: f"{x:+,.2f}" if pd.notna(x) else "—",
            "Change (%)": lambda x: f"{x:+.2f}%" if pd.notna(x) else "—",
            "Last Scraped": lambda x: x.strftime("%Y-%m-%d %H:%M") if pd.notna(x) else "",
        }
    ),
    use_container_width=True,
    height=350,
)

# ===================================================================
# SECTION 2 — Country detail with charts
# ===================================================================
st.divider()
st.header("Country Detail")

countries = sorted(df["Country"].unique())
selected = st.selectbox(
    "Select a country",
    options=countries,
    index=0,
    key="cb_monitor_country",
)

country_df = df[df["Country"] == selected].sort_values("Report_Date").copy()

if len(country_df) < 2:
    st.warning(
        f"Only {len(country_df)} data point(s) for {selected}. "
        "Need at least 2 to show charts."
    )
    st.stop()

# Compute net change for flow chart
country_df["Net_Change"] = country_df["Gold_Tonnes"].diff()

tab_rolling, tab_flow = st.tabs(
    ["Gold Reserves Over Time", "Period-over-Period Flow"]
)

# --- Tab 1: Rolling line chart ------------------------------------------
with tab_rolling:
    fig1 = px.area(
        country_df,
        x="Report_Date",
        y="Gold_Tonnes",
        title=f"{selected} — Official Gold Reserves",
        labels={"Gold_Tonnes": "Metric Tonnes", "Report_Date": ""},
        color_discrete_sequence=["#1a5276"],
    )
    fig1.update_traces(
        line=dict(width=2.5),
        fillcolor="rgba(174, 214, 241, 0.3)",
        mode="lines+markers",
        marker=dict(size=5, color="#1a5276"),
    )
    fig1.update_layout(
        hovermode="x unified",
        yaxis_tickformat=",.0f",
        xaxis_title="",
        yaxis_title="Metric Tonnes",
    )
    st.plotly_chart(fig1, use_container_width=True)

# --- Tab 2: Flow bar chart (green/red) ---------------------------------
with tab_flow:
    flow_df = country_df.dropna(subset=["Net_Change"]).copy()
    flow_df["Color"] = flow_df["Net_Change"].apply(
        lambda x: "Inflow" if x >= 0 else "Outflow"
    )

    n_points = len(flow_df)
    freq_label = "Weekly" if n_points > 15 else "Monthly"

    fig2 = px.bar(
        flow_df,
        x="Report_Date",
        y="Net_Change",
        color="Color",
        color_discrete_map={"Inflow": "#27ae60", "Outflow": "#c0392b"},
        title=f"{selected} — {freq_label} Gold Flow (\u0394 Tonnes)",
        labels={"Net_Change": "Change (Tonnes)", "Report_Date": ""},
    )
    fig2.update_layout(
        hovermode="x unified",
        showlegend=True,
        yaxis_tickformat="+,.1f",
        xaxis_title="",
        yaxis_title="Change (Tonnes)",
    )
    fig2.add_hline(y=0, line_width=1.5, line_color="black")
    st.plotly_chart(fig2, use_container_width=True)
