"""
wgc_scraper.py
==============
Playwright-based scraper that downloads the World Gold Council (WGC)
Central Bank gold-reserve data from Goldhub by iterating through the
quarterly snapshots and scraping the rendered table.

The dashboard at gold.org/goldhub/data/gold-reserves-by-country provides
a <select> dropdown with quarters from Q1 2000 to the latest.  This
script selects each quarter, clicks "Show more countries", and extracts
the table (Country, Gold Reserves Tonnes) from the DOM.  No login is
needed for this read-only table data.

Usage
-----
    python wgc_scraper.py            # headless (default)
    python wgc_scraper.py --headed   # visible browser for debugging

Output:  data/wgc_reserves.csv   (Date, Country, Tonnes)
"""

import argparse
import asyncio
import pathlib
import re

import pandas as pd
from playwright.async_api import (
    async_playwright,
    Page,
    TimeoutError as PwTimeout,
)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
RESERVES_URL = "https://www.gold.org/goldhub/data/gold-reserves-by-country"

HERE = pathlib.Path(__file__).resolve().parent
OUTPUT_DIR = HERE / "data"
OUTPUT_CSV = OUTPUT_DIR / "wgc_reserves.csv"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
QUARTER_TO_MONTH = {"Q1": "03", "Q2": "06", "Q3": "09", "Q4": "12"}


def _quarter_to_date(q_label: str) -> str:
    """Convert 'Q4 2025' to '2025-12'."""
    parts = q_label.strip().split()
    if len(parts) == 2:
        quarter, year = parts
        month = QUARTER_TO_MONTH.get(quarter, "12")
        return f"{year}-{month}"
    return q_label


def _clean_number(text: str) -> float | None:
    """Parse '2,306.30' or '2306.3' into a float, return None on failure."""
    text = text.strip().replace(",", "").replace(" ", "")
    if not text or text == "-" or text.lower() == "n/a":
        return None
    try:
        return float(text)
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Main scraping logic
# ---------------------------------------------------------------------------
async def _scrape_all_quarters(page: Page) -> pd.DataFrame:
    """
    For each quarter available in the <select>, pick it, expand the table,
    and extract (Country, Gold Reserves Tonnes).
    """

    # ── 1. Get the list of available quarter options ──────────────────────
    #    The first <select> on the page is the quarter picker.
    quarter_select = page.locator("select.custom-select").first
    options = await quarter_select.evaluate(
        """sel => [...sel.options].map(o => ({value: o.value, text: o.text.trim()}))"""
    )
    print(f"[*] Found {len(options)} quarter options: "
          f"{options[0]['text']} ... {options[-1]['text']}")

    all_rows: list[dict] = []

    for i, opt in enumerate(options):
        q_label = opt["text"]            # e.g. "Q4 2025"
        q_value = opt["value"]
        date_str = _quarter_to_date(q_label)

        # Select the quarter in the dropdown
        await quarter_select.select_option(value=q_value)
        # Wait for the dashboard to re-render
        await page.wait_for_timeout(2500)

        # Click "Show more countries" if it exists
        try:
            more_btn = page.locator('button:has-text("Show more countries")').first
            if await more_btn.is_visible():
                await more_btn.click()
                await page.wait_for_timeout(1500)
        except Exception:
            pass

        # Extract table rows
        rows = await page.evaluate("""() => {
            const result = [];
            const trs = document.querySelectorAll('table tbody tr');
            trs.forEach(tr => {
                const cells = tr.querySelectorAll('td');
                if (cells.length >= 6) {
                    result.push({
                        country: cells[0].textContent.trim(),
                        tonnes:  cells[5].textContent.trim(),
                    });
                }
            });
            return result;
        }""")

        for row in rows:
            tonnes = _clean_number(row["tonnes"])
            if tonnes is not None:
                all_rows.append({
                    "Date": date_str,
                    "Country": row["country"],
                    "Tonnes": tonnes,
                })

        pct = (i + 1) / len(options) * 100
        print(f"    [{i+1}/{len(options)}] {q_label} ({date_str}): "
              f"{len(rows)} countries  ({pct:.0f}%)")

    return pd.DataFrame(all_rows)


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------
async def scrape(headless: bool = True) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=headless)
        context = await browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
        )
        page = await context.new_page()
        page.set_default_timeout(30_000)

        # ── 1. Navigate ──────────────────────────────────────────────────
        print(f"[*] Loading {RESERVES_URL} ...")
        try:
            await page.goto(RESERVES_URL, wait_until="domcontentloaded",
                            timeout=60_000)
        except PwTimeout:
            print("[!] Page load timed out, continuing ...")

        await page.wait_for_timeout(10_000)
        print(f"[*] Page title: {await page.title()}")

        # ── 2. Dismiss cookie banners ────────────────────────────────────
        for sel in [
            "#truste-consent-button",
            "#onetrust-accept-btn-handler",
            'button:has-text("Accept All")',
            'button:has-text("Accept")',
        ]:
            try:
                btn = page.locator(sel).first
                if await btn.is_visible():
                    await btn.click(force=True)
                    await page.wait_for_timeout(1000)
                    print("[*] Dismissed cookie banner.")
                    break
            except Exception:
                continue

        # ── 3. Make sure we're on the Snapshot tab (default) ─────────────
        #    The Snapshot tab shows a single-quarter table we can iterate.
        await page.screenshot(
            path=str(OUTPUT_DIR / "debug_reserves_page.png"), full_page=True
        )

        # ── 4. Scrape all quarters ───────────────────────────────────────
        print("[*] Scraping quarterly data ...")
        df = await _scrape_all_quarters(page)

        # ── 5. Save ─────────────────────────────────────────────────────
        if not df.empty:
            df.to_csv(OUTPUT_CSV, index=False)
            n_countries = df["Country"].nunique()
            n_quarters = df["Date"].nunique()
            print(f"\n[+] SUCCESS: {len(df)} rows, "
                  f"{n_countries} countries, {n_quarters} quarters")
            print(f"[+] Saved to {OUTPUT_CSV}")
        else:
            print("\n[!] FAILED: no data scraped.")

        await page.screenshot(
            path=str(OUTPUT_DIR / "debug_final.png"), full_page=True
        )
        await browser.close()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(
        description="Scrape WGC gold-reserve data via Playwright."
    )
    parser.add_argument(
        "--headed", action="store_true",
        help="Show the browser window for debugging.",
    )
    args = parser.parse_args()
    asyncio.run(scrape(headless=not args.headed))


if __name__ == "__main__":
    main()
