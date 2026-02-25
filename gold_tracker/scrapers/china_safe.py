"""
Scraper: People's Republic of China — SAFE (State Administration of
         Foreign Exchange)

Index page : https://www.safe.gov.cn/en/2021/0203/1799.html
             Lists monthly .xls files for the SDDS International
             Reserves template.

Downloads up to 24 monthly .xls files to build a time-series.
Each file contains a row:
  以盎司计算的纯金数量（百万盎司）
  volume in millions of fine troy ounces

This is the physical gold quantity — no USD conversion needed.
Conversion: millions of fine troy ounces → metric tonnes
            gold_tonnes = value * 1_000_000 / 32_150.7465
"""

import re
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

INDEX_URL = "https://www.safe.gov.cn/en/2021/0203/1799.html"
OZ_PER_TONNE = 32_150.7465


class ChinaSAFEScraper(BaseScraper):

    @property
    def country(self) -> str:
        return "China"

    @property
    def source_url(self) -> str:
        return INDEX_URL

    def fetch(self) -> list[ScraperResult]:
        resp = self._get(INDEX_URL)
        soup = BeautifulSoup(resp.text, "html.parser")

        xls_links = self._collect_xls_links(soup)
        if not xls_links:
            raise ValueError("No .xls download links found on the SAFE page")

        xls_links = xls_links[-24:]

        results: list[ScraperResult] = []
        for url in xls_links:
            try:
                report_date = self._infer_date_from_url(url)
                xls_resp = self._get(url)
                gold_mn_oz = self._parse_xls(xls_resp.content)
                gold_tonnes = round(
                    gold_mn_oz * 1_000_000 / OZ_PER_TONNE, 2
                )
                results.append(ScraperResult(
                    country=self.country,
                    gold_tonnes=gold_tonnes,
                    report_date=report_date,
                    source_url=url,
                ))
            except Exception:
                continue

        results.sort(key=lambda x: x["report_date"])
        return results

    @staticmethod
    def _collect_xls_links(soup: BeautifulSoup) -> list[str]:
        base = "https://www.safe.gov.cn"
        links: list[str] = []
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if href.endswith(".xls") or href.endswith(".xlsx"):
                url = href if href.startswith("http") else base + href
                links.append(url)
        return links

    @staticmethod
    def _infer_date_from_url(url: str) -> str:
        m = re.search(r"/(\d{4})(\d{2})(\d{2})/", url)
        if m:
            return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")

    @staticmethod
    def _parse_xls(content: bytes) -> float:
        """Extract gold volume in millions of fine troy ounces."""
        try:
            dfs = pd.read_excel(
                BytesIO(content), sheet_name=0, header=None, engine="xlrd"
            )
        except ImportError as e:
            raise ImportError(
                "Reading SAFE .xls files requires 'xlrd'. "
                "Install: pip install xlrd"
            ) from e

        target = "volume in millions of fine troy ounces"

        for row_idx in range(len(dfs)):
            for col_idx in range(dfs.shape[1]):
                cell = dfs.iat[row_idx, col_idx]
                if pd.isna(cell):
                    continue
                if target in str(cell).lower():
                    for c in range(dfs.shape[1]):
                        val = dfs.iat[row_idx, c]
                        if pd.notna(val) and _is_number(val):
                            return float(val)
                    break

        raise ValueError(
            "Could not locate 'volume in millions of fine troy ounces' "
            "row in the SAFE .xls"
        )


def _is_number(val) -> bool:
    try:
        f = float(val)
        return f != 0
    except (ValueError, TypeError):
        return False


if __name__ == "__main__":
    scraper = ChinaSAFEScraper()
    for r in scraper.fetch():
        print(r)
