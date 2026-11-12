"""Remembers every lead ever collected, so later runs never return the same business again.

Stored as plain text (%LOCALAPPDATA%/Lead Scraper/lead_history.txt), one entry per line:
    lead:<normalized name>|<phone or address>
    place:<Google Maps place id>      (lets the Maps scraper skip a place without opening it)
"""
from __future__ import annotations

import re
import threading
from pathlib import Path

from core import paths
from core.models import Lead

HISTORY_PATH = paths.HISTORY_PATH

# Maps place URLs contain the place id as "!1s0x<hex>:0x<hex>".
_PLACE_ID_RE = re.compile(r"!1s(0x[0-9a-f]+:0x[0-9a-f]+)", re.I)


def place_id(url: str) -> str:
    match = _PLACE_ID_RE.search(url or "")
    return match.group(1).lower() if match else ""


class LeadHistory:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or HISTORY_PATH
        path = self.path
        self._entries: set[str] = set()
        self._lock = threading.Lock()
        try:
            with open(path, encoding="utf-8") as handle:
                self._entries.update(line.rstrip("\n") for line in handle if line.strip())
        except OSError:
            pass  # no history yet

    @staticmethod
    def _entries_for(lead: Lead) -> list[str]:
        entries = ["lead:" + "|".join(lead.key())]
        pid = place_id(lead.listing_url)
        if pid:
            entries.append("place:" + pid)
        return entries

    def has_lead(self, lead: Lead) -> bool:
        return any(entry in self._entries for entry in self._entries_for(lead))

    def has_place(self, url: str) -> bool:
        pid = place_id(url)
        return bool(pid) and f"place:{pid}" in self._entries

    def add(self, lead: Lead) -> None:
        """Remember a lead immediately (appended to disk, so a crash loses nothing)."""
        new = [entry for entry in self._entries_for(lead) if entry not in self._entries]
        if not new:
            return
        with self._lock:
            self._entries.update(new)
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                with open(self.path, "a", encoding="utf-8") as handle:
                    handle.write("\n".join(new) + "\n")
            except OSError:
                pass  # history is a convenience; never break a run over it

    @property
    def lead_count(self) -> int:
        return sum(1 for entry in self._entries if entry.startswith("lead:"))

    @staticmethod
    def reset(path: Path | None = None) -> None:
        (path or HISTORY_PATH).unlink(missing_ok=True)
