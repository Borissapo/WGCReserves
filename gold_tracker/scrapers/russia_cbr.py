"""
Scraper: Bank of Russia (CBR) — SDDS International Reserves Template

Primary source (physical gold, no USD conversion):
  https://cbr.ru/vfs/eng/statistics/credit_statistics/liquidity_e.xls
  Multi-sheet .xls workbook.  Sheets named "Лист1 (Month, Year)" each
  contain a row "volume in millions of fine troy ounces" with the
  physical gold quantity.  Only the 2 most recent months are present.

Fallback source (USD-denominated, needs gold-price conversion):
  https://cbr.ru/eng/hd_base/mrrf/mrrf_m/
  HTML table with ~13 months of Gold in USD millions.  Used to fill
  historical gaps beyond what the SDDS template provides.

Conversion: millions of fine troy ounces → metric tonnes
            gold_tonnes = value * 1_000_000 / 32_150.7465

IMPORTANT: Set PROXY_URL in .env if the CBR is geo-blocked.
"""

import calendar
import os
import re
import sys
import warnings
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path

import pandas as pd
from bs4 import BeautifulSoup
from dotenv import load_dotenv

try:
    from .base_scraper import BaseScraper, ScraperResult
except ImportError:
    _root = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(_root))
    from scrapers.base_scraper import BaseScraper, ScraperResult

try:
    from utils.gold_price import (
        fetch_gold_prices, get_price_for_date, usd_millions_to_tonnes,
    )
except ImportError:
    _root2 = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(_root2))
    from utils.gold_price import (
        fetch_gold_prices, get_price_for_date, usd_millions_to_tonnes,
    )

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))

SDDS_XLS_URL = (
    "https://cbr.ru/vfs/eng/statistics/credit_statistics/liquidity_e.xls"
)
CBR_HTML_URL = "https://cbr.ru/eng/hd_base/mrrf/mrrf_m/"
PROXY_URL = os.getenv("PROXY_URL", "")
OZ_PER_TONNE = 32_150.7465

MONTH_NAMES = {m.lower(): i for i, m in enumerate(calendar.month_name) if m}


