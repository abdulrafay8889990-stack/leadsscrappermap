"""Visual design system: a light, soft "pastel glass" look - lavender-white background, white
rounded cards, pastel accent chips (lavender, mint, peach, sky) and a glossy blue orb logo.

apply_theme() must run before any widget is created: it rewrites CustomTkinter's default
theme so every standard widget (entries, menus, switches, ...) already matches.
"""
from __future__ import annotations

import math
import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk

import customtkinter as ctk

# ----------------------------------------------------------------- palette
BG = "#eef0f9"          # window background (lavender white)
CARD = "#ffffff"        # cards
PANEL = "#f7f8fd"       # inner panel inside a card
INPUT = "#ffffff"       # entries, text boxes
BORDER = "#e4e6f2"
BORDER_HI = "#d6d9eb"
HOVER = "#f0f1fa"
SELECTED = "#ebe8ff"
TEXT = "#15161d"
MUTED = "#686d80"
FAINT = "#9ba0b3"

PRIMARY = "#5b5cf6"     # main action (indigo-violet)
PRIMARY_HOVER = "#4a4be6"
INK = "#16171d"         # dark pill buttons

BLUE = "#4f6bff"
BLUE_BG = "#e6ebff"
GREEN = "#14a06a"
GREEN_BG = "#ddf5ec"
YELLOW = "#d98a1c"
YELLOW_BG = "#fdf0dc"
RED = "#e0464c"
RED_BG = "#fde7e8"
PINK = "#d9488f"
PINK_BG = "#fbe5f0"
PURPLE = "#6c55f5"
PURPLE_BG = "#ece8ff"
ORANGE = YELLOW
WHITE = "#ffffff"

LOG_COLORS = {"info": "#3b3f50", "success": GREEN, "warning": "#c07510", "error": RED, "skip": FAINT}

FONT = "Segoe UI"
DISPLAY = "Segoe UI"
MONO = "Cascadia Mono"
ICON_FONT = "Segoe Fluent Icons"

# Segoe Fluent Icons / MDL2 code points
ICONS = {
    "play": "", "pause": "", "stop": "", "download": "", "share": "",
    "folder": "", "delete": "", "refresh": "", "settings": "", "history": "",
    "mail": "", "search": "", "send": "", "filter": "", "globe": "",
    "add": "", "save": "", "left": "", "right": "", "eye": "",
    "attach": "", "link": "", "check": "", "close": "", "map": "",
    "bolt": "", "list": "", "people": "", "clock": "", "test": "",
    "upload": "", "reset": "", "clear": "", "more": "", "plug": "",
    "phone": "", "skip": "", "file": "",
}


def icon(name: str) -> str:
    return ICONS.get(name, "")


