"""
CSV-based time-series tracker for gold reserves.

File : data/gold_history.csv
Cols : Date_Scraped, Country, Report_Date, Gold_Tonnes
"""

import os
from datetime import datetime, timezone

import pandas as pd

_PROJECT_ROOT = os.path.dirname(os.path.dirname(__file__))
DATA_DIR = os.path.join(_PROJECT_ROOT, "data")
HISTORY_CSV = os.path.join(DATA_DIR, "gold_history.csv")

COLUMNS = ["Date_Scraped", "Country", "Report_Date", "Gold_Tonnes"]


def _ensure_csv() -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    if not os.path.exists(HISTORY_CSV):
        pd.DataFrame(columns=COLUMNS).to_csv(HISTORY_CSV, index=False)


def record_new_data(country: str, report_date: str, gold_tonnes: float) -> bool:
    """Append a row if this (Country, Report_Date) pair is new.

    Returns True if a new row was inserted, False if it already existed.
    """
    _ensure_csv()
    df = pd.read_csv(HISTORY_CSV)

    already_exists = (
        (df["Country"] == country) & (df["Report_Date"] == report_date)
    ).any()

    if already_exists:
        return False

    new_row = pd.DataFrame(
        [
            {
                "Date_Scraped": datetime.now(timezone.utc).strftime(
                    "%Y-%m-%d %H:%M:%S"
                ),
                "Country": country,
                "Report_Date": report_date,
                "Gold_Tonnes": gold_tonnes,
            }
        ]
    )
    new_row.to_csv(HISTORY_CSV, mode="a", header=False, index=False)
    return True


def bulk_record_data(data_list: list[dict]) -> int:
    """Insert multiple records, skipping (Country, Report_Date) duplicates.

    After insertion the CSV is sorted by Country + Report_Date and saved.
    Returns the number of new rows inserted.
    """
    _ensure_csv()
    df = pd.read_csv(HISTORY_CSV)

    existing_keys = set(
        zip(df["Country"].astype(str), df["Report_Date"].astype(str))
    )
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    new_rows: list[dict] = []

    for rec in data_list:
        key = (str(rec["country"]), str(rec["report_date"]))
        if key in existing_keys:
            continue
        new_rows.append({
            "Date_Scraped": now_str,
            "Country": rec["country"],
            "Report_Date": rec["report_date"],
            "Gold_Tonnes": rec["gold_tonnes"],
        })
        existing_keys.add(key)

    if not new_rows:
        return 0

    new_df = pd.DataFrame(new_rows)
    df = pd.concat([df, new_df], ignore_index=True)
    df = df.sort_values(["Country", "Report_Date"]).reset_index(drop=True)
    df.to_csv(HISTORY_CSV, index=False)

    return len(new_rows)


def get_historical_data(country: str) -> pd.DataFrame:
    """Return ALL historical data for a country, sorted chronologically."""
    _ensure_csv()
    df = pd.read_csv(HISTORY_CSV)
    df = df[df["Country"] == country].copy()

    if df.empty:
        return df

    df["Report_Date"] = pd.to_datetime(
        df["Report_Date"], format="ISO8601", errors="coerce"
    )
    df = df.sort_values("Report_Date", ascending=True)
    df = df.drop_duplicates(subset=["Report_Date"])
    df = df.reset_index(drop=True)

    return df
