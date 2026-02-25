"""
One-time script to generate a realistic sample CSV of central bank gold reserves
in the WGC format (Date, Country, Tonnes) at quarterly frequency.

Run this once, then the dashboard can use data/gold_reserves.csv as a fallback
when WGC scraping hasn't been run yet.

Sources for approximate 2024 reserve levels (tonnes):
  World Gold Council / IMF IFS public tables.
"""

import pandas as pd
import numpy as np
import os

np.random.seed(42)

# Approximate gold reserves (tonnes) as of ~Q1 2000 for major holders,
# plus a handful of active buyers/sellers in recent years.
COUNTRIES: dict[str, dict] = {
    # name: { base_tonnes (approx 2000), trend_per_quarter, noise_std }
    "United States": {"base": 8133, "trend": 0.0, "noise": 0.3},
    "Germany": {"base": 3468, "trend": -0.9, "noise": 0.6},
    "Italy": {"base": 2452, "trend": 0.0, "noise": 0.15},
    "France": {"base": 3025, "trend": -1.0, "noise": 0.15},
    "Russia": {"base": 384, "trend": 16.5, "noise": 9.0},
    "China": {"base": 395, "trend": 15.0, "noise": 12.0},
    "Switzerland": {"base": 2590, "trend": -3.0, "noise": 0.15},
    "Japan": {"base": 754, "trend": 0.15, "noise": 0.15},
    "India": {"base": 358, "trend": 7.5, "noise": 7.5},
    "Netherlands": {"base": 912, "trend": -1.0, "noise": 0.15},
    "Turkiye": {"base": 116, "trend": 10.5, "noise": 15.0},
    "Poland": {"base": 103, "trend": 6.0, "noise": 9.0},
    "United Kingdom": {"base": 487, "trend": -1.0, "noise": 0.15},
    "Portugal": {"base": 607, "trend": -0.5, "noise": 0.15},
    "Kazakhstan": {"base": 56, "trend": 4.5, "noise": 6.0},
    "Uzbekistan": {"base": 53, "trend": 5.4, "noise": 7.5},
    "Thailand": {"base": 84, "trend": 2.4, "noise": 3.0},
    "Singapore": {"base": 127, "trend": 1.2, "noise": 1.5},
    "Czech Republic": {"base": 14, "trend": 4.5, "noise": 4.5},
    "Hungary": {"base": 3, "trend": 1.5, "noise": 3.0},
    "Qatar": {"base": 12, "trend": 0.9, "noise": 1.5},
    "Saudi Arabia": {"base": 143, "trend": 0.0, "noise": 0.9},
    "Australia": {"base": 80, "trend": 0.0, "noise": 0.15},
    "Sweden": {"base": 185, "trend": -0.3, "noise": 0.15},
    "Mexico": {"base": 7, "trend": 0.9, "noise": 1.5},
    "Egypt": {"base": 76, "trend": 0.3, "noise": 0.9},
    "Philippines": {"base": 247, "trend": -0.3, "noise": 1.5},
    "Brazil": {"base": 34, "trend": 0.6, "noise": 0.9},
    "South Korea": {"base": 14, "trend": 0.6, "noise": 0.9},
    "Romania": {"base": 104, "trend": 0.0, "noise": 0.15},
}

# Quarterly date range: Q1 2000 → Q4 2024
# Quarter-end months: March, June, September, December
dates = pd.date_range("2000-03", "2024-12", freq="3MS")

rows = []
for name, params in COUNTRIES.items():
    base = params["base"]
    trend = params["trend"]
    noise_std = params["noise"]

    cumulative = base
    for dt in dates:
        change = trend + np.random.normal(0, noise_std)
        cumulative += change
        cumulative = max(cumulative, 0.1)  # no negatives
        rows.append(
            {
                "Date": dt.strftime("%Y-%m"),
                "Country": name,
                "Tonnes": round(cumulative, 2),
            }
        )

df = pd.DataFrame(rows)

out_dir = os.path.join(os.path.dirname(__file__), "data")
os.makedirs(out_dir, exist_ok=True)
out_path = os.path.join(out_dir, "gold_reserves.csv")
df.to_csv(out_path, index=False)
print(f"Wrote {len(df)} rows ({df['Country'].nunique()} countries, "
      f"{df['Date'].nunique()} quarters) -> {out_path}")
