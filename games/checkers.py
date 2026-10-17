"""Checkers - standard 8x8 draughts with optional forced-capture and
forced-promotion rules.

Settings (via the Settings button):
  * Forced captures:  if you can capture, you must.
  * Forced promotions: if you can promote (move a piece to the far row),
                       you must.
  Both default to the standard ruleset: captures forced, promotions optional.

Controls:
  * Click a piece, then a highlighted square.
  * R restarts.
"""

import random
import tkinter as tk

import save_manager
from theme import theme

GAME_ID = "checkers"
BOARD_SIZE = 8

# Internal piece values. RED = +1 (bottom, moves up), BLACK = -1 (top, moves
# down). Kings are +/-2. The rendered *colours* come from the theme (accent_o
# for red, accent_x for black), so the names "RED" and "BLACK" refer to
# sides, not to displayed colours - the UI never says "Red"/"Black".
RED, BLACK = 1, -1
DIRECTIONS = [(-1, -1), (-1, 1), (1, -1), (1, 1)]


def _in_bounds(r, c): return 0 <= r < BOARD_SIZE and 0 <= c < BOARD_SIZE
def _is_king(p): return abs(p) == 2
def _sign(p): return 1 if p > 0 else (-1 if p < 0 else 0)
def _forward_dirs(piece): return [(-1, -1), (-1, 1)] if piece > 0 else [(1, -1), (1, 1)]


def _initial_board():
    board = [[0] * BOARD_SIZE for _ in range(BOARD_SIZE)]
    for r in range(3):
        for c in range(BOARD_SIZE):
            if (r + c) % 2 == 1: board[r][c] = BLACK
    for r in range(5, 8):
        for c in range(BOARD_SIZE):
            if (r + c) % 2 == 1: board[r][c] = RED
    return board


def _captures_for(board, r, c):
    piece = board[r][c]
    if piece == 0: return []
    dirs = DIRECTIONS if _is_king(piece) else _forward_dirs(piece)
    out = []
    for dr, dc in dirs:
        mr, mc = r + dr, c + dc
        tr, tc = r + 2 * dr, c + 2 * dc
        if not _in_bounds(tr, tc): continue
        mid = board[mr][mc]
        if mid != 0 and _sign(mid) != _sign(piece) and board[tr][tc] == 0:
            out.append((tr, tc, mr, mc))
    return out


def _quiet_moves_for(board, r, c):
    piece = board[r][c]
    if piece == 0: return []
    dirs = DIRECTIONS if _is_king(piece) else _forward_dirs(piece)
    return [(r + dr, c + dc) for dr, dc in dirs if _in_bounds(r + dr, c + dc) and board[r + dr][c + dc] == 0]


def _move_promotes(board, move):
    """True if this move promotes a non-king on the far row."""
    fr, fc, tr, tc, _cap = move
    piece = board[fr][fc]
    if piece == RED and tr == 0: return True
    if piece == BLACK and tr == BOARD_SIZE - 1: return True
    return False


def _all_legal_moves(board, side, forced_captures=True, forced_promotions=False):
    """Return the list of legal moves under the current rule settings.

    Rules are applied in priority order:
      1. Forced captures: if any captures exist, only capture moves are legal.
      2. Forced promotions: within the resulting pool, if any promoting moves
         exist, only promoting moves are legal.
    """
    captures, quiets = [], []
    for r in range(BOARD_SIZE):
        for c in range(BOARD_SIZE):
            p = board[r][c]
            if p == 0 or _sign(p) != side: continue
            for tr, tc, cr, cc in _captures_for(board, r, c):
                captures.append((r, c, tr, tc, (cr, cc)))
            for tr, tc in _quiet_moves_for(board, r, c):
                quiets.append((r, c, tr, tc, None))

    # Step 1: forced captures.
    if forced_captures and captures:
        pool = captures
    else:
        pool = captures + quiets

    # Step 2: forced promotions (applied to whatever is in the pool).
    if forced_promotions and pool:
        promoting = [m for m in pool if _move_promotes(board, m)]
        if promoting:
            return promoting

    return pool


def _apply_move(board, move):
    fr, fc, tr, tc, cap = move
    new_board = [row[:] for row in board]
    piece = new_board[fr][fc]
    new_board[fr][fc] = 0
    if cap: new_board[cap[0]][cap[1]] = 0
    promoted = False
    if piece == RED and tr == 0: piece, promoted = 2, True
    elif piece == BLACK and tr == BOARD_SIZE - 1: piece, promoted = -2, True
    new_board[tr][tc] = piece
    return new_board, promoted