def apply_theme(root: tk.Misc) -> None:
    """Call right after creating the CTk window and before creating any other widget."""
    global FONT, DISPLAY, MONO, ICON_FONT
    families = set(tkfont.families(root))
    FONT = next((f for f in ("Segoe UI Variable Text", "Segoe UI", "Arial") if f in families), "TkDefaultFont")
    DISPLAY = next((f for f in ("Segoe UI Variable Display", "Segoe UI Semibold", "Segoe UI") if f in families), FONT)
    MONO = next((f for f in ("Cascadia Mono", "Consolas", "Courier New") if f in families), "TkFixedFont")
    ICON_FONT = next((f for f in ("Segoe Fluent Icons", "Segoe MDL2 Assets") if f in families), FONT)
    ctk.set_appearance_mode("light")

    def c(value):
        return [value, value]

    t = ctk.ThemeManager.theme
    t["CTkFont"].update(family=FONT, size=13)
    t["CTk"]["fg_color"] = c(BG)
    t["CTkToplevel"]["fg_color"] = c(BG)
    t["CTkFrame"].update(fg_color=c(CARD), top_fg_color=c(PANEL), border_color=c(BORDER), corner_radius=16)
    t["CTkLabel"].update(text_color=c(TEXT))
    t["CTkButton"].update(fg_color=c(CARD), hover_color=c(HOVER), border_color=c(BORDER_HI), border_width=1,
                          text_color=c(TEXT), text_color_disabled=c(FAINT), corner_radius=12)
    t["CTkEntry"].update(fg_color=c(INPUT), border_color=c(BORDER), text_color=c(TEXT),
                         placeholder_text_color=c(FAINT), corner_radius=12, border_width=1)
    t["CTkTextbox"].update(fg_color=c(INPUT), border_color=c(BORDER), text_color=c(TEXT), corner_radius=12,
                           border_width=1, scrollbar_button_color=c(BORDER_HI), scrollbar_button_hover_color=c(FAINT))
    t["CTkOptionMenu"].update(fg_color=c(PANEL), button_color=c(PANEL), button_hover_color=c(HOVER),
                              text_color=c(TEXT), text_color_disabled=c(FAINT), corner_radius=12)
    t["CTkComboBox"].update(fg_color=c(INPUT), border_color=c(BORDER), button_color=c(PANEL),
                            button_hover_color=c(HOVER), text_color=c(TEXT))
    t["CTkSegmentedButton"].update(fg_color=c("#eceef8"), selected_color=c(CARD), selected_hover_color=c(CARD),
                                   unselected_color=c("#eceef8"), unselected_hover_color=c("#e3e6f4"),
                                   text_color=c(TEXT), text_color_disabled=c(FAINT), corner_radius=12, border_width=3)
    t["CTkSwitch"].update(fg_color=c("#dde0ee"), progress_color=c(PRIMARY), button_color=c(WHITE),
                          button_hover_color=c(WHITE), text_color=c(TEXT), text_color_disabled=c(FAINT))
    t["CTkCheckBox"].update(fg_color=c(PRIMARY), border_color=c(BORDER_HI), hover_color=c(PRIMARY_HOVER),
                            checkmark_color=c(WHITE), text_color=c(TEXT), corner_radius=6, border_width=2)
    t["CTkProgressBar"].update(fg_color=c("#e4e6f3"), progress_color=c(PRIMARY), border_color=c(BORDER),
                               corner_radius=6)
    t["CTkScrollbar"].update(fg_color="transparent", button_color=c("#d3d6e6"), button_hover_color=c("#b9bdd3"))
    t["CTkScrollableFrame"].update(label_fg_color=c(CARD))
    t["DropdownMenu"].update(fg_color=c(CARD), hover_color=c(SELECTED), text_color=c(TEXT))


def font(size: int = 13, weight: str = "normal", family: str | None = None) -> ctk.CTkFont:
    return ctk.CTkFont(family=family or FONT, size=size, weight=weight)


def display_font(size: int = 24, weight: str = "bold") -> ctk.CTkFont:
    return ctk.CTkFont(family=DISPLAY, size=size, weight=weight)


def icon_font(size: int = 13) -> ctk.CTkFont:
    return ctk.CTkFont(family=ICON_FONT, size=size)


# ------------------------------------------------------------- components
class Node(ctk.CTkFrame):
    """A white rounded card: header (tinted icon chip or dot, title, optional pill badge) + body."""

    def __init__(self, master, title: str, dot: str = PRIMARY, badge: str | None = None,
                 badge_color: str = GREEN, badge_bg: str = GREEN_BG, inner: bool = False, bg: str = BG,
                 icon_name: str | None = None, tint: str = PURPLE_BG) -> None:
        super().__init__(master, fg_color=CARD, border_color=BORDER, border_width=1, corner_radius=20, bg_color=bg)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        header = ctk.CTkFrame(self, fg_color="transparent", height=40)
        header.grid(row=0, column=0, sticky="ew", padx=16, pady=(14, 4))
        if icon_name:
            self.dot = ctk.CTkLabel(header, text=icon(icon_name), font=icon_font(13), text_color=dot,
                                    fg_color=tint, corner_radius=9, width=28, height=28)
        else:
            self.dot = ctk.CTkLabel(header, text="●", text_color=dot, font=font(9), width=10)
        self.dot.pack(side="left")
        ctk.CTkLabel(header, text=title, font=font(13, "bold"), text_color=TEXT).pack(side="left", padx=(10, 0))
        self.badge = ctk.CTkLabel(header, text=badge or "", fg_color=badge_bg if badge else "transparent",
                                  text_color=badge_color, corner_radius=10, font=font(11), height=24,
                                  padx=10 if badge else 0)
        self.badge.pack(side="right")
        self.header = header

        if inner:
            self.body = ctk.CTkFrame(self, fg_color=PANEL, border_color=BORDER, border_width=1, corner_radius=14)
            self.body.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 8))
        else:
            self.body = ctk.CTkFrame(self, fg_color="transparent")
            self.body.grid(row=1, column=0, sticky="nsew", padx=2, pady=(0, 6))
        self.body.grid_columnconfigure(0, weight=1)

    def set_badge(self, text: str, color: str = GREEN, bg: str = GREEN_BG) -> None:
        self.badge.configure(text=text, text_color=color, fg_color=bg if text else "transparent",
                             padx=10 if text else 0)

    def set_dot(self, color: str) -> None:
        self.dot.configure(text_color=color)


