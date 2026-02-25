"""
Scraper: Central Bank of the Republic of Turkey (TCMB) — Reserves

Source page:
  https://www.tcmb.gov.tr/wps/wcm/connect/EN/TCMB+EN/Main+Menu/
  Statistics/Balance+of+Payments+and+Related+Statistics/
  International+Reserves+and+Foreign+Currency+Liquidity

The TCMB publishes:
  1. A ZIP containing an XLSX (URDL_*_ING.xlsx) with the latest monthly
     point + 2 weekly points, including the row
     "Volume in millions of fine troy ounces".
  2. A weekly PDF (RT{YYYYMMDD}ING.pdf) with the same row.

We use:
  - The XLSX in the ZIP for all available dates (up to 3).
  - The PDF for the most recent weekly date (as a fallback / supplement).

Physical gold quantity — no USD conversion needed.
Conversion: millions of fine troy ounces → metric tonnes
            gold_tonnes = value * 1_000_000 / 32_150.7465
"""

import re
import sys
import zipfile
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path

import pandas as pd
import pdfplumber
from bs4 import BeautifulSoup

try:
    from .base_scraper import BaseScraper, ScraperResult
except ImportError:
    _root = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(_root))
    from scrapers.base_scraper import BaseScraper, ScraperResult

RESERVES_PAGE = (
    "https://www.tcmb.gov.tr/wps/wcm/connect/EN/TCMB+EN/Main+Menu/"
    "Statistics/Balance+of+Payments+and+Related+Statistics/"
    "International+Reserves+and+Foreign+Currency+Liquidity"
)
OZ_PER_TONNE = 32_150.7465


