"""
Scraper: United States — Treasury FiscalData API

Endpoint : /v2/accounting/od/gold_reserve
Docs     : https://fiscaldata.treasury.gov/api-documentation/

The API returns every facility's gold holdings in fine troy ounces and
book-value USD (at the statutory $42.2222/oz).  We sum all facilities
to get the national total, then convert to metric tonnes.

page[size]=1000 fetches ~24 months of multi-facility rows in one call.
No API key required.  Updated monthly.
"""

import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

try:
    from .base_scraper import BaseScraper, ScraperResult
except ImportError:
    _root = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(_root))
    from scrapers.base_scraper import BaseScraper, ScraperResult

API_BASE = (
    "https://api.fiscaldata.treasury.gov/services/api/fiscal_service"
    "/v2/accounting/od/gold_reserve"
)
OZ_PER_TONNE = 32_150.7466


class USTreasuryScraper(BaseScraper):

    @property
    def country(self) -> str:
        return "United States"

    @property
    def source_url(self) -> str:
        return API_BASE

    def fetch(self) -> list[ScraperResult]:
        url = (
            f"{API_BASE}?"
            "sort=-record_date"
            "&page[size]=1000"
            "&fields=record_date,facility_desc,fine_troy_ounce_qty"
        )
        resp = self._get(url)
        rows = resp.json()["data"]
        if not rows:
            raise ValueError("FiscalData returned no gold_reserve rows")

        by_date: dict[str, float] = defaultdict(float)
        for r in rows:
            by_date[r["record_date"]] += float(r["fine_troy_ounce_qty"])

        results: list[ScraperResult] = []
        for date_str in sorted(by_date.keys()):
            gold_tonnes = round(by_date[date_str] / OZ_PER_TONNE, 2)
            results.append(ScraperResult(
                country=self.country,
                gold_tonnes=gold_tonnes,
                report_date=date_str,
                source_url=url,
            ))

        return results[-24:]


if __name__ == "__main__":
    scraper = USTreasuryScraper()
    for r in scraper.fetch():
        print(r)
