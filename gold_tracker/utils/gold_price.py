"""
Shared gold-price helper: fetches monthly close prices from Yahoo Finance
(COMEX gold futures, GC=F) and provides USD-to-tonnes conversion using the
correct price for each reporting period.

Used by any scraper whose source reports gold in USD rather than physical
ounces/tonnes.
"""

from datetime import datetime

import requests

YAHOO_GOLD_URL = "https://query1.finance.yahoo.com/v8/finance/chart/GC=F"
OZ_PER_TONNE = 32_150.7466
_FALLBACK_PRICE = 2_850.0


def fetch_gold_prices(range_years: int = 5) -> dict[str, float]:
    """Fetch monthly gold close prices from Yahoo Finance.

    Returns a dict mapping ``'YYYY-MM'`` to the monthly close price in USD/oz.
    On failure returns an empty dict (callers should handle gracefully).
    """
    prices: dict[str, float] = {}
    try:
        resp = requests.get(
            YAHOO_GOLD_URL,
            params={"range": f"{range_years}y", "interval": "1mo"},
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=20,
        )
        resp.raise_for_status()
        data = resp.json()
        result = data["chart"]["result"][0]
        timestamps = result["timestamp"]
        closes = result["indicators"]["quote"][0]["close"]

        for ts, close in zip(timestamps, closes):
            if close is not None:
                dt = datetime.fromtimestamp(ts)
                prices[dt.strftime("%Y-%m")] = float(close)
    except Exception as exc:
        print(f"  [WARN] Could not fetch gold prices from Yahoo: {exc}")

    return prices


def get_price_for_date(
    gold_prices: dict[str, float], report_date: str
) -> float:
    """Best gold price for *report_date* (``YYYY-MM-DD`` or ``YYYY-MM``).

    Priority: exact month match → nearest available month → fallback constant.
    """
    target_month = report_date[:7]

    if target_month in gold_prices:
        return gold_prices[target_month]

    if gold_prices:
        target_num = int(target_month[:4]) * 12 + int(target_month[5:])
        closest = min(
            gold_prices,
            key=lambda m: abs(
                (int(m[:4]) * 12 + int(m[5:])) - target_num
            ),
        )
        return gold_prices[closest]

    return _FALLBACK_PRICE


def fetch_weekly_gold_prices(range_years: int = 2) -> dict[str, float]:
    """Fetch weekly gold close prices (Friday close) from Yahoo Finance.

    Returns a dict mapping ``'YYYY-MM-DD'`` to the weekly close price in
    USD/oz.  Yahoo's weekly candles close on Friday, so each key is a
    Friday date.  On failure returns an empty dict.
    """
    prices: dict[str, float] = {}
    try:
        resp = requests.get(
            YAHOO_GOLD_URL,
            params={"range": f"{range_years}y", "interval": "1wk"},
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=20,
        )
        resp.raise_for_status()
        data = resp.json()
        result = data["chart"]["result"][0]
        timestamps = result["timestamp"]
        closes = result["indicators"]["quote"][0]["close"]

        for ts, close in zip(timestamps, closes):
            if close is not None:
                dt = datetime.fromtimestamp(ts)
                prices[dt.strftime("%Y-%m-%d")] = float(close)
    except Exception as exc:
        print(f"  [WARN] Could not fetch weekly gold prices from Yahoo: {exc}")

    return prices


def get_weekly_price_for_date(
    weekly_prices: dict[str, float], report_date: str
) -> float:
    """Best weekly gold price for *report_date* (``YYYY-MM-DD``).

    Finds the closest Friday close to the given date.
    Falls back to the monthly fetcher, then to a constant.
    """
    if report_date in weekly_prices:
        return weekly_prices[report_date]

    if weekly_prices:
        from datetime import datetime as _dt
        target = _dt.strptime(report_date[:10], "%Y-%m-%d").toordinal()
        closest = min(
            weekly_prices,
            key=lambda d: abs(
                _dt.strptime(d, "%Y-%m-%d").toordinal() - target
            ),
        )
        return weekly_prices[closest]

    return _FALLBACK_PRICE


def usd_millions_to_tonnes(
    usd_millions: float,
    gold_price_per_oz: float,
) -> float:
    """Convert a USD-millions gold value to metric tonnes."""
    usd_total = usd_millions * 1_000_000
    value_per_tonne = gold_price_per_oz * OZ_PER_TONNE
    return round(usd_total / value_per_tonne, 2)
