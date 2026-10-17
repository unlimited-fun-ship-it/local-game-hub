"""Mastermind - a Mastermind-style code-breaking game.

Rules:
  * The codemaker picks a hidden sequence of coloured pegs.
  * The codebreaker guesses a full row each turn.
  * After each guess, feedback pegs are awarded:
      - BLACK: correct colour in the correct slot.
      - WHITE: correct colour in the wrong slot.
    Feedback does not say *which* pegs are which.
  * Break the code before running out of rows.

Settings (via the Settings button):
  * Code length (1-50)
  * Maximum guesses (1-100)
  * Number of colours in play (1-50)
  * Allow or forbid duplicate colours in the secret code.
    (The codebreaker's guesses may ALWAYS contain duplicates - that is
    part of the game's strategy space and is never restricted.)
  * Display mode: colours only / numbers only / both

Zoom (via the - / + buttons or Ctrl+-/=):
  * Scales the board inside the canvas only.
  * Does not resize the window, palette, or any other widget.
  * 100% == auto-fit; higher = larger (scrolls); lower = smaller (padded).
"""

import colorsys
import random
from collections import Counter
from types import SimpleNamespace

import tkinter as tk

import save_manager
from theme import theme

GAME_ID = "mastermind"

# Practical caps. The old limits (8/20/8) were hardcoded to the palette size;
# these are just guards so a stray keystroke can't freeze the canvas. Values
# above the caps set directly in settings.json get clamped on load.
MIN_CODE_LEN = 1
MAX_CODE_LEN = 50
MIN_ROWS = 1
MAX_ROWS = 100
MIN_COLORS = 1
MAX_COLORS = 50

# Cell-size bounds for the board.
MIN_CELL_FIT = 20    # below this we stop shrinking and turn on scrolling
MIN_CELL_ABS = 4     # absolute floor (only reached on very narrow windows)
MAX_CELL = 42        # upper cap on the *auto-fit* cell (zoom may exceed it)

# Practical cap on palette buttons per row before wrapping to a new row.
PALETTE_COLUMNS = 10

# Feedback pegs are laid out in a single horizontal row. Each code slot gets
# this many cell-widths of horizontal space for its feedback peg. 0.55 * 4
# == 2.2, which is exactly the old fixed feedback width for the default
# code length of 4, so the default board looks unchanged.
FB_SLOT_FACTOR = 0.55

# Board zoom: 1.0 == auto-fit. 0.5..3.0 in 0.25 steps gives 50%..300%.
MIN_ZOOM = 0.5
MAX_ZOOM = 3.0
ZOOM_STEP = 0.25


# ============================================================ dynamic palette
PEG_COLORS = []
_active_palette_size = 0


def ensure_palette(n):
    """Populate PEG_COLORS with n visually distinct hex colours."""
    global PEG_COLORS, _active_palette_size
    n = max(1, int(n))
    if n == _active_palette_size:
        return

    _active_palette_size = n
    PEG_COLORS.clear()

    if n <= 13:
        for i in range(n):
            hue = i / n
            r, g, b = colorsys.hsv_to_rgb(hue, 0.85, 0.85)
            PEG_COLORS.append("#{:02x}{:02x}{:02x}".format(
                int(r * 255 + 0.5), int(g * 255 + 0.5), int(b * 255 + 0.5)))
    else:
        golden = 0.618033988749895
        bands = [(0.85, 0.85), (0.60, 0.95), (0.95, 0.65)]
        for i in range(n):
            hue = (i * golden) % 1.0
            sat, val = bands[i % 3]
            r, g, b = colorsys.hsv_to_rgb(hue, sat, val)
            PEG_COLORS.append("#{:02x}{:02x}{:02x}".format(
                int(r * 255 + 0.5), int(g * 255 + 0.5), int(b * 255 + 0.5)))


ensure_palette(6)


PRESETS = {
    "Easy":   {"code_len": 4, "n_colors": 4, "max_rows": 10,
               "allow_duplicates": False, "display": "both"},
    "Medium": {"code_len": 4, "n_colors": 6, "max_rows": 10,
               "allow_duplicates": True, "display": "both"},
    "Hard":   {"code_len": 5, "n_colors": 8, "max_rows": 12,
               "allow_duplicates": True, "display": "both"},
}

DISPLAY_MODES = [
    ("Colours only", "colors"),
    ("Numbers only", "numbers"),
    ("Both", "both"),
]


# ============================================================ settings
class MastermindSettings:
    def __init__(self):
        self.code_len = 4
        self.max_rows = 10
        self.n_colors = 6
        self.allow_duplicates = True
        self.display = "both"

    def to_dict(self):
        return {
            "code_len": self.code_len,
            "max_rows": self.max_rows,
            "n_colors": self.n_colors,
            "allow_duplicates": self.allow_duplicates,
            "display": self.display,
        }

    @classmethod
    def from_dict(cls, data):
        s = cls()
        try:
            s.code_len = max(MIN_CODE_LEN,
                             min(MAX_CODE_LEN, int(data.get("code_len", 4))))
            s.max_rows = max(MIN_ROWS,
                             min(MAX_ROWS, int(data.get("max_rows", 10))))
            s.n_colors = max(MIN_COLORS,
                             min(MAX_COLORS, int(data.get("n_colors", 6))))
        except (TypeError, ValueError):
            pass
        s.allow_duplicates = bool(data.get("allow_duplicates", True))
        if data.get("display") in ("colors", "numbers", "both"):
            s.display = data["display"]
        return s

    def is_valid(self):
        if not (MIN_CODE_LEN <= self.code_len <= MAX_CODE_LEN):
            return False, (f"Code length must be between "
                           f"{MIN_CODE_LEN} and {MAX_CODE_LEN}.")
        if not (MIN_ROWS <= self.max_rows <= MAX_ROWS):
            return False, (f"Max guesses must be between "
                           f"{MIN_ROWS} and {MAX_ROWS}.")
        if not (MIN_COLORS <= self.n_colors <= MAX_COLORS):
            return False, (f"Number of colours must be between "
                           f"{MIN_COLORS} and {MAX_COLORS}.")
        if not self.allow_duplicates and self.code_len > self.n_colors:
            return False, ("Code length exceeds the number of colours. "
                           "Enable duplicates or reduce the code length.")
        return True, ""


