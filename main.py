import colorsys
import importlib
import math
import traceback
import tkinter as tk
from tkinter import messagebox, ttk

from theme import theme, Theme

# (module path, display name, short description)
GAMES = [
    ("games.tictactoe", "Tic-Tac-Toe",   "Three in a row - beat the computer or a friend."),
    ("games.memory",    "Memory Match",  "Flip the cards and find every matching pair."),
    ("games.snake",     "Snake",         "Eat the apples without biting yourself."),
    ("games.pong",      "Pong",          "W / S to move. First to 7 points wins."),
    ("games.sudoku",    "Sudoku",        "Fill every row, column and box with 1-9."),
    ("games.checkers",  "Checkers",      "Diagonal captures, kings, and forced multi-jumps."),
    ("games.chess",     "Chess",         "Full rules, castling, en passant, promotion, and AI."),
]


# ======================================================================
# Custom Color Picker
# ======================================================================
class ColorPicker(tk.Toplevel):
    """Modal picker with hue ring, SV square, RGB spinboxes + sliders,
    hex entry and a preview swatch — every method is bidirectionally
    synced with the others."""

    WHEEL_SIZE = 220
    RING_OUTER = 108
    RING_INNER = 80
    SQUARE_SIZE = 110

    def __init__(self, master, initial="#ffffff"):
        super().__init__(master)
        self.title("Color Picker")
        self.transient(master)
        self.resizable(False, False)

        self.result = None

        try:
            r, g, b = self._hex_to_rgb(initial)
        except (ValueError, TypeError):
            r, g, b = 255, 255, 255

        self._r, self._g, self._b = r, g, b
        self._h, self._s, self._v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)

        # Guards so the traces don't recurse.
        self._updating = False
        self._last_drawn_hue = None

        # Pre-create the SV square image (contents get overwritten on hue change)
        self._sv_photo = tk.PhotoImage(width=self.SQUARE_SIZE, height=self.SQUARE_SIZE)

        self._build()
        self._draw_ring()
        self._draw_sv(force=True)
        self._place_sv_image()
        self._refresh()

        # Keyboard shortcuts
        self.bind("<Return>", lambda e: self._ok())
        self.bind("<Escape>", lambda e: self._cancel())

        # Make it modal
        self.update_idletasks()
        try:
            self.wait_visibility()
            self.grab_set()
        except tk.TclError:
            pass
        self.focus_set()

    # ----------------------------------------------------------- conversions
    @staticmethod
    def _hex_to_rgb(h):
        h = str(h).strip().lstrip("#")
        if len(h) == 3:
            h = "".join(c * 2 for c in h)
        if len(h) != 6:
            raise ValueError("bad hex")
        return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)

    @staticmethod
    def _rgb_to_hex(r, g, b):
        return "#{:02x}{:02x}{:02x}".format(int(r) & 0xFF,
                                            int(g) & 0xFF,
                                            int(b) & 0xFF)

    # ------------------------------------------------------------------ build
    def _build(self):
        root = tk.Frame(self)
        root.pack(fill="both", expand=True, padx=12, pady=12)

        # ----- Wheel on the left -----
        self.canvas = tk.Canvas(root, width=self.WHEEL_SIZE, height=self.WHEEL_SIZE,
                                highlightthickness=0, bg="#404040")
        self.canvas.grid(row=0, column=0, rowspan=2, sticky="n")
        self.canvas.bind("<Button-1>", self._on_canvas)
        self.canvas.bind("<B1-Motion>", self._on_canvas)

        # ----- Controls on the right -----
        controls = tk.Frame(root)
        controls.grid(row=0, column=1, sticky="new", padx=(14, 0))
        controls.columnconfigure(2, weight=1)

        self._r_var = tk.IntVar(value=self._r)
        self._g_var = tk.IntVar(value=self._g)
        self._b_var = tk.IntVar(value=self._b)
        self._hex_var = tk.StringVar(value=self._rgb_to_hex(self._r, self._g, self._b))

        def channel_row(row, label, var, trough):
            tk.Label(controls, text=label, width=2, anchor="w").grid(
                row=row, column=0, sticky="w", pady=3)
            tk.Spinbox(controls, from_=0, to=255, textvariable=var,
                       width=5, justify="center").grid(
                row=row, column=1, padx=(2, 6), pady=3)
            tk.Scale(controls, from_=0, to=255, orient="horizontal",
                     variable=var, showvalue=False,
                     sliderlength=14, width=12,
                     highlightthickness=0, bd=1,
                     troughcolor=trough).grid(
                row=row, column=2, sticky="ew", pady=3)

        channel_row(0, "R", self._r_var, "#ff0000")
        channel_row(1, "G", self._g_var, "#00ff00")
        channel_row(2, "B", self._b_var, "#0000ff")

        # Hex
        tk.Label(controls, text="Hex", anchor="w").grid(
            row=3, column=0, columnspan=2, sticky="w", pady=(10, 3))
        self._hex_entry = tk.Entry(controls, textvariable=self._hex_var,
                                   width=10, justify="center")
        self._hex_entry.grid(row=3, column=2, sticky="w", pady=(10, 3))

        # Preview
        tk.Label(controls, text="Preview", anchor="w").grid(
            row=4, column=0, columnspan=2, sticky="w", pady=(10, 3))
        self._preview = tk.Label(controls, width=12, height=2,
                                 bg=self._rgb_to_hex(self._r, self._g, self._b),
                                 relief="solid", bd=1)
        self._preview.grid(row=4, column=2, sticky="w", pady=(10, 3))

        # ----- Buttons -----
        btns = tk.Frame(self)
        btns.pack(fill="x", padx=12, pady=(0, 12))
        tk.Button(btns, text="Cancel", width=8,
                  command=self._cancel).pack(side="right", padx=(6, 0))
        self._ok_btn = tk.Button(btns, text="OK", width=8, command=self._ok)
        self._ok_btn.pack(side="right")
        self._ok_btn.focus_set()

        # ----- Live sync via traces -----
        self._r_var.trace_add("write", lambda *_: self._on_var_changed())
        self._g_var.trace_add("write", lambda *_: self._on_var_changed())
        self._b_var.trace_add("write", lambda *_: self._on_var_changed())
        self._hex_var.trace_add("write", lambda *_: self._on_hex_changed())

    # --------------------------------------------------------------- drawing
    def _draw_ring(self):
        cx = cy = self.WHEEL_SIZE / 2
        r_in, r_out = self.RING_INNER, self.RING_OUTER
        segs = 120
        for i in range(segs):
            a0 = math.radians(i * (360 / segs))
            a1 = math.radians((i + 1) * (360 / segs))
            x1i = cx + r_in * math.cos(a0)
            y1i = cy - r_in * math.sin(a0)
            x2i = cx + r_out * math.cos(a0)
            y2i = cy - r_out * math.sin(a0)
            x1o = cx + r_in * math.cos(a1)
            y1o = cy - r_in * math.sin(a1)
            x2o = cx + r_out * math.cos(a1)
            y2o = cy - r_out * math.sin(a1)
            hue = (i + 0.5) / segs
            r, g, b = colorsys.hsv_to_rgb(hue, 1, 1)
            color = "#{:02x}{:02x}{:02x}".format(int(r * 255), int(g * 255), int(b * 255))
            self.canvas.create_polygon(x1i, y1i, x2i, y2i, x2o, y2o, x1o, y1o,
                                       fill=color, outline=color, tags="ring")

    def _draw_sv(self, force=False):
        """Populate the SV square's PhotoImage. Skips if the hue hasn't changed."""
        if not force and self._last_drawn_hue is not None:
            if abs(self._last_drawn_hue - self._h) < 0.0005:
                return
        self._last_drawn_hue = self._h

        size = self.SQUARE_SIZE
        for y in range(size):
            v = 1 - y / (size - 1)
            row = []
            for x in range(size):
                s = x / (size - 1)
                r, g, b = colorsys.hsv_to_rgb(self._h, s, v)
                row.append("#{:02x}{:02x}{:02x}".format(
                    int(r * 255 + 0.5),
                    int(g * 255 + 0.5),
                    int(b * 255 + 0.5)))
            self._sv_photo.put(" ".join(row), to=(0, y))

    def _place_sv_image(self):
        cx = cy = self.WHEEL_SIZE / 2
        sq_x0 = cx - self.SQUARE_SIZE / 2
        sq_y0 = cy - self.SQUARE_SIZE / 2
        self.canvas.create_image(sq_x0, sq_y0, image=self._sv_photo,
                                 anchor="nw", tags="sv_img")
        self.canvas.create_rectangle(sq_x0, sq_y0,
                                     sq_x0 + self.SQUARE_SIZE,
                                     sq_y0 + self.SQUARE_SIZE,
                                     outline="#dddddd", tags="sv_border")

    def _draw_markers(self):
        self.canvas.delete("marker")
        cx = cy = self.WHEEL_SIZE / 2

        # Hue marker on the ring
        r_mid = (self.RING_OUTER + self.RING_INNER) / 2
        a = self._h * 2 * math.pi
        x = cx + r_mid * math.cos(a)
        y = cy - r_mid * math.sin(a)
        self.canvas.create_oval(x - 7, y - 7, x + 7, y + 7,
                                outline="white", width=3, tags="marker")
        self.canvas.create_oval(x - 5, y - 5, x + 5, y + 5,
                                outline="black", width=1, tags="marker")

        # SV marker inside the square
        sq_x0 = cx - self.SQUARE_SIZE / 2
        sq_y0 = cy - self.SQUARE_SIZE / 2
        mx = sq_x0 + self._s * self.SQUARE_SIZE
        my = sq_y0 + (1 - self._v) * self.SQUARE_SIZE
        self.canvas.create_oval(mx - 7, my - 7, mx + 7, my + 7,
                                outline="white", width=3, tags="marker")
        self.canvas.create_oval(mx - 5, my - 5, mx + 5, my + 5,
                                outline="black", width=1, tags="marker")

    # --------------------------------------------------------------- syncing
    def _refresh(self):
        """Push current RGB/HSV state out to every widget."""
        self._updating = True
        try:
            hexval = self._rgb_to_hex(self._r, self._g, self._b)

            # Hex entry
            if self._hex_var.get() != hexval:
                self._hex_var.set(hexval)

            # RGB vars (may differ if the user typed out-of-range in a spinbox)
            try:
                if self._r_var.get() != self._r:
                    self._r_var.set(self._r)
                if self._g_var.get() != self._g:
                    self._g_var.set(self._g)
                if self._b_var.get() != self._b:
                    self._b_var.set(self._b)
            except tk.TclError:
                self._r_var.set(self._r)
                self._g_var.set(self._g)
                self._b_var.set(self._b)

            # Preview
            self._preview.configure(bg=hexval)

            # SV square & markers
            self._draw_sv()
            self._draw_markers()
        finally:
            self._updating = False

    def _on_var_changed(self):
        """Fired when R/G/B IntVars change (spinbox or slider)."""
        if self._updating:
            return
        try:
            r, g, b = self._r_var.get(), self._g_var.get(), self._b_var.get()
        except tk.TclError:
            return
        self._r = max(0, min(255, r))
        self._g = max(0, min(255, g))
        self._b = max(0, min(255, b))
        self._h, self._s, self._v = colorsys.rgb_to_hsv(
            self._r / 255, self._g / 255, self._b / 255)
        self._refresh()

    def _on_hex_changed(self):
        if self._updating:
            return
        try:
            r, g, b = self._hex_to_rgb(self._hex_var.get())
        except (ValueError, TypeError):
            return
        self._r, self._g, self._b = r, g, b
        self._h, self._s, self._v = colorsys.rgb_to_hsv(
            r / 255, g / 255, b / 255)
        self._refresh()

    # ------------------------------------------------------------- wheel click
    def _on_canvas(self, event):
        cx = cy = self.WHEEL_SIZE / 2
        dx, dy = event.x - cx, event.y - cy
        dist = math.hypot(dx, dy)

        # --- Ring (hue) ---
        if self.RING_INNER - 4 <= dist <= self.RING_OUTER + 6:
            angle = math.atan2(-dy, dx)          # -dy: canvas y grows downward
            self._h = (angle / (2 * math.pi)) % 1.0
            r, g, b = colorsys.hsv_to_rgb(self._h, self._s, self._v)
            self._r = int(r * 255 + 0.5)
            self._g = int(g * 255 + 0.5)
            self._b = int(b * 255 + 0.5)
            self._refresh()
            return

        # --- SV square ---
        sq_x0 = cx - self.SQUARE_SIZE / 2
        sq_y0 = cy - self.SQUARE_SIZE / 2
        if (sq_x0 <= event.x <= sq_x0 + self.SQUARE_SIZE and
                sq_y0 <= event.y <= sq_y0 + self.SQUARE_SIZE):
            self._s = max(0.0, min(1.0, (event.x - sq_x0) / self.SQUARE_SIZE))
            self._v = max(0.0, min(1.0, 1 - (event.y - sq_y0) / self.SQUARE_SIZE))
            r, g, b = colorsys.hsv_to_rgb(self._h, self._s, self._v)
            self._r = int(r * 255 + 0.5)
            self._g = int(g * 255 + 0.5)
            self._b = int(b * 255 + 0.5)
            self._refresh()

    # ------------------------------------------------------------- OK/Cancel
    def _ok(self):
        self.result = self._rgb_to_hex(self._r, self._g, self._b)
        self.destroy()

    def _cancel(self):
        self.result = None
        self.destroy()


