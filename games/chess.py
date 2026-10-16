"""Chess - resizable, themeable, full rules, with a simple AI opponent.

Rules implemented:
  * All piece movement.
  * Castling (kingside/queenside), including "not through check".
  * En passant.
  * Pawn promotion (Q/R/B/N) via a small dialog.
  * Check, checkmate, stalemate and the fifty-move rule.

Extras:
  * Captured pieces shown either side of the board (coloured like the
    side they belonged to).
  * Engine panel with search depth, evaluation (White's perspective),
    and the engine's top 3 suggested moves.
  * Full game log window - copyable to the clipboard.

Controls:
  * Click a piece, then click a highlighted square to move.
  * R restarts.
  * The AI plays Black; uncheck "vs Computer" for two-player hot-seat.
"""

import random
from collections import namedtuple

import tkinter as tk

from theme import theme

# How many plies the engine looks ahead. 2 = snappy, 3 = stronger (~0.3-1s).
AI_DEPTH = 3
MATE_SCORE = 1_000_000


# ============================================================ engine
Move = namedtuple("Move", "fr fc tr tc promo")

PIECE_VALUES = {"p": 100, "n": 320, "b": 330, "r": 500, "q": 900, "k": 0}

UNICODE = {
    "K": "\u2654", "Q": "\u2655", "R": "\u2656",
    "B": "\u2657", "N": "\u2658", "P": "\u2659",
    "k": "\u265A", "q": "\u265B", "r": "\u265C",
    "b": "\u265D", "n": "\u265E", "p": "\u265F",
}

# Solid silhouettes (used with the stroke+fill technique so both sides
# can have a coloured border around a filled interior).
SOLID_UNICODE = {
    "k": "\u265A", "q": "\u265B", "r": "\u265C",
    "b": "\u265D", "n": "\u265E", "p": "\u265F",
}

KNIGHT_DELTAS = [(-2, -1), (-2, 1), (-1, -2), (-1, 2),
                 (1, -2), (1, 2), (2, -1), (2, 1)]
KING_DELTAS = [(-1, -1), (-1, 0), (-1, 1),
               (0, -1), (0, 1),
               (1, -1), (1, 0), (1, 1)]
BISHOP_DIRS = [(-1, -1), (-1, 1), (1, -1), (1, 1)]
ROOK_DIRS = [(-1, 0), (1, 0), (0, -1), (0, 1)]

FILES = "abcdefgh"


def move_uci(m):
    """Return UCI-style text like e2e4, e7e8q."""
    s = f"{FILES[m.fc]}{8 - m.fr}{FILES[m.tc]}{8 - m.tr}"
    if m.promo:
        s += m.promo.lower()
    return s


class ChessState:
    __slots__ = ("board", "turn", "castling", "ep_square",
                 "halfmove", "fullmove")

    def __init__(self, board, turn="w", castling=None,
                 ep_square=None, halfmove=0, fullmove=1):
        self.board = board
        self.turn = turn
        self.castling = castling if castling is not None else {
            "K": True, "Q": True, "k": True, "q": True}
        self.ep_square = ep_square
        self.halfmove = halfmove
        self.fullmove = fullmove


def initial_state():
    return ChessState([
        list("rnbqkbnr"),
        list("pppppppp"),
        list("........"),
        list("........"),
        list("........"),
        list("........"),
        list("PPPPPPPP"),
        list("RNBQKBNR"),
    ])