# ============================================================ rules engine
def evaluate_guess(secret, guess):
    black = sum(1 for s, g in zip(secret, guess) if s == g)
    secret_counts = Counter(secret)
    guess_counts = Counter(guess)
    total_matches = sum(
        min(secret_counts[c], guess_counts[c]) for c in secret_counts
    )
    return black, total_matches - black


def _peg_text_color(bg_hex):
    r = int(bg_hex[1:3], 16)
    g = int(bg_hex[3:5], 16)
    b = int(bg_hex[5:7], 16)
    return "#000000" if (0.299 * r + 0.587 * g + 0.114 * b) > 150 else "#ffffff"


def _peg_look(color_idx, display_mode):
    """(fill, text, text_fg) for a peg in the current display mode."""
    if display_mode == "colors":
        return PEG_COLORS[color_idx], "", None
    elif display_mode == "numbers":
        return theme.color("fg"), str(color_idx + 1), theme.color("bg")
    else:  # "both"
        bg = PEG_COLORS[color_idx]
        return bg, str(color_idx + 1), _peg_text_color(bg)


def _generate_code(settings):
    if settings.allow_duplicates:
        return [random.randrange(settings.n_colors)
                for _ in range(settings.code_len)]
    if settings.code_len <= settings.n_colors:
        return random.sample(range(settings.n_colors), settings.code_len)
    return [random.randrange(settings.n_colors)
            for _ in range(settings.code_len)]


# ============================================================ circular peg button
class PegButton(tk.Canvas):
    """Circular colour swatch drawn on a Canvas."""

    SIZE = 34

    def __init__(self, parent, idx, command):
        super().__init__(parent, width=self.SIZE, height=self.SIZE,
                         highlightthickness=0, bd=0)
        self.idx = idx
        self.command = command
        self.display_mode = "both"
        self._hover = False
        self._enabled = True
        self.bind("<Button-1>", self._on_click)
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self._draw()

    def _on_click(self, _e):
        if self._enabled:
            self.command(self.idx)

    def _on_enter(self, _e):
        self._hover = True
        self._draw()

    def _on_leave(self, _e):
        self._hover = False
        self._draw()

    def set_display_mode(self, mode):
        if self.display_mode == mode:
            return
        self.display_mode = mode
        self._draw()

    def set_enabled(self, enabled):
        if self._enabled == enabled:
            return
        self._enabled = enabled
        self._draw()

    def refresh(self):
        self._draw()

    def _draw(self):
        self.delete("all")
        self.configure(bg=theme.color("bg"))

        s = self.SIZE
        if not self._enabled:
            fill = theme.color("subtle")
            text = ""
            text_fg = theme.color("muted")
            outline = theme.color("subtle")
        else:
            fill, text, text_fg = _peg_look(self.idx, self.display_mode)
            outline = (theme.color("button_hover") if self._hover
                       else theme.color("fg"))

        r = s * 0.42
        self.create_oval(s / 2 - r, s / 2 - r, s / 2 + r, s / 2 + r,
                         fill=fill, outline=outline,
                         width=2 if (self._hover and self._enabled) else 1)
        if text:
            self.create_text(s / 2, s / 2, text=text,
                             fill=text_fg or theme.color("fg"),
                             font=(theme.font_family,
                                   max(8, int(s * 0.36)), "bold"))


