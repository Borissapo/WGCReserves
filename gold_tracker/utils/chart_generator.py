"""
Professional chart generation for gold reserve email alerts.

Produces two charts per country:
  1. Rolling line chart of Gold_Tonnes over all available history.
  2. Period-over-period net-flow bar chart (green/red).

Charts are saved as PNG files and returned as paths for email embedding.
"""

import os
import tempfile

import matplotlib
matplotlib.use("Agg")

import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib.ticker as mticker
import numpy as np
import pandas as pd
import seaborn as sns

sns.set_theme(style="whitegrid", font_scale=1.05)
plt.rcParams.update({
    "figure.facecolor": "#ffffff",
    "axes.facecolor": "#fafafa",
    "axes.edgecolor": "#cccccc",
    "axes.labelcolor": "#333333",
    "text.color": "#222222",
    "xtick.color": "#555555",
    "ytick.color": "#555555",
    "grid.color": "#e0e0e0",
    "grid.alpha": 0.7,
    "font.family": "sans-serif",
    "axes.spines.top": False,
    "axes.spines.right": False,
})

CHART_DIR = os.path.join(tempfile.gettempdir(), "gold_monitor_charts")

LINE_COLOR = "#1a5276"
FILL_COLOR = "#aed6f1"
POSITIVE_COLOR = "#27ae60"
NEGATIVE_COLOR = "#c0392b"


def _ensure_dir() -> None:
    os.makedirs(CHART_DIR, exist_ok=True)


def _smart_date_locator(ax, dates: pd.Series) -> None:
    """Choose ticks intelligently based on data density."""
    n = len(dates)
    if n <= 14:
        ax.xaxis.set_major_locator(mdates.AutoDateLocator(minticks=3, maxticks=n))
    elif n <= 30:
        ax.xaxis.set_major_locator(mdates.MonthLocator())
    else:
        ax.xaxis.set_major_locator(mdates.MonthLocator(interval=2))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))


def generate_rolling_chart(df: pd.DataFrame, country: str) -> str:
    """Rolling line chart of Gold_Tonnes over available history.

    Expects df with datetime 'Report_Date' and float 'Gold_Tonnes',
    sorted chronologically ascending.  Must have >= 2 rows.

    Returns the file path of the saved PNG.
    """
    if len(df) < 2:
        print(
            f"  [CHART SKIP] {country} rolling: "
            f"need >=2 rows, got {len(df)}"
        )
        return ""

    _ensure_dir()
    path = os.path.join(
        CHART_DIR, f"{country.lower().replace(' ', '_')}_rolling.png"
    )

    dates = pd.to_datetime(df["Report_Date"])
    tonnes = df["Gold_Tonnes"].astype(float)

    fig, ax = plt.subplots(figsize=(10, 5), dpi=150)

    ax.plot(
        dates,
        tonnes,
        color=LINE_COLOR,
        linewidth=2.0,
        marker="o",
        markersize=4 if len(dates) > 20 else 5,
        markerfacecolor="#ffffff",
        markeredgecolor=LINE_COLOR,
        markeredgewidth=1.0,
        zorder=3,
    )
    ax.fill_between(dates, tonnes, alpha=0.18, color=FILL_COLOR, zorder=2)

    ax.set_title(
        f"{country} \u2014 Official Gold Reserves",
        fontsize=14,
        fontweight="bold",
        pad=15,
    )
    ax.set_ylabel("Metric Tonnes", fontsize=11)
    ax.set_xlabel("")

    y_min = tonnes.min()
    y_max = tonnes.max()
    margin = (y_max - y_min) * 0.15 if y_max != y_min else y_max * 0.05
    ax.set_ylim(y_min - margin, y_max + margin)

    pad = pd.Timedelta(days=10)
    ax.set_xlim(dates.min() - pad, dates.max() + pad)

    _smart_date_locator(ax, dates)
    ax.yaxis.set_major_formatter(
        mticker.FuncFormatter(lambda x, _: f"{x:,.0f}")
    )

    plt.xticks(rotation=45, ha="right")
    plt.tight_layout()
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return path


def generate_flow_chart(df: pd.DataFrame, country: str) -> str:
    """Period-over-period net-flow bar chart (green = inflow, red = outflow).

    Expects df with datetime 'Report_Date' and float 'Gold_Tonnes',
    sorted chronologically ascending.  Must have >= 2 rows.

    Returns the file path of the saved PNG.
    """
    if len(df) < 2:
        print(
            f"  [CHART SKIP] {country} flow: "
            f"need >=2 rows, got {len(df)}"
        )
        return ""

    _ensure_dir()
    path = os.path.join(
        CHART_DIR, f"{country.lower().replace(' ', '_')}_flow.png"
    )

    flow = df.copy()
    flow["Report_Date"] = pd.to_datetime(flow["Report_Date"])
    flow["Gold_Tonnes"] = flow["Gold_Tonnes"].astype(float)
    flow = flow.sort_values("Report_Date", ascending=True)
    flow["Net_Change"] = flow["Gold_Tonnes"].diff()
    flow = flow.dropna(subset=["Net_Change"])

    dates = flow["Report_Date"]
    net_change = flow["Net_Change"]
    colors = [
        POSITIVE_COLOR if v >= 0 else NEGATIVE_COLOR for v in net_change
    ]

    n = len(flow)
    if n >= 2:
        median_gap = np.median(np.diff(mdates.date2num(dates)))
        bar_width = max(median_gap * 0.7, 1)
    else:
        bar_width = 5

    fig, ax = plt.subplots(figsize=(10, 5), dpi=150)

    ax.bar(
        dates,
        net_change,
        color=colors,
        width=bar_width,
        edgecolor="white",
        linewidth=0.4,
        alpha=0.88,
        zorder=3,
    )
    ax.axhline(0, color="black", linewidth=1.2, zorder=2)

    freq_label = "Weekly" if n > 15 else "Monthly"
    ax.set_title(
        f"{country} \u2014 {freq_label} Gold Flow (\u0394 Tonnes)",
        fontsize=14,
        fontweight="bold",
        pad=15,
    )
    ax.set_ylabel("Change (Tonnes)", fontsize=11)
    ax.set_xlabel("")

    pad = pd.Timedelta(days=max(bar_width, 10))
    ax.set_xlim(dates.min() - pad, dates.max() + pad)

    _smart_date_locator(ax, dates)
    ax.yaxis.set_major_formatter(
        mticker.FuncFormatter(lambda x, _: f"{x:+,.1f}")
    )

    plt.xticks(rotation=45, ha="right")
    plt.tight_layout()
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return path
