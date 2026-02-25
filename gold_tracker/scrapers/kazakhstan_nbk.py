"""
Scraper: National Bank of Kazakhstan (NBK) — International Reserves

Internal JSON API:
  Base : https://nationalbank.kz/en/international-reserve-and-asset/
         mezhdunarodnye-rezervy-i-aktivy-nacionalnogo-fonda-rk
  /records  → JSON array of monthly records (params: year, mount)

Each record contains:
  gold_volume_million_dollar  — gold reserves value in millions of USD
  reporting_date              — end-of-period date

Since the API only provides USD value (no physical ounces), we fetch
monthly gold prices from Yahoo Finance (GC=F) to convert each period's
USD value to metric tonnes accurately.
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

BASE_URL = (
    "https://nationalbank.kz/en/international-reserve-and-asset/"
    "mezhdunarodnye-rezervy-i-aktivy-nacionalnogo-fonda-rk"
)
RECORDS_URL = f"{BASE_URL}/records"


class KazakhstanNBKScraper(BaseScraper):

    @property
    def country(self) -> str:
        return "Kazakhstan"

    @property
    def source_url(self) -> str:
        return BASE_URL

    def fetch(self) -> list[ScraperResult]:
        headers = {
            "Accept": "application/json",
            "X-Requested-With": "XMLHttpRequest",
        }

        gold_prices = fetch_gold_prices()
        if gold_prices:
            latest_month = max(gold_prices.keys())
            print(
                f"  [KZ] Gold prices loaded: {len(gold_prices)} months, "
                f"latest {latest_month} = ${gold_prices[latest_month]:,.0f}/oz"
            )

        now = datetime.now(timezone.utc)
        raw_records: list[dict] = []
        seen_ids: set = set()

        for month_offset in range(24):
            year = now.year
            month = now.month - month_offset
            while month < 1:
                month += 12
                year -= 1

            try:
                resp = self.session.get(
                    RECORDS_URL,
                    params={"year": year, "mount": month},
                    headers=headers,
                    timeout=30,
                )
                resp.raise_for_status()
                data = resp.json()

                if isinstance(data, list):
                    for record in data:
                        rid = record.get("id")
                        if rid not in seen_ids:
                            raw_records.append(record)
                            seen_ids.add(rid)
            except Exception:
                continue

        results: list[ScraperResult] = []
        seen_dates: set[str] = set()

        for record in raw_records:
            result = self._build_result(record, gold_prices)
            if result["report_date"] not in seen_dates:
                results.append(result)
                seen_dates.add(result["report_date"])

        results.sort(key=lambda x: x["report_date"])
        return results

    def _build_result(
        self, record: dict, gold_prices: dict[str, float]
    ) -> ScraperResult:
        raw = record.get("gold_volume_million_dollar")
        if raw is None:
            raise ValueError(
                f"No gold_volume_million_dollar in NBK record: {record}"
            )

        raw_date = record.get("reporting_date", "")
        report_date = self._parse_date(raw_date)

        gold_usd_millions = float(raw)
        price = get_price_for_date(gold_prices, report_date)
        gold_tonnes = usd_millions_to_tonnes(gold_usd_millions, price)

        return ScraperResult(
            country=self.country,
            gold_tonnes=gold_tonnes,
            report_date=report_date,
            source_url=RECORDS_URL,
        )

    @staticmethod
    def _parse_date(raw: str) -> str:
        for fmt in ("%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                return datetime.strptime(raw.strip(), fmt).strftime("%Y-%m-%d")
            except ValueError:
                continue
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")


if __name__ == "__main__":
    scraper = KazakhstanNBKScraper()
    for r in scraper.fetch():
        print(r)
