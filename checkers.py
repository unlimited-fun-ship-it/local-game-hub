"""Checkers - resizable, themeable, player vs player or vs a simple AI.

Rules implemented:
  * 8x8 board, 12 pieces per side on the dark squares.
  * Men move diagonally forward one step; kings move in all four diagonal
    directions.
  * Captures are mandatory. Multi-jumps are forced (you must keep jumping
    with the same piece until no more captures are available).
  * Reaching the far row promotes to king and ends the turn.

Rendering note: "black" pieces are drawn in the theme's blue accent for
contrast against the dark board; "red" pieces use the red accent.

Controls:
  * Click your piece, then click a highlighted destination to move.
  * R restarts.
"""

import random
import tkinter as tk

from theme import theme

BOARD_SIZE = 8

RED = 1
BLACK = -1

DIRECTIONS = [(-1, -1), (-1, 1), (1, -1), (1, 1)]


# ============================================================ pure logic
def _in_bounds(r, c):
    return 0 <= r < BOARD_SIZE and 0 <= c < BOARD_SIZE


def _is_king(p):
    return abs(p) == 2


def _sign(p):
    return 1 if p > 0 else (-1 if p < 0 else 0)


def _forward_dirs(piece):
    """Men move toward the opponent's back row."""
    return [(-1, -1), (-1, 1)] if piece > 0 else [(1, -1), (1, 1)]


def _initial_board():
    board = [[0] * BOARD_SIZE for _ in range(BOARD_SIZE)]
    for r in range(3):                      # black on rows 0..2
        for c in range(BOARD_SIZE):
            if (r + c) % 2 == 1:
                board[r][c] = BLACK
    for r in range(5, 8):                   # red on rows 5..7
        for c in range(BOARD_SIZE):
            if (r + c) % 2 == 1:
                board[r][c] = RED
    return board


def _captures_for(board, r, c):
    """Return [(to_r, to_c, captured_r, captured_c), ...] from this square."""
    piece = board[r][c]
    if piece == 0:
        return []
    dirs = DIRECTIONS if _is_king(piece) else _forward_dirs(piece)
    out = []
    for dr, dc in dirs:
        mr, mc = r + dr, c + dc
        tr, tc = r + 2 * dr, c + 2 * dc
        if not _in_bounds(tr, tc):
            continue
        mid = board[mr][mc]
        if mid != 0 and _sign(mid) != _sign(piece) and board[tr][tc] == 0:
            out.append((tr, tc, mr, mc))
    return out


def _quiet_moves_for(board, r, c):
    piece = board[r][c]
    if piece == 0:
        return []
    dirs = DIRECTIONS if _is_king(piece) else _forward_dirs(piece)
    return [(r + dr, c + dc) for dr, dc in dirs
            if _in_bounds(r + dr, c + dc) and board[r + dr][c + dc] == 0]


def _all_legal_moves(board, side):
    """Return moves as (fr, fc, tr, tc, captured or None).
    Captures are mandatory: if any exist, only captures are returned."""
    captures, quiets = [], []
    for r in range(BOARD_SIZE):
        for c in range(BOARD_SIZE):
            p = board[r][c]
            if p == 0 or _sign(p) != side:
                continue
            for tr, tc, cr, cc in _captures_for(board, r, c):
                captures.append((r, c, tr, tc, (cr, cc)))
            for tr, tc in _quiet_moves_for(board, r, c):
                quiets.append((r, c, tr, tc, None))
    return captures if captures else quiets


def _apply_move(board, move):
    """Return (new_board, promoted)."""
    fr, fc, tr, tc, cap = move
    new_board = [row[:] for row in board]
    piece = new_board[fr][fc]
    new_board[fr][fc] = 0
    if cap:
        new_board[cap[0]][cap[1]] = 0
    promoted = False
    if piece == RED and tr == 0:
        piece, promoted = 2, True
    elif piece == BLACK and tr == BOARD_SIZE - 1:
        piece, promoted = -2, True
    new_board[tr][tc] = piece
    return new_board, promoted


def _has_any_move(board, side):
    for r in range(BOARD_SIZE):
        for c in range(BOARD_SIZE):
            p = board[r][c]
            if p == 0 or _sign(p) != side:
                continue
            if _captures_for(board, r, c) or _quiet_moves_for(board, r, c):
                return True
    return False


