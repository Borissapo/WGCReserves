"""
Scraper: Deutsche Bundesbank — Gold Reserves via Time-Series API

API endpoint:
  https://api.statistiken.bundesbank.de/rest/download/BBFI3/
  M.N.DE.W19.S121.S1N.LE.A.FA.R.F11A._Z.XAU._Z.N?format=csv&lang=en

Series     : BBFI3.M.N.DE.W19.S121.S1N.LE.A.FA.R.F11A._Z.XAU._Z.N
Description: Reserve Assets — Gold bullion — Troy ounces
Unit       : Millions of fine troy ounces (unit multiplier = Millions)
Frequency  : Monthly

The CSV contains ALL historical monthly rows (YYYY-MM,value).
We parse every row and return the last 24 months.
"""

import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    from .base_scraper import BaseScraper, ScraperResult
except ImportError:
    _root = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(_root))
    from scrapers.base_scraper import BaseScraper, ScraperResult

SERIES_KEY = "BBFI3/M.N.DE.W19.S121.S1N.LE.A.FA.R.F11A._Z.XAU._Z.N"
API_URL = (
    f"https://api.statistiken.bundesbank.de/rest/download/"
    f"{SERIES_KEY}?format=csv&lang=en"
)
OZ_PER_TONNE = 32_150.7466


class GermanyBundesbankScraper(BaseScraper):

    @property
    def country(self) -> str:
        return "Germany"

    @property
    def source_url(self) -> str:
        return API_URL

    def fetch(self) -> list[ScraperResult]:
        resp = self._get(API_URL)
        text = resp.text.lstrip("\ufeff")

        data_points = self._parse_csv_all(text)

        results: list[ScraperResult] = []
        for period, millions_oz in data_points:
            gold_oz = millions_oz * 1_000_000
            gold_tonnes = round(gold_oz / OZ_PER_TONNE, 2)
            report_date = self._period_to_date(period)
            results.append(ScraperResult(
                country=self.country,
                gold_tonnes=gold_tonnes,
                report_date=report_date,
                source_url=API_URL,
            ))

        return results[-24:]

    @staticmethod
    def _parse_csv_all(text: str) -> list[tuple[str, float]]:
        """Extract all data rows (YYYY-MM, value) from the Bundesbank CSV."""
        data_points: list[tuple[str, float]] = []
        for line in text.strip().splitlines():
            parts = line.split(",")
            if len(parts) < 2:
                continue
            period = parts[0].strip().strip('"')
            raw_val = parts[1].strip().strip('"')
            if len(period) == 7 and period[4] == "-" and raw_val:
                try:
                    val = float(raw_val)
                    data_points.append((period, val))
                except ValueError:
                    continue
        return data_points

    @staticmethod
    def _period_to_date(period: str) -> str:
        try:
            dt = datetime.strptime(period, "%Y-%m")
            return dt.strftime("%Y-%m-01")
        except ValueError:
            return datetime.now(timezone.utc).strftime("%Y-%m-%d")


if __name__ == "__main__":
    scraper = GermanyBundesbankScraper()
    for r in scraper.fetch():
        print(r)