def label(parent, text: str, size: int = 12, color: str = MUTED, weight: str = "normal", **kw) -> ctk.CTkLabel:
    return ctk.CTkLabel(parent, text=text, font=font(size, weight), text_color=color, anchor="w", **kw)


def pill(parent, text: str = "", icon_name: str | None = None, kind: str = "ghost", command=None,
         width: int = 0, height: int = 34, size: int = 12) -> ctk.CTkButton:
    """kind: ghost (white), primary (dark ink), go (indigo), danger (red tint), soft (lavender tint),
    warn (peach tint), plain (no background)."""
    # Windows font fallback draws the icon glyph inside normal Segoe UI text.
    caption = f"{icon(icon_name)}   {text}" if icon_name and text else (icon(icon_name) if icon_name else text)
    button = ctk.CTkButton(parent, text=caption, command=command, height=height, corner_radius=height // 2,
                           font=font(size, "bold" if kind in ("go", "primary") else "normal") if text
                           else icon_font(size + 1),
                           width=width or (height if not text else 0), **PILL_STYLES[kind])
    button.kind = kind
    return button


def restyle(button: ctk.CTkButton, kind: str) -> None:
    """Switch a pill between kinds, e.g. Start (go) <-> Stop (danger)."""
    button.configure(**PILL_STYLES[kind])
    button.kind = kind


PILL_STYLES = {
    "ghost": dict(fg_color=CARD, hover_color=HOVER, text_color=TEXT, border_color=BORDER_HI, border_width=1,
                  text_color_disabled=FAINT),
    "primary": dict(fg_color=INK, hover_color="#2b2d38", text_color=WHITE, border_color=INK, border_width=0,
                    text_color_disabled="#8d90a0"),
    "go": dict(fg_color=PRIMARY, hover_color=PRIMARY_HOVER, text_color=WHITE, border_color=PRIMARY, border_width=0,
               text_color_disabled="#c9caf9"),
    "danger": dict(fg_color=RED_BG, hover_color="#fbd6d8", text_color=RED, border_color="#f7c9cc", border_width=1,
                   text_color_disabled="#f0a3a6"),
    "soft": dict(fg_color=PURPLE_BG, hover_color="#e0dbff", text_color=PURPLE, border_color=PURPLE_BG,
                 border_width=0, text_color_disabled=FAINT),
    "warn": dict(fg_color=YELLOW_BG, hover_color="#fbe5c4", text_color=YELLOW, border_color=YELLOW_BG,
                 border_width=0, text_color_disabled=FAINT),
    "plain": dict(fg_color="transparent", hover_color=HOVER, text_color=MUTED, border_color=CARD, border_width=0,
                  text_color_disabled=FAINT),
}


def icon_button(parent, icon_name: str, command=None, tooltip: str = "", size: int = 34,
                kind: str = "ghost") -> ctk.CTkButton:
    button = pill(parent, icon_name=icon_name, kind=kind, command=command, height=size, width=size)
    button.configure(font=icon_font(13))
    if tooltip:
        Tooltip(button, tooltip)
    return button


class Tooltip:
    """Small dark tooltip shown on hover."""

    def __init__(self, widget, text: str) -> None:
        self.widget, self.text, self.tip = widget, text, None
        # Some CustomTkinter widgets (e.g. CTkSegmentedButton) refuse bind(): use their inner parts.
        if not self._bind(widget):
            for child in widget.winfo_children():
                self._bind(child)

    def _bind(self, target) -> bool:
        try:
            target.bind("<Enter>", self.show, add="+")
            target.bind("<Leave>", self.hide, add="+")
            return True
        except NotImplementedError:
            return False

    def show(self, _event=None) -> None:
        if self.tip:
            return
        x = self.widget.winfo_rootx() + self.widget.winfo_width() + 8
        y = self.widget.winfo_rooty() + 4
        self.tip = tk.Toplevel(self.widget)
        self.tip.wm_overrideredirect(True)
        self.tip.configure(bg=INK)
        tk.Label(self.tip, text=self.text, bg=INK, fg=WHITE, font=(FONT, 9), padx=10, pady=5, wraplength=320,
                 justify="left").pack()
        self.tip.wm_geometry(f"+{x}+{y}")

    def hide(self, _event=None) -> None:
        if self.tip:
            self.tip.destroy()
            self.tip = None