class TurkeyTCMBScraper(BaseScraper):

    @property
    def country(self) -> str:
        return "Turkey"

    @property
    def source_url(self) -> str:
        return RESERVES_PAGE

    def fetch(self) -> list[ScraperResult]:
        resp = self._get(RESERVES_PAGE)
        soup = BeautifulSoup(resp.text, "html.parser")

        results: dict[str, ScraperResult] = {}

        zip_url = self._find_link(soup, ".zip")
        if zip_url:
            try:
                xlsx_results = self._parse_zip(zip_url)
                for r in xlsx_results:
                    results[r["report_date"]] = r
            except Exception as exc:
                print(f"  [TR] ZIP/XLSX parse failed: {exc}")

        pdf_url = self._find_link(soup, "ING.pdf")
        if pdf_url:
            try:
                pdf_result = self._parse_pdf(pdf_url)
                if pdf_result["report_date"] not in results:
                    results[pdf_result["report_date"]] = pdf_result
            except Exception as exc:
                print(f"  [TR] PDF parse failed: {exc}")

        out = sorted(results.values(), key=lambda x: x["report_date"])
        return out

    # ------------------------------------------------------------------
    # Link discovery
    # ------------------------------------------------------------------

    def _find_link(self, soup: BeautifulSoup, suffix: str) -> str | None:
        base = "https://www.tcmb.gov.tr"
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if href.lower().endswith(suffix) or suffix in href.lower():
                return href if href.startswith("http") else base + href
        return None

    # ------------------------------------------------------------------
    # XLSX inside ZIP
    # ------------------------------------------------------------------

    def _parse_zip(self, zip_url: str) -> list[ScraperResult]:
        resp = self._get(zip_url)
        z = zipfile.ZipFile(BytesIO(resp.content))
        xlsx_name = next(
            (n for n in z.namelist() if n.lower().endswith(".xlsx")), None
        )
        if not xlsx_name:
            raise ValueError("No .xlsx found inside ZIP")

        df = pd.read_excel(
            BytesIO(z.read(xlsx_name)),
            sheet_name=0, header=None, engine="openpyxl",
        )
        z.close()

        troy_row_idx = None
        for ri in range(len(df)):
            cell = df.iat[ri, 1] if df.shape[1] > 1 else df.iat[ri, 0]
            if pd.notna(cell) and "volume" in str(cell).lower() and "fine" in str(cell).lower():
                troy_row_idx = ri
                break

        if troy_row_idx is None:
            raise ValueError(
                "Could not find 'Volume in millions of fine troy ounces' "
                "row in XLSX"
            )

        header_row_idx = None
        for ri in range(troy_row_idx):
            for ci in range(df.shape[1]):
                cell = df.iat[ri, ci]
                if pd.notna(cell) and isinstance(cell, datetime):
                    header_row_idx = ri
                    break
                if pd.notna(cell) and re.match(
                    r"(January|February|March|April|May|June|July|August|"
                    r"September|October|November|December)\s+\d{4}",
                    str(cell).strip(),
                ):
                    header_row_idx = ri
                    break
            if header_row_idx is not None:
                break

        if header_row_idx is None:
            raise ValueError("Could not find date header row in XLSX")

        results: list[ScraperResult] = []
        for ci in range(2, df.shape[1]):
            header = df.iat[header_row_idx, ci]
            value = df.iat[troy_row_idx, ci]

            if pd.isna(header) or pd.isna(value):
                continue

            report_date = self._parse_header_date(header)
            gold_mn_oz = float(value)
            gold_tonnes = round(gold_mn_oz * 1_000_000 / OZ_PER_TONNE, 2)

            results.append(ScraperResult(
                country=self.country,
                gold_tonnes=gold_tonnes,
                report_date=report_date,
                source_url=zip_url,
            ))

        return results

    @staticmethod
    def _parse_header_date(header) -> str:
        if isinstance(header, datetime):
            return header.strftime("%Y-%m-%d")

        text = str(header).strip()
        for fmt in ("%B %Y", "%b %Y", "%d.%m.%Y", "%Y-%m-%d"):
            try:
                dt = datetime.strptime(text, fmt)
                if dt.day == 1 and "%d" not in fmt:
                    import calendar
                    dt = dt.replace(day=calendar.monthrange(dt.year, dt.month)[1])
                return dt.strftime("%Y-%m-%d")
            except ValueError:
                continue

        return datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # ------------------------------------------------------------------
    # PDF (weekly RT*ING.pdf)
    # ------------------------------------------------------------------

    def _parse_pdf(self, pdf_url: str) -> ScraperResult:
        resp = self._get(pdf_url)
        pdf = pdfplumber.open(BytesIO(resp.content))
        tables = pdf.pages[0].extract_tables()
        if not tables:
            raise ValueError("No tables in weekly PDF")

        tbl = tables[0]

        report_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if tbl and tbl[0]:
            for cell in reversed(tbl[0]):
                if cell and re.match(r"\d{2}\.\d{2}\.\d{4}", cell.strip()):
                    report_date = datetime.strptime(
                        cell.strip(), "%d.%m.%Y"
                    ).strftime("%Y-%m-%d")
                    break

        for row in tbl:
            row_text = " ".join(str(c or "") for c in row).lower()
            if "volume" in row_text and "fine troy" in row_text:
                raw = _last_numeric(row)
                if raw is not None:
                    gold_tonnes = round(
                        raw * 1_000_000 / OZ_PER_TONNE, 2
                    )
                    pdf.close()
                    return ScraperResult(
                        country=self.country,
                        gold_tonnes=gold_tonnes,
                        report_date=report_date,
                        source_url=pdf_url,
                    )

        pdf.close()
        raise ValueError(
            "Could not find 'volume in millions of fine troy ounces' in PDF"
        )


def _last_numeric(row: list) -> float | None:
    for cell in reversed(row):
        if cell is None:
            continue
        raw = str(cell).strip()
        if not raw:
            continue
        raw = raw.replace(",", ".")
        try:
            return float(raw)
        except ValueError:
            continue
    return None


if __name__ == "__main__":
    scraper = TurkeyTCMBScraper()
    for r in scraper.fetch():
        print(r)
