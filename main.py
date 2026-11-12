"""Entry point: `python main.py` from source, or "Lead Scraper.exe" when installed.

`smoke` (or `--smoke`) runs a tiny headless Google Maps scrape without opening the window and
writes the result to the log (used to check that a freshly built app works end to end).
"""
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from core import paths  # noqa: E402

paths.ensure_dirs()
# Full tracebacks go to the log file; the window shows short messages.
logging.basicConfig(
    filename=paths.LOG_PATH,
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(threadName)s %(name)s: %(message)s",
)


def _set_windows_app_id() -> None:
    """Without this the taskbar groups the window under Python's icon instead of the app's."""
    if sys.platform == "win32":
        try:
            import ctypes

            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(paths.APP_ID)
        except (AttributeError, OSError):
            pass


def smoke_test() -> int:
    """Headless 2-lead scrape; the lead history used here is a throw-away file."""
    import queue

    import core.history as history
    from core.worker import ScraperWorker

    log = logging.getLogger("smoke")
    history.HISTORY_PATH = paths.DATA_DIR / "smoke_history.txt"
    history.HISTORY_PATH.unlink(missing_ok=True)
    events: queue.Queue = queue.Queue()
    worker = ScraperWorker(["cafe"], ["Clifton, Karachi, Pakistan"], 2, True, events,
                           {"website_filter": "all", "require_phone": True, "find_emails": False,
                            "auto_expand": False})
    worker.start()
    leads = []
    while True:
        kind, payload = events.get()
        if kind == "lead":
            leads.append(payload)
            log.info("SMOKE LEAD: %s | %s | %s", payload.name, payload.phone, payload.city)
        elif kind in ("log", "error"):
            log.info("SMOKE %s: %s", kind, payload)
        elif kind == "done":
            break
    history.HISTORY_PATH.unlink(missing_ok=True)
    log.info("SMOKE RESULT: %d lead(s)", len(leads))
    return 0 if leads else 1


def main() -> None:
    # "smoke" without dashes too: "Lead Scraper.exe --smoke" would be read as a Python option.
    if {"--smoke", "smoke"} & set(sys.argv[1:]):
        sys.exit(smoke_test())
    _set_windows_app_id()
    if not getattr(sys, "frozen", False):
        # Running from the project folder: bring over the old data/ and browser_profiles/ once.
        for item in paths.migrate_legacy(ROOT):
            logging.info("Migrated %s", item)
    from gui.app import run

    run()


if __name__ == "__main__":
    main()
