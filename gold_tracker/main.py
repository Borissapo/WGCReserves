#!/usr/bin/env python3
"""
Central Banks Gold Monitor — main entry point.

Run manually:
    python main.py

Schedule via cron (Linux/macOS):
    */30 * * * * cd /path/to/gold_tracker && python main.py >> cron.log 2>&1

Schedule via Task Scheduler (Windows):
    Create a task that runs: python "C:\\...\\gold_tracker\\main.py"
"""

import os
import sys
import traceback
from datetime import datetime, timezone

from scrapers import ALL_SCRAPERS
from utils.history_manager import record_new_data, get_historical_data
from utils.chart_generator import generate_rolling_chart, generate_flow_chart
from utils.email_alert import send_alert


def run() -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    print(f"\n{'=' * 60}")
    print(f"  Gold Monitor Run -- {ts} UTC")
    print(f"{'=' * 60}\n")

    scrapers = [cls() for cls in ALL_SCRAPERS]
    changes = 0

    for scraper in scrapers:
        country = scraper.country
        try:
            results = scraper.fetch()
            if not results:
                print(f"[WARN]   {country}: scraper returned no data")
                continue

            latest = results[-1]
            new_tonnes = latest["gold_tonnes"]
            report_date = latest["report_date"]
            source_url = latest["source_url"]

            is_new = record_new_data(country, report_date, new_tonnes)

            if is_new:
                historical_df = get_historical_data(country)
                print(
                    f"         {country}: {len(historical_df)} historical "
                    f"data points loaded from CSV"
                )

                old_tonnes = None
                delta = 0.0
                if len(historical_df) >= 2:
                    old_tonnes = float(
                        historical_df["Gold_Tonnes"].iloc[-2]
                    )
                    delta = (
                        float(historical_df["Gold_Tonnes"].iloc[-1])
                        - old_tonnes
                    )

                print(
                    f"[CHANGE] {country}: "
                    f"{old_tonnes or 'N/A'} -> {new_tonnes} tonnes "
                    f"({delta:+.2f})  (report: {report_date})"
                )

                rolling_path = None
                flow_path = None
                try:
                    if len(historical_df) >= 2:
                        rolling_path = generate_rolling_chart(
                            historical_df, country
                        )
                        flow_path = generate_flow_chart(
                            historical_df, country
                        )
                        print(f"         Charts saved for {country}")
                    else:
                        print(
                            f"         [CHART SKIP] {country}: need >=2 "
                            f"data points, have {len(historical_df)}"
                        )
                except Exception as chart_err:
                    print(f"         [CHART WARN] {country}: {chart_err}")

                try:
                    send_alert(
                        country=country,
                        old_tonnes=old_tonnes,
                        new_tonnes=new_tonnes,
                        report_date=report_date,
                        source_url=source_url,
                        rolling_chart_path=rolling_path,
                        flow_chart_path=flow_path,
                    )
                except Exception as email_err:
                    print(f"         [EMAIL WARN] {country}: {email_err}")

                changes += 1
            else:
                print(
                    f"[OK]     {country}: No new release "
                    f"({new_tonnes} tonnes, report: {report_date})"
                )

        except Exception as exc:
            print(f"[ERROR]  {country}: {exc}")
            traceback.print_exc()

    # Write last-run timestamp so the Streamlit dashboard can show it
    last_run_path = os.path.join(os.path.dirname(__file__), "data", "last_run.txt")
    run_ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    os.makedirs(os.path.dirname(last_run_path), exist_ok=True)
    with open(last_run_path, "w") as f:
        f.write(run_ts)

    print(f"\n{'=' * 60}")
    print(f"  Run complete -- {changes} update(s) detected.")
    print(f"{'=' * 60}\n")


if __name__ == "__main__":
    try:
        run()
    except KeyboardInterrupt:
        print("\nInterrupted by user.")
        sys.exit(0)