def _is_capturable(board, r, c, opponent_sign):
    """True if any opponent piece could immediately jump the piece at (r, c)."""
    if board[r][c] == 0:
        return False
    for dr, dc in DIRECTIONS:
        orr, occ = r - dr, c - dc       # opponent's square
        lr, lc = r + dr, c + dc         # opponent's landing square
        if not (_in_bounds(orr, occ) and _in_bounds(lr, lc)):
            continue
        opp = board[orr][occ]
        if opp == 0 or _sign(opp) != opponent_sign:
            continue
        if board[lr][lc] != 0:
            continue
        if _is_king(opp) or (dr, dc) in _forward_dirs(opp):
            return True
    return False


# ================================================================== game
class Checkers(tk.Toplevel):
    def __init__(self, master=None):
        super().__init__(master)
        self.title("Checkers")
        self.geometry("640x720")
        self.minsize(360, 460)

        self.vs_computer = tk.BooleanVar(master=self, value=True)

        self.cell = 60
        self.offset_x = 0
        self.offset_y = 0

        self.board = None
        self.turn = RED
        self.selected = None
        self.legal_targets = {}
        self.chain_from = None
        self.game_over = False
        self.winner = None

        self._build()
        self.apply_theme()
        self.new_game()
        self.focus_set()

    # ------------------------------------------------------------- build
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
                                    relief="flat", bd=0, highlightthickness=0)
        self.vs_cb.pack(side="left")

        self.new_btn = tk.Button(self.bottom, text="New Game",
                                 command=self.new_game, relief="flat", bd=0,
                                 padx=10, pady=3)
        self.new_btn.pack(side="right")

        self.hint_lbl = tk.Label(
            self,
            text="Click a piece, then a highlighted square  •  R to restart")
        self.hint_lbl.pack(pady=(0, 12))

        self.bind("<KeyPress>", self.on_key)

    # ------------------------------------------------------------- theme
    def apply_theme(self):
        bg = theme.color("bg")
        fg = theme.color("fg")
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
        self.new_btn.configure(bg=btn_bg, fg=btn_fg,
                               activebackground=hover, activeforeground=btn_fg,
                               font=theme.font("button"))

        self.draw()

    # --------------------------------------------------------- game flow
    def new_game(self):
        self.board = _initial_board()
        self.turn = RED
        self.selected = None
        self.legal_targets = {}
        self.chain_from = None
        self.game_over = False
        self.winner = None
        self.update_status()
        self.draw()

    def on_key(self, event):
        if event.keysym.lower() == "r":
            self.new_game()

    def on_click(self, event):
        if self.cell <= 0 or self.game_over:
            return
        if self.vs_computer.get() and self.turn == BLACK:
            return                                   # wait for AI
        if self.chain_from is not None:
            # A multi-jump chain is in progress: only destination clicks count.
            pass

        c = int((event.x - self.offset_x) // self.cell)
        r = int((event.y - self.offset_y) // self.cell)
        if not _in_bounds(r, c):
            return

        if (r, c) in self.legal_targets:
            self.execute_move(self.selected, (r, c))
            return

        piece = self.board[r][c]
        if (piece != 0 and _sign(piece) == self.turn
                and self.chain_from is None):
            self.selected = (r, c)
            self.recompute_targets()
            self.draw()
            return

        if self.chain_from is None:
            self.selected = None
            self.legal_targets = {}
            self.draw()

    def recompute_targets(self):
        self.legal_targets = {}
        if self.selected is None:
            return
        fr, fc = self.selected
        for mr, mc, tr, tc, cap in _all_legal_moves(self.board, self.turn):
            if (mr, mc) == (fr, fc):
                self.legal_targets[(tr, tc)] = cap

    def execute_move(self, frc, toc):
        fr, fc = frc
        tr, tc = toc
        cap = self.legal_targets.get((tr, tc))

        self.board, promoted = _apply_move(
            self.board, (fr, fc, tr, tc, cap))
        self.selected = None
        self.legal_targets = {}

        # Mandatory chain continuation
        if cap is not None and not promoted:
            more = _captures_for(self.board, tr, tc)
            if more:
                self.selected = (tr, tc)
                self.chain_from = (tr, tc)
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

        if (not self.game_over
                and self.vs_computer.get()
                and self.turn == BLACK):
            self.after(300, self.computer_move)

    def check_game_over(self):
        if not _has_any_move(self.board, self.turn):
            self.game_over = True
            self.winner = -self.turn

    def update_status(self):
        if self.game_over:
            self.status.config(
                text="Red wins! 🎉" if self.winner == RED else "Black wins!")
            return
        if self.chain_from is not None:
            self.status.config(text="Continue jumping!")
            return
        whose = "Red" if self.turn == RED else "Black"
        if self.vs_computer.get() and self.turn == BLACK:
            suffix = " (thinking...)"
        else:
            suffix = " (your turn)"
        self.status.config(text=f"{whose} to move{suffix}")

    # ------------------------------------------------------------- AI
    def _score_move(self, move):
        """Higher is better. Very small heuristic."""
        fr, fc, tr, tc, cap = move
        score = 0
        if cap is not None:
            captured = self.board[cap[0]][cap[1]]
            score += 12 if _is_king(captured) else 6
        piece = self.board[fr][fc]
        if piece == BLACK and tr == BOARD_SIZE - 1:
            score += 8                                # promotion
        # Penalise moves that put our piece where red can take it.
        new_board, _ = _apply_move(self.board, move)
        if _is_capturable(new_board, tr, tc, RED):
            score -= 10
        return score

    def computer_move(self):
        if self.game_over or self.turn != BLACK:
            return
        moves = _all_legal_moves(self.board, BLACK)
        if not moves:
            self.check_game_over()
            self.update_status()
            self.draw()
            return

        best = max(moves, key=self._score_move)
        candidates = [m for m in moves if self._score_move(m) == self._score_move(best)]
        move = random.choice(candidates)

        fr, fc, tr, tc, cap = move
        self.selected = (fr, fc)
        self.legal_targets = {(tr, tc): cap}
        self.draw()
        self.after(180, lambda: self.execute_move((fr, fc), (tr, tc)))

    def computer_continue_chain(self):
        if self.game_over or self.turn != BLACK or self.selected is None:
            return
        targets = list(self.legal_targets.keys())
        if not targets:
            return
        tr, tc = random.choice(targets)
        fr, fc = self.selected
        self.after(180, lambda: self.execute_move((fr, fc), (tr, tc)))

    # --------------------------------------------------------- render
    def _on_canvas_resize(self, event):
        size = min(event.width, event.height) - 8
        self.cell = size / BOARD_SIZE
        self.offset_x = (event.width - self.cell * BOARD_SIZE) / 2
        self.offset_y = (event.height - self.cell * BOARD_SIZE) / 2
        self.draw()

    def _px(self, c):
        return self.offset_x + c * self.cell

    def _py(self, r):
        return self.offset_y + r * self.cell

    def draw(self):
        if self.cell <= 0 or self.board is None:
            return
        self.canvas.delete("all")

        light = theme.color("card")
        dark = theme.color("canvas_bg")

        # Board squares
        for r in range(BOARD_SIZE):
            for c in range(BOARD_SIZE):
                fill = light if (r + c) % 2 == 0 else dark
                self.canvas.create_rectangle(
                    self._px(c), self._py(r),
                    self._px(c + 1), self._py(r + 1),
                    fill=fill, outline="")

        # Selected piece outline
        if self.selected is not None:
            r, c = self.selected
            self.canvas.create_rectangle(
                self._px(c) + 1, self._py(r) + 1,
                self._px(c + 1) - 1, self._py(r + 1) - 1,
                outline=theme.color("accent_x"), width=3)

        # Legal destinations
        for (tr, tc) in self.legal_targets:
            pad = self.cell * 0.32
            self.canvas.create_oval(
                self._px(tc) + pad, self._py(tr) + pad,
                self._px(tc + 1) - pad, self._py(tr + 1) - pad,
                fill=theme.color("accent_o"), outline="")

        # Pieces
        pad = self.cell * 0.12
        crown = self.cell * 0.28
        for r in range(BOARD_SIZE):
            for c in range(BOARD_SIZE):
                p = self.board[r][c]
                if p == 0:
                    continue
                color = (theme.color("accent_o") if p > 0
                         else theme.color("accent_x"))
                self.canvas.create_oval(
                    self._px(c) + pad, self._py(r) + pad,
                    self._px(c + 1) - pad, self._py(r + 1) - pad,
                    fill=color, outline=theme.color("fg"), width=2)
                if _is_king(p):
                    self.canvas.create_oval(
                        self._px(c) + crown, self._py(r) + crown,
                        self._px(c + 1) - crown, self._py(r + 1) - crown,
                        outline=theme.color("fg"), width=2)

        # Outer border
        self.canvas.create_rectangle(
            self._px(0), self._py(0), self._px(BOARD_SIZE), self._py(BOARD_SIZE),
            outline=theme.color("fg"), width=2)


def run(master=None):
    return Checkers(master)