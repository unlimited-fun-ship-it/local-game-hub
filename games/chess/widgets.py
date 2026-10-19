"""Reusable Tk widgets for the chess window."""

import tkinter as tk

from theme import theme

from .constants import KING, PAWN, KNIGHT, BISHOP, ROOK, QUEEN, SOLID_GLYPH

# Queen first ... pawns last, so the most valuable captures are easiest to see.
CAPTURE_ORDER = {QUEEN: 0, ROOK: 1, BISHOP: 2, KNIGHT: 3, PAWN: 4, KING: 5}


def sort_captured(pieces):
    return sorted(pieces, key=lambda p: CAPTURE_ORDER.get(abs(p), 6))


def _button(parent, text, command):
    return tk.Button(
        parent, text=text, command=command,
        bg=theme.color("button_bg"), fg=theme.color("button_fg"),
        activebackground=theme.color("button_hover"), activeforeground=theme.color("button_fg"),
        relief="flat", bd=0, padx=12, pady=4, font=theme.font("button"),
    )


class CapturedPanel(tk.Frame):
    """Side panel showing the pieces one player has captured.

    The pieces are drawn exactly like the ones on the board (solid glyph, fill
    colour per side, coloured outline), wrapped into as many columns as fit, so
    they stay readable no matter how many have been taken.  A small "+N" shows
    the material lead when this side is ahead.
    """

    PANEL_WIDTH = 128
    CELL = 34                       # pixel size of one captured-piece slot

    def __init__(self, master, title):
        super().__init__(master, width=self.PANEL_WIDTH)
        self.pack_propagate(False)  # keep the panel from growing with its contents
        self._pieces = []
        self.title_lbl = tk.Label(self, text=title, justify="center")
        self.title_lbl.pack(pady=(6, 0))
        self.lead_lbl = tk.Label(self, text=" ", justify="center")
        self.lead_lbl.pack(pady=(0, 4))
        self.canvas = tk.Canvas(self, highlightthickness=0)
        self.canvas.pack(fill="both", expand=True, padx=4, pady=(0, 6))
        self.canvas.bind("<Configure>", lambda _e: self.redraw())

    def apply_theme(self):
        bg = theme.color("bg")
        self.configure(bg=bg)
        self.title_lbl.configure(bg=bg, fg=theme.color("muted"), font=theme.font("small"))
        self.lead_lbl.configure(bg=bg, fg=theme.color("accent_o"), font=theme.font("small", "bold"))
        self.canvas.configure(bg=bg)
        self.redraw()

    def set_pieces(self, pieces, lead=0):
        """`pieces`: signed piece codes this side has captured; `lead`: pawns ahead (0 = none)."""
        self._pieces = sort_captured(pieces)
        self.lead_lbl.config(text=f"+{lead}" if lead > 0 else " ")
        self.redraw()

    def redraw(self):
        cv = self.canvas
        cv.delete("all")
        width = cv.winfo_width()
        if width <= 1:
            return
        if not self._pieces:
            cv.create_text(width / 2, self.CELL / 2, text="\u2014", fill=theme.color("muted"),
                           font=theme.font("body"))
            return

        cell = self.CELL
        cols = max(1, width // cell)
        x0 = (width - cols * cell) / 2
        font = (theme.font_family, -int(cell * 0.78))        # negative = pixels
        offsets = [(-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (1, -1), (-1, 1), (1, 1)]
        for i, p in enumerate(self._pieces):
            row, col = divmod(i, cols)
            cx = x0 + col * cell + cell / 2
            cy = 4 + row * cell + cell / 2
            white = p > 0
            glyph = SOLID_GLYPH[abs(p)]
            fill = theme.color("piece_white") if white else theme.color("piece_black")
            outline = theme.color("accent_x") if white else theme.color("accent_o")
            for dx, dy in offsets:
                cv.create_text(cx + dx, cy + dy, text=glyph, fill=outline, font=font)
            cv.create_text(cx, cy, text=glyph, fill=fill, font=font)


class MoveHistoryWindow(tk.Toplevel):
    def __init__(self, master, get_text_fn):
        super().__init__(master)
        self.title("Move History")
        self.geometry("460x580")
        self.minsize(280, 240)
        self._get_text = get_text_fn
        bg, fg = theme.color("bg"), theme.color("fg")
        self.configure(bg=bg)
        tk.Label(self, text="Full game log  \u2022  copyable", bg=bg, fg=theme.color("muted"),
                 font=theme.font("small")).pack(pady=(10, 4))

        text_frame = tk.Frame(self, bg=bg)
        text_frame.pack(fill="both", expand=True, padx=10, pady=(0, 6))
        self.text = tk.Text(text_frame, bg=theme.color("canvas_bg"), fg=fg, font=("Consolas", 11),
                            wrap="none", bd=0, highlightthickness=0, insertbackground=fg)
        self.text.pack(side="left", fill="both", expand=True)
        sb = tk.Scrollbar(text_frame, orient="vertical", command=self.text.yview)
        sb.pack(side="right", fill="y")
        self.text.config(yscrollcommand=sb.set)

        btn_frame = tk.Frame(self, bg=bg)
        btn_frame.pack(fill="x", padx=10, pady=(0, 10))
        self.status_lbl = tk.Label(btn_frame, text="", bg=bg, fg=theme.color("accent_o"),
                                   font=theme.font("small"))
        self.status_lbl.pack(side="left")
        _button(btn_frame, "Close", self.destroy).pack(side="right")
        _button(btn_frame, "Copy", self._copy).pack(side="right", padx=(0, 4))
        self.refresh()

    def refresh(self):
        self.text.config(state="normal")
        self.text.delete("1.0", "end")
        self.text.insert("1.0", self._get_text())
        self.text.config(state="disabled")

    def _copy(self):
        self.clipboard_clear()
        self.clipboard_append(self.text.get("1.0", "end-1c"))
        self.status_lbl.config(text="Copied!")
        self.after(1800, lambda: self.status_lbl.config(text=""))


class FenDialog(tk.Toplevel):
    def __init__(self, master, current_fen):
        super().__init__(master)
        self.title("FEN Position")
        self.transient(master)
        self.resizable(False, False)
        bg, fg = theme.color("bg"), theme.color("fg")
        self.configure(bg=bg)
        self.result = None

        tk.Label(self, text="Forsyth-Edwards Notation (FEN):", bg=bg, fg=fg).pack(padx=14, pady=(12, 4))
        self.entry = tk.Entry(self, width=60)
        self.entry.insert(0, current_fen)
        self.entry.pack(padx=14, pady=4)

        btns = tk.Frame(self, bg=bg)
        btns.pack(fill="x", padx=14, pady=12)
        self.status_lbl = tk.Label(btns, text="", bg=bg, fg=theme.color("accent_o"))
        self.status_lbl.pack(side="left")
        for text, cmd in (("Load Position", self._load), ("Copy", self._copy), ("Cancel", self.destroy)):
            tk.Button(btns, text=text, command=cmd, bg=theme.color("button_bg"),
                      fg=theme.color("button_fg")).pack(side="right", padx=4)

    def _load(self):
        self.result = self.entry.get().strip()
        self.destroy()

    def _copy(self):
        self.clipboard_clear()
        self.clipboard_append(self.entry.get())
        self.status_lbl.config(text="Copied!")
