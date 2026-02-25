from abc import ABC, abstractmethod
from typing import TypedDict

import requests


class ScraperResult(TypedDict):
    country: str
    gold_tonnes: float
    report_date: str        # YYYY-MM-DD
    source_url: str


class BaseScraper(ABC):
    """Every country scraper must subclass this and implement fetch().

    fetch() returns a **list** of ScraperResult dicts sorted
    chronologically (oldest → newest).  For the daily monitor,
    main.py takes results[-1].  For backfills, the full list is
    recorded via bulk_record_data().
    """

    HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "en-US,en;q=0.9",
    }

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(self.HEADERS)

    @property
    @abstractmethod
    def country(self) -> str:
        """Human-readable country name, e.g. 'India'."""

    @property
    @abstractmethod
    def source_url(self) -> str:
        """Primary URL this scraper hits."""

    @abstractmethod
    def fetch(self) -> list[ScraperResult]:
        """Scrape the source and return a chronologically sorted list.

        Each entry:
            {
                "country": str,
                "gold_tonnes": float,
                "report_date": "YYYY-MM-DD",
                "source_url": str,
            }
        """

    def _get(self, url: str | None = None, **kwargs) -> requests.Response:
        target = url or self.source_url
        resp = self.session.get(target, timeout=30, **kwargs)
        resp.raise_for_status()
        return resp
