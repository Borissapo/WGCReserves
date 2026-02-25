"""
Scraper: Reserve Bank of India — Weekly Statistical Supplement (WSS)

Source page : https://rbi.org.in/Scripts/BS_viewWssExtract.aspx
              URL pattern: ?SelectedDate=M/DD/YYYY  (a Friday)

Target table: Table 2 — Foreign Exchange Reserves
Target row  : 1.2 Gold
Target col  : US$ Mn. ("As on" column)

The page publishes every Thursday/Friday with data "as on" the prior
Friday.  We sample every available Friday for the last 12 months to
build a **weekly** time-series.

Unit note:
  RBI reports gold in Rs. Crores and US$ Millions.
  We use dynamic Yahoo Finance gold prices to convert each period's
  USD value to metric tonnes.
  The RBI marks gold at ~90 % of the LBMA AM fix.
"""

import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from bs4 import BeautifulSoup

try:
    from .base_scraper import BaseScraper, ScraperResult
except ImportError:
    _root = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(_root))
    from scrapers.base_scraper import BaseScraper, ScraperResult

try:
    from utils.gold_price import fetch_weekly_gold_prices, get_weekly_price_for_date
except ImportError:
    _root2 = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(_root2))
    from utils.gold_price import fetch_weekly_gold_prices, get_weekly_price_for_date

WSS_EXTRACT_URL = "https://rbi.org.in/Scripts/BS_viewWssExtract.aspx"
OZ_PER_TONNE = 32_150.7466
RBI_MARKUP = 0.90


class IndiaRBIScraper(BaseScraper):

    @property
    def country(self) -> str:
        return "India"

    @property
    def source_url(self) -> str:
        return WSS_EXTRACT_URL

    @staticmethod
    def usd_millions_to_tonnes(
        usd_millions: float,
        gold_price_per_oz: float,
    ) -> float:
        effective_price = gold_price_per_oz * RBI_MARKUP
        value_per_tonne = effective_price * OZ_PER_TONNE
        return round(usd_millions * 1_000_000 / value_per_tonne, 2)

    def fetch(self) -> list[ScraperResult]:
        weekly_prices = fetch_weekly_gold_prices()
        if weekly_prices:
            latest_date = max(weekly_prices.keys())
            print(
                f"  [IN] Weekly gold prices loaded: {len(weekly_prices)} weeks, "
                f"latest {latest_date} = ${weekly_prices[latest_date]:,.0f}/oz"
            )

        results: list[ScraperResult] = []
        today = datetime.now(timezone.utc)

        for week_offset in range(52):
            days_since_friday = (today.weekday() - 4) % 7
            friday = today - timedelta(days=days_since_friday + 7 * week_offset)

            date_param = f"{friday.month}/{friday.day}/{friday.year}"
            url = f"{WSS_EXTRACT_URL}?SelectedDate={date_param}"

            try:
                resp = self._get(url)
                if "Foreign Exchange Reserves" not in resp.text:
                    continue

                soup = BeautifulSoup(resp.text, "html.parser")
                gold_usd_mn, parsed_date = self._parse_gold_row(soup)
                report_date = parsed_date or friday.strftime("%Y-%m-%d")
                price = get_weekly_price_for_date(weekly_prices, report_date)
                gold_tonnes = self.usd_millions_to_tonnes(gold_usd_mn, price)

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
    def _parse_gold_row(soup: BeautifulSoup) -> tuple[float, str | None]:
        """Find the properly structured '1.2 Gold' <tr> and return
        (gold_usd_millions, report_date_or_None).
        """
        report_date: str | None = None

        page_text = soup.get_text(" ", strip=True)
        date_match = re.search(
            r"As on\s+(\w+\.?\s+\d{1,2},?\s+\d{4})", page_text
        )
        if date_match:
            report_date = _parse_rbi_date(date_match.group(1))

        for row in soup.find_all("tr"):
            cells = row.find_all("td")
            if not (3 <= len(cells) <= 20):
                continue

            label_text = cells[0].get_text(strip=True)
            if not re.search(r"1\.2\s*Gold", label_text):
                continue

            nums = _extract_numbers(cells[1:])
            if len(nums) < 2:
                continue

            usd_mn = nums[1]
            return usd_mn, report_date

        raise ValueError(
            "Could not find a properly structured '1.2 Gold' row "
            "with US$ Mn value >= 1000"
        )


def _extract_numbers(cells) -> list[float]:
    nums: list[float] = []
    for cell in cells:
        raw = cell.get_text(strip=True).replace(",", "").replace(" ", "")
        try:
            nums.append(float(raw))
        except ValueError:
            continue
    return nums


def _parse_rbi_date(text: str) -> str:
    text = text.strip().rstrip(".")
    for fmt in ("%b. %d, %Y", "%b %d, %Y", "%B %d, %Y",
                "%b. %d %Y", "%b %d %Y", "%B %d %Y"):
        try:
            return datetime.strptime(text, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


if __name__ == "__main__":
    scraper = IndiaRBIScraper()
    for r in scraper.fetch():
        print(r)