# ============================================================ codemaker dialog
class SecretCodeDialog(tk.Toplevel):
    def __init__(self, master, settings):
        super().__init__(master)
        self.title("Codemaker - set the secret code")
        self.transient(master)
        self.resizable(False, False)

        self.settings = settings
        self.slots = [None] * settings.code_len
        self.result = None

        ensure_palette(settings.n_colors)

        bg = theme.color("bg")
        fg = theme.color("fg")
        self.configure(bg=bg)

        tk.Label(self, text="Choose the secret code (the codebreaker must not look):",
                 bg=bg, fg=fg, font=theme.font("body")).pack(padx=16, pady=(14, 8))

        self.slot_frame = tk.Frame(self, bg=bg)
        self.slot_frame.pack(padx=16, pady=(0, 10))
        self.slot_labels = []
        for _ in range(settings.code_len):
            lbl = tk.Label(self.slot_frame, width=4, height=2,
                           relief="flat", bd=1, bg=theme.color("card"),
                           font=theme.font("button", "bold"))
            lbl.grid(row=0, column=len(self.slot_labels), padx=3)
            self.slot_labels.append(lbl)

        self.pal = tk.Frame(self, bg=bg)
        self.pal.pack(padx=16, pady=(0, 10))
        self.palette_buttons = []
        self._setup_palette()

        self._refresh_slots()

        btns = tk.Frame(self, bg=bg)
        btns.pack(fill="x", padx=16, pady=(0, 14))
        self._ok_btn = tk.Button(btns, text="Set Code", command=self._ok,
                                 relief="flat", bd=0, padx=12, pady=4,
                                 bg=theme.color("button_bg"),
                                 fg=theme.color("button_fg"),
                                 activebackground=theme.color("button_hover"),
                                 activeforeground=theme.color("button_fg"),
                                 font=theme.font("button"))
        self._ok_btn.pack(side="right", padx=(6, 0))
        tk.Button(btns, text="Random", command=self._random,
                  relief="flat", bd=0, padx=12, pady=4,
                  bg=theme.color("button_bg"), fg=theme.color("button_fg"),
                  activebackground=theme.color("button_hover"),
                  activeforeground=theme.color("button_fg"),
                  font=theme.font("button")).pack(side="right", padx=(6, 0))
        tk.Button(btns, text="Cancel", command=self._cancel,
                  relief="flat", bd=0, padx=12, pady=4,
                  bg=theme.color("button_bg"), fg=theme.color("button_fg"),
                  activebackground=theme.color("button_hover"),
                  activeforeground=theme.color("button_fg"),
                  font=theme.font("button")).pack(side="right")

        self.bind("<BackSpace>", lambda e: self._remove_last())
        self.bind("<Return>", lambda e: self._ok())
        self.bind("<Escape>", lambda e: self._cancel())

        self.update_idletasks()
        try:
            self.wait_visibility()
            self.grab_set()
        except tk.TclError:
            pass
        self.focus_set()

    def _setup_palette(self):
        for b in self.palette_buttons:
            b.destroy()
        self.palette_buttons = []
        n = self.settings.n_colors
        cols = min(PALETTE_COLUMNS, max(1, n))
        for i in range(n):
            r, c = divmod(i, cols)
            b = PegButton(self.pal, i, self._pick)
            b.set_display_mode(self.settings.display)
            b.grid(row=r, column=c, padx=3, pady=2)
            self.palette_buttons.append(b)

    def _pick(self, idx):
        # Codemaker rules: when duplicates are forbidden, only one of each
        # colour may appear in the secret code. (This restriction applies
        # to the codemaker only - the codebreaker may always guess
        # duplicates.)
        if not self.settings.allow_duplicates and idx in self.slots:
            return
        for i in range(self.settings.code_len):
            if self.slots[i] is None:
                self.slots[i] = idx
                break
        self._refresh_slots()

    def _remove_last(self):
        for i in range(self.settings.code_len - 1, -1, -1):
            if self.slots[i] is not None:
                self.slots[i] = None
                break
        self._refresh_slots()

    def _random(self):
        if self.settings.allow_duplicates:
            self.slots = [random.randrange(self.settings.n_colors)
                          for _ in range(self.settings.code_len)]
        elif self.settings.code_len <= self.settings.n_colors:
            self.slots = random.sample(range(self.settings.n_colors),
                                       self.settings.code_len)
        else:
            self.slots = [random.randrange(self.settings.n_colors)
                          for _ in range(self.settings.code_len)]
        self._refresh_slots()

    def _refresh_slots(self):
        mode = self.settings.display
        for i, lbl in enumerate(self.slot_labels):
            v = self.slots[i]
            if v is None:
                lbl.configure(bg=theme.color("card"), text="",
                              fg=theme.color("fg"))
            else:
                fill, text, text_fg = _peg_look(v, mode)
                lbl.configure(bg=fill, text=text,
                              fg=text_fg or theme.color("fg"))

        for i, b in enumerate(self.palette_buttons):
            used = (i in self.slots) and not self.settings.allow_duplicates
            b.set_enabled(not used)

        state = ("normal" if all(v is not None for v in self.slots)
                 else "disabled")
        self._ok_btn.configure(state=state)

    def _ok(self):
        if any(v is None for v in self.slots):
            return
        self.result = list(self.slots)
        self.destroy()

    def _cancel(self):
        self.result = None
        self.destroy()


