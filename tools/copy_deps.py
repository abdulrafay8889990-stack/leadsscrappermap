"""Copy the app's runtime packages (and everything they depend on) into a portable site-packages.

Usage: python tools/copy_deps.py <destination site-packages folder>
"""
from __future__ import annotations

import importlib.metadata as md
import re
import shutil
import sys
from pathlib import Path

ROOTS = ["customtkinter", "playwright", "pandas", "openpyxl"]


def dependency_closure(roots: list[str]) -> dict[str, md.Distribution]:
    found: dict[str, md.Distribution] = {}
    stack = list(roots)
    while stack:
        name = stack.pop()
        try:
            dist = md.distribution(name)
        except md.PackageNotFoundError:
            continue
        key = dist.metadata["Name"].lower()
        if key in found:
            continue
        found[key] = dist
        for requirement in dist.requires or []:
            marker = requirement.split(";", 1)[1] if ";" in requirement else ""
            if "extra ==" in marker or "darwin" in marker:
                continue
            if "platform_system" in marker and "Windows" not in marker and "!=" not in marker:
                continue
            stack.append(re.split(r"[ ;<>=!~\[(]", requirement, maxsplit=1)[0])
    return found


def main() -> None:
    destination = Path(sys.argv[1])
    destination.mkdir(parents=True, exist_ok=True)
    ignore = shutil.ignore_patterns("__pycache__", "*.pyc", "tests")  # test suites aren't needed to run
    for key, dist in sorted(dependency_closure(ROOTS).items()):
        site = Path(dist.locate_file(""))
        tops = {str(f).split("/")[0] for f in dist.files or [] if not str(f).startswith("..")}
        for top in sorted(tops - {"__pycache__"}):
            source = site / top
            target = destination / top
            if source.is_dir():
                shutil.copytree(source, target, ignore=ignore, dirs_exist_ok=True)
            elif source.is_file():
                shutil.copy2(source, target)
        print(f"   {key}")


if __name__ == "__main__":
    main()
