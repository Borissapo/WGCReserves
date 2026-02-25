"""
Scraper: Central Bank of Uzbekistan (CBU) — International Reserves

Listing page:
    https://cbu.uz/en/statistics/intlreserves/
    Filtered by arFilter_ff[SECTION_ID]=3500 (reserves data).

Each listing entry links to a detail page that contains a downloadable
XLSX spreadsheet following the IMF International Reserves template.

Row 17 (1-based) of each spreadsheet contains:
    "Volume in millions of fine troy ounces"
which is the physical gold reserves figure.  Columns are monthly
observations spanning roughly two calendar years per file.

Strategy:
    1. Scrape the listing page for detail-page URLs.
    2. Visit a sample of detail pages (spread across years) to collect
       unique XLSX download links.
    3. Download each XLSX and parse the gold-ounces row.
    4. Convert millions of troy ounces -> metric tonnes.
    5. Deduplicate by report_date and return sorted.
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

BASE_URL = "https://cbu.uz"
INDEX_URL = (
    "https://cbu.uz/en/statistics/intlreserves/"
    "?arFilter_DATE_ACTIVE_FROM_1="
    "&arFilter_DATE_ACTIVE_FROM_2="
    "&arFilter_ff%5BSECTION_ID%5D=3500"
    "&set_filter=Y"
)
OZ_PER_TONNE = 32_150.7466
# 1-based row in the IMF template that holds the gold troy-ounce volume
GOLD_ROW_LABEL_HINT = "fine troy ounces"


class UzbekistanCBUScraper(BaseScraper):

    @property
    def country(self) -> str:
        return "Uzbekistan"

    @property
    def source_url(self) -> str:
        return INDEX_URL

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def fetch(self) -> list[ScraperResult]:
        # 1. Listing page -> detail-page URLs
        detail_urls = self._get_detail_urls()
        if not detail_urls:
            raise ValueError(
                "No detail-page links found on the CBU reserves listing"
            )
        print(f"  [UZ] Found {len(detail_urls)} detail pages on listing")

        # 2. Visit a sample of detail pages -> unique XLSX URLs
        xlsx_urls = self._collect_xlsx_urls(detail_urls)
        if not xlsx_urls:
            raise ValueError(
                "No XLSX download links found on CBU detail pages"
            )
        print(f"  [UZ] Collected {len(xlsx_urls)} unique XLSX files")

        # 3. Download & parse each XLSX
        results: list[ScraperResult] = []
        seen_dates: set[str] = set()

        for xlsx_url in xlsx_urls:
            try:
                resp = self._get(xlsx_url)
                parsed = self._parse_xlsx(resp.content, xlsx_url)
                for entry in parsed:
                    if entry["report_date"] not in seen_dates:
                        results.append(entry)
                        seen_dates.add(entry["report_date"])
            except Exception as exc:
                print(f"  [UZ] Skipping {xlsx_url}: {exc}")
                continue

        results.sort(key=lambda x: x["report_date"])
        print(f"  [UZ] Total data points: {len(results)}")
        return results

    # ------------------------------------------------------------------
    # Step 1: listing page -> detail URLs
    # ------------------------------------------------------------------

    def _get_detail_urls(self) -> list[str]:
        """Fetch the listing page and extract all detail-page URLs."""
        resp = self._get(INDEX_URL)
        soup = BeautifulSoup(resp.text, "html.parser")

        urls: list[str] = []
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if re.match(r"/en/statistics/intlreserves/\d+/?$", href):
                full_url = BASE_URL + href.rstrip("/") + "/"
                if full_url not in urls:
                    urls.append(full_url)
        return urls

    # ------------------------------------------------------------------
    # Step 2: detail pages -> unique XLSX download links
    # ------------------------------------------------------------------

    def _collect_xlsx_urls(self, detail_urls: list[str]) -> list[str]:
        """Visit a sample of detail pages and collect unique XLSX links.

        Each XLSX is named like ``Reserves_IMF_eng-YYYY.xlsx`` and covers
        about two calendar years, so visiting one page per year-range is
        enough to capture all files.
        """
        sampled = self._sample_urls(detail_urls)
        xlsx_urls: list[str] = []

        for url in sampled:
            try:
                resp = self._get(url)
                soup = BeautifulSoup(resp.text, "html.parser")
                for a in soup.find_all("a", href=True):
                    href = a["href"]
                    if href.lower().endswith((".xls", ".xlsx")):
                        full = (
                            href
                            if href.startswith("http")
                            else BASE_URL + href
                        )
                        if full not in xlsx_urls:
                            xlsx_urls.append(full)
            except Exception:
                continue

        return xlsx_urls

    @staticmethod
    def _sample_urls(detail_urls: list[str]) -> list[str]:
        """Pick a spread of detail-page URLs to cover all years.

        Releases are ~monthly, so every 12th URL roughly covers a new
        annual XLSX.  We always include the latest (index 0).
        """
        if not detail_urls:
            return []

        sampled: list[str] = [detail_urls[0]]
        for i in range(12, len(detail_urls), 12):
            if detail_urls[i] not in sampled:
                sampled.append(detail_urls[i])

        # Also include the very last (oldest) to catch the earliest file
        if detail_urls[-1] not in sampled:
            sampled.append(detail_urls[-1])

        return sampled

    # ------------------------------------------------------------------
    # Step 3: parse a single XLSX
    # ------------------------------------------------------------------

    def _parse_xlsx(
        self, content: bytes, url: str
    ) -> list[ScraperResult]:
        """Parse the gold-ounces row from an IMF-template XLSX.

        Returns one ScraperResult per monthly column.
        """
        df = pd.read_excel(BytesIO(content), sheet_name=0, header=None)

        # --- locate the gold row ---
        gold_row_idx = self._find_gold_row(df)
        gold_row = df.iloc[gold_row_idx]

        # --- locate date columns ---
        date_cols = self._find_date_columns(df)
        if not date_cols:
            raise ValueError("No date columns found in XLSX header rows")

        # --- extract values and convert ---
        results: list[ScraperResult] = []
        for col_idx, report_date in date_cols.items():
            try:
                raw = gold_row.iloc[col_idx]
                if pd.isna(raw):
                    continue
                millions_oz = float(str(raw).replace(",", "").strip())
                if millions_oz <= 0:
                    continue
                gold_tonnes = round(
                    millions_oz * 1_000_000 / OZ_PER_TONNE, 2
                )
                results.append(
                    ScraperResult(
                        country=self.country,
                        gold_tonnes=gold_tonnes,
                        report_date=report_date,
                        source_url=url,
                    )
                )
            except (ValueError, TypeError, IndexError):
                continue

        return results

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _find_gold_row(df: pd.DataFrame) -> int:
        """Return the 0-based row index containing gold troy-ounce data.

        Searches for *GOLD_ROW_LABEL_HINT* ("fine troy ounces") in the
        first few columns of every row.  Falls back to row index 16
        (row 17 in 1-based) if the text match fails.
        """
        for idx in range(len(df)):
            row_text = " ".join(
                str(c) for c in df.iloc[idx, :5] if pd.notna(c)
            ).lower()
            if GOLD_ROW_LABEL_HINT in row_text:
                return idx

        # Fallback: user-specified row 17 (1-based)
        if len(df) > 16:
            return 16

        raise ValueError(
            f"Could not locate the gold row ('{GOLD_ROW_LABEL_HINT}') "
            f"in the XLSX"
        )

    @staticmethod
    def _find_date_columns(df: pd.DataFrame) -> dict[int, str]:
        """Scan the first rows for date-like column headers.

        Returns ``{col_index: 'YYYY-MM-DD'}`` for every column whose
        header can be parsed as a date.  Uses the last day implied by
        the month (stored as the 1st for simplicity, matching the
        pattern used elsewhere in this project).
        """
        date_map: dict[int, str] = {}

        for row_idx in range(min(8, len(df))):
            for col_idx in range(df.shape[1]):
                if col_idx in date_map:
                    continue

                cell = df.iat[row_idx, col_idx]
                if pd.isna(cell):
                    continue

                parsed = _try_parse_date(cell)
                if parsed:
                    date_map[col_idx] = parsed

        return date_map


# ------------------------------------------------------------------
# Module-level helpers
# ------------------------------------------------------------------

def _try_parse_date(cell) -> str | None:
    """Try to interpret *cell* as a date and return 'YYYY-MM-DD'."""
    if isinstance(cell, datetime):
        return cell.strftime("%Y-%m-%d")
    if isinstance(cell, pd.Timestamp):
        return cell.to_pydatetime().strftime("%Y-%m-%d")

    raw = str(cell).strip()

    # Common date formats in IMF templates
    for fmt in (
        "%d.%m.%Y",
        "%Y-%m-%d",
        "%m/%d/%Y",
        "%B %Y",        # "January 2024"
        "%b %Y",        # "Jan 2024"
        "%b-%y",        # "Jan-24"
        "%B %d, %Y",
        "%d-%b-%Y",
        "%d-%b-%y",
    ):
        try:
            return datetime.strptime(raw, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue

    return None


if __name__ == "__main__":
    scraper = UzbekistanCBUScraper()
    for r in scraper.fetch():
        print(r)
