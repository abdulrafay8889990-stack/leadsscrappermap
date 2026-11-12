"""City picker: choose a country, tick its cities, add them to the Locations box.

The window stays open after "Add", so several countries can be added one after another.
"""
from __future__ import annotations

from typing import Callable

import customtkinter as ctk

from core.locations import CITY_AREAS, COUNTRIES, location_lines
from gui import theme as th


class CityPicker(ctk.CTkToplevel):
    def __init__(self, master, on_add: Callable[[list[str], bool], int]) -> None:
        super().__init__(master, fg_color=th.BG)
        self.on_add = on_add
        self.title("Add cities")
        self.geometry("560x660")
        self.minsize(480, 560)
        self.transient(master)
        self.checks: dict[str, ctk.CTkCheckBox] = {}

        card = th.Node(self, "Cities", dot=th.YELLOW, badge="30 countries", badge_color=th.YELLOW,
                       badge_bg=th.YELLOW_BG)
        card.pack(fill="both", expand=True, padx=16, pady=16)
        body = card.body
        body.grid_rowconfigure(3, weight=1)

        th.label(body, "Country").grid(row=0, column=0, sticky="w", padx=14, pady=(14, 4))
        top = ctk.CTkFrame(body, fg_color="transparent")
        top.grid(row=1, column=0, sticky="ew", padx=14)
        top.grid_columnconfigure(0, weight=1)
        self.country_menu = ctk.CTkOptionMenu(top, values=sorted(COUNTRIES), command=self._show_country, height=32,
                                              font=th.font(12))
        self.country_menu.set("Pakistan")
        self.country_menu.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self.search = ctk.CTkEntry(top, placeholder_text="Filter cities…", height=32, width=150, font=th.font(12))
        self.search.grid(row=0, column=1)
        self.search.bind("<KeyRelease>", lambda _e: self._apply_filter())

        bar = ctk.CTkFrame(body, fg_color="transparent")
        bar.grid(row=2, column=0, sticky="ew", padx=14, pady=(10, 6))
        th.pill(bar, "Select all", "check", command=lambda: self._select(True), height=28, size=11).pack(side="left")
        th.pill(bar, "Clear", "clear", command=lambda: self._select(False), height=28, size=11).pack(
            side="left", padx=6)
        self.count_label = th.label(bar, "", size=11, color=th.FAINT)
        self.count_label.pack(side="right")

        self.city_frame = ctk.CTkScrollableFrame(body, fg_color=th.INPUT, corner_radius=12)
        self.city_frame.grid(row=3, column=0, sticky="nsew", padx=10)
        self.city_frame.grid_columnconfigure((0, 1), weight=1)

        self.areas_switch = ctk.CTkSwitch(body, text="Split big cities into areas (many more leads)",
                                          font=th.font(12), command=self._update_count)
        self.areas_switch.select()
        self.areas_switch.grid(row=4, column=0, sticky="w", padx=14, pady=(12, 0))
        th.label(body, "Cities marked ◆ have areas, e.g. Karachi → Clifton, DHA, Gulshan…", size=10,
                 color=th.FAINT).grid(row=5, column=0, sticky="w", padx=14, pady=(2, 8))

        actions = ctk.CTkFrame(body, fg_color="transparent")
        actions.grid(row=6, column=0, sticky="ew", padx=14, pady=(4, 14))
        self.result_label = th.label(actions, "", size=11, color=th.GREEN)
        self.result_label.pack(side="left")
        th.pill(actions, "Done", command=self.destroy, height=34, size=12).pack(side="right")
        th.pill(actions, "Add to list", "add", kind="primary", command=lambda: self._add(False), height=34,
                size=12).pack(side="right", padx=6)
        th.pill(actions, "Replace list", "refresh", command=lambda: self._add(True), height=34, size=12).pack(
            side="right")

        self._show_country("Pakistan")
        self.after(150, self._bring_to_front)

    def _bring_to_front(self) -> None:
        self.lift()
        self.focus_force()

    # ------------------------------------------------------------ cities
    def _show_country(self, country: str) -> None:
        for check in self.checks.values():
            check.destroy()
        self.checks = {}
        for index, city in enumerate(COUNTRIES[country]):
            text = f"{city}  ◆" if city in CITY_AREAS else city
            check = ctk.CTkCheckBox(self.city_frame, text=text, font=th.font(12), checkbox_width=18,
                                    checkbox_height=18, command=self._update_count)
            check.grid(row=index // 2, column=index % 2, sticky="w", padx=10, pady=5)
            self.checks[city] = check
        self.result_label.configure(text="")
        self._apply_filter()

    def _apply_filter(self) -> None:
        text = self.search.get().strip().lower()
        for index, (city, check) in enumerate(self.checks.items()):
            if text in city.lower():
                check.grid()
            else:
                check.grid_remove()
        self._update_count()

    def _select(self, on: bool) -> None:
        for check in self.checks.values():
            if check.winfo_ismapped() or not on:
                check.select() if on else check.deselect()
        self._update_count()

    def _selected(self) -> list[str]:
        return [city for city, check in self.checks.items() if check.get()]

    def _lines(self) -> list[str]:
        return location_lines(self.country_menu.get(), self._selected(), bool(self.areas_switch.get()))

    def _update_count(self) -> None:
        cities, lines = self._selected(), self._lines()
        self.count_label.configure(text=f"{len(cities)} cities → {len(lines)} locations" if cities else "")

    def _add(self, replace: bool) -> None:
        lines = self._lines()
        if not lines:
            self.result_label.configure(text="Tick at least one city.", text_color=th.ORANGE)
            return
        total = self.on_add(lines, replace)
        self.result_label.configure(text=f"✔ {len(lines)} added · {total} locations in list", text_color=th.GREEN)
        self._select(False)