# ============================================================ settings dialog
class GameSettingsDialog(tk.Toplevel):
    def __init__(self, master, current):
        super().__init__(master)
        self.title("Mastermind Settings")
        self.transient(master)
        self.resizable(True, True)
        self.minsize(340, 460)
        self.result = None

        bg = theme.color("bg")
        fg = theme.color("fg")
        btn_bg = theme.color("button_bg")
        btn_fg = theme.color("button_fg")
        hover = theme.color("button_hover")

        self.configure(bg=bg)

        body = tk.Frame(self, bg=bg)
        body.pack(fill="both", expand=True, padx=18, pady=14)
        body.columnconfigure(2, weight=1)

        preset_row = tk.Frame(body, bg=bg)
        preset_row.grid(row=0, column=0, columnspan=3, sticky="w",
                        pady=(0, 14))
        tk.Label(preset_row, text="Quick presets:",
                 bg=bg, fg=theme.color("muted"),
                 font=theme.font("small")).pack(side="left", padx=(0, 6))
        for name in PRESETS:
            tk.Button(preset_row, text=name,
                      command=lambda n=name: self._apply_preset(n),
                      relief="flat", bd=0, padx=8, pady=2,
                      bg=btn_bg, fg=btn_fg,
                      activebackground=hover, activeforeground=btn_fg,
                      font=theme.font("small")).pack(side="left", padx=2)

        self._code_len_var = tk.IntVar(value=current.code_len)
        self._max_rows_var = tk.IntVar(value=current.max_rows)
        self._n_colors_var = tk.IntVar(value=current.n_colors)
        self._allow_dup_var = tk.BooleanVar(value=current.allow_duplicates)
        self._display_var = tk.StringVar(value=current.display)

        row = 1
        row = self._row_spinbox(body, row,
                                f"Code length ({MIN_CODE_LEN}-{MAX_CODE_LEN}):",
                                self._code_len_var, MIN_CODE_LEN, MAX_CODE_LEN)
        row = self._row_spinbox(body, row,
                                f"Max guesses ({MIN_ROWS}-{MAX_ROWS}):",
                                self._max_rows_var, MIN_ROWS, MAX_ROWS)
        row = self._row_spinbox(body, row,
                                f"Number of colours ({MIN_COLORS}-{MAX_COLORS}):",
                                self._n_colors_var, MIN_COLORS, MAX_COLORS)

        tk.Checkbutton(body, text="Allow duplicate colours in the secret code\n"
                                  "(guesses may always repeat colours)",
                       variable=self._allow_dup_var,
                       bg=bg, fg=fg, selectcolor=btn_bg,
                       activebackground=bg, activeforeground=fg,
                       justify="left",
                       font=theme.font("body")).grid(
            row=row, column=0, columnspan=3, sticky="w", pady=(12, 4))
        row += 1

        tk.Label(body, text="Display mode:",
                 bg=bg, fg=fg,
                 font=theme.font("body")).grid(
            row=row, column=0, columnspan=3, sticky="w", pady=(12, 2))
        row += 1

        for text, val in DISPLAY_MODES:
            tk.Radiobutton(body, text=text, value=val,
                           variable=self._display_var,
                           bg=bg, fg=fg, selectcolor=btn_bg,
                           activebackground=bg, activeforeground=fg,
                           font=theme.font("body")).grid(
                row=row, column=0, columnspan=3, sticky="w", padx=(14, 0))
            row += 1

        self._warning_lbl = tk.Label(body, text="",
                                     bg=bg, fg=theme.color("accent_o"),
                                     font=theme.font("small"),
                                     wraplength=340, justify="left")
        self._warning_lbl.grid(row=row, column=0, columnspan=3,
                               sticky="w", pady=(8, 0))
        row += 1

        body.rowconfigure(row, weight=1)
        row += 1

        btns = tk.Frame(body, bg=bg)
        btns.grid(row=row, column=0, columnspan=3, sticky="e", pady=(14, 0))

        self._ok_btn = tk.Button(btns, text="Apply", command=self._ok,
                                 relief="flat", bd=0, padx=14, pady=4,
                                 bg=btn_bg, fg=btn_fg,
                                 activebackground=hover,
                                 activeforeground=btn_fg,
                                 font=theme.font("button"))
        self._ok_btn.pack(side="right", padx=(6, 0))
        tk.Button(btns, text="Cancel", command=self._cancel,
                  relief="flat", bd=0, padx=14, pady=4,
                  bg=btn_bg, fg=btn_fg,
                  activebackground=hover, activeforeground=btn_fg,
                  font=theme.font("button")).pack(side="right")

        for v in (self._code_len_var, self._max_rows_var, self._n_colors_var,
                  self._allow_dup_var):
            v.trace_add("write", lambda *_: self._validate())
        self._display_var.trace_add("write", lambda *_: self._validate())

        self._validate()

        self.bind("<Return>", lambda e: self._ok())
        self.bind("<Escape>", lambda e: self._cancel())

        self.update_idletasks()
        try:
            self.wait_visibility()
            self.grab_set()
        except tk.TclError:
            pass
        self.focus_set()

    def _row_spinbox(self, parent, row, label, var, min_val, max_val):
        bg = theme.color("bg")
        fg = theme.color("fg")
        tk.Label(parent, text=label, bg=bg, fg=fg,
                 font=theme.font("body")).grid(
            row=row, column=0, sticky="w", pady=4)
        tk.Spinbox(parent, from_=min_val, to=max_val, textvariable=var,
                   width=6, justify="center",
                   font=theme.font("body")).grid(
            row=row, column=1, sticky="w", padx=(8, 0), pady=4)
        return row + 1

    def _apply_preset(self, name):
        p = PRESETS[name]
        self._code_len_var.set(p["code_len"])
        self._max_rows_var.set(p["max_rows"])
        self._n_colors_var.set(p["n_colors"])
        self._allow_dup_var.set(p["allow_duplicates"])
        self._display_var.set(p["display"])

    def _validate(self):
        try:
            cl = self._code_len_var.get()
            mr = self._max_rows_var.get()
            nc = self._n_colors_var.get()
            ad = self._allow_dup_var.get()
        except tk.TclError:
            self._warning_lbl.config(text="Invalid numeric value.")
            self._ok_btn.configure(state="disabled")
            return False

        probe = MastermindSettings()
        probe.code_len = cl
        probe.max_rows = mr
        probe.n_colors = nc
        probe.allow_duplicates = ad
        probe.display = self._display_var.get()

        ok, msg = probe.is_valid()
        if not ok:
            self._warning_lbl.config(text=msg)
            self._ok_btn.configure(state="disabled")
            return False
        self._warning_lbl.config(text="")
        self._ok_btn.configure(state="normal")
        return True

    def _ok(self):
        if not self._validate():
            return
        s = MastermindSettings()
        s.code_len = self._code_len_var.get()
        s.max_rows = self._max_rows_var.get()
        s.n_colors = self._n_colors_var.get()
        s.allow_duplicates = self._allow_dup_var.get()
        s.display = self._display_var.get()
        self.result = s
        self.destroy()

    def _cancel(self):
        self.result = None
        self.destroy()