def _has_any_move(board, side):
    """True if *any* move (capture or quiet) is available. Used for game-over
    detection only; does not need to know about forced-rule settings because
    a forced rule can never leave a side with moves available in the raw
    pool but zero in the filtered pool."""
    for r in range(BOARD_SIZE):
        for c in range(BOARD_SIZE):
            p = board[r][c]
            if p == 0 or _sign(p) != side: continue
            if _captures_for(board, r, c) or _quiet_moves_for(board, r, c): return True
    return False


def _is_capturable(board, r, c, opponent_sign):
    if board[r][c] == 0: return False
    for dr, dc in DIRECTIONS:
        orr, occ = r - dr, c - dc
        lr, lc = r + dr, c + dc
        if not (_in_bounds(orr, occ) and _in_bounds(lr, lc)): continue
        opp = board[orr][occ]
        if opp == 0 or _sign(opp) != opponent_sign or board[lr][lc] != 0: continue
        if _is_king(opp) or (dr, dc) in _forward_dirs(opp): return True
    return False


# ============================================================ settings
class CheckersSettings:
    def __init__(self):
        # Defaults match the standard ruleset: captures are forced,
        # promotions are not.
        self.forced_captures = True
        self.forced_promotions = False

    def to_dict(self):
        return {
            "forced_captures": self.forced_captures,
            "forced_promotions": self.forced_promotions,
        }

    @classmethod
    def from_dict(cls, data):
        s = cls()
        s.forced_captures = bool(data.get("forced_captures", True))
        s.forced_promotions = bool(data.get("forced_promotions", False))
        return s


class GameSettingsDialog(tk.Toplevel):
    def __init__(self, master, current):
        super().__init__(master)
        self.title("Checkers Settings")
        self.transient(master)
        self.resizable(False, False)
        self.result = None

        bg = theme.color("bg")
        fg = theme.color("fg")
        btn_bg = theme.color("button_bg")
        btn_fg = theme.color("button_fg")
        hover = theme.color("button_hover")

        self.configure(bg=bg)

        body = tk.Frame(self, bg=bg)
        body.pack(fill="both", expand=True, padx=20, pady=16)

        tk.Label(body, text="Rule settings",
                 bg=bg, fg=fg,
                 font=theme.font("heading", "bold")).pack(anchor="w",
                                                          pady=(0, 10))

        self._forced_captures_var = tk.BooleanVar(value=current.forced_captures)
        self._forced_promotions_var = tk.BooleanVar(value=current.forced_promotions)

        tk.Checkbutton(
            body,
            text="Forced captures\n(if you can capture, you must)",
            variable=self._forced_captures_var,
            bg=bg, fg=fg, selectcolor=btn_bg,
            activebackground=bg, activeforeground=fg,
            justify="left", anchor="w",
            font=theme.font("body")).pack(anchor="w", pady=4)

        tk.Checkbutton(
            body,
            text="Forced promotions\n(if you can promote, you must)",
            variable=self._forced_promotions_var,
            bg=bg, fg=fg, selectcolor=btn_bg,
            activebackground=bg, activeforeground=fg,
            justify="left", anchor="w",
            font=theme.font("body")).pack(anchor="w", pady=4)

        btns = tk.Frame(body, bg=bg)
        btns.pack(fill="x", pady=(16, 0))

        tk.Button(btns, text="Apply", command=self._ok,
                  bg=btn_bg, fg=btn_fg,
                  activebackground=hover, activeforeground=btn_fg,
                  relief="flat", bd=0, padx=14, pady=4,
                  font=theme.font("button")).pack(side="right", padx=(6, 0))
        tk.Button(btns, text="Cancel", command=self._cancel,
                  bg=btn_bg, fg=btn_fg,
                  activebackground=hover, activeforeground=btn_fg,
                  relief="flat", bd=0, padx=14, pady=4,
                  font=theme.font("button")).pack(side="right")

        self.bind("<Return>", lambda e: self._ok())
        self.bind("<Escape>", lambda e: self._cancel())

        self.update_idletasks()
        try:
            self.wait_visibility()
            self.grab_set()
        except tk.TclError:
            pass
        self.focus_set()

    def _ok(self):
        s = CheckersSettings()
        s.forced_captures = self._forced_captures_var.get()
        s.forced_promotions = self._forced_promotions_var.get()
        self.result = s
        self.destroy()

    def _cancel(self):
        self.result = None
        self.destroy()


