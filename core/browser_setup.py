"""Download Playwright's Chromium on first use, so the installed app works on any PC.

The browser lives in %LOCALAPPDATA%\\ms-playwright (Playwright's default), shared by every
Playwright app; it is ~150 MB and only downloaded once.
"""
from __future__ import annotations

import subprocess
import sys
from typing import Callable

MISSING_BROWSER_MARKERS = ("Executable doesn't exist", "playwright install")


def browser_missing(exc: BaseException) -> bool:
    return any(marker in str(exc) for marker in MISSING_BROWSER_MARKERS)


def install_chromium(log: Callable[[str], None] = print, timeout: int = 900) -> bool:
    """Run Playwright's bundled driver: `install chromium`. Returns True on success."""
    from playwright._impl._driver import compute_driver_executable, get_driver_env

    node, cli = compute_driver_executable()
    flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0  # no console window flashing
    log("Downloading the Chromium browser (first run only, about 150 MB). This can take a few minutes...")
    try:
        result = subprocess.run([node, cli, "install", "chromium"], env=get_driver_env(), capture_output=True,
                                text=True, timeout=timeout, creationflags=flags)
    except (OSError, subprocess.TimeoutExpired) as exc:
        log(f"Browser download failed: {exc}")
        return False
    if result.returncode != 0:
        log("Browser download failed: " + (result.stderr or result.stdout).strip()[-400:])
        return False
    log("Chromium is installed.")
    return True
