"""
Scraper: National Bank of Poland (NBP) — International Reserves

Direct XLSX: https://static.nbp.pl/dane/bilans-platniczy/pap.xlsx
             Updated monthly.  Contains sheets: PLN, EUR, USD, etc.

We use the USD sheet.  Structure:
  Row 3 : date headers (datetime objects, YYYY-MM-01 per column)
  Target row: "ilość złota w uncjach (mln) / volume in millions of
               fine troy ounces"
  Unit  : millions of fine troy ounces → convert to metric tonnes.

All monthly columns are extracted to build a 24-month time-series.
"""

import sys
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path

import pandas as pd

try:
    from .base_scraper import BaseScraper, ScraperResult
except ImportError:
    _root = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(_root))
    from scrapers.base_scraper import BaseScraper, ScraperResult

RESERVES_XLSX = "https://static.nbp.pl/dane/bilans-platniczy/pap.xlsx"
OZ_PER_TONNE = 32_150.7466


class PolandNBPScraper(BaseScraper):

    @property
    def country(self) -> str:
        return "Poland"

    @property
    def source_url(self) -> str:
        return RESERVES_XLSX

    @staticmethod
    def millions_oz_to_tonnes(millions_oz: float) -> float:
        """Convert millions of fine troy ounces to metric tonnes."""
        return round(millions_oz * 1_000_000 / OZ_PER_TONNE, 2)

    def fetch(self) -> list[ScraperResult]:
        resp = self._get(RESERVES_XLSX)
        data_points = self._parse_xlsx_all(resp.content)

        results: list[ScraperResult] = []
        for millions_oz, report_date in data_points:
            gold_tonnes = self.millions_oz_to_tonnes(millions_oz)
            results.append(ScraperResult(
                country=self.country,
                gold_tonnes=gold_tonnes,
                report_date=report_date,
                source_url=RESERVES_XLSX,
            ))

        return results[-24:]

    @staticmethod
    def _parse_xlsx_all(content: bytes) -> list[tuple[float, str]]:
        """Parse every monthly column from the NBP USD sheet.

        Targets the row containing 'volume in millions of fine troy ounces'
        (Polish: 'ilość złota w uncjach (mln)').
        """
        df = pd.read_excel(BytesIO(content), sheet_name="USD", header=None)
        DATE_HEADER_ROW = 3

        volume_row_idx = None
        for idx, row in df.iterrows():
            cell0 = str(row.iloc[0]) if pd.notna(row.iloc[0]) else ""
            cell_lower = cell0.lower()
            if (
                "volume" in cell_lower and "troy" in cell_lower
            ) or (
                "ilo" in cell_lower and "uncj" in cell_lower
            ):
                volume_row_idx = idx
                break

        if volume_row_idx is None:
            raise ValueError(
                "Volume-in-troy-ounces row not found in the NBP USD sheet"
            )

        volume_row = df.iloc[volume_row_idx]
        data_points: list[tuple[float, str]] = []

        for col_i in range(1, df.shape[1]):
            val = volume_row.iloc[col_i]
            if pd.notna(val) and _is_number(str(val)):
                millions_oz = float(str(val))
                date_cell = df.iat[DATE_HEADER_ROW, col_i]
                report_date = _parse_nbp_date(date_cell)
                data_points.append((millions_oz, report_date))

        data_points.sort(key=lambda x: x[1])
        return data_points


def _parse_nbp_date(raw) -> str:
    if isinstance(raw, datetime):
        return raw.strftime("%Y-%m-%d")
    if pd.isna(raw):
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")
    raw_str = str(raw).strip()
    for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%d.%m.%Y", "%m/%Y"):
        try:
            return datetime.strptime(raw_str, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _is_number(s: str) -> bool:
    try:
        float(s)
        return True
    except ValueError:
        return False


if __name__ == "__main__":
    scraper = PolandNBPScraper()
    for r in scraper.fetch():
        print(r)