# ============================================================ main game
class Checkers(tk.Toplevel):
    def __init__(self, master=None):
        super().__init__(master)
        self.title("Checkers")
        self.geometry("640x720")
        self.minsize(360, 460)
        self.vs_computer = tk.BooleanVar(master=self, value=True)
        self.settings = CheckersSettings()

        self.cell, self.offset_x, self.offset_y = 60, 0, 0
        self.board, self.turn, self.selected, self.legal_targets = None, RED, None, {}
        self.chain_from, self.game_over, self.winner = None, False, None

        self._build()
        self.apply_theme()
        self.new_game()
        self.focus_set()

    def _build(self):
        self.status = tk.Label(self)
        self.status.pack(pady=(12, 6))
        self.canvas = tk.Canvas(self, highlightthickness=0)
        self.canvas.pack(fill="both", expand=True, padx=12, pady=(0, 6))
        self.canvas.bind("<Configure>", self._on_canvas_resize)
        self.canvas.bind("<Button-1>", self.on_click)

        self.bottom = tk.Frame(self)
        self.bottom.pack(fill="x", padx=12, pady=(0, 8))

        self.vs_cb = tk.Checkbutton(self.bottom, text="vs Computer",
                                     variable=self.vs_computer,
                                     command=self.new_game,
                                     relief="flat", bd=0,
                                     highlightthickness=0)
        self.vs_cb.pack(side="left")

        self.settings_btn = tk.Button(self.bottom, text="Settings",
                                       command=self.open_settings,
                                       relief="flat", bd=0, padx=10, pady=3)
        self.settings_btn.pack(side="left", padx=(8, 0))

        self.new_btn = tk.Button(self.bottom, text="New", command=self.new_game,
                                  relief="flat", bd=0, padx=10, pady=3)
        self.new_btn.pack(side="right")

        self.load_btn = tk.Button(self.bottom, text="Load",
                                   command=self.load_game,
                                   relief="flat", bd=0, padx=10, pady=3)
        self.load_btn.pack(side="right", padx=(0, 4))

        self.save_btn = tk.Button(self.bottom, text="Save",
                                   command=self.save_game,
                                   relief="flat", bd=0, padx=10, pady=3)
        self.save_btn.pack(side="right", padx=(0, 4))

        self.hint_lbl = tk.Label(
            self,
            text="Click a piece, then a highlighted square  •  R to restart")
        self.hint_lbl.pack(pady=(0, 12))
        self.bind("<KeyPress>", self.on_key)

    def apply_theme(self):
        bg, fg = theme.color("bg"), theme.color("fg")
        btn_bg = theme.color("button_bg")
        btn_fg = theme.color("button_fg")
        hover = theme.color("button_hover")

        self.configure(bg=bg)
        self.status.configure(bg=bg, fg=fg, font=theme.font("status", "bold"))
        self.bottom.configure(bg=bg)
        self.hint_lbl.configure(bg=bg, fg=theme.color("muted"),
                                font=theme.font("small"))
        self.canvas.configure(bg=theme.color("canvas_bg"))
        self.vs_cb.configure(bg=bg, fg=fg, selectcolor=btn_bg,
                             activebackground=bg, activeforeground=fg,
                             font=theme.font("body"))
        for btn in (self.new_btn, self.save_btn, self.load_btn,
                    self.settings_btn):
            btn.configure(bg=btn_bg, fg=btn_fg,
                          activebackground=hover, activeforeground=btn_fg,
                          font=theme.font("button"))
        self.draw()

    # ----------------------------------------------------------- settings
    def open_settings(self):
        dlg = GameSettingsDialog(self, self.settings)
        self.wait_window(dlg)
        if dlg.result is not None:
            self.settings = dlg.result
            self.recompute_targets()
            self.update_status()
            self.draw()

    # ----------------------------------------------------------- game flow
    def new_game(self):
        self.board, self.turn, self.selected, self.legal_targets = _initial_board(), RED, None, {}
        self.chain_from, self.game_over, self.winner = None, False, None
        self.update_status()
        self.draw()

    def get_state(self):
        return {
            "board": self.board,
            "turn": self.turn,
            "selected": self.selected,
            "chain_from": self.chain_from,
            "game_over": self.game_over,
            "winner": self.winner,
            "vs_computer": self.vs_computer.get(),
            "settings": self.settings.to_dict(),
        }

    def set_state(self, data):
        self.board = data["board"]
        self.turn = data["turn"]
        self.selected = tuple(data["selected"]) if data["selected"] else None
        self.chain_from = tuple(data["chain_from"]) if data["chain_from"] else None
        self.game_over = data["game_over"]
        self.winner = data["winner"]
        self.vs_computer.set(data["vs_computer"])
        if "settings" in data:
            self.settings = CheckersSettings.from_dict(data["settings"])
        else:
            # Saves from before settings existed used forced captures.
            self.settings = CheckersSettings()
        self.recompute_targets()
        self.update_status()
        self.draw()

    def save_game(self):
        save_manager.prompt_save(self, GAME_ID, self.get_state())

    def load_game(self):
        fname = save_manager.prompt_load(self, GAME_ID)
        if fname:
            data = save_manager.load_game(GAME_ID, fname)
            self.set_state(data)

    def on_key(self, event):
        if event.keysym.lower() == "r":
            self.new_game()

    def on_click(self, event):
        if self.cell <= 0 or self.game_over: return
        if self.vs_computer.get() and self.turn == BLACK: return
        c, r = int((event.x - self.offset_x) // self.cell), int((event.y - self.offset_y) // self.cell)
        if not _in_bounds(r, c): return
        if (r, c) in self.legal_targets:
            self.execute_move(self.selected, (r, c))
            return
        piece = self.board[r][c]
        if piece != 0 and _sign(piece) == self.turn and self.chain_from is None:
            self.selected = (r, c)
            self.recompute_targets()
            self.draw()
            return
        if self.chain_from is None:
            self.selected, self.legal_targets = None, {}
            self.draw()

    def recompute_targets(self):
        self.legal_targets = {}
        if self.selected is None: return
        fr, fc = self.selected
        if self.chain_from is not None:
            # Chain continuation: only captures from the chain piece count,
            # regardless of the forced_captures setting.
            for tr, tc, cr, cc in _captures_for(self.board, fr, fc):
                self.legal_targets[(tr, tc)] = (cr, cc)
            return
        for mr, mc, tr, tc, cap in _all_legal_moves(
                self.board, self.turn,
                forced_captures=self.settings.forced_captures,
                forced_promotions=self.settings.forced_promotions):
            if (mr, mc) == (fr, fc):
                self.legal_targets[(tr, tc)] = cap

    def execute_move(self, frc, toc):
        fr, fc = frc
        tr, tc = toc
        cap = self.legal_targets.get((tr, tc))
        self.board, promoted = _apply_move(self.board, (fr, fc, tr, tc, cap))
        self.selected, self.legal_targets = None, {}
        if cap is not None and not promoted:
            if _captures_for(self.board, tr, tc):
                self.selected, self.chain_from = (tr, tc), (tr, tc)
                self.recompute_targets()
                self.update_status()
                self.draw()
                if self.vs_computer.get() and self.turn == BLACK:
                    self.after(300, self.computer_continue_chain)
                return
        self.chain_from = None
        self.turn = -self.turn
        self.check_game_over()
        self.update_status()
        self.draw()
        if not self.game_over and self.vs_computer.get() and self.turn == BLACK:
            self.after(300, self.computer_move)

    def check_game_over(self):
        if not _has_any_move(self.board, self.turn):
            self.game_over, self.winner = True, -self.turn

    # ----------------------------------------------------------- display
    def _side_name(self, side):
        """User-facing name for a side. Deliberately colour-agnostic so the
        text can never contradict the theme's rendered piece colours."""
        if self.vs_computer.get():
            return "You" if side == RED else "Computer"
        return "Player 1" if side == RED else "Player 2"

    def _forced_hint(self, side):
        """Short suffix for the status line listing active forced rules."""
        moves = _all_legal_moves(
            self.board, side,
            forced_captures=self.settings.forced_captures,
            forced_promotions=self.settings.forced_promotions)
        if not moves:
            return ""
        hints = []
        if self.settings.forced_captures:
            if all(m[4] is not None for m in moves):
                hints.append("must capture")
        if self.settings.forced_promotions:
            if all(_move_promotes(self.board, m) for m in moves):
                hints.append("must promote")
        if hints:
            return " — " + " and ".join(hints) + "!"
        return ""

    def update_status(self):
        if self.game_over:
            if self.vs_computer.get():
                self.status.config(
                    text="You win! 🎉" if self.winner == RED else "Computer wins!")
            else:
                name = self._side_name(self.winner)
                self.status.config(text=f"{name} wins! 🎉")
            return

        if self.chain_from is not None:
            self.status.config(text="Continue jumping!")
            return

        if self.vs_computer.get():
            if self.turn == BLACK:
                self.status.config(text="Computer thinking...")
            else:
                self.status.config(text=f"Your turn{self._forced_hint(RED)}")
        else:
            name = self._side_name(self.turn)
            self.status.config(
                text=f"{name}'s turn{self._forced_hint(self.turn)}")

    # ----------------------------------------------------------- AI
    def _score_move(self, move):
        fr, fc, tr, tc, cap = move
        score = 0
        if cap is not None:
            score += 12 if _is_king(self.board[cap[0]][cap[1]]) else 6
        if self.board[fr][fc] == BLACK and tr == BOARD_SIZE - 1: score += 8
        new_board, _ = _apply_move(self.board, move)
        if _is_capturable(new_board, tr, tc, RED): score -= 10
        return score

    def computer_move(self):
        if self.game_over or self.turn != BLACK: return
        moves = _all_legal_moves(
            self.board, BLACK,
            forced_captures=self.settings.forced_captures,
            forced_promotions=self.settings.forced_promotions)
        if not moves:
            self.check_game_over()
            self.update_status()
            self.draw()
            return
        best = max(moves, key=self._score_move)
        candidates = [m for m in moves if self._score_move(m) == self._score_move(best)]
        move = random.choice(candidates)
        fr, fc, tr, tc, cap = move
        self.selected, self.legal_targets = (fr, fc), {(tr, tc): cap}
        self.draw()
        self.after(180, lambda: self.execute_move((fr, fc), (tr, tc)))

    def computer_continue_chain(self):
        if self.game_over or self.turn != BLACK or self.selected is None: return
        targets = list(self.legal_targets.keys())
        if not targets: return
        tr, tc = random.choice(targets)
        fr, fc = self.selected
        self.after(180, lambda: self.execute_move((fr, fc), (tr, tc)))

    # ----------------------------------------------------------- geometry
    def _on_canvas_resize(self, event):
        size = min(event.width, event.height) - 8
        self.cell = size / BOARD_SIZE
        self.offset_x = (event.width - self.cell * BOARD_SIZE) / 2
        self.offset_y = (event.height - self.cell * BOARD_SIZE) / 2
        self.draw()

    def _px(self, c): return self.offset_x + c * self.cell
    def _py(self, r): return self.offset_y + r * self.cell

    # ----------------------------------------------------------- drawing
    def draw(self):
        if self.cell <= 0 or self.board is None: return
        self.canvas.delete("all")
        light, dark = theme.color("card"), theme.color("canvas_bg")

        for r in range(BOARD_SIZE):
            for c in range(BOARD_SIZE):
                fill = light if (r + c) % 2 == 0 else dark
                self.canvas.create_rectangle(self._px(c), self._py(r), self._px(c + 1), self._py(r + 1), fill=fill, outline="")

        if self.selected is not None:
            r, c = self.selected
            self.canvas.create_rectangle(self._px(c) + 1, self._py(r) + 1, self._px(c + 1) - 1, self._py(r + 1) - 1, outline=theme.color("accent_x"), width=3)

        for (tr, tc) in self.legal_targets:
            pad = self.cell * 0.32
            self.canvas.create_oval(self._px(tc) + pad, self._py(tr) + pad, self._px(tc + 1) - pad, self._py(tr + 1) - pad, fill=theme.color("accent_o"), outline="")

        pad, crown = self.cell * 0.12, self.cell * 0.28
        for r in range(BOARD_SIZE):
            for c in range(BOARD_SIZE):
                p = self.board[r][c]
                if p == 0: continue
                color = theme.color("accent_o") if p > 0 else theme.color("accent_x")
                self.canvas.create_oval(self._px(c) + pad, self._py(r) + pad, self._px(c + 1) - pad, self._py(r + 1) - pad, fill=color, outline=theme.color("fg"), width=2)
                if _is_king(p):
                    self.canvas.create_oval(self._px(c) + crown, self._py(r) + crown, self._px(c + 1) - crown, self._py(r + 1) - crown, outline=theme.color("fg"), width=2)

        self.canvas.create_rectangle(self._px(0), self._py(0), self._px(BOARD_SIZE), self._py(BOARD_SIZE), outline=theme.color("fg"), width=2)


def run(master=None):
    return Checkers(master)