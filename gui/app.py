"""Main window: classic desktop layout.

    ┌ sidebar ──────────┬ main ───────────────────────────────────────────┐
    │ logo + title      │ stat cards (leads, email, no website, ...)      │
    │ Search            │ progress + live status                          │
    │ Filters           │ toolbar: search · quick filter · export ...     │
    │ Emails            │ results table                                   │
    │ Output / Advanced │                                                 │
    │ [ Start Scraping ]│ live log (collapsible)                          │
    └───────────────────┴─────────────────────────────────────────────────┘

All scraping happens in core.worker.ScraperWorker (a background thread). This window
only reads that worker's event queue every 100 ms via `after()`, so the UI never blocks.
"""
from __future__ import annotations

import datetime as dt
import os
import queue
import re
import time
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk

from core import paths
from core.exporter import export_leads
from core.history import LeadHistory
from core.models import COLUMN_TITLES, WEBSITE_NONE, WEBSITE_SOCIAL, Lead
from core.worker import ScraperWorker
from gui import theme as th
from gui.city_picker import CityPicker

POLL_MS = 100
MAX_EVENTS_PER_POLL = 300
MAX_LEADS = 50000
MAX_LOG_LINES = 3000  # older log lines are trimmed so long runs stay fast
AUTOSAVE_EVERY = 100  # every 500 once a run passes 5,000 leads (saving 50k rows often would slow the app)
DEFAULT_MAX_LEADS = 50000
DEFAULT_BATCH_SIZE = 10000  # leads per file written during a run
VIEW_LIMIT = 5000  # rows drawn in the table at once (exports always contain everything)
AUTOSAVE_DIR = paths.AUTOSAVE_DIR
EXPORTS_DIR = paths.EXPORTS_DIR

SIDEBAR_BG = "#f6f7fc"
SIDEBAR_WIDTH = 360
FILE_FORMATS = {"CSV": ".csv", "Excel": ".xlsx"}  # type of the files saved every N leads
TABLE_COLUMNS = ("name", "phone", "email", "city", "country", "website_status", "website", "address", "rating",
                 "review_count", "category", "search_query")
TABLE_WIDTHS = {"name": 210, "phone": 130, "email": 200, "city": 105, "country": 110, "website_status": 100,
                "website": 190, "address": 260, "rating": 55, "review_count": 65, "category": 140,
                "search_query": 200}
WEBSITE_FILTERS = {
    "No real website (social pages OK)": "no_real_website",
    "No website at all": "no_website",
    "All businesses": "all",
}
QUICK_FILTERS = ("All", "With email", "No website", "Social only")
SPEEDS = {"Safe": 1, "Fast": 3, "Max": 4}  # Google Maps places opened at the same time


class LeadScraperApp(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        th.apply_theme(self)
        self.configure(fg_color=th.BG)
        self.title(paths.APP_NAME)
        if paths.ICON_PATH.exists():
            self.iconbitmap(str(paths.ICON_PATH))  # also stops CustomTkinter replacing it with its own icon
        self.geometry("1440x860")
        self.minsize(1100, 680)

        self.events: queue.Queue = queue.Queue()
        self.worker: ScraperWorker | None = None
        self.leads: list[Lead] = []
        self._lead_keys: set[tuple[str, str]] = set()
        self._counts = {"email": 0, "none": 0, "social": 0}
        self._progress_indeterminate = False
        self._autosave_path: Path | None = None
        self._run_started = 0.0
        self._run_seconds = 0.0
        self._skipped = 0
        self.worker_leads = 0  # leads added by the current run (for leads/min)
        self._shown = 0  # rows currently drawn in the table
        self._search_job: str | None = None
        # split files for the current run: every `_batch_size` new leads -> one .csv/.xlsx
        self._batch: list[Lead] = []
        self._batch_size = 0
        self._batch_number = 0
        self._batch_dir: Path | None = None
        self._batch_ext = ".csv"

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self._build_sidebar()
        self._build_main()
        # Start maximised. Set here (not via after()) because CustomTkinter re-applies the
        # window state it sees when mainloop() starts.
        self.state("zoomed")

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(POLL_MS, self._poll_events)
        self.after(1000, self._tick)
        self._update_run_chip()
        self._log("Ready. Enter keywords and locations, then press Start Scraping.")
        self._log("Tip: use the Cities button to add many cities or countries at once.")

    # =========================================================== sidebar
    def _build_sidebar(self) -> None:
        bar = ctk.CTkFrame(self, fg_color=SIDEBAR_BG, corner_radius=0, width=SIDEBAR_WIDTH, border_width=0)
        bar.grid(row=0, column=0, sticky="nsw")
        bar.grid_propagate(False)
        bar.grid_columnconfigure(0, weight=1)
        bar.grid_rowconfigure(1, weight=1)
        tk.Frame(self, bg=th.BORDER, width=1).grid(row=0, column=0, sticky="nse")  # divider line

        self._build_hero(bar).grid(row=0, column=0, sticky="ew", padx=18, pady=(18, 12))

        scroll = ctk.CTkScrollableFrame(bar, fg_color=SIDEBAR_BG, corner_radius=0,
                                        scrollbar_button_color=th.BORDER_HI, scrollbar_button_hover_color=th.FAINT)
        scroll.grid(row=1, column=0, sticky="nsew", padx=(8, 4))
        scroll.grid_columnconfigure(0, weight=1)
        self._build_search_section(scroll).grid(row=0, column=0, sticky="ew", padx=6, pady=(0, 12))
        self._build_output_section(scroll).grid(row=1, column=0, sticky="ew", padx=6, pady=(0, 12))
        self._build_filters_section(scroll).grid(row=2, column=0, sticky="ew", padx=6, pady=(0, 12))
        self._build_emails_section(scroll).grid(row=3, column=0, sticky="ew", padx=6, pady=(0, 12))
        self._build_advanced_section(scroll).grid(row=4, column=0, sticky="ew", padx=6, pady=(0, 6))

        footer = tk.Frame(bar, bg=SIDEBAR_BG)
        footer.grid(row=2, column=0, sticky="ew", padx=18, pady=(10, 16))
        footer.grid_columnconfigure(0, weight=1)
        self.start_button = th.pill(footer, "Start Scraping", "play", kind="go", command=self._toggle_scraping,
                                    height=50, size=14)
        self.start_button.grid(row=0, column=0, sticky="ew")
        self.footer_status = th.label(footer, "Idle", size=11, color=th.FAINT)
        self.footer_status.grid(row=1, column=0, sticky="w", pady=(8, 0))

    def _build_hero(self, parent) -> tk.Canvas:
        """Pastel gradient card with the glossy orb logo, the app name and a tagline."""
        scale = ctk.ScalingTracker.get_widget_scaling(self)
        width, height = int((SIDEBAR_WIDTH - 36) * scale), int(92 * scale)
        hero = tk.Canvas(parent, width=width, height=height, bg=SIDEBAR_BG, highlightthickness=0)
        th.gradient_card(hero, width, height, ["#d8d2ff", "#c6d3ff", "#e3edff", "#ffe8df"], int(22 * scale),
                         SIDEBAR_BG)
        th.orb(hero, 46 * scale, height / 2, 26 * scale)
        hero.create_text(86 * scale, height / 2 - 11 * scale, text=paths.APP_NAME, anchor="w", fill=th.TEXT,
                         font=(th.DISPLAY, 15, "bold"))
        hero.create_text(86 * scale, height / 2 + 13 * scale, text="Business leads from Google Maps", anchor="w",
                         fill=th.MUTED, font=(th.FONT, 9))
        return hero

    def _section(self, parent, title: str, color: str, icon_name: str, tint: str) -> th.Node:
        return th.Node(parent, title, dot=color, bg=SIDEBAR_BG, icon_name=icon_name, tint=tint)

    def _build_search_section(self, parent) -> th.Node:
        node = self._section(parent, "Search", th.PURPLE, "search", th.PURPLE_BG)
        body = node.body
        th.label(body, "Keywords · one per line").grid(row=0, column=0, sticky="ew", padx=14, pady=(8, 4))
        self.keywords_box = ctk.CTkTextbox(body, height=70, wrap="none", font=th.font(12))
        self.keywords_box.grid(row=1, column=0, sticky="ew", padx=14)
        self.keywords_box.insert("1.0", "cafe")

        head = tk.Frame(body, bg=th.CARD)
        head.grid(row=2, column=0, sticky="ew", padx=14, pady=(12, 4))
        self.locations_title = th.label(head, "Locations · one per line")
        self.locations_title.pack(side="left")
        self.cities_button = th.pill(head, "Cities", "globe", kind="soft", command=self._open_city_picker, height=28,
                                     size=11)
        self.cities_button.pack(side="right")
        th.Tooltip(self.cities_button, "Pick cities from 30 countries (USA, UK, Canada, UAE, …)")
        self.locations_box = ctk.CTkTextbox(body, height=110, wrap="none", font=th.font(12))
        self.locations_box.grid(row=3, column=0, sticky="ew", padx=14, pady=(0, 14))
        self.locations_box.insert("1.0", "Karachi, Pakistan")
        self.locations_box.bind("<KeyRelease>", lambda _e: self._update_locations_title())
        return node

    def _build_filters_section(self, parent) -> th.Node:
        node = self._section(parent, "Filters", th.GREEN, "filter", th.GREEN_BG)
        body = node.body
        th.label(body, "Keep only businesses with").grid(row=0, column=0, sticky="ew", padx=14, pady=(8, 4))
        self.filter_var = ctk.StringVar(value=next(iter(WEBSITE_FILTERS)))
        self.filter_menu = ctk.CTkOptionMenu(body, values=list(WEBSITE_FILTERS), variable=self.filter_var,
                                             height=32, font=th.font(12))
        self.filter_menu.grid(row=1, column=0, sticky="ew", padx=14)
        self.phone_switch = ctk.CTkSwitch(body, text="Only leads with a phone number", font=th.font(12))
        self.phone_switch.select()
        self.phone_switch.grid(row=2, column=0, sticky="w", padx=14, pady=(12, 0))
        self.history_switch = ctk.CTkSwitch(body, text="Skip leads from earlier runs", font=th.font(12))
        self.history_switch.select()
        self.history_switch.grid(row=3, column=0, sticky="w", padx=14, pady=(10, 0))
        row = tk.Frame(body, bg=th.CARD)
        row.grid(row=4, column=0, sticky="ew", padx=14, pady=(6, 10))
        self.history_label = th.label(row, "", size=11, color=th.FAINT)
        self.history_label.pack(side="left")
        self.reset_history_button = th.pill(row, "Reset", "reset", kind="plain", command=self._reset_history,
                                            height=26, size=11)
        self.reset_history_button.pack(side="right")
        self._refresh_history_label()
        return node

    def _build_emails_section(self, parent) -> th.Node:
        node = self._section(parent, "Emails", th.PINK, "mail", th.PINK_BG)
        body = node.body
        self.email_switch = ctk.CTkSwitch(body, text="Find emails (website + web search)", font=th.font(12))
        self.email_switch.select()
        self.email_switch.grid(row=0, column=0, sticky="w", padx=14, pady=(8, 0))
        th.Tooltip(self.email_switch, "Businesses without a website: their email is looked up in online "
                                      "business directories via web search.")
        self.require_email_switch = ctk.CTkSwitch(body, text="Only leads with an email", font=th.font(12),
                                                  command=self._on_require_email)
        self.require_email_switch.grid(row=1, column=0, sticky="w", padx=14, pady=(10, 12))
        th.Tooltip(self.require_email_switch, "Works with every website filter, including 'No real website'.")
        return node

    def _build_output_section(self, parent) -> th.Node:
        node = self._section(parent, "Leads & files", th.BLUE, "file", th.BLUE_BG)
        body = node.body
        body.grid_columnconfigure((0, 1), weight=1)
        th.label(body, "How many leads").grid(row=0, column=0, sticky="w", padx=(14, 6), pady=(8, 4))
        th.label(body, "New file every").grid(row=0, column=1, sticky="w", padx=(6, 14), pady=(8, 4))
        self.max_entry = ctk.CTkEntry(body, height=34, font=th.font(13, "bold"))
        self.max_entry.insert(0, str(DEFAULT_MAX_LEADS))
        self.max_entry.grid(row=1, column=0, sticky="ew", padx=(14, 6))
        self.batch_entry = ctk.CTkEntry(body, height=34, font=th.font(13, "bold"), placeholder_text="0 = one file")
        self.batch_entry.insert(0, str(DEFAULT_BATCH_SIZE))
        self.batch_entry.grid(row=1, column=1, sticky="ew", padx=(6, 14))
        th.Tooltip(self.max_entry, f"Total leads for this run (1 - {MAX_LEADS:,})")
        th.Tooltip(self.batch_entry, "A new file is saved after this many leads (0 = no split files, "
                                     "only the autosave and Export)")
        th.label(body, "File type").grid(row=2, column=0, columnspan=2, sticky="w", padx=14, pady=(10, 4))
        self.format_selector = ctk.CTkSegmentedButton(body, values=list(FILE_FORMATS), height=30, font=th.font(12),
                                                      command=lambda _v: self._update_files_hint())
        self.format_selector.set("CSV")
        self.format_selector.grid(row=3, column=0, columnspan=2, sticky="ew", padx=14)
        self.files_hint = th.label(body, "", size=11, color=th.BLUE)
        self.files_hint.grid(row=4, column=0, columnspan=2, sticky="w", padx=14, pady=(8, 10))
        for entry in (self.max_entry, self.batch_entry):
            entry.bind("<KeyRelease>", lambda _e: self._update_files_hint())
        self._update_files_hint()
        return node

    def _update_files_hint(self) -> None:
        """'100 leads → 4 CSV files of 25' so the split is clear before starting."""
        try:
            total = int(self.max_entry.get().strip())
            every = int(self.batch_entry.get().strip() or 0)
        except ValueError:
            self.files_hint.configure(text="Enter whole numbers", text_color=th.RED)
            return
        kind = self.format_selector.get()
        if total <= 0:
            text = "How many leads must be at least 1"
        elif every <= 0:
            text = "No split files · use Export when done"
        elif every >= total:
            text = f"{total:,} leads → 1 {kind} file"
        else:
            files, rest = divmod(total, every)
            text = (f"{total:,} leads → {files} {kind} files of {every:,}" +
                    (f" + 1 of {rest:,}" if rest else ""))
        self.files_hint.configure(text=text, text_color=th.BLUE)

    def _build_advanced_section(self, parent) -> th.Node:
        node = self._section(parent, "Advanced", th.YELLOW, "settings", th.YELLOW_BG)
        body = node.body
        self.spread_switch = ctk.CTkSwitch(body, text="Split leads evenly across locations", font=th.font(12))
        self.spread_switch.select()
        self.spread_switch.grid(row=0, column=0, sticky="w", padx=14, pady=(8, 0))
        th.Tooltip(self.spread_switch, "e.g. 100 leads over 4 cities = about 25 from each city")
        self.expand_switch = ctk.CTkSwitch(body, text="Keep going when results run out", font=th.font(12))
        self.expand_switch.select()
        self.expand_switch.grid(row=1, column=0, sticky="w", padx=14, pady=(10, 0))
        th.Tooltip(self.expand_switch, "Google Maps lists ~120 places per search. When that runs out before your "
                                       "target: a country is searched city by city, and a city area by area on the "
                                       "map, until Max leads is reached.")
        self.headless_switch = ctk.CTkSwitch(body, text="Run headless (hide browser)", font=th.font(12))
        self.headless_switch.grid(row=2, column=0, sticky="w", padx=14, pady=(10, 0))
        th.Tooltip(self.headless_switch, "Keep the browser visible to solve CAPTCHAs")
        th.label(body, "Speed · places opened at once").grid(row=3, column=0, sticky="w", padx=14, pady=(12, 4))
        self.speed_selector = ctk.CTkSegmentedButton(body, values=list(SPEEDS), height=30, font=th.font(12))
        self.speed_selector.set("Fast")
        self.speed_selector.grid(row=4, column=0, sticky="ew", padx=14, pady=(0, 12))
        th.Tooltip(self.speed_selector, "Safe = 1 tab (slowest, gentlest)  ·  Fast = 3 tabs (recommended, about "
                                        "4x faster)  ·  Max = 4 tabs (can trigger Google CAPTCHAs sooner)")
        return node

    # ============================================================== main
    def _build_main(self) -> None:
        main = tk.Frame(self, bg=th.BG)
        main.grid(row=0, column=1, sticky="nsew", padx=(22, 22), pady=(18, 16))
        main.grid_columnconfigure(0, weight=1)
        main.grid_rowconfigure(4, weight=1)

        # ---- title row
        top = tk.Frame(main, bg=th.BG)
        top.grid(row=0, column=0, sticky="ew")
        titles = tk.Frame(top, bg=th.BG)
        titles.pack(side="left")
        ctk.CTkLabel(titles, text="Leads", font=th.display_font(30), text_color=th.TEXT, anchor="w").pack(anchor="w")
        th.label(titles, "Find businesses that need a website · live from Google Maps", size=12,
                 color=th.MUTED).pack(anchor="w")
        self.run_chip = ctk.CTkLabel(top, text="○  Idle", fg_color="#e6e8f4", corner_radius=14, height=30,
                                     font=th.font(11), text_color=th.MUTED, padx=14)
        self.run_chip.pack(side="left", padx=18, anchor="n", pady=(8, 0))
        self.export_button = th.pill(top, "Export", "upload", kind="primary", command=self._export, height=40,
                                     width=120)
        self.export_button.pack(side="right")
        th.icon_button(top, "save", lambda: self._open_folder(AUTOSAVE_DIR), "Open autosave folder", 40).pack(
            side="right", padx=(0, 8))
        self.open_exports_button = th.icon_button(top, "folder", self._open_exports, "Open the files folder", 40)
        self.open_exports_button.pack(side="right", padx=(0, 8))

        # ---- stat cards (pastel icon chips, like the reference design)
        cards = tk.Frame(main, bg=th.BG)
        cards.grid(row=1, column=0, sticky="ew", pady=(18, 14))
        self.stat_values: dict[str, ctk.CTkLabel] = {}
        self.stat_notes: dict[str, ctk.CTkLabel] = {}
        specs = (("leads", "Leads", "people", th.BLUE, th.BLUE_BG),
                 ("email", "With email", "mail", th.GREEN, th.GREEN_BG),
                 ("none", "No website", "globe", th.YELLOW, th.YELLOW_BG),
                 ("social", "Social only", "share", th.PINK, th.PINK_BG),
                 ("skipped", "Skipped", "skip", th.MUTED, "#eceef6"),
                 ("time", "Run time", "clock", th.PURPLE, th.PURPLE_BG))
        for column, (key, title, icon_name, color, tint) in enumerate(specs):
            cards.grid_columnconfigure(column, weight=1, uniform="stat")
            card = ctk.CTkFrame(cards, fg_color=th.CARD, corner_radius=20, border_width=1, border_color=th.BORDER,
                                bg_color=th.BG)
            card.grid(row=0, column=column, sticky="ew", padx=(0 if column == 0 else 12, 0))
            head = ctk.CTkFrame(card, fg_color="transparent")
            head.pack(fill="x", padx=16, pady=(14, 0))
            ctk.CTkLabel(head, text=th.icon(icon_name), font=th.icon_font(13), text_color=color, fg_color=tint,
                         corner_radius=10, width=30, height=30).pack(side="left")
            th.label(head, title, size=12, color=th.MUTED).pack(side="left", padx=10)
            value = ctk.CTkLabel(card, text="0" if key != "time" else "00:00", font=th.display_font(26),
                                 text_color=th.TEXT, anchor="w")
            value.pack(anchor="w", padx=16, pady=(6, 0))
            note = th.label(card, "", size=10, color=th.FAINT)
            note.pack(anchor="w", padx=16, pady=(0, 12))
            self.stat_values[key], self.stat_notes[key] = value, note

        # ---- progress + status
        status_row = tk.Frame(main, bg=th.BG)
        status_row.grid(row=2, column=0, sticky="ew")
        status_row.grid_columnconfigure(0, weight=1)
        self.status_label = th.label(status_row, "Idle", size=12, color=th.MUTED)
        self.status_label.grid(row=0, column=0, sticky="w")
        self.progress = ctk.CTkProgressBar(status_row, height=6)
        self.progress.set(0)
        self.progress.grid(row=1, column=0, sticky="ew", pady=(6, 14))

        # ---- toolbar
        tools = tk.Frame(main, bg=th.BG)
        tools.grid(row=3, column=0, sticky="ew", pady=(0, 10))
        self.search_entry = ctk.CTkEntry(tools, width=320, height=40, font=th.font(12), corner_radius=20,
                                         placeholder_text=f"{th.icon('search')}   Search name, phone, email, city…")
        self.search_entry.pack(side="left")
        self.search_entry.bind("<KeyRelease>", lambda _e: self._schedule_view_refresh())
        self.quick_filter = ctk.CTkSegmentedButton(tools, values=list(QUICK_FILTERS), height=40, font=th.font(12),
                                                   corner_radius=20, command=lambda _v: self._refresh_view())
        self.quick_filter.set("All")
        self.quick_filter.pack(side="left", padx=12)
        self.view_label = th.label(tools, "", size=11, color=th.FAINT)
        self.view_label.pack(side="left")
        self.clear_button = th.icon_button(tools, "delete", self._clear_results, "Clear results", 40)
        self.clear_button.pack(side="right")
        th.pill(tools, "Copy emails", "mail", kind="soft", command=self._copy_emails, height=40, size=12).pack(
            side="right", padx=(0, 8))

        # ---- table
        table_box = ctk.CTkFrame(main, fg_color=th.CARD, corner_radius=20, border_width=1, border_color=th.BORDER)
        table_box.grid(row=4, column=0, sticky="nsew")
        table_box.grid_columnconfigure(0, weight=1)
        table_box.grid_rowconfigure(0, weight=1)
        self.table = th.tree(table_box, TABLE_WIDTHS, name="Leads.Treeview", height=6, titles=COLUMN_TITLES)
        y_scroll = ctk.CTkScrollbar(table_box, command=self.table.yview, width=12, height=40)
        x_scroll = ctk.CTkScrollbar(table_box, orientation="horizontal", command=self.table.xview, height=12)
        self.table.configure(yscrollcommand=y_scroll.set, xscrollcommand=x_scroll.set)
        self.table.grid(row=0, column=0, sticky="nsew", padx=(10, 0), pady=(10, 0))
        y_scroll.grid(row=0, column=1, sticky="ns", pady=(10, 0), padx=(0, 4))
        x_scroll.grid(row=1, column=0, sticky="ew", padx=(10, 0), pady=(0, 6))
        self.table.bind("<Double-1>", lambda _e: self._open_selected("maps"))
        self.table.bind("<Button-3>", self._show_row_menu)
        self.row_menu = tk.Menu(self, tearoff=0, bg=th.CARD, fg=th.TEXT, activebackground=th.SELECTED,
                                activeforeground=th.TEXT, bd=0, font=(th.FONT, 10))
        self.row_menu.add_command(label="Copy phone", command=lambda: self._copy_field("phone"))
        self.row_menu.add_command(label="Copy email", command=lambda: self._copy_field("email"))
        self.row_menu.add_command(label="Copy name", command=lambda: self._copy_field("name"))
        self.row_menu.add_separator()
        self.row_menu.add_command(label="Open website", command=lambda: self._open_selected("website"))
        self.row_menu.add_command(label="Open on Google Maps", command=lambda: self._open_selected("maps"))

        # ---- log
        log_card = ctk.CTkFrame(main, fg_color=th.CARD, corner_radius=20, border_width=1, border_color=th.BORDER)
        log_card.grid(row=5, column=0, sticky="ew", pady=(14, 0))
        log_card.grid_columnconfigure(0, weight=1)
        head = tk.Frame(log_card, bg=th.CARD)
        head.grid(row=0, column=0, sticky="ew", padx=16, pady=(10, 4))
        ctk.CTkLabel(head, text=th.icon("list"), font=th.icon_font(12), text_color=th.PURPLE, fg_color=th.PURPLE_BG,
                     corner_radius=8, width=24, height=24).pack(side="left")
        th.label(head, "Live log", size=12, color=th.TEXT, weight="bold").pack(side="left", padx=8)
        self.log_toggle = th.pill(head, "Hide", kind="plain", command=self._toggle_log, height=24, size=10)
        self.log_toggle.pack(side="right")
        th.pill(head, "Clear", kind="plain", command=self._clear_log, height=24, size=10).pack(side="right")
        self.log_box = th.log_box(log_card, height=96)
        self.log_box.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 10))
        self._update_view_label()

    # ======================================================= stats / view
    def _update_stats(self) -> None:
        total = len(self.leads)
        self.stat_values["leads"].configure(text=f"{total:,}")
        for key in ("email", "none", "social"):
            self.stat_values[key].configure(text=f"{self._counts[key]:,}")
            self.stat_notes[key].configure(text=f"{self._counts[key] / total:.0%} of leads" if total else "")
        self.stat_values["skipped"].configure(text=f"{self._skipped:,}")
        self.stat_notes["skipped"].configure(text="filters / duplicates")
        running = bool(self.worker and self.worker.is_alive())
        seconds = time.time() - self._run_started if running else self._run_seconds
        hours, rest = divmod(int(seconds), 3600)
        self.stat_values["time"].configure(text=f"{hours}:{rest // 60:02d}:{rest % 60:02d}" if hours
                                           else f"{rest // 60:02d}:{rest % 60:02d}")
        run_leads = self.worker_leads if running else 0
        self.stat_notes["time"].configure(text=f"{run_leads / (seconds / 60):.1f} leads/min"
                                          if running and seconds > 60 else "")
        self.stat_notes["leads"].configure(text=f"{self._history_count:,} in history")

    def _tick(self) -> None:
        self._update_stats()
        self.after(1000, self._tick)

    def _matches_view(self, lead: Lead) -> bool:
        quick = self.quick_filter.get()
        if quick == "With email" and not lead.email:
            return False
        if quick == "No website" and lead.website_status != WEBSITE_NONE:
            return False
        if quick == "Social only" and lead.website_status != WEBSITE_SOCIAL:
            return False
        text = self.search_entry.get().strip().lower()
        if text:
            haystack = " ".join((lead.name, lead.phone, lead.email, lead.city, lead.country, lead.category,
                                 lead.address)).lower()
            return all(part in haystack for part in text.split())
        return True

    def _view_is_filtered(self) -> bool:
        return self.quick_filter.get() != "All" or bool(self.search_entry.get().strip())

    def _view_leads(self) -> list[Lead]:
        return [lead for lead in self.leads if self._matches_view(lead)]

    def _schedule_view_refresh(self) -> None:
        if self._search_job:
            self.after_cancel(self._search_job)
        self._search_job = self.after(250, self._refresh_view)

    def _refresh_view(self) -> None:
        """Redraw the table for the current search text + quick filter."""
        self._search_job = None
        self.table.delete(*self.table.get_children())
        self._shown = 0
        for index, lead in enumerate(self.leads):
            if self._shown >= VIEW_LIMIT:
                break
            if self._matches_view(lead):
                self._insert_row(index, lead)
        self._update_view_label()

    def _insert_row(self, index: int, lead: Lead) -> None:
        values = [getattr(lead, column) for column in TABLE_COLUMNS]
        self.table.insert("", "end", iid=str(index), values=values, tags=("odd",) if self._shown % 2 else ())
        self._shown += 1

    def _update_view_label(self) -> None:
        total = len(self.leads)
        if not self._view_is_filtered():
            text = f"{total:,} leads" if self._shown >= total else f"showing first {self._shown:,} of {total:,}"
        else:
            matching = sum(1 for lead in self.leads if self._matches_view(lead))
            text = f"{matching:,} of {total:,} match" + (f" · first {VIEW_LIMIT:,} shown" if matching > self._shown
                                                          else "")
        self.view_label.configure(text=text)

    # ============================================================ actions
    def _on_require_email(self) -> None:
        # Requiring an email only makes sense if emails are being looked up.
        if self.require_email_switch.get():
            self.email_switch.select()

    @staticmethod
    def _lines(textbox: ctk.CTkTextbox) -> list[str]:
        """Non-empty, de-duplicated lines of a textbox, in order."""
        lines = (line.strip() for line in textbox.get("1.0", "end").splitlines())
        return list(dict.fromkeys(line for line in lines if line))

    def _open_city_picker(self) -> None:
        if getattr(self, "_city_picker", None) and self._city_picker.winfo_exists():
            self._city_picker.lift()
            return
        self._city_picker = CityPicker(self, on_add=self._add_locations)

    def _add_locations(self, lines: list[str], replace: bool) -> int:
        current = [] if replace else self._lines(self.locations_box)
        merged = list(dict.fromkeys(current + lines))
        self.locations_box.delete("1.0", "end")
        self.locations_box.insert("1.0", "\n".join(merged))
        self._update_locations_title()
        return len(merged)

    def _update_locations_title(self) -> None:
        count = len(self._lines(self.locations_box))
        self.locations_title.configure(text=f"Locations · {count} in list" if count > 1 else "Locations · one per line")

    def _toggle_scraping(self) -> None:
        if self.worker and self.worker.is_alive():
            self._stop_scraping()
        else:
            self._start_scraping()

    def _start_scraping(self) -> None:
        keywords = self._lines(self.keywords_box)
        locations = self._lines(self.locations_box)
        if not keywords or not locations:
            messagebox.showwarning("Missing input", "Please enter at least one keyword and one location.")
            return
        try:
            max_results = int(self.max_entry.get().strip())
            if not 1 <= max_results <= MAX_LEADS:
                raise ValueError
        except ValueError:
            messagebox.showwarning("Invalid number", f"How many leads must be a whole number between 1 and {MAX_LEADS:,}.")
            return
        try:
            batch_size = int(self.batch_entry.get().strip() or 0)
            if not 0 <= batch_size <= MAX_LEADS:
                raise ValueError
        except ValueError:
            messagebox.showwarning("Invalid number", "'New file every' must be a whole number (0 turns it off).")
            return

        options = {
            "website_filter": WEBSITE_FILTERS[self.filter_var.get()],
            "require_phone": bool(self.phone_switch.get()),
            "skip_known": bool(self.history_switch.get()),
            "find_emails": bool(self.email_switch.get()),
            "require_email": bool(self.require_email_switch.get()),
            "spread_evenly": bool(self.spread_switch.get()),
            "auto_expand": bool(self.expand_switch.get()),
            "parallel_tabs": SPEEDS.get(self.speed_selector.get(), 3),
        }
        self.worker = ScraperWorker(
            keywords=keywords,
            locations=locations,
            max_results=max_results,
            headless=bool(self.headless_switch.get()),
            events=self.events,
            options=options,
        )
        stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        AUTOSAVE_DIR.mkdir(parents=True, exist_ok=True)
        self._autosave_path = AUTOSAVE_DIR / f"leads_{stamp}.csv"
        self._batch, self._batch_number, self._batch_size = [], 0, batch_size
        self._batch_ext = FILE_FORMATS.get(self.format_selector.get(), ".csv")
        self._batch_dir = EXPORTS_DIR / f"{_slug(keywords[0])}_{stamp}" if batch_size else None

        self._run_started = time.time()
        self.worker_leads = 0
        self._skipped = 0
        self._set_running(True)
        self._log(f"--- New run: {len(keywords)} keyword(s) x {len(locations)} location(s) "
                  f"| max {max_results} | filter: {self.filter_var.get()} ---")
        self._log(f"Autosaving everything to {self._autosave_path}")
        if self._batch_dir:
            self._log(f"A new {self.format_selector.get()} file is saved every {batch_size:,} leads in {self._batch_dir}")
        self.worker.start()
        self._update_run_chip()

    def _stop_scraping(self) -> None:
        if self.worker:
            self.worker.stop()
        self.start_button.configure(text=f"{th.icon('stop')}   Stopping...", state="disabled")
        self.status_label.configure(text="Stopping - closing the browser...")
        self._log("Stop requested. Finishing current step...", "warning")

    def _set_running(self, running: bool) -> None:
        state = "disabled" if running else "normal"
        for widget in (self.keywords_box, self.locations_box, self.cities_button, self.spread_switch,
                       self.expand_switch, self.max_entry, self.batch_entry, self.format_selector, self.filter_menu, self.phone_switch,
                       self.email_switch, self.require_email_switch, self.history_switch, self.headless_switch,
                       self.speed_selector, self.clear_button, self.reset_history_button):
            widget.configure(state=state)
        if running:
            self.start_button.configure(text=f"{th.icon('stop')}   Stop Scraping", state="normal")
            th.restyle(self.start_button, "danger")
            self.status_label.configure(text="Starting...")
            self.progress.configure(mode="indeterminate")
            self.progress.start()
            self._progress_indeterminate = True
        else:
            self.start_button.configure(text=f"{th.icon('play')}   Start Scraping", state="normal")
            th.restyle(self.start_button, "go")
            self._run_seconds = time.time() - self._run_started if self._run_started else 0
            self.progress.stop()
            self.progress.configure(mode="determinate")
            self._progress_indeterminate = False
        self._update_run_chip()

    def _update_run_chip(self) -> None:
        running = bool(self.worker and self.worker.is_alive())
        self.run_chip.configure(text="●  Scraping" if running else "○  Idle",
                                text_color=th.GREEN if running else th.MUTED,
                                fg_color=th.GREEN_BG if running else "#e6e8f4")
        self.footer_status.configure(text="Running - you can keep using the app" if running
                                     else f"Idle · files in Documents / {paths.APP_NAME}")

    def _autosave(self) -> None:
        if not self._autosave_path or not self.leads:
            return
        try:
            export_leads(self.leads, self._autosave_path)
        except OSError as exc:  # e.g. the CSV is open in Excel; try again at the next checkpoint
            self._log(f"Autosave failed: {exc}", "warning")

    def _write_batch(self) -> None:
        """Save the leads collected since the last batch as their own numbered CSV/Excel file."""
        if not self._batch_dir or not self._batch:
            return
        self._batch_number += 1
        first = (self._batch_number - 1) * self._batch_size + 1
        last = first + len(self._batch) - 1
        path = self._batch_dir / f"leads_{self._batch_number:03d}_{first}-{last}{self._batch_ext}"
        try:
            self._batch_dir.mkdir(parents=True, exist_ok=True)
            export_leads(self._batch, path)
        except Exception as exc:  # noqa: BLE001 - keep the leads and retry with the next lead
            self._batch_number -= 1
            self._log(f"Could not save file {path.name}: {exc}", "warning")
            return
        self._log(f"Saved file #{self._batch_number}: {path.name} ({len(self._batch):,} leads)", "success")
        self._batch = []

    def _open_exports(self) -> None:
        folder = self._batch_dir if self._batch_dir and self._batch_dir.exists() else EXPORTS_DIR
        self._open_folder(folder)

    @staticmethod
    def _open_folder(folder: Path) -> None:
        folder.mkdir(parents=True, exist_ok=True)
        os.startfile(folder)  # Windows: open in Explorer

    def _refresh_history_label(self) -> None:
        self._history_count = LeadHistory().lead_count
        self.history_label.configure(text=f"{self._history_count:,} leads remembered")

    def _reset_history(self) -> None:
        if not messagebox.askyesno(
                "Reset lead history",
                "Forget every lead collected so far?\n\nLater runs may then return businesses you already have."):
            return
        LeadHistory.reset()
        self._refresh_history_label()
        self._log("Lead history cleared.", "warning")

    def _export(self) -> None:
        if not self.leads:
            messagebox.showinfo("Nothing to export", "There are no leads yet. Run a scrape first.")
            return
        leads = self.leads
        if self._view_is_filtered():
            view = self._view_leads()
            answer = messagebox.askyesnocancel(
                "Export", f"Export only the {len(view):,} leads in the current view?\n\n"
                          f"Yes = current view ({len(view):,})     No = all leads ({len(self.leads):,})")
            if answer is None:
                return
            leads = view if answer else self.leads
        first_keyword = next(iter(self._lines(self.keywords_box)), "leads")
        ext = FILE_FORMATS.get(self.format_selector.get(), ".csv")
        types = [("CSV file", "*.csv"), ("Excel workbook", "*.xlsx")]
        EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
        path = filedialog.asksaveasfilename(
            title="Export leads",
            initialdir=str(EXPORTS_DIR),
            initialfile=f"{_slug(first_keyword)}_{dt.datetime.now():%Y%m%d_%H%M}{ext}",
            defaultextension=ext,
            filetypes=types if ext == ".csv" else types[::-1],
        )
        if not path:
            return
        try:
            rows = export_leads(leads, path)
        except PermissionError:
            messagebox.showerror("Export failed", "The file is open in another program. Close it and try again.")
            return
        except Exception as exc:  # noqa: BLE001 - show any pandas/openpyxl problem to the user
            messagebox.showerror("Export failed", str(exc))
            return
        self._log(f"Exported {rows} leads to {path}", "success")
        messagebox.showinfo("Export complete", f"Saved {rows:,} leads to:\n{path}")

    def _copy_emails(self) -> None:
        emails = list(dict.fromkeys(lead.email.split(",")[0].strip() for lead in self._view_leads() if lead.email))
        if not emails:
            messagebox.showinfo("No emails", "No lead in the current view has an email.")
            return
        self.clipboard_clear()
        self.clipboard_append("\n".join(emails))
        self._log(f"Copied {len(emails):,} emails to the clipboard (one per line).", "success")

    def _selected_lead(self) -> Lead | None:
        selection = self.table.selection()
        return self.leads[int(selection[0])] if selection else None

    def _show_row_menu(self, event) -> None:
        row = self.table.identify_row(event.y)
        if row:
            self.table.selection_set(row)
            self.row_menu.tk_popup(event.x_root, event.y_root)

    def _copy_field(self, field: str) -> None:
        lead = self._selected_lead()
        if lead and getattr(lead, field):
            self.clipboard_clear()
            self.clipboard_append(getattr(lead, field))

    def _open_selected(self, target: str) -> None:
        lead = self._selected_lead()
        if not lead:
            return
        url = lead.website if target == "website" else lead.listing_url
        if url:
            webbrowser.open(url)

    def _clear_results(self) -> None:
        if self.leads and not messagebox.askyesno("Clear results", f"Remove all {len(self.leads)} leads?"):
            return
        self.leads.clear()
        self._lead_keys.clear()
        self._counts = {"email": 0, "none": 0, "social": 0}
        self._skipped = 0
        self.table.delete(*self.table.get_children())
        self._shown = 0
        self.progress.set(0)
        self.status_label.configure(text="Idle")
        self._update_view_label()
        self._update_stats()

    def _clear_log(self) -> None:
        self.log_box.configure(state="normal")
        self.log_box.delete("1.0", "end")
        self.log_box.configure(state="disabled")

    def _toggle_log(self) -> None:
        if self.log_box.winfo_ismapped():
            self.log_box.grid_remove()
            self.log_toggle.configure(text="Show")
        else:
            self.log_box.grid()
            self.log_toggle.configure(text="Hide")

    # ======================================================== worker events
    def _poll_events(self) -> None:
        """Drain the worker queue on the Tk thread (the only thread allowed to touch widgets)."""
        try:
            for _ in range(MAX_EVENTS_PER_POLL):
                event_type, payload = self.events.get_nowait()
                self._handle_event(event_type, payload)
        except queue.Empty:
            pass
        self.after(POLL_MS, self._poll_events)

    def _handle_event(self, event_type: str, payload) -> None:
        if event_type == "log":
            level, message = payload
            self._log(message, level)
        elif event_type == "status":
            self.status_label.configure(text=payload)
        elif event_type == "lead":
            self._add_lead_row(payload)
        elif event_type == "skipped":
            self._skipped = payload
        elif event_type == "progress":
            count, total = payload
            if self._progress_indeterminate:
                self.progress.stop()
                self.progress.configure(mode="determinate")
                self._progress_indeterminate = False
            self.progress.set(min(count / max(total, 1), 1.0))
        elif event_type == "error":
            self._log(f"ERROR: {payload}", "error")
            messagebox.showerror("Scraper error", payload)
        elif event_type == "done":
            self._set_running(False)
            self._write_batch()  # last, partly filled file
            self._autosave()
            self._refresh_history_label()
            if not payload:
                self.progress.set(0)
            self.status_label.configure(text=f"Finished - {payload} leads this run, {len(self.leads)} total")
            self._update_stats()

    def _add_lead_row(self, lead: Lead) -> None:
        key = lead.key()
        if key in self._lead_keys:  # same business found in an earlier run
            return
        self._lead_keys.add(key)
        self.leads.append(lead)
        self.worker_leads += 1
        self._counts["email"] += bool(lead.email)
        self._counts["none"] += lead.website_status == WEBSITE_NONE
        self._counts["social"] += lead.website_status == WEBSITE_SOCIAL
        if self._shown < VIEW_LIMIT and self._matches_view(lead):
            self._insert_row(len(self.leads) - 1, lead)
            self.table.see(str(len(self.leads) - 1))
        self._update_view_label()
        self.stat_values["leads"].configure(text=f"{len(self.leads):,}")
        if len(self.leads) % (AUTOSAVE_EVERY if len(self.leads) < 5000 else 500) == 0:
            self._autosave()
        if self._batch_dir:
            self._batch.append(lead)
            if len(self._batch) >= self._batch_size:
                self._write_batch()

    def _log(self, message: str, level: str = "info") -> None:
        timestamp = dt.datetime.now().strftime("%H:%M:%S")
        self.log_box.configure(state="normal")
        self.log_box.insert("end", f"[{timestamp}] {message}\n", level)
        line_count = int(self.log_box.index("end-1c").split(".")[0])
        if line_count > MAX_LOG_LINES:
            self.log_box.delete("1.0", f"{line_count - MAX_LOG_LINES}.0")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    def _on_close(self) -> None:
        if self.worker and self.worker.is_alive():
            if not messagebox.askyesno("Scraping in progress", "A scrape is running. Stop it and quit?"):
                return
            self.worker.stop()
            self.worker.join(timeout=5)
        self._write_batch()
        self._autosave()
        self.destroy()


def _slug(text: str) -> str:
    """'Web Development Agency' -> 'Web_Development_Agency' (safe for file and folder names)."""
    return re.sub(r"[^A-Za-z0-9]+", "_", text).strip("_") or "leads"


def run() -> None:
    ctk.set_appearance_mode("light")
    ctk.set_default_color_theme("blue")
    app = LeadScraperApp()
    app.mainloop()


if __name__ == "__main__":
    run()
