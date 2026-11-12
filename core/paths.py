"""Where the app keeps its files (the same whether it runs from source or as the installed .exe).

    %LOCALAPPDATA%\\Lead Scraper\\      app data: lead history, browser profile (cookies), log
    Documents\\Lead Scraper\\           your files: exports (Excel batches) and autosave CSVs
"""
from __future__ import annotations

import ctypes
import os
import shutil
import sys
from pathlib import Path

APP_NAME = "Lead Scraper"
APP_ID = "LeadScraper.Desktop.1"  # Windows AppUserModelID: taskbar groups the app under its own icon


def _documents_dir() -> Path:
    """The real Documents folder, also when OneDrive redirects it."""
    if sys.platform == "win32":
        buffer = ctypes.create_unicode_buffer(260)
        if ctypes.windll.shell32.SHGetFolderPathW(None, 5, None, 0, buffer) == 0:  # CSIDL_PERSONAL
            return Path(buffer.value)
    return Path.home() / "Documents"


DATA_DIR = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local") / APP_NAME
OUTPUT_DIR = _documents_dir() / APP_NAME

HISTORY_PATH = DATA_DIR / "lead_history.txt"
PROFILES_DIR = DATA_DIR / "browser_profiles"
LOG_PATH = DATA_DIR / "scraper.log"
EXPORTS_DIR = OUTPUT_DIR / "exports"
AUTOSAVE_DIR = OUTPUT_DIR / "autosave"

# Files shipped with the app (icon).
ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets"
ICON_PATH = ASSETS_DIR / "app.ico"


def ensure_dirs() -> None:
    for folder in (DATA_DIR, PROFILES_DIR, EXPORTS_DIR, AUTOSAVE_DIR):
        folder.mkdir(parents=True, exist_ok=True)


def migrate_legacy(project_root: Path) -> list[str]:
    """Copy data from the old project-folder layout (data/, browser_profiles/) the first time.

    Only copies, never moves or deletes, and never overwrites data that already exists here.
    Returns what was copied.
    """
    copied = []
    old_history = project_root / "data" / "lead_history.txt"
    if old_history.is_file() and not HISTORY_PATH.exists():
        HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(old_history, HISTORY_PATH)
        copied.append(f"lead history -> {HISTORY_PATH}")
    old_profile = project_root / "browser_profiles" / "google"
    new_profile = PROFILES_DIR / "google"
    if old_profile.is_dir() and not new_profile.exists():
        # Lock/cache files of a profile in use can't be copied; they aren't needed.
        shutil.copytree(old_profile, new_profile, ignore=shutil.ignore_patterns("Singleton*", "*Cache*", "*.lock"),
                        ignore_dangling_symlinks=True, dirs_exist_ok=True)
        copied.append(f"browser profile -> {new_profile}")
    return copied
