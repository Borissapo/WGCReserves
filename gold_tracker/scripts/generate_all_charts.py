#!/usr/bin/env python3
"""Generate rolling and flow charts for all countries from gold_history.csv."""
import sys
sys.path.insert(0, ".")

from utils.history_manager import get_historical_data
from utils.chart_generator import generate_rolling_chart, generate_flow_chart, CHART_DIR

import pandas as pd

def main():
    # Get list of countries that have data in the CSV
    df_all = pd.read_csv("data/gold_history.csv")
    countries = df_all["Country"].unique().tolist()

    print(f"Generating charts for {len(countries)} countries...")
    print(f"Output folder: {CHART_DIR}\n")

    for country in sorted(countries):
        hist = get_historical_data(country)
        if len(hist) < 2:
            print(f"  [SKIP] {country}: need >=2 data points, have {len(hist)}")
            continue
        rolling_path = generate_rolling_chart(hist, country)
        flow_path = generate_flow_chart(hist, country)
        if rolling_path or flow_path:
            print(f"  [OK]   {country}: rolling + flow saved")

    print("\nDone. Charts are in:", CHART_DIR)

if __name__ == "__main__":
    main()