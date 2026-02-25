#!/usr/bin/env python3
"""
One-off backfill script — populates data/gold_history.csv with
12-24 months of historical data from every scraper.

Usage (from the gold_tracker directory):
    python scripts/backfill_history.py
"""

import sys
import time
import traceback
from pathlib import Path

project_root = str(Path(__file__).resolve().parent.parent)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from scrapers import ALL_SCRAPERS
from utils.history_manager import bulk_record_data


def main() -> None:
    print("=" * 60)
    print("  Gold Monitor — Historical Backfill")
    print("=" * 60)
    print()

    total_inserted = 0

    for cls in ALL_SCRAPERS:
        scraper = cls()
        country = scraper.country
        print(f"[*] Fetching {country} …", end=" ", flush=True)
        t0 = time.time()

        try:
            results = scraper.fetch()
            elapsed = time.time() - t0
            print(f"found {len(results)} records ({elapsed:.1f}s)")

            if results:
                inserted = bulk_record_data(results)
                total_inserted += inserted
                print(
                    f"    [+] Backfilling {country}: "
                    f"{inserted} new row(s) inserted "
                    f"({len(results) - inserted} duplicates skipped)"
                )
            else:
                print(f"    [!] {country}: no data returned")

        except Exception as exc:
            elapsed = time.time() - t0
            print(f"ERROR ({elapsed:.1f}s)")
            print(f"    [!] {country}: {exc}")
            traceback.print_exc()

        print()

    print("=" * 60)
    print(f"  Backfill complete — {total_inserted} total new rows inserted.")
    print("=" * 60)


if __name__ == "__main__":
    main()