# ======================================================================
# Launcher
# ======================================================================
class Launcher(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Mini Game Hub")
        self.geometry("560x560")
        self.minsize(420, 400)

        self._windows = {}
        self._cards = []
        self._settings = None

        self._build_ui()
        self.apply_theme()

    def _build_ui(self):
        self.header = tk.Frame(self)
        self.header.pack(fill="x", pady=(22, 0))

        self.title_lbl = tk.Label(self.header, text="Mini Game Hub")
        self.title_lbl.pack()
        self.subtitle_lbl = tk.Label(self.header, text="Choose a game to play")
        self.subtitle_lbl.pack(pady=(2, 12))

        self.container = tk.Frame(self)
        self.container.pack(fill="both", expand=True, padx=22, pady=(0, 8))

        for module, name, desc in GAMES:
            self._make_card(module, name, desc)

        self.bottom = tk.Frame(self)
        self.bottom.pack(fill="x", padx=22, pady=(0, 14))

        self.footer_lbl = tk.Label(self.bottom,
                                   text="Each game is its own module in  games/")
        self.footer_lbl.pack(side="left")

        self.settings_btn = tk.Button(self.bottom, text="Settings",
                                      command=self.open_settings,
                                      relief="flat", bd=0, padx=12, pady=4)
        self.settings_btn.pack(side="right")

    def _make_card(self, module, name, desc):
        card = tk.Frame(self.container, cursor="hand2")
        card.pack(fill="x", pady=6)

        title = tk.Label(card, text=name, anchor="w")
        title.pack(fill="x", padx=14, pady=(10, 0))

        info = tk.Label(card, text=desc, anchor="w")
        info.pack(fill="x", padx=14, pady=(0, 10))

        widgets = (card, title, info)
        self._cards.append({"title": title, "info": info, "widgets": widgets})

        def on_enter(_e):
            for w in widgets:
                w.configure(bg=theme.color("card_hover"))

        def on_leave(_e):
            for w in widgets:
                w.configure(bg=theme.color("card"))

        def on_click(_e):
            self.launch(module)

        for w in widgets:
            w.bind("<Enter>", on_enter)
            w.bind("<Leave>", on_leave)
            w.bind("<Button-1>", on_click)

    def apply_theme(self):
        bg = theme.color("bg")
        fg = theme.color("fg")
        muted = theme.color("muted")
        subtle = theme.color("subtle")
        card = theme.color("card")
        btn_bg = theme.color("button_bg")
        btn_fg = theme.color("button_fg")
        hover = theme.color("button_hover")

        self.configure(bg=bg)
        for w in (self.header, self.container, self.bottom):
            w.configure(bg=bg)

        self.title_lbl.configure(bg=bg, fg=fg, font=theme.font("title", "bold"))
        self.subtitle_lbl.configure(bg=bg, fg=muted, font=theme.font("subtitle"))
        self.footer_lbl.configure(bg=bg, fg=subtle, font=theme.font("small"))

        self.settings_btn.configure(bg=btn_bg, fg=btn_fg,
                                    activebackground=hover,
                                    activeforeground=btn_fg,
                                    font=theme.font("button"))

        for entry in self._cards:
            for w in entry["widgets"]:
                w.configure(bg=card)
            entry["title"].configure(fg=fg, font=theme.font("heading", "bold"))
            entry["info"].configure(fg=muted, font=theme.font("small"))

    def broadcast_theme(self):
        self.apply_theme()
        for win in list(self._windows.values()):
            try:
                if win.winfo_exists() and hasattr(win, "apply_theme"):
                    win.apply_theme()
            except tk.TclError:
                pass

    def launch(self, module_name):
        win = self._windows.get(module_name)
        if win is not None:
            try:
                if win.winfo_exists():
                    win.deiconify()
                    win.lift()
                    win.focus_force()
                    return
            except tk.TclError:
                pass

        try:
            module = importlib.import_module(module_name)
            win = module.run(self)
        except Exception:
            messagebox.showerror(
                "Could not start game",
                f"Failed to launch '{module_name}'.\n\n{traceback.format_exc()}",
                parent=self,
            )
            return

        self._windows[module_name] = win

    def open_settings(self):
        if self._settings and self._settings.winfo_exists():
            self._settings.lift()
            self._settings.focus_force()
            return
        self._settings = SettingsDialog(self)


# ======================================================================
# Settings dialog
# ======================================================================
class SettingsDialog(tk.Toplevel):
    def __init__(self, master):
        super().__init__(master)
        self.title("Theme Settings")
        self.transient(master)
        self.geometry("560x620")
        self.minsize(42, 40)

        self._family_var = tk.StringVar(value=theme.font_family)
        self._size_vars = {k: tk.IntVar(value=v) for k, v in theme.font_sizes.items()}
        self._color_vars = {k: tk.StringVar(value=v) for k, v in theme.colors.items()}

        self._font_labels = []
        self._size_widgets = []
        self._color_labels = []
        self._color_swatches = []

        self._build()
        self.apply_theme()

        self._family_var.trace_add("write", lambda *_: self._on_font())
        for v in self._size_vars.values():
            v.trace_add("write", lambda *_: self._on_font())
        for k, v in self._color_vars.items():
            v.trace_add("write", lambda *_a, k=k: self._on_color(k))

    def _build(self):
        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=10, pady=10)

        self.fonts_tab = tk.Frame(nb)
        nb.add(self.fonts_tab, text="  Fonts  ")
        self.colors_tab = tk.Frame(nb)
        nb.add(self.colors_tab, text="  Colors  ")

        # ---------- Fonts tab ----------
        self.fonts_tab.columnconfigure(1, weight=1)

        family_lbl = tk.Label(self.fonts_tab, text="Font family")
        family_lbl.grid(row=0, column=0, sticky="w", padx=8, pady=(10, 2))
        self._font_labels.append(family_lbl)

        families = ["Segoe UI", "Arial", "Helvetica", "Courier New",
                    "Times New Roman", "Verdana", "Tahoma", "Georgia",
                    "Consolas", "Comic Sans MS"]
        ttk.Combobox(self.fonts_tab, textvariable=self._family_var,
                     values=families, width=22).grid(
            row=0, column=1, sticky="ew", padx=8, pady=(10, 2))

        for i, (k, v) in enumerate(self._size_vars.items(), start=1):
            lbl = tk.Label(self.fonts_tab, text=k.replace("_", " ").title())
            lbl.grid(row=i, column=0, sticky="w", padx=8, pady=2)
            self._font_labels.append(lbl)

            sp = tk.Spinbox(self.fonts_tab, from_=6, to=96, textvariable=v, width=6)
            sp.grid(row=i, column=1, sticky="w", padx=8, pady=2)
            self._size_widgets.append(sp)

        self.fonts_tab.rowconfigure(len(self._size_vars) + 1, weight=1)

        # ---------- Colors tab ----------
        self.colors_tab.columnconfigure(2, weight=1)
        self.colors_tab.columnconfigure(5, weight=1)

        for i, (k, v) in enumerate(self._color_vars.items()):
            r, c = divmod(i, 2)

            lbl = tk.Label(self.colors_tab, text=k.replace("_", " ").title())
            lbl.grid(row=r, column=c * 3, sticky="w", padx=(8, 4), pady=3)
            self._color_labels.append(lbl)

            swatch = tk.Button(self.colors_tab, width=3, bg=v.get(),
                               relief="flat", bd=1,
                               command=lambda k=k: self._pick(k))
            swatch.grid(row=r, column=c * 3 + 1, padx=2, pady=3)
            self._color_swatches.append((k, swatch))

            ent = tk.Entry(self.colors_tab, textvariable=self._color_vars[k])
            ent.grid(row=r, column=c * 3 + 2, sticky="ew", padx=2, pady=3)

        n_color_rows = (len(self._color_vars) + 1) // 2
        self.colors_tab.rowconfigure(n_color_rows, weight=1)

        # ---------- Bottom buttons ----------
        self.footer = tk.Frame(self)
        self.footer.pack(fill="x", padx=10, pady=(0, 10))

        self.close_btn = tk.Button(self.footer, text="Close", command=self.destroy,
                                   relief="flat", bd=0, padx=12, pady=4)
        self.close_btn.pack(side="right")

        self.reset_btn = tk.Button(self.footer, text="Reset to defaults",
                                   command=self._reset,
                                   relief="flat", bd=0, padx=12, pady=4)
        self.reset_btn.pack(side="right", padx=4)

    # -------------------------------------------------------------- handlers
    def _pick(self, key):
        """Open the custom color picker and apply whatever it returns."""
        current = self._color_vars[key].get()
        picker = ColorPicker(self, initial=current)
        self.wait_window(picker)
        if picker.result:
            self._color_vars[key].set(picker.result)

    def _reset(self):
        defaults = Theme()
        self._family_var.set(defaults.font_family)
        for k, v in defaults.font_sizes.items():
            self._size_vars[k].set(v)
        for k, v in defaults.colors.items():
            self._color_vars[k].set(v)

    def _on_font(self):
        try:
            theme.font_family = self._family_var.get()
            for k, v in self._size_vars.items():
                theme.font_sizes[k] = int(v.get())
        except (tk.TclError, ValueError):
            return
        self._broadcast()

    def _on_color(self, key):
        val = self._color_vars[key].get().strip()
        if not val:
            return
        try:
            self.winfo_rgb(val)
        except tk.TclError:
            return
        theme.colors[key] = val
        for k, sw in self._color_swatches:
            if k == key:
                sw.configure(bg=val)
        self._broadcast()

    def _broadcast(self):
        self.apply_theme()
        master = self.master
        if hasattr(master, "broadcast_theme"):
            master.broadcast_theme()

    def apply_theme(self):
        bg = theme.color("bg")
        fg = theme.color("fg")
        btn_bg = theme.color("button_bg")
        btn_fg = theme.color("button_fg")
        hover = theme.color("button_hover")

        self.configure(bg=bg)
        for w in (self.fonts_tab, self.colors_tab, self.footer):
            w.configure(bg=bg)

        for lbl in self._font_labels + self._color_labels:
            lbl.configure(bg=bg, fg=fg, font=theme.font("body"))

        for btn in (self.close_btn, self.reset_btn):
            btn.configure(bg=btn_bg, fg=btn_fg,
                          activebackground=hover, activeforeground=btn_fg,
                          font=theme.font("button"))

        for k, sw in self._color_swatches:
            sw.configure(bg=theme.colors.get(k, "#000000"))


if __name__ == "__main__":
    Launcher().mainloop()