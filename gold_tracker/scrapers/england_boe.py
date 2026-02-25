"""
Scraper: Bank of England (BoE) — UK Gold Statistics

Gold statistics page:
  https://www.bankofengland.co.uk/statistics/gold

Downloads the gold-data.xlsx which contains monthly custody holdings
in thousands of fine troy ounces.  All data rows are parsed to build
a full time-series.

Note: BoE gold stats report *custody* holdings (gold held on behalf
of other central banks + the UK's own reserves).
"""

import sys
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path

import pandas as pd
from bs4 import BeautifulSoup

try:
    from .base_scraper import BaseScraper, ScraperResult
except ImportError:
    _root = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(_root))
    from scrapers.base_scraper import BaseScraper, ScraperResult

GOLD_STATS_URL = "https://www.bankofengland.co.uk/statistics/gold"
OZ_PER_TONNE = 32_150.7466


class EnglandBoEScraper(BaseScraper):

    @property
    def country(self) -> str:
        return "England"

    @property
    def source_url(self) -> str:
        return GOLD_STATS_URL

    def fetch(self) -> list[ScraperResult]:
        resp = self._get(GOLD_STATS_URL)
        soup = BeautifulSoup(resp.text, "html.parser")

        xlsx_url = self._find_latest_download(soup)
        xls_resp = self._get(xlsx_url)

        data_points = self._parse_xlsx_all(xls_resp.content)

        results: list[ScraperResult] = []
        for gold_oz, report_date in data_points:
            gold_tonnes = round(gold_oz / OZ_PER_TONNE, 2)
            results.append(ScraperResult(
                country=self.country,
                gold_tonnes=gold_tonnes,
                report_date=report_date,
                source_url=xlsx_url,
            ))

        return results[-24:]

    @staticmethod
    def _find_latest_download(soup: BeautifulSoup) -> str:
        base = "https://www.bankofengland.co.uk"
        for a in soup.find_all("a", href=True):
            href = a["href"]
            text = a.get_text(strip=True).lower()
            if any(ext in href.lower() for ext in (".xlsx", ".xls", ".xlsb")):
                return href if href.startswith("http") else base + href
            if "download" in text and "gold" in text:
                return href if href.startswith("http") else base + href

        raise ValueError(
            "No downloadable gold-data file found on the BoE gold statistics page"
        )

    @staticmethod
    def _parse_xlsx_all(content: bytes) -> list[tuple[float, str]]:
        """Parse every data row from the BoE gold-data XLSX.

        Col 1 = Date, Col 2 = Holdings (thousands of fine troy oz).
        Data starts at row 7.
        """
        dfs = pd.read_excel(BytesIO(content), sheet_name=0, header=None)
        date_col = 1
        value_col = 2
        data_start_row = 7

        if dfs.shape[1] <= value_col:
            raise ValueError("BoE XLSX has fewer columns than expected")

        data_points: list[tuple[float, str]] = []
        for i in range(data_start_row, len(dfs)):
            raw_val = dfs.iat[i, value_col]
            if pd.notna(raw_val) and _is_number(str(raw_val).replace(",", "")):
                gold_thousands_oz = float(str(raw_val).replace(",", ""))
                gold_oz = gold_thousands_oz * 1_000
                raw_date = dfs.iat[i, date_col]
                report_date = _parse_boe_date(raw_date)
                data_points.append((gold_oz, report_date))

        data_points.sort(key=lambda x: x[1])
        return data_points


def _parse_boe_date(raw) -> str:
    if isinstance(raw, datetime):
        return raw.strftime("%Y-%m-%d")
    raw_str = str(raw).strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%b %Y", "%B %Y"):
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
    scraper = EnglandBoEScraper()
    for r in scraper.fetch():
        print(r)
