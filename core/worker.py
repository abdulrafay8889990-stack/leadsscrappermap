"""Background thread that runs the Google Maps scraper inside its own asyncio event loop.

The worker never touches Tk widgets. It only pushes ``(event_type, payload)`` tuples
onto a ``queue.Queue`` that the GUI drains on its own thread:

    ("log",      (level, message))   level is "info" | "success" | "warning" | "error" | "skip"
    ("status",   message)            short text for the status label
    ("lead",     Lead)               a newly scraped, de-duplicated lead
    ("progress", (count, total))     leads collected so far vs. the requested maximum
    ("skipped",  count)              listings dropped by the filters so far
    ("error",    message)            fatal error; the run is ending
    ("done",     count)              always the last event of a run
"""
from __future__ import annotations

import asyncio
import logging
import queue
import threading
from typing import Any

from core.browser_setup import browser_missing, install_chromium
from scrapers import MapsScraper

log = logging.getLogger(__name__)


class ScraperWorker(threading.Thread):
    def __init__(
        self,
        keywords: list[str],
        locations: list[str],
        max_results: int,
        headless: bool,
        events: queue.Queue,
        options: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(daemon=True, name="ScraperWorker")
        self.keywords = keywords
        self.locations = locations
        self.max_results = max_results
        self.headless = headless
        self.options = options or {}
        self.events = events
        self.stop_event = threading.Event()

    def emit(self, event_type: str, payload: Any = None) -> None:
        self.events.put((event_type, payload))

    def stop(self) -> None:
        """Ask the scraper to finish its current step and shut the browser down."""
        self.stop_event.set()

    def _new_scraper(self) -> MapsScraper:
        return MapsScraper(keywords=self.keywords, locations=self.locations, max_results=self.max_results,
                           headless=self.headless, stop_event=self.stop_event, emit=self.emit, options=self.options)

    def run(self) -> None:
        collected = 0
        scraper = None
        try:
            scraper = self._new_scraper()
            try:
                # asyncio.run creates a fresh event loop owned by this thread.
                leads = asyncio.run(scraper.run())
            except Exception as exc:  # noqa: BLE001 - only the "browser not installed" case is handled here
                if not browser_missing(exc):
                    raise
                # First run on this PC: download Chromium once, then start again.
                if not install_chromium(lambda message: self.emit("log", ("warning", message))):
                    raise
                scraper = self._new_scraper()
                leads = asyncio.run(scraper.run())
            collected = len(leads)
        except Exception as exc:  # noqa: BLE001 - surface anything to the GUI instead of dying silently
            log.exception("Scraper crashed")
            collected = len(scraper.leads) if scraper else 0
            self.emit("error", self._friendly_error(exc))
        finally:
            self.emit("done", collected)

    @staticmethod
    def _friendly_error(exc: Exception) -> str:
        message = str(exc).strip().splitlines()[0] if str(exc).strip() else type(exc).__name__
        if browser_missing(exc):
            return "The Chromium browser could not be downloaded. Check your internet connection and try again."
        return f"{type(exc).__name__}: {message}"
