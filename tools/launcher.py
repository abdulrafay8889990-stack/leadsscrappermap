"""Copied into the portable app as app/sitecustomize.py.

"Lead Scraper.exe" is Python's own pythonw.exe (signed by the Python Software Foundation, so
Windows Smart App Control lets it run), renamed. Python imports `sitecustomize` while it starts
up; when the running program is "Lead Scraper.exe", this file starts the app and exits, so
double-clicking the .exe opens Lead Scraper. Arguments are passed on (e.g. "smoke").
"""
import os
import sys

if os.path.splitext(os.path.basename(sys.executable))[0].lower() == "lead scraper":
    _app_dir = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, _app_dir)
    sys.argv = [os.path.join(_app_dir, "main.py"), *getattr(sys, "orig_argv", [])[1:]]
    _code = 0
    try:
        import runpy

        runpy.run_path(sys.argv[0], run_name="__main__")
    except SystemExit as _exit:
        _code = _exit.code if isinstance(_exit.code, int) else 0
    except BaseException:  # noqa: BLE001 - no console: write the crash where it can be found
        import traceback

        _log_dir = os.path.join(os.environ.get("LOCALAPPDATA", _app_dir), "Lead Scraper")
        os.makedirs(_log_dir, exist_ok=True)
        with open(os.path.join(_log_dir, "startup_error.log"), "a", encoding="utf-8") as _log:
            traceback.print_exc(file=_log)
        _code = 1
    # Leave now, before Python would try to run "main.py"/arguments as an interactive session.
    os._exit(_code)