# ============================================================ main game
class Mastermind(tk.Toplevel):
    def __init__(self, master=None):
        super().__init__(master)
        self.title("Mastermind")
        self.geometry("640x800")
        self.minsize(460, 580)

        self.vs_computer = tk.BooleanVar(master=self, value=True)
        self.settings = MastermindSettings()

        self.n_colors = self.settings.n_colors
        self.code_len = self.settings.code_len
        self.max_rows = self.settings.max_rows
        self.display = self.settings.display

        # Board zoom multiplier on top of the auto-fit cell size.
        self.zoom = 1.0

        self.code = []
        self.guesses = []
        self.feedbacks = []
        self.current = []
        self.row_index = 0
        self.game_over = False
        self.won = False

        self.cell = 30
        self.offset_x = 0
        self.offset_y = 0
        self._scrollbar_visible = False

        ensure_palette(self.n_colors)

        self._build()
        self._update_zoom_label()
        self.apply_theme()
        self.new_game()
        self.focus_set()

    # ---------------------------------------------------------------- build
    def _build(self):
        self.status = tk.Label(self, text="")
        self.status.pack(pady=(12, 4))

        self.canvas_frame = tk.Frame(self)
        self.canvas_frame.pack(fill="both", expand=True, padx=12, pady=(0, 6))

        self.canvas = tk.Canvas(self.canvas_frame, highlightthickness=0)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.canvas.bind("<Configure>", self._on_canvas_resize)
        self.canvas.bind("<Button-1>", self.on_canvas_click)
        self.canvas.bind("<MouseWheel>", self._on_mousewheel)
        self.canvas.bind("<Button-4>", self._on_mousewheel)
        self.canvas.bind("<Button-5>", self._on_mousewheel)
        # Ctrl+wheel zooms the board instead of scrolling.
        self.canvas.bind("<Control-MouseWheel>", self._on_zoom_wheel)

        self.scrollbar = tk.Scrollbar(self.canvas_frame, orient="vertical",
                                      command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self._sidebar = tk.Frame(self.canvas_frame, width=16)
        self._sidebar.pack_propagate(False)
        self._sidebar.pack(side="right", fill="y")

        self.palette_frame = tk.Frame(self)
        self.palette_frame.pack(fill="x", padx=12, pady=(0, 4))
        self._palette_inner = tk.Frame(self.palette_frame)
        self._palette_inner.pack()
        self.palette_buttons = []
        self._setup_palette_buttons()

        self.bottom = tk.Frame(self)
        self.bottom.pack(fill="x", padx=12, pady=(0, 6))

        self.vs_cb = tk.Checkbutton(
            self.bottom, text="vs Computer",
            variable=self.vs_computer, command=self.new_game,
            relief="flat", bd=0, highlightthickness=0)
        self.vs_cb.pack(side="left")

        self.settings_btn = tk.Button(
            self.bottom, text="Settings",
            command=self.open_settings,
            relief="flat", bd=0, padx=10, pady=3)
        self.settings_btn.pack(side="left", padx=(8, 0))

        self.submit_btn = tk.Button(self.bottom, text="Submit Guess",
                                    command=self.submit_guess,
                                    relief="flat", bd=0, padx=10, pady=3)
        self.submit_btn.pack(side="right")

        self.delete_btn = tk.Button(self.bottom, text="Delete",
                                    command=self.delete_last,
                                    relief="flat", bd=0, padx=10, pady=3)
        self.delete_btn.pack(side="right", padx=(0, 4))

        self.new_btn = tk.Button(self.bottom, text="New",
                                 command=self.new_game, relief="flat", bd=0,
                                 padx=10, pady=3)
        self.new_btn.pack(side="right", padx=(0, 4))

        self.load_btn = tk.Button(self.bottom, text="Load",
                                  command=self.load_game, relief="flat", bd=0,
                                  padx=10, pady=3)
        self.load_btn.pack(side="right", padx=(0, 4))

        self.save_btn = tk.Button(self.bottom, text="Save",
                                  command=self.save_game, relief="flat", bd=0,
                                  padx=10, pady=3)
        self.save_btn.pack(side="right", padx=(0, 4))

        # ---- Zoom row (centred; does not affect other widgets) ----
        self.zoom_row = tk.Frame(self)
        self.zoom_row.pack(fill="x", padx=12, pady=(0, 4))
        self._zoom_inner = tk.Frame(self.zoom_row)
        self._zoom_inner.pack()

        self.zoom_out_btn = tk.Button(
            self._zoom_inner, text="\u2212", width=2,
            command=self.zoom_out, relief="flat", bd=0)
        self.zoom_out_btn.pack(side="left")

        self.zoom_lbl = tk.Label(self._zoom_inner, text="100%",
                                 width=5, anchor="center")
        self.zoom_lbl.pack(side="left", padx=4)

        self.zoom_in_btn = tk.Button(
            self._zoom_inner, text="+", width=2,
            command=self.zoom_in, relief="flat", bd=0)
        self.zoom_in_btn.pack(side="left")

        self.zoom_reset_btn = tk.Button(
            self._zoom_inner, text="Reset",
            command=self.zoom_reset, relief="flat", bd=0, padx=8)
        self.zoom_reset_btn.pack(side="left", padx=(10, 0))

        self.hint_lbl = tk.Label(
            self,
            text="Click a peg  •  Backspace deletes  •  Enter submits  •  "
                 "Ctrl+-/= zoom  •  R restarts")
        self.hint_lbl.pack(pady=(0, 12))

        self.bind("<KeyPress>", self.on_key)
        self.bind("<Control-plus>", self._key_zoom_in)
        self.bind("<Control-equal>", self._key_zoom_in)
        self.bind("<Control-KP_Add>", self._key_zoom_in)
        self.bind("<Control-minus>", self._key_zoom_out)
        self.bind("<Control-KP_Subtract>", self._key_zoom_out)
        self.bind("<Control-0>", self._key_zoom_reset)
        self.bind("<Control-KP_0>", self._key_zoom_reset)

    def _setup_palette_buttons(self):
        for b in self.palette_buttons:
            b.destroy()
        self.palette_buttons = []
        n = self.n_colors
        cols = min(PALETTE_COLUMNS, max(1, n))
        for i in range(n):
            r, c = divmod(i, cols)
            b = PegButton(self._palette_inner, i, self.pick_color)
            b.set_display_mode(self.display)
            b.grid(row=r, column=c, padx=4, pady=2)
            self.palette_buttons.append(b)

    def _fb_width_cells(self):
        """Feedback strip width in cell-units."""
        return self.code_len * FB_SLOT_FACTOR

    # ---------------------------------------------------------------- zoom
    def zoom_in(self):
        self._set_zoom(self.zoom + ZOOM_STEP)

    def zoom_out(self):
        self._set_zoom(self.zoom - ZOOM_STEP)

    def zoom_reset(self):
        self._set_zoom(1.0)

    def _set_zoom(self, new_zoom):
        new_zoom = round(max(MIN_ZOOM, min(MAX_ZOOM, new_zoom)),
                         4)
        if abs(new_zoom - self.zoom) < 0.001:
            return
        self.zoom = new_zoom
        self._update_zoom_label()
        self._trigger_relayout()
        self._scroll_to_current_row()

    def _update_zoom_label(self):
        self.zoom_lbl.config(text=f"{int(round(self.zoom * 100))}%")

    def _key_zoom_in(self, _e):
        self.zoom_in()
        return "break"

    def _key_zoom_out(self, _e):
        self.zoom_out()
        return "break"

    def _key_zoom_reset(self, _e):
        self.zoom_reset()
        return "break"

    def _on_zoom_wheel(self, event):
        if event.delta > 0:
            self.zoom_in()
        else:
            self.zoom_out()
        return "break"

    # ---------------------------------------------------------------- theme
    def apply_theme(self):
        bg = theme.color("bg")
        fg = theme.color("fg")
        btn_bg = theme.color("button_bg")
        btn_fg = theme.color("button_fg")
        hover = theme.color("button_hover")

        self.configure(bg=bg)
        self.status.configure(bg=bg, fg=fg, font=theme.font("status", "bold"))
        self.canvas.configure(bg=theme.color("canvas_bg"))
        self.canvas_frame.configure(bg=bg)
        self._sidebar.configure(bg=bg)
        self.palette_frame.configure(bg=bg)
        self._palette_inner.configure(bg=bg)
        self.bottom.configure(bg=bg)
        self.zoom_row.configure(bg=bg)
        self._zoom_inner.configure(bg=bg)
        self.hint_lbl.configure(bg=bg, fg=theme.color("muted"),
                                font=theme.font("small"))

        self.scrollbar.configure(
            bg=btn_bg,
            troughcolor=theme.color("canvas_bg"),
            activebackground=hover,
            highlightthickness=0,
            bd=0,
            relief="flat",
        )

        for b in self.palette_buttons:
            b.set_display_mode(self.display)
            b.refresh()

        for btn in (self.new_btn, self.save_btn, self.load_btn,
                    self.delete_btn, self.submit_btn, self.settings_btn,
                    self.zoom_out_btn, self.zoom_in_btn, self.zoom_reset_btn):
            btn.configure(bg=btn_bg, fg=btn_fg,
                          activebackground=hover, activeforeground=btn_fg,
                          font=theme.font("button"))
        self.zoom_lbl.configure(bg=bg, fg=fg, font=theme.font("body"))

        self.vs_cb.configure(bg=bg, fg=fg, selectcolor=btn_bg,
                             activebackground=bg, activeforeground=fg,
                             font=theme.font("body"))

        self.draw()

    # ----------------------------------------------------------- game flow
    def open_settings(self):
        dlg = GameSettingsDialog(self, self.settings)
        self.wait_window(dlg)
        if dlg.result is not None:
            self.settings = dlg.result
            self.new_game()

    def new_game(self):
        s = self.settings
        self.n_colors = s.n_colors
        self.code_len = s.code_len
        self.max_rows = s.max_rows
        self.display = s.display

        ensure_palette(self.n_colors)
        self._setup_palette_buttons()

        self.guesses = []
        self.feedbacks = []
        self.current = []
        self.row_index = 0
        self.game_over = False
        self.won = False

        if self.vs_computer.get():
            self.code = _generate_code(s)
        else:
            dlg = SecretCodeDialog(self, s)
            self.wait_window(dlg)
            if dlg.result is None:
                self.vs_computer.set(True)
                self.code = _generate_code(s)
            else:
                self.code = dlg.result

        self.apply_theme()
        self.update_status()
        self._trigger_relayout()

    def on_key(self, event):
        # Skip Ctrl-modified keys (they're reserved for the zoom shortcuts).
        if getattr(event, "state", 0) & 0x0004:
            return
        key = event.keysym.lower()
        if key == "r":
            self.new_game()
            return
        if self.game_over:
            return
        if key in ("backspace", "delete"):
            self.delete_last()
        elif key in ("return", "kp_enter"):
            self.submit_guess()
        elif key.isdigit() and 1 <= int(key) <= self.n_colors:
            self.pick_color(int(key) - 1)

    def pick_color(self, idx):
        """Add a peg to the current guess.

        The codebreaker may always repeat colours in their guess, regardless
        of the `allow_duplicates` setting, which only governs the secret
        code. Guessing duplicates is a legitimate probing strategy.
        """
        if self.game_over or idx >= self.n_colors:
            return
        if len(self.current) >= self.code_len:
            return
        self.current.append(idx)
        self.update_status()
        self.draw()

    def delete_last(self):
        if self.game_over or not self.current:
            return
        self.current.pop()
        self.update_status()
        self.draw()

    def submit_guess(self):
        if self.game_over:
            return
        if len(self.current) != self.code_len:
            return

        black, white = evaluate_guess(self.code, self.current)
        self.guesses.append(list(self.current))
        self.feedbacks.append((black, white))
        self.current = []
        self.row_index += 1

        if black == self.code_len:
            self.game_over = True
            self.won = True
        elif self.row_index >= self.max_rows:
            self.game_over = True
            self.won = False

        self.update_status()
        self.draw()
        if self.game_over:
            self._trigger_relayout()
        else:
            self._scroll_to_current_row()

    def update_status(self):
        if self.game_over:
            if self.won:
                n = len(self.guesses)
                self.status.config(
                    text=f"Cracked in {n} guess{'es' if n != 1 else ''}!")
            else:
                self.status.config(text="Out of rows - the code wins.")
            return
        remaining = self.max_rows - self.row_index
        if len(self.current) == self.code_len:
            self.status.config(
                text=f"Guess {self.row_index + 1}/{self.max_rows}"
                     f"  •  press Enter to submit")
        else:
            self.status.config(
                text=f"Guess {self.row_index + 1}/{self.max_rows}"
                     f"  •  {len(self.current)}/{self.code_len} pegs placed"
                     f"  •  {remaining} row{'s' if remaining != 1 else ''} left")

    # ----------------------------------------------------------- save/load
    def get_state(self):
        return {
            "code": self.code,
            "guesses": self.guesses,
            "feedbacks": self.feedbacks,
            "current": self.current,
            "row_index": self.row_index,
            "game_over": self.game_over,
            "won": self.won,
            "vs_computer": self.vs_computer.get(),
            "settings": self.settings.to_dict(),
            "zoom": self.zoom,
        }

    def set_state(self, data):
        if "settings" in data:
            self.settings = MastermindSettings.from_dict(data["settings"])
        else:
            s = MastermindSettings()
            s.code_len = data.get("code_len", 4)
            s.max_rows = data.get("max_rows", 10)
            s.n_colors = data.get("n_colors", 6)
            s.allow_duplicates = True
            s.display = "both" if data.get("show_numbers") else "colors"
            self.settings = s

        self.n_colors = self.settings.n_colors
        self.code_len = self.settings.code_len
        self.max_rows = self.settings.max_rows
        self.display = self.settings.display

        try:
            self.zoom = max(MIN_ZOOM, min(MAX_ZOOM,
                                          float(data.get("zoom", 1.0))))
        except (TypeError, ValueError):
            self.zoom = 1.0
        self._update_zoom_label()

        ensure_palette(self.n_colors)
        self._setup_palette_buttons()

        self.code = data["code"]
        self.guesses = [list(g) for g in data["guesses"]]
        self.feedbacks = [tuple(f) for f in data["feedbacks"]]
        self.current = list(data["current"])
        self.row_index = data["row_index"]
        self.game_over = data["game_over"]
        self.won = data["won"]
        self.vs_computer.set(data["vs_computer"])

        self.apply_theme()
        self.update_status()
        self._trigger_relayout()

    def save_game(self):
        save_manager.prompt_save(self, GAME_ID, self.get_state())

    def load_game(self):
        fname = save_manager.prompt_load(self, GAME_ID)
        if fname:
            data = save_manager.load_game(GAME_ID, fname)
            self.set_state(data)

    # ------------------------------------------------------------ geometry
    def _trigger_relayout(self):
        self.update_idletasks()
        w, h = self.canvas.winfo_width(), self.canvas.winfo_height()
        if w < 10 or h < 10:
            return
        self._on_canvas_resize(SimpleNamespace(width=w, height=h))

    def _on_canvas_resize(self, event):
        if event.width < 40 or event.height < 40:
            return

        avail_w = event.width - 20
        avail_h = event.height - 10

        # Feedback strip scales with code_len so pegs fit in a single row.
        fb_cells = self.code_len * FB_SLOT_FACTOR
        cell_w = avail_w / (self.code_len + fb_cells + 0.2)
        cell_h_fit = avail_h / self.max_rows / 1.15

        # ---- Auto-fit base cell (this is what "100% zoom" maps to) ----
        if cell_h_fit >= MIN_CELL_FIT:
            base_cell = min(cell_w, cell_h_fit, MAX_CELL)
        else:
            base_cell = min(cell_w, MIN_CELL_FIT)
        base_cell = max(MIN_CELL_ABS, base_cell)

        # ---- Apply user zoom. Zoom > 1 pushes content past the canvas,
        # which the scroll logic below handles naturally. Zoom < 1 pads. ----
        self.cell = max(1.0, base_cell * self.zoom)

        row_h = self.cell * 1.15
        board_w = self.cell * (self.code_len + fb_cells)
        content_h = self.max_rows * row_h
        if self.game_over:
            content_h += row_h * 1.2

        needs_scroll = content_h > avail_h + 1

        if needs_scroll and not self._scrollbar_visible:
            self._sidebar.pack_forget()
            self.scrollbar.pack(side="right", fill="y")
            self._scrollbar_visible = True
        elif not needs_scroll and self._scrollbar_visible:
            self.scrollbar.pack_forget()
            self._sidebar.pack(side="right", fill="y")
            self._scrollbar_visible = False

        if needs_scroll:
            self.offset_x = (event.width - board_w) / 2
            self.offset_y = 10
            self.canvas.configure(
                scrollregion=(0, 0, event.width, content_h + 20))
        else:
            self.offset_x = (event.width - board_w) / 2
            board_h = self.max_rows * row_h
            self.offset_y = (event.height - board_h) / 2
            self.canvas.configure(
                scrollregion=(0, 0, event.width, event.height))
            self.canvas.yview_moveto(0)

        self.draw()

    def _scroll_to_current_row(self):
        if not self._scrollbar_visible:
            return
        canvas_h = self.canvas.winfo_height()
        if canvas_h <= 0:
            return
        row_h = self.cell * 1.15
        row_top = self.offset_y + self.row_index * row_h
        row_bot = row_top + row_h

        view_top = self.canvas.canvasy(0)
        view_bot = view_top + canvas_h
        if row_top >= view_top and row_bot <= view_bot:
            return

        target_top = row_top - canvas_h / 2 + row_h / 2
        bbox = self.canvas.bbox("all")
        if not bbox:
            return
        content_h = bbox[3] - bbox[1]
        if content_h <= 0:
            return
        frac = max(0.0, min(1.0, target_top / content_h))
        self.canvas.yview_moveto(frac)

    def _on_mousewheel(self, event):
        # Skip if Control is held - that's a zoom gesture, not a scroll.
        if getattr(event, "state", 0) & 0x0004:
            return
        if not self._scrollbar_visible:
            return
        if event.num == 4:
            delta = -1
        elif event.num == 5:
            delta = 1
        else:
            delta = -1 if event.delta > 0 else 1
        self.canvas.yview_scroll(delta, "units")

    def _px(self, c):
        return self.offset_x + c * self.cell

    def _py(self, r):
        return self.offset_y + r * self.cell * 1.15

    # ------------------------------------------------------------ drawing
    def _refresh_palette_state(self):
        """Palette buttons are only disabled when the row is full or the
        game is over. They are never disabled for being 'already used',
        because guesses may freely repeat colours."""
        full = len(self.current) >= self.code_len
        for b in self.palette_buttons:
            b.set_enabled(not (self.game_over or full))

    def draw(self):
        if self.cell <= 0:
            return
        self.canvas.delete("all")

        row_h = self.cell * 1.15
        radius = self.cell * 0.38

        # Feedback strip: one horizontal row, one slot per code position.
        fb_start_x = self.offset_x + self.code_len * self.cell
        fb_slot_w = self.cell * FB_SLOT_FACTOR
        fb_strip_w = self.code_len * fb_slot_w

        for r in range(self.max_rows):
            y_center = self._py(r) + row_h / 2
            is_current = (r == self.row_index and not self.game_over)

            if is_current:
                self.canvas.create_rectangle(
                    self.offset_x - 4, self._py(r),
                    fb_start_x + fb_strip_w + 4,
                    self._py(r) + row_h,
                    outline=theme.color("accent_x"), width=2, fill="")

            if r < len(self.guesses):
                peg_row = self.guesses[r]
            elif is_current:
                peg_row = self.current
            else:
                peg_row = []

            for c in range(self.code_len):
                cx = self._px(c) + self.cell / 2
                if c < len(peg_row):
                    fill, text, text_fg = _peg_look(peg_row[c], self.display)
                    self.canvas.create_oval(
                        cx - radius, y_center - radius,
                        cx + radius, y_center + radius,
                        fill=fill, outline=theme.color("fg"), width=1)
                    if text:
                        self.canvas.create_text(
                            cx, y_center, text=text,
                            fill=text_fg or theme.color("fg"),
                            font=(theme.font_family,
                                  max(7, int(self.cell * 0.32)), "bold"))
                else:
                    self.canvas.create_oval(
                        cx - radius, y_center - radius,
                        cx + radius, y_center + radius,
                        fill="", outline=theme.color("subtle"), width=1)

            if r < len(self.feedbacks):
                black, white = self.feedbacks[r]
                n_marks = black + white
                if n_marks:
                    fb_radius = max(1, min(self.cell * 0.14,
                                           fb_slot_w * 0.42))
                    for i in range(n_marks):
                        is_black = i < black
                        fx = fb_start_x + i * fb_slot_w + fb_slot_w / 2
                        self.canvas.create_oval(
                            fx - fb_radius, y_center - fb_radius,
                            fx + fb_radius, y_center + fb_radius,
                            fill="#111111" if is_black else "#f5f5f5",
                            outline=theme.color("fg"), width=1)

        if self.game_over:
            code_y = self._py(self.max_rows) + row_h * 0.6
            self.canvas.create_text(
                self.offset_x, code_y - row_h * 0.9,
                text="Secret code:", anchor="w",
                fill=theme.color("muted"),
                font=(theme.font_family, max(8, int(self.cell * 0.3))))
            for c, v in enumerate(self.code):
                cx = self._px(c) + self.cell / 2
                fill, text, text_fg = _peg_look(v, self.display)
                self.canvas.create_oval(
                    cx - radius, code_y - radius,
                    cx + radius, code_y + radius,
                    fill=fill, outline=theme.color("fg"), width=1)
                if text:
                    self.canvas.create_text(
                        cx, code_y, text=text,
                        fill=text_fg or theme.color("fg"),
                        font=(theme.font_family,
                              max(7, int(self.cell * 0.32)), "bold"))

        self._refresh_palette_state()

    def on_canvas_click(self, event):
        if self.game_over:
            return
        row_h = self.cell * 1.15
        if row_h <= 0:
            return
        cx = self.canvas.canvasx(event.x)
        cy = self.canvas.canvasy(event.y)
        r = int((cy - self.offset_y) // row_h)
        if r != self.row_index:
            return
        c = int((cx - self.offset_x) // self.cell)
        if not (0 <= c < self.code_len):
            return
        if c < len(self.current):
            self.current.pop(c)
            self.update_status()
            self.draw()


def run(master=None):
    return Mastermind(master)