def style_treeview(widget, name: str = "Node.Treeview", rowheight: int = 30) -> str:
    style = ttk.Style(widget)
    style.theme_use("clam")
    style.configure(name, background=CARD, fieldbackground=CARD, foreground=TEXT, rowheight=rowheight,
                    borderwidth=0, relief="flat", font=(FONT, 10))
    style.configure(f"{name}.Heading", background=PANEL, foreground=MUTED, relief="flat", borderwidth=0,
                    font=(FONT, 9, "bold"), padding=(6, 6))
    style.map(name, background=[("selected", SELECTED)], foreground=[("selected", TEXT)])
    style.map(f"{name}.Heading", background=[("active", HOVER)])
    style.layout(name, [("Treeview.treearea", {"sticky": "nswe"})])  # drop the default 3D border
    return name


def tree(parent, columns: dict[str, int], name: str = "Node.Treeview", height: int = 8,
         titles: dict[str, str] | None = None) -> ttk.Treeview:
    style_treeview(parent, name)
    widget = ttk.Treeview(parent, columns=list(columns), show="headings", style=name, height=height)
    for column, width in columns.items():
        widget.heading(column, text=(titles or {}).get(column, column), anchor="w")
        widget.column(column, width=width, minwidth=40, anchor="w", stretch=True)
    widget.tag_configure("odd", background="#f8f9fd")
    return widget


def log_box(parent, height: int = 120) -> ctk.CTkTextbox:
    box = ctk.CTkTextbox(parent, height=height, wrap="word", font=font(11, family=MONO), fg_color=PANEL,
                         border_width=0, corner_radius=12, text_color=TEXT)
    for level, color in LOG_COLORS.items():
        box.tag_config(level, foreground=color)
    box.configure(state="disabled")
    return box


# ------------------------------------------------------------- drawings
def _mix(a: str, b: str, amount: float) -> str:
    """Blend two #rrggbb colours (0 -> a, 1 -> b)."""
    ca = [int(a[i:i + 2], 16) for i in (1, 3, 5)]
    cb = [int(b[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x + (y - x) * amount):02x}" for x, y in zip(ca, cb))


def gradient_card(canvas: tk.Canvas, width: int, height: int, stops: list[str], radius: int,
                  background: str) -> None:
    """Diagonal multi-stop gradient with rounded corners (corners painted in `background`)."""
    steps = width + height
    for i in range(0, steps, 2):
        t = i / steps * (len(stops) - 1)
        index = min(int(t), len(stops) - 2)
        color = _mix(stops[index], stops[index + 1], t - index)
        # each diagonal line x + y = i
        canvas.create_line(i, 0, i - height, height, fill=color, width=3)
    # rounded corners: paint the area outside a quarter circle in the page background
    for cx, cy, start in ((radius, radius, 90), (width - radius, radius, 0),
                          (width - radius, height - radius, 270), (radius, height - radius, 180)):
        corner_x = 0 if cx == radius else width
        corner_y = 0 if cy == radius else height
        points = [corner_x, corner_y]
        for step in range(0, 91, 6):
            angle = math.radians(start + step)
            points += [cx + radius * math.cos(angle), cy - radius * math.sin(angle)]
        canvas.create_polygon(points, fill=background, outline=background)


def orb(canvas: tk.Canvas, cx: float, cy: float, r: float, eyes: bool = True) -> None:
    """Glossy blue orb (soft radial shading, top-left highlight) with two little eyes."""
    rings = max(int(r), 12)
    for i in range(rings, 0, -1):
        t = i / rings                      # 1 = outer edge, 0 = centre of the highlight
        color = _mix("#a9b7ff", "#2f45ff", t ** 1.4)
        rr = r * t
        # shift the lighter inner rings up-left, so the light comes from the top-left
        ox, oy = (1 - t) * -r * 0.28, (1 - t) * -r * 0.32
        canvas.create_oval(cx + ox - rr, cy + oy - rr, cx + ox + rr, cy + oy + rr, fill=color, outline=color)
    if eyes:
        ew, eh, gap = r * 0.11, r * 0.24, r * 0.26
        for side in (-1, 1):
            ex = cx + side * gap
            canvas.create_oval(ex - ew, cy - eh * 0.6, ex + ew, cy + eh * 0.9, fill=WHITE, outline=WHITE)