class RussiaCBRScraper(BaseScraper):

    def __init__(self):
        super().__init__()
        if PROXY_URL:
            self.session.proxies.update({
                "http": PROXY_URL,
                "https": PROXY_URL,
            })
            self.session.verify = False
            warnings.filterwarnings(
                "ignore", message="Unverified HTTPS request"
            )

    @property
    def country(self) -> str:
        return "Russia"

    @property
    def source_url(self) -> str:
        return SDDS_XLS_URL

    # ── main entry point ───────────────────────────────────────────

    def fetch(self) -> list[ScraperResult]:
        sdds_results = self._fetch_sdds()
        sdds_dates = {r["report_date"] for r in sdds_results}

        html_results = self._fetch_html_fallback()

        merged: list[ScraperResult] = list(sdds_results)
        for r in html_results:
            if r["report_date"] not in sdds_dates:
                merged.append(r)

        merged.sort(key=lambda x: x["report_date"])
        return merged[-24:]

    # ── SDDS Excel (physical troy ounces) ──────────────────────────

    def _fetch_sdds(self) -> list[ScraperResult]:
        """Parse the SDDS .xls template for physical gold volumes."""
        results: list[ScraperResult] = []
        try:
            resp = self._get(SDDS_XLS_URL)
            dfs = pd.read_excel(
                BytesIO(resp.content), sheet_name=None, header=None
            )
        except Exception as exc:
            print(f"  [RU] SDDS download failed: {exc}")
            return results

        for sheet_name, df in dfs.items():
            try:
                report_date = self._parse_sheet_date(str(sheet_name), df)
                if report_date is None:
                    continue

                gold_mn_oz = self._find_gold_volume(df)
                if gold_mn_oz is None:
                    continue

                gold_tonnes = round(
                    gold_mn_oz * 1_000_000 / OZ_PER_TONNE, 2
                )
                results.append(ScraperResult(
                    country=self.country,
                    gold_tonnes=gold_tonnes,
                    report_date=report_date,
                    source_url=SDDS_XLS_URL,
                ))
            except Exception:
                continue

        if results:
            print(
                f"  [RU] SDDS: {len(results)} month(s) with physical "
                f"gold data"
            )
        return results

    # ── HTML table fallback (USD millions) ─────────────────────────

    def _fetch_html_fallback(self) -> list[ScraperResult]:
        """Parse the CBR monthly reserves HTML table (USD millions)."""
        results: list[ScraperResult] = []
        try:
            gold_prices = fetch_gold_prices()
            if gold_prices:
                latest = max(gold_prices.keys())
                print(
                    f"  [RU] Gold prices loaded: {len(gold_prices)} months, "
                    f"latest {latest} = ${gold_prices[latest]:,.0f}/oz"
                )

            resp = self._get(CBR_HTML_URL)
            soup = BeautifulSoup(resp.text, "html.parser")
            data_points = self._parse_html_table(soup)

            for date_str, gold_usd_mn in data_points:
                price = get_price_for_date(gold_prices, date_str)
                gold_tonnes = usd_millions_to_tonnes(gold_usd_mn, price)
                results.append(ScraperResult(
                    country=self.country,
                    gold_tonnes=gold_tonnes,
                    report_date=date_str,
                    source_url=CBR_HTML_URL,
                ))
        except Exception as exc:
            print(f"  [RU] HTML fallback failed: {exc}")

        return results

    # ── SDDS helpers ───────────────────────────────────────────────

    @staticmethod
    def _parse_sheet_date(
        sheet_name: str, df: pd.DataFrame
    ) -> str | None:
        """Derive YYYY-MM-DD (last day of month) from the sheet name
        or from cell content in the first rows."""
        date = _parse_month_year(sheet_name)
        if date:
            return date

        for row_idx in range(min(15, len(df))):
            for col_idx in range(min(5, df.shape[1])):
                cell = df.iat[row_idx, col_idx]
                if pd.isna(cell):
                    continue
                if isinstance(cell, datetime):
                    return cell.strftime("%Y-%m-%d")
                date = _parse_month_year(str(cell))
                if date:
                    return date

        return None

    @staticmethod
    def _find_gold_volume(df: pd.DataFrame) -> float | None:
        """Find 'volume in millions of fine troy ounces' and return
        the numeric value from the same row."""
        target = "volume in millions of fine troy ounces"

        for row_idx in range(len(df)):
            for col_idx in range(df.shape[1]):
                cell = df.iat[row_idx, col_idx]
                if pd.isna(cell):
                    continue
                if target in str(cell).lower():
                    for c in range(df.shape[1]):
                        val = df.iat[row_idx, c]
                        if pd.notna(val) and _is_number(val):
                            return float(val)
                    return None

        return None

    # ── HTML helpers ───────────────────────────────────────────────

    @staticmethod
    def _parse_html_table(
        soup: BeautifulSoup,
    ) -> list[tuple[str, float]]:
        table = soup.find("table")
        if table is None:
            raise ValueError("No table found on the CBR reserves page")

        data_points: list[tuple[str, float]] = []
        for row in table.find_all("tr")[1:]:
            cells = row.find_all("td")
            if len(cells) < 7:
                continue
            date_raw = cells[0].get_text(strip=True)
            gold_raw = (
                cells[-1].get_text(strip=True)
                .replace(",", "").replace(" ", "").replace("\xa0", "")
            )
            try:
                gold_val = float(gold_raw)
            except ValueError:
                continue

            report_date = _parse_cbr_date(date_raw)
            data_points.append((report_date, gold_val))

        data_points.sort(key=lambda x: x[0])
        return data_points


# ── module-level helpers ───────────────────────────────────────────

def _parse_month_year(text: str) -> str | None:
    """Parse 'January, 2026' or 'December 2025' → YYYY-MM-DD (last day)."""
    m = re.search(r"([A-Za-z]+)[,\s]+(\d{4})", text)
    if not m:
        return None
    month_str = m.group(1).lower()
    year = int(m.group(2))
    month_num = MONTH_NAMES.get(month_str)
    if month_num is None:
        return None
    last_day = calendar.monthrange(year, month_num)[1]
    return f"{year}-{month_num:02d}-{last_day:02d}"


def _parse_cbr_date(raw: str) -> str:
    for fmt in ("%d.%m.%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw.strip(), fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _is_number(val) -> bool:
    try:
        f = float(val)
        return f != 0
    except (ValueError, TypeError):
        return False


if __name__ == "__main__":
    scraper = RussiaCBRScraper()
    results = scraper.fetch()
    print()
    for r in results:
        src = "SDDS" if "liquidity" in r["source_url"] else "HTML"
        print(
            f"  {r['report_date']}  {r['gold_tonnes']:>8.2f} t  [{src}]"
        )
    print(f"\n  Total: {len(results)} data points")