def apply_move(state, move):
    board = [row[:] for row in state.board]
    fr, fc, tr, tc, promo = move
    piece = board[fr][fc]
    captured = board[tr][tc]
    is_white = piece.isupper()

    if piece.lower() == "p" and fc != tc and captured == ".":
        cap_r = tr + (1 if is_white else -1)
        board[cap_r][tc] = "."
        captured = "P" if is_white else "p"

    board[tr][tc] = piece
    board[fr][fc] = "."

    if promo:
        board[tr][tc] = promo if is_white else promo.lower()

    if piece.lower() == "k" and abs(tc - fc) == 2:
        if tc > fc:
            board[tr][5] = board[tr][7]
            board[tr][7] = "."
        else:
            board[tr][3] = board[tr][0]
            board[tr][0] = "."

    new_castling = dict(state.castling)
    if piece == "K":
        new_castling["K"] = new_castling["Q"] = False
    elif piece == "k":
        new_castling["k"] = new_castling["q"] = False
    if (fr, fc) == (7, 0) or (tr, tc) == (7, 0):
        new_castling["Q"] = False
    if (fr, fc) == (7, 7) or (tr, tc) == (7, 7):
        new_castling["K"] = False
    if (fr, fc) == (0, 0) or (tr, tc) == (0, 0):
        new_castling["q"] = False
    if (fr, fc) == (0, 7) or (tr, tc) == (0, 7):
        new_castling["k"] = False

    new_ep = None
    if piece.lower() == "p" and abs(tr - fr) == 2:
        new_ep = ((tr + fr) // 2, fc)

    new_halfmove = state.halfmove + 1
    if piece.lower() == "p" or captured != ".":
        new_halfmove = 0

    return ChessState(
        board=board,
        turn="b" if state.turn == "w" else "w",
        castling=new_castling,
        ep_square=new_ep,
        halfmove=new_halfmove,
        fullmove=state.fullmove + (1 if state.turn == "b" else 0),
    )


def find_king(board, color):
    target = "K" if color == "w" else "k"
    for r in range(8):
        row = board[r]
        for c in range(8):
            if row[c] == target:
                return (r, c)
    return None


def is_attacked(board, r, c, by_white):
    pawn = "P" if by_white else "p"
    pr = r + (1 if by_white else -1)
    if 0 <= pr < 8:
        for dc in (-1, 1):
            pc = c + dc
            if 0 <= pc < 8 and board[pr][pc] == pawn:
                return True

    knight = "N" if by_white else "n"
    for dr, dc in KNIGHT_DELTAS:
        rr, cc = r + dr, c + dc
        if 0 <= rr < 8 and 0 <= cc < 8 and board[rr][cc] == knight:
            return True

    king = "K" if by_white else "k"
    for dr, dc in KING_DELTAS:
        rr, cc = r + dr, c + dc
        if 0 <= rr < 8 and 0 <= cc < 8 and board[rr][cc] == king:
            return True

    bishop = "B" if by_white else "b"
    rook = "R" if by_white else "r"
    queen = "Q" if by_white else "q"

    for dr, dc in BISHOP_DIRS:
        rr, cc = r + dr, c + dc
        while 0 <= rr < 8 and 0 <= cc < 8:
            p = board[rr][cc]
            if p != ".":
                if p == bishop or p == queen:
                    return True
                break
            rr += dr
            cc += dc

    for dr, dc in ROOK_DIRS:
        rr, cc = r + dr, c + dc
        while 0 <= rr < 8 and 0 <= cc < 8:
            p = board[rr][cc]
            if p != ".":
                if p == rook or p == queen:
                    return True
                break
            rr += dr
            cc += dc

    return False


def in_check(state, color):
    kp = find_king(state.board, color)
    if kp is None:
        return False
    return is_attacked(state.board, kp[0], kp[1], by_white=(color == "b"))


def _gen_pawn(state, r, c, is_white):
    moves = []
    board = state.board
    d = -1 if is_white else 1
    start_row = 6 if is_white else 1
    promo_row = 0 if is_white else 7

    nr = r + d
    if 0 <= nr < 8 and board[nr][c] == ".":
        if nr == promo_row:
            for p in ("Q", "R", "B", "N"):
                moves.append(Move(r, c, nr, c, p))
        else:
            moves.append(Move(r, c, nr, c, None))
            if r == start_row:
                nr2 = r + 2 * d
                if board[nr2][c] == ".":
                    moves.append(Move(r, c, nr2, c, None))

    for dc in (-1, 1):
        nc = c + dc
        if not (0 <= nc < 8 and 0 <= nr < 8):
            continue
        target = board[nr][nc]
        if target != "." and target.isupper() != is_white:
            if nr == promo_row:
                for p in ("Q", "R", "B", "N"):
                    moves.append(Move(r, c, nr, nc, p))
            else:
                moves.append(Move(r, c, nr, nc, None))
        elif state.ep_square == (nr, nc):
            moves.append(Move(r, c, nr, nc, None))

    return moves


def _gen_slide(state, r, c, dirs, is_white):
    moves = []
    board = state.board
    for dr, dc in dirs:
        rr, cc = r + dr, c + dc
        while 0 <= rr < 8 and 0 <= cc < 8:
            t = board[rr][cc]
            if t == ".":
                moves.append(Move(r, c, rr, cc, None))
            else:
                if t.isupper() != is_white:
                    moves.append(Move(r, c, rr, cc, None))
                break
            rr += dr
            cc += dc
    return moves


def _gen_castling(state, r, c, is_white):
    moves = []
    if is_white:
        if (r, c) != (7, 4):
            return []
        back = 7
        enemy_is_white = False
        rights = (state.castling["K"], state.castling["Q"])
    else:
        if (r, c) != (0, 4):
            return []
        back = 0
        enemy_is_white = True
        rights = (state.castling["k"], state.castling["q"])

    board = state.board

    if rights[0]:
        if (board[back][5] == "." and board[back][6] == "."
                and not is_attacked(board, back, 4, enemy_is_white)
                and not is_attacked(board, back, 5, enemy_is_white)
                and not is_attacked(board, back, 6, enemy_is_white)):
            moves.append(Move(r, c, back, 6, None))

    if rights[1]:
        if (board[back][1] == "." and board[back][2] == "."
                and board[back][3] == "."
                and not is_attacked(board, back, 4, enemy_is_white)
                and not is_attacked(board, back, 3, enemy_is_white)
                and not is_attacked(board, back, 2, enemy_is_white)):
            moves.append(Move(r, c, back, 2, None))

    return moves


def gen_pseudo_moves(state):
    moves = []
    board = state.board
    turn = state.turn
    for r in range(8):
        for c in range(8):
            p = board[r][c]
            if p == ".":
                continue
            is_white = p.isupper()
            if (turn == "w") != is_white:
                continue
            low = p.lower()
            if low == "p":
                moves.extend(_gen_pawn(state, r, c, is_white))
            elif low == "n":
                for dr, dc in KNIGHT_DELTAS:
                    rr, cc = r + dr, c + dc
                    if 0 <= rr < 8 and 0 <= cc < 8:
                        t = board[rr][cc]
                        if t == "." or t.isupper() != is_white:
                            moves.append(Move(r, c, rr, cc, None))
            elif low == "b":
                moves.extend(_gen_slide(state, r, c, BISHOP_DIRS, is_white))
            elif low == "r":
                moves.extend(_gen_slide(state, r, c, ROOK_DIRS, is_white))
            elif low == "q":
                moves.extend(_gen_slide(state, r, c,
                                        BISHOP_DIRS + ROOK_DIRS, is_white))
            elif low == "k":
                for dr, dc in KING_DELTAS:
                    rr, cc = r + dr, c + dc
                    if 0 <= rr < 8 and 0 <= cc < 8:
                        t = board[rr][cc]
                        if t == "." or t.isupper() != is_white:
                            moves.append(Move(r, c, rr, cc, None))
                moves.extend(_gen_castling(state, r, c, is_white))
    return moves


def gen_legal_moves(state):
    legal = []
    side = state.turn
    for m in gen_pseudo_moves(state):
        if not in_check(apply_move(state, m), side):
            legal.append(m)
    return legal


# ============================================================ AI
def evaluate_for_black(state):
    """Material only, positive = good for Black."""
    score = 0
    for r in range(8):
        row = state.board[r]
        for c in range(8):
            p = row[c]
            if p == ".":
                continue
            v = PIECE_VALUES[p.lower()]
            if p.isupper():
                score -= v
            else:
                score += v
    return score


def _order_moves(state, moves):
    """MVV-LVA-ish ordering: captures/promotions first, using the mover's
    value to break ties so cheap captures of expensive pieces come first."""
    def key(m):
        s = 0
        cap = state.board[m.tr][m.tc]
        if cap != ".":
            s += 10 * PIECE_VALUES.get(cap.lower(), 0)
            s -= PIECE_VALUES.get(state.board[m.fr][m.fc].lower(), 0)
        if m.promo:
            s += PIECE_VALUES.get(m.promo.lower(), 0)
        return s
    return sorted(moves, key=key, reverse=True)


def negamax(state, depth, alpha, beta):
    """Return (score from side-to-move perspective, best_move)."""
    moves = gen_legal_moves(state)
    if not moves:
        if in_check(state, state.turn):
            return -MATE_SCORE - depth, None
        return 0, None

    if depth == 0:
        s = evaluate_for_black(state)
        if state.turn == "w":
            s = -s
        return s, None

    moves = _order_moves(state, moves)
    best_score = -float("inf")
    best_move = None
    for m in moves:
        child = apply_move(state, m)
        score, _ = negamax(child, depth - 1, -beta, -alpha)
        score = -score
        if score > best_score:
            best_score = score
            best_move = m
        if score > alpha:
            alpha = score
        if alpha >= beta:
            break
    return best_score, best_move


def analyze_position(state, depth=AI_DEPTH):
    """Return [(move, score_from_side_to_move), ...] sorted best-first.
    The root uses a full window so the reported scores are exact."""
    moves = gen_legal_moves(state)
    if not moves:
        return []

    results = []
    inf = float("inf")
    for m in _order_moves(state, moves):
        child = apply_move(state, m)
        score, _ = negamax(child, depth - 1, -inf, inf)
        score = -score
        results.append((m, score))
    results.sort(key=lambda x: -x[1])
    return results


# ============================================================ helpers
CAPTURE_ORDER = {"q": 0, "r": 1, "b": 2, "n": 3, "p": 4, "k": 5}


def _sort_captured(pieces):
    return sorted(pieces, key=lambda p: CAPTURE_ORDER.get(p.lower(), 6))


def _fmt_eval_white(score_white_centipawns):
    if score_white_centipawns >= MATE_SCORE - 1000:
        return "+M"
    if score_white_centipawns <= -(MATE_SCORE - 1000):
        return "-M"
    return f"{score_white_centipawns / 100:+.2f}"


# ============================================================ history window
class MoveHistoryWindow(tk.Toplevel):
    """Read-only, copyable snapshot of the game's move log."""

    def __init__(self, master, get_text_fn):
        super().__init__(master)
        self.title("Move History")
        self.geometry("460x580")
        self.minsize(280, 240)
        self._get_text = get_text_fn

        bg = theme.color("bg")
        fg = theme.color("fg")

        self.configure(bg=bg)

        self.info_lbl = tk.Label(self, text="Full game log  •  copyable",
                                 bg=bg, fg=theme.color("muted"),
                                 font=theme.font("small"))
        self.info_lbl.pack(pady=(10, 4))

        text_frame = tk.Frame(self, bg=bg)
        text_frame.pack(fill="both", expand=True, padx=10, pady=(0, 6))

        self.text = tk.Text(
            text_frame,
            bg=theme.color("canvas_bg"), fg=fg,
            font=("Consolas", 11), wrap="none", bd=0,
            highlightthickness=0, insertbackground=fg,
        )
        self.text.pack(side="left", fill="both", expand=True)

        sb = tk.Scrollbar(text_frame, orient="vertical", command=self.text.yview)
        sb.pack(side="right", fill="y")
        self.text.config(yscrollcommand=sb.set)

        btn_frame = tk.Frame(self, bg=bg)
        btn_frame.pack(fill="x", padx=10, pady=(0, 10))

        self.status_lbl = tk.Label(btn_frame, text="", bg=bg,
                                   fg=theme.color("accent_o"),
                                   font=theme.font("small"))
        self.status_lbl.pack(side="left")

        self.close_btn = tk.Button(btn_frame, text="Close",
                                   command=self.destroy,
                                   bg=theme.color("button_bg"),
                                   fg=theme.color("button_fg"),
                                   activebackground=theme.color("button_hover"),
                                   activeforeground=theme.color("button_fg"),
                                   relief="flat", bd=0, padx=12, pady=4,
                                   font=theme.font("button"))
        self.close_btn.pack(side="right")

        self.copy_btn = tk.Button(btn_frame, text="Copy to clipboard",
                                  command=self._copy,
                                  bg=theme.color("button_bg"),
                                  fg=theme.color("button_fg"),
                                  activebackground=theme.color("button_hover"),
                                  activeforeground=theme.color("button_fg"),
                                  relief="flat", bd=0, padx=12, pady=4,
                                  font=theme.font("button"))
        self.copy_btn.pack(side="right", padx=(0, 4))

        self.refresh()

    def refresh(self):
        content = self._get_text()
        self.text.config(state="normal")
        self.text.delete("1.0", "end")
        self.text.insert("1.0", content)
        self.text.config(state="disabled")

    def _copy(self):
        content = self.text.get("1.0", "end-1c")
        self.clipboard_clear()
        self.clipboard_append(content)
        self.status_lbl.config(text="Copied to clipboard!")
        self.after(1800, lambda: self.status_lbl.config(text=""))


# ============================================================ main game
class Chess(tk.Toplevel):
    def __init__(self, master=None):
        super().__init__(master)
        self.title("Chess")
        self.geometry("860x760")
        self.minsize(560, 520)

        self.vs_computer = tk.BooleanVar(master=self, value=True)

        self.cell = 70
        self.offset_x = 0
        self.offset_y = 0

        self.state = initial_state()
        self.selected = None
        self.legal_targets = {}
        self.last_move = None
        self.game_over = False
        self.game_over_text = ""
        self.ai_thinking = False

        # Capture trackers: white_taken = black pieces White has captured, etc.
        self.white_taken = []          # list of lowercase pieces
        self.black_taken = []          # list of uppercase pieces

        # Engine display
        self.engine_depth = AI_DEPTH
        self.engine_analysis = []

        # Game log: list of (fullmove_number, side 'w'/'b', san-ish notation)
        self.move_history = []
        self._history_window = None

        self._build()
        self.apply_theme()
        self.new_game()
        self.focus_set()

    # ---------------------------------------------------------------- build
    def _build(self):
        self.status = tk.Label(self)
        self.status.pack(pady=(12, 6))

        self.middle = tk.Frame(self)
        self.middle.pack(fill="both", expand=True, padx=8, pady=(0, 4))
        self.middle.columnconfigure(1, weight=1)
        self.middle.rowconfigure(0, weight=1)

        self.left_panel = tk.Frame(self.middle, width=110)
        self.left_panel.grid(row=0, column=0, sticky="ns", padx=(0, 4))
        self.left_panel.grid_propagate(False)

        self.left_title = tk.Label(self.left_panel, text="White\nhas taken")
        self.left_title.pack(pady=(6, 2))

        self.left_pieces = tk.Label(self.left_panel, text="", justify="center")
        self.left_pieces.pack(fill="both", expand=True, padx=4, pady=(0, 6),
                              anchor="n")

        self.canvas = tk.Canvas(self.middle, highlightthickness=0)
        self.canvas.grid(row=0, column=1, sticky="nsew")
        self.canvas.bind("<Configure>", self._on_canvas_resize)
        self.canvas.bind("<Button-1>", self.on_click)

        self.right_panel = tk.Frame(self.middle, width=110)
        self.right_panel.grid(row=0, column=2, sticky="ns", padx=(4, 0))
        self.right_panel.grid_propagate(False)

        self.right_title = tk.Label(self.right_panel, text="Black\nhas taken")
        self.right_title.pack(pady=(6, 2))

        self.right_pieces = tk.Label(self.right_panel, text="", justify="center")
        self.right_pieces.pack(fill="both", expand=True, padx=4, pady=(0, 6),
                               anchor="n")

        # ----- Engine panel -----
        self.engine_frame = tk.Frame(self)
        self.engine_frame.pack(fill="x", padx=14, pady=(0, 4))

        self.engine_lbl = tk.Label(self.engine_frame, text="", justify="left",
                                   anchor="w")
        self.engine_lbl.pack(fill="x")

        # ----- Controls -----
        self.bottom = tk.Frame(self)
        self.bottom.pack(fill="x", padx=12, pady=(0, 6))

        self.vs_cb = tk.Checkbutton(
            self.bottom, text="vs Computer (you play White)",
            variable=self.vs_computer, command=self.on_vs_toggle,
            relief="flat", bd=0, highlightthickness=0)
        self.vs_cb.pack(side="left")

        self.new_btn = tk.Button(self.bottom, text="New Game",
                                 command=self.new_game, relief="flat", bd=0,
                                 padx=10, pady=3)
        self.new_btn.pack(side="right")

        self.history_btn = tk.Button(self.bottom, text="Move History",
                                     command=self.open_history,
                                     relief="flat", bd=0, padx=10, pady=3)
        self.history_btn.pack(side="right", padx=(0, 4))

        self.hint_lbl = tk.Label(
            self,
            text="Click a piece, then a highlighted square  •  R to restart")
        self.hint_lbl.pack(pady=(0, 12))

        self.bind("<KeyPress>", self.on_key)

    # ---------------------------------------------------------------- theme
    def apply_theme(self):
        bg = theme.color("bg")
        fg = theme.color("fg")
        btn_bg = theme.color("button_bg")
        btn_fg = theme.color("button_fg")
        hover = theme.color("button_hover")

        self.configure(bg=bg)
        self.status.configure(bg=bg, fg=fg, font=theme.font("status", "bold"))
        self.middle.configure(bg=bg)
        for p in (self.left_panel, self.right_panel):
            p.configure(bg=bg)
        for lbl in (self.left_title, self.right_title):
            lbl.configure(bg=bg, fg=theme.color("muted"),
                          font=theme.font("small"))

        # Captured panels: the pieces they show are the *opponent's* colour.
        self.left_pieces.configure(bg=bg, fg=theme.color("piece_black"),
                                   font=theme.font("heading"))
        self.right_pieces.configure(bg=bg, fg=theme.color("piece_white"),
                                    font=theme.font("heading"))

        self.engine_frame.configure(bg=bg)
        self.engine_lbl.configure(bg=bg, fg=theme.color("muted"),
                                  font=theme.font("small"))
        self.bottom.configure(bg=bg)
        self.hint_lbl.configure(bg=bg, fg=theme.color("muted"),
                                font=theme.font("small"))
        self.canvas.configure(bg=theme.color("canvas_bg"))

        self.vs_cb.configure(bg=bg, fg=fg, selectcolor=btn_bg,
                             activebackground=bg, activeforeground=fg,
                             font=theme.font("body"))
        for btn in (self.new_btn, self.history_btn):
            btn.configure(bg=btn_bg, fg=btn_fg,
                          activebackground=hover, activeforeground=btn_fg,
                          font=theme.font("button"))

        self.draw()
        self._update_captures_display()

    # ----------------------------------------------------------- game flow
    def new_game(self):
        self.state = initial_state()
        self.selected = None
        self.legal_targets = {}
        self.last_move = None
        self.game_over = False
        self.game_over_text = ""
        self.ai_thinking = False
        self.white_taken = []
        self.black_taken = []
        self.engine_analysis = []
        self.engine_depth = AI_DEPTH
        self.move_history = []
        self.update_status()
        self.draw()
        self._update_captures_display()
        if self._history_window and self._history_window.winfo_exists():
            self._history_window.refresh()
        self.after(10, self.refresh_engine)

    def on_vs_toggle(self):
        if (self.vs_computer.get() and self.state.turn == "b"
                and not self.game_over and not self.ai_thinking):
            self.ai_thinking = True
            self.update_status()
            self.after(50, self.ai_move)
        else:
            self.update_status()

    def on_key(self, event):
        if event.keysym.lower() == "r":
            self.new_game()
        elif event.keysym.lower() == "h":
            self.open_history()

    def on_click(self, event):
        if self.game_over or self.ai_thinking:
            return
        if self.vs_computer.get() and self.state.turn == "b":
            return
        if self.cell <= 0:
            return

        c = int((event.x - self.offset_x) // self.cell)
        r = int((event.y - self.offset_y) // self.cell)
        if not (0 <= r < 8 and 0 <= c < 8):
            return

        if (r, c) in self.legal_targets:
            moves = self.legal_targets[(r, c)]
            if len(moves) == 1:
                self.execute_move(moves[0])
            else:
                promo = self.ask_promotion(self.state.turn == "w")
                if promo is None:
                    return
                mv = next(m for m in moves if m.promo == promo)
                self.execute_move(mv)
            return

        piece = self.state.board[r][c]
        if piece != "." and (piece.isupper() == (self.state.turn == "w")):
            self.selected = (r, c)
            self.recompute_targets()
            self.draw()
            return

        self.selected = None
        self.legal_targets = {}
        self.draw()

    def recompute_targets(self):
        self.legal_targets = {}
        if self.selected is None:
            return
        fr, fc = self.selected
        for m in gen_legal_moves(self.state):
            if m.fr == fr and m.fc == fc:
                self.legal_targets.setdefault((m.tr, m.tc), []).append(m)

    def _detect_capture(self, move):
        fr, fc, tr, tc, _ = move
        target = self.state.board[tr][tc]
        if target != ".":
            return target
        piece = self.state.board[fr][fc]
        if piece.lower() == "p" and fc != tc:
            cap_r = tr + (1 if piece.isupper() else -1)
            return self.state.board[cap_r][tc]
        return None

    def _format_move(self, state_before, move):
        """SAN-ish string: e2e4, g1f3, e4xd5, e7e8=Q, O-O, O-O-O."""
        piece = state_before.board[move.fr][move.fc]
        cap = state_before.board[move.tr][move.tc]
        is_ep = (piece.lower() == "p" and move.fc != move.tc and cap == ".")
        is_capture = (cap != ".") or is_ep

        # Castling
        if piece.lower() == "k" and abs(move.tc - move.fc) == 2:
            return "O-O" if move.tc > move.fc else "O-O-O"

        s = ""
        if piece.lower() != "p":
            s += piece.upper()
        else:
            if is_capture:
                s += FILES[move.fc]         # pawn captures include origin file

        s += f"{FILES[move.fc]}{8 - move.fr}"
        if is_capture:
            s += "x"
        s += f"{FILES[move.tc]}{8 - move.tr}"
        if move.promo:
            s += "=" + move.promo.upper()
        return s

    def execute_move(self, move):
        # Record history BEFORE applying (state must reflect the position).
        notation = self._format_move(self.state, move)
        self.move_history.append((self.state.fullmove, self.state.turn, notation))

        captured = self._detect_capture(move)
        if captured:
            if captured.isupper():
                self.black_taken.append(captured)
            else:
                self.white_taken.append(captured)

        self.state = apply_move(self.state, move)
        self.last_move = move
        self.selected = None
        self.legal_targets = {}

        self.check_game_over()
        self.update_status()
        self.draw()
        self._update_captures_display()

        if self._history_window and self._history_window.winfo_exists():
            self._history_window.refresh()

        if self.game_over:
            self.after(10, self.refresh_engine)
            return

        if self.vs_computer.get() and self.state.turn == "b":
            self.ai_thinking = True
            self.update_status()
            self.after(50, self.ai_move)
        else:
            self.after(10, self.refresh_engine)

    def ai_move(self):
        if self.game_over or self.state.turn != "b" or not self.vs_computer.get():
            self.ai_thinking = False
            return

        analysis = analyze_position(self.state, AI_DEPTH)
        if not analysis:
            self.ai_thinking = False
            self.check_game_over()
            self.update_status()
            self.draw()
            return

        self._update_engine_display(analysis, AI_DEPTH)

        best_score = analysis[0][1]
        ties = [m for m, s in analysis if s == best_score]
        move = random.choice(ties)
        self.ai_thinking = False
        self.execute_move(move)

    def check_game_over(self):
        if self.state.halfmove >= 100:
            self.game_over = True
            self.game_over_text = "Draw — fifty-move rule."
            return

        if not gen_legal_moves(self.state):
            if in_check(self.state, self.state.turn):
                winner = "Black" if self.state.turn == "w" else "White"
                self.game_over = True
                self.game_over_text = f"Checkmate — {winner} wins!"
            else:
                self.game_over = True
                self.game_over_text = "Stalemate — draw."

    def update_status(self):
        if self.game_over:
            self.status.config(text=self.game_over_text)
            return
        if self.ai_thinking:
            self.status.config(text="Computer thinking...")
            return

        side = "White" if self.state.turn == "w" else "Black"
        if self.vs_computer.get():
            suffix = " — your turn" if self.state.turn == "w" else ""
        else:
            suffix = "'s turn"
        if in_check(self.state, self.state.turn):
            self.status.config(text=f"{side}{suffix}  •  Check!")
        else:
            self.status.config(text=f"{side}{suffix}")

    # ------------------------------------------------------ captures panel
    def _update_captures_display(self):
        left_sorted = _sort_captured(self.white_taken)      # black pieces
        right_sorted = _sort_captured(self.black_taken)     # white pieces
        self.left_pieces.config(
            text=" ".join(UNICODE[p] for p in left_sorted) or "—")
        self.right_pieces.config(
            text=" ".join(UNICODE[p] for p in right_sorted) or "—")

    # ---------------------------------------------------- engine display
    def refresh_engine(self):
        if self.game_over:
            self.engine_lbl.config(text="Game over — no further analysis.")
            return
        analysis = analyze_position(self.state, AI_DEPTH)
        self._update_engine_display(analysis, AI_DEPTH)

    def _update_engine_display(self, analysis, depth):
        self.engine_analysis = analysis
        self.engine_depth = depth

        if not analysis:
            self.engine_lbl.config(text=f"Depth {depth}  •  No legal moves.")
            return

        side_sign = 1 if self.state.turn == "w" else -1
        side_name = "White" if self.state.turn == "w" else "Black"

        best_side_score = analysis[0][1]
        eval_white = best_side_score * side_sign

        lines = [
            f"Depth {depth}  •  Eval {_fmt_eval_white(eval_white)} (White POV)"
            f"  •  Best for {side_name}:"
        ]
        for i, (m, score_side) in enumerate(analysis[:3], start=1):
            eval_for_side = _fmt_eval_white(score_side * side_sign)
            lines.append(f"    {i}. {move_uci(m)}   {eval_for_side}")

        self.engine_lbl.config(text="\n".join(lines))

    # ---------------------------------------------------- history window
    def _format_history_text(self):
        if not self.move_history:
            return "No moves have been played yet."
        lines = ["Chess game log", "=" * 13, ""]
        i = 0
        while i < len(self.move_history):
            num, side, notation = self.move_history[i]
            if side == "w":
                if (i + 1 < len(self.move_history)
                        and self.move_history[i + 1][1] == "b"):
                    _, _, bnote = self.move_history[i + 1]
                    lines.append(f"{num:>3}. {notation:<10s} {bnote}")
                    i += 2
                else:
                    lines.append(f"{num:>3}. {notation}")
                    i += 1
            else:
                lines.append(f"{num:>3}. ... {notation}")
                i += 1

        # Captured summary
        lines.append("")
        lines.append("Captured by White:  "
                     + (" ".join(UNICODE[p] for p in _sort_captured(self.white_taken))
                        or "—"))
        lines.append("Captured by Black:  "
                     + (" ".join(UNICODE[p] for p in _sort_captured(self.black_taken))
                        or "—"))

        if self.game_over:
            lines.append("")
            lines.append(self.game_over_text)
        return "\n".join(lines)

    def open_history(self):
        if self._history_window and self._history_window.winfo_exists():
            self._history_window.refresh()
            self._history_window.lift()
            self._history_window.focus_force()
            return
        self._history_window = MoveHistoryWindow(self, self._format_history_text)

    # ------------------------------------------------------ promotion
    def ask_promotion(self, is_white):
        dlg = tk.Toplevel(self)
        dlg.title("Promote Pawn")
        dlg.transient(self)
        dlg.resizable(False, False)

        result = [None]

        bg = theme.color("bg")
        fg = theme.color("fg")
        btn_bg = theme.color("button_bg")
        btn_fg = theme.color("button_fg")
        hover = theme.color("button_hover")

        dlg.configure(bg=bg)
        tk.Label(dlg, text="Promote to:", bg=bg, fg=fg,
                 font=theme.font("body")).pack(padx=14, pady=(12, 8))
        frame = tk.Frame(dlg, bg=bg)
        frame.pack(padx=14, pady=(0, 12))

        def choose(code):
            result[0] = code
            dlg.destroy()

        for code, name in (("Q", "Queen"), ("R", "Rook"),
                           ("B", "Bishop"), ("N", "Knight")):
            key = code if is_white else code.lower()
            tk.Button(frame, text=f"{UNICODE[key]} {name}", width=11,
                      bg=btn_bg, fg=btn_fg,
                      activebackground=hover, activeforeground=btn_fg,
                      relief="flat", bd=0, padx=8, pady=4,
                      font=theme.font("button"),
                      command=lambda c=code: choose(c)
                      ).pack(side="left", padx=3)

        dlg.update_idletasks()
        try:
            dlg.grab_set()
        except tk.TclError:
            pass
        dlg.wait_window()
        return result[0]

    # ------------------------------------------------------------ render
    def _on_canvas_resize(self, event):
        size = min(event.width, event.height) - 8
        self.cell = size / 8
        self.offset_x = (event.width - self.cell * 8) / 2
        self.offset_y = (event.height - self.cell * 8) / 2
        self.draw()

    def _px(self, c):
        return self.offset_x + c * self.cell

    def _py(self, r):
        return self.offset_y + r * self.cell

    def draw(self):
        if self.cell <= 0:
            return
        self.canvas.delete("all")

        light = theme.color("board_light")
        dark = theme.color("board_dark")
        fg = theme.color("fg")
        accent_x = theme.color("accent_x")
        accent_o = theme.color("accent_o")

        # --- Board squares ---
        for r in range(8):
            for c in range(8):
                fill = light if (r + c) % 2 == 0 else dark
                self.canvas.create_rectangle(
                    self._px(c), self._py(r),
                    self._px(c + 1), self._py(r + 1),
                    fill=fill, outline="")

        # --- Last-move squares ---
        if self.last_move is not None:
            lm = self.last_move
            for (rr, cc) in ((lm.fr, lm.fc), (lm.tr, lm.tc)):
                self.canvas.create_rectangle(
                    self._px(cc) + 2, self._py(rr) + 2,
                    self._px(cc + 1) - 2, self._py(rr + 1) - 2,
                    outline=accent_o, width=2)

        # --- Selected piece highlight ---
        if self.selected is not None:
            r, c = self.selected
            self.canvas.create_rectangle(
                self._px(c) + 1, self._py(r) + 1,
                self._px(c + 1) - 1, self._py(r + 1) - 1,
                outline=accent_x, width=3)

        # --- King in check ---
        if not self.game_over and in_check(self.state, self.state.turn):
            kp = find_king(self.state.board, self.state.turn)
            if kp:
                kr, kc = kp
                self.canvas.create_rectangle(
                    self._px(kc) + 1, self._py(kr) + 1,
                    self._px(kc + 1) - 1, self._py(kr + 1) - 1,
                    outline=accent_o, width=3)

        # --- Legal-target markers ---
        for (tr, tc), moves in self.legal_targets.items():
            target = self.state.board[tr][tc]
            mv = moves[0]
            src = self.state.board[mv.fr][mv.fc]
            is_ep = (src.lower() == "p" and mv.fc != tc and target == ".")
            is_capture = target != "." or is_ep
            if is_capture:
                pad = self.cell * 0.08
                self.canvas.create_oval(
                    self._px(tc) + pad, self._py(tr) + pad,
                    self._px(tc + 1) - pad, self._py(tr + 1) - pad,
                    outline=accent_o, width=3)
            else:
                pad = self.cell * 0.36
                self.canvas.create_oval(
                    self._px(tc) + pad, self._py(tr) + pad,
                    self._px(tc + 1) - pad, self._py(tr + 1) - pad,
                    fill=accent_o, outline="")

        # --- Pieces: stroke in outline colour, then fill on top ---
        font_size = max(8, int(self.cell * 0.72))
        stroke = max(1, int(self.cell * 0.028))
        offsets = [(-stroke, 0), (stroke, 0), (0, -stroke), (0, stroke),
                   (-stroke, -stroke), (stroke, -stroke),
                   (-stroke, stroke), (stroke, stroke)]

        for r in range(8):
            row = self.state.board[r]
            for c in range(8):
                p = row[c]
                if p == ".":
                    continue
                is_white = p.isupper()
                glyph = SOLID_UNICODE[p.lower()]
                interior = (theme.color("piece_white") if is_white
                            else theme.color("piece_black"))
                outline = accent_x if is_white else accent_o

                cx = self._px(c) + self.cell / 2
                cy = self._py(r) + self.cell / 2

                # Stroke layer: offset copies in the outline colour.
                for dx, dy in offsets:
                    self.canvas.create_text(
                        cx + dx, cy + dy, text=glyph,
                        fill=outline,
                        font=(theme.font_family, font_size))

                # Fill layer: the same glyph on top in the interior colour.
                self.canvas.create_text(
                    cx, cy, text=glyph,
                    fill=interior,
                    font=(theme.font_family, font_size))

        # --- Outer border ---
        self.canvas.create_rectangle(
            self._px(0), self._py(0), self._px(8), self._py(8),
            outline=fg, width=2)


def run(master=None):
    return Chess(master)