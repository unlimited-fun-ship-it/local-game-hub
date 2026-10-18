"""Connect Four - drop discs, line up four in a row."""

import atexit
import os
import pickle
import random
import struct
import threading
import tkinter as tk
from collections import OrderedDict

import save_manager
import memoization_manager as memo
from theme import theme

GAME_ID = "connect4"
COLS, ROWS = 7, 6
WIN_LENGTH = 4
EMPTY = 0
PLAYER1 = 1
PLAYER2 = 2

CHECK_DIRS = [(0, 1), (1, 0), (1, 1), (1, -1)]
DIFFICULTIES = ("Easy", "Medium", "Hard")

# ============================================================ opening book
_BOOK_DIR = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "opening_books", "connect4"))
_opening_book = {}
_book_loaded = False
_book_loading = False

def _load_opening_book():
    global _opening_book, _book_loaded, _book_loading
    if _book_loaded or _book_loading: return
    _book_loading = True

    if not os.path.exists(_BOOK_DIR):
        os.makedirs(_BOOK_DIR, exist_ok=True); _book_loading = False; return

    best_file, best_depth = None, -1
    for f in os.listdir(_BOOK_DIR):
        if f.startswith("opening_book_depth") and f.endswith(".bin"):
            try:
                depth = int(f.replace("opening_book_depth", "").replace(".bin", ""))
                if depth > best_depth: best_depth, best_file = depth, os.path.join(_BOOK_DIR, f)
            except ValueError: pass

    if not best_file: _book_loading = False; return

    pkl_file = best_file + ".pkl"
    if os.path.exists(pkl_file):
        try:
            with open(pkl_file, "rb") as f: _opening_book = pickle.load(f)
            _book_loaded = True; _book_loading = False; return
        except Exception: pass

    try:
        with open(best_file, "rb") as f:
            raw_len = f.read(8)
            if len(raw_len) < 8: raise ValueError("File too short")
            length = struct.unpack("<Q", raw_len)[0]
            raw_data = f.read(length * 9)
            if len(raw_data) != length * 9: raise ValueError("File truncated")
            book = dict(struct.iter_unpack("<Qb", raw_data))
        try:
            with open(pkl_file, "wb") as f: pickle.dump(book, f)
        except Exception: pass
        _opening_book = book; _book_loaded = True
    except Exception as e: print(f"Failed to load opening book: {e}")
    _book_loading = False

def _mirror_bb(bb):
    res = 0
    for _ in range(7): res <<= 7; res |= (bb & 0x7F); bb >>= 7
    return res

def _board_to_bitboards(board, current_player):
    position, mask = 0, 0
    for r in range(ROWS):
        for c in range(COLS):
            p = board[r][c]
            if p == EMPTY: continue
            bit = c * 7 + (5 - r); mask |= (1 << bit)
            if p == current_player: position |= (1 << bit)
    return position, mask

def _get_book_key(pos, mask):
    key = pos + mask; m_pos = _mirror_bb(pos); m_mask = _mirror_bb(mask); m_key = m_pos + m_mask
    return min(key, m_key)

# ============================================================ memoization
_CACHE_DIR = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "memoization", "connect4"))
_CACHE_PATH = os.path.join(_CACHE_DIR, "memo.pkl")
_memo_cache = OrderedDict()
_memo_stats = {"hits": 0, "misses": 0}
_memo_loaded_from_file = False

def _ensure_cache_dir():
    try: os.makedirs(_CACHE_DIR, exist_ok=True)
    except OSError: pass

def load_memo_from_disk():
    global _memo_cache, _memo_loaded_from_file
    if not memo.is_enabled(GAME_ID): return False
    if not os.path.exists(_CACHE_PATH): return False
    try:
        with open(_CACHE_PATH, "rb") as f:
            data = pickle.load(f)
        cache = data.get("cache")
        if not isinstance(cache, dict): return False
        _memo_cache = OrderedDict(cache); _memo_loaded_from_file = True
        return True
    except Exception: return False

def save_memo_to_disk():
    if not memo.is_enabled(GAME_ID): return False
    _ensure_cache_dir()
    try:
        with open(_CACHE_PATH, "wb") as f: pickle.dump({"version": 1, "cache": dict(_memo_cache)}, f)
        return True
    except OSError: return False

_memo_loaded_from_file = load_memo_from_disk()
atexit.register(save_memo_to_disk)

# ============================================================ board helpers
def _empty_board(): return [[EMPTY] * COLS for _ in range(ROWS)]
def _column_height(board, c):
    for r in range(ROWS - 1, -1, -1):
        if board[r][c] == EMPTY: return r
    return None
def _legal_columns(board): return [c for c in range(COLS) if board[0][c] == EMPTY]
def _is_full(board): return all(board[0][c] != EMPTY for c in range(COLS))
def _is_empty(board): return all(board[r][c] == EMPTY for r in range(ROWS) for c in range(COLS))

def _find_win(board, r, c):
    player = board[r][c]
    if player == EMPTY: return None
    for dr, dc in CHECK_DIRS:
        cells = [(r, c)]
        rr, cc = r + dr, c + dc
        while 0 <= rr < ROWS and 0 <= cc < COLS and board[rr][cc] == player: cells.append((rr, cc)); rr += dr; cc += dc
        rr, cc = r - dr, c - dc
        while 0 <= rr < ROWS and 0 <= cc < COLS and board[rr][cc] == player: cells.insert(0, (rr, cc)); rr -= dr; cc -= dc
        if len(cells) >= WIN_LENGTH: return cells
    return None

# ============================================================ AI heuristic
def _winning_column(board, player):
    for c in _legal_columns(board):
        r = _column_height(board, c)
        if r is None: continue
        board[r][c] = player; win = _find_win(board, r, c); board[r][c] = EMPTY
        if win: return c
    return None

def _score_window(window, ai_player, opp):
    a_count, o_count, empty_count = window.count(ai_player), window.count(opp), window.count(EMPTY)
    if a_count > 0 and o_count > 0: return 0
    if a_count == 4: return 100000
    elif a_count == 3 and empty_count == 1: return 50
    elif a_count == 2 and empty_count == 2: return 10
    elif a_count == 1 and empty_count == 3: return 1
    elif o_count == 4: return -100000
    elif o_count == 3 and empty_count == 1: return -50
    elif o_count == 2 and empty_count == 2: return -10
    elif o_count == 1 and empty_count == 3: return -1
    return 0

def _evaluate(board, ai_player):
    opp = 3 - ai_player; score = 0
    for r in range(ROWS):
        if board[r][COLS // 2] == ai_player: score += 3
        elif board[r][COLS // 2] == opp: score -= 3
    for r in range(ROWS):
        for c in range(COLS - 3): score += _score_window([board[r][c + i] for i in range(4)], ai_player, opp)
    for r in range(ROWS - 3):
        for c in range(COLS): score += _score_window([board[r + i][c] for i in range(4)], ai_player, opp)
    for r in range(ROWS - 3):
        for c in range(COLS - 3): score += _score_window([board[r + i][c + i] for i in range(4)], ai_player, opp)
    for r in range(3, ROWS):
        for c in range(COLS - 3): score += _score_window([board[r - i][c + i] for i in range(4)], ai_player, opp)
    return score

def _canonicalize_c4(board_tuple):
    flipped = tuple(tuple(row[COLS - 1 - c] for c in range(COLS)) for row in board_tuple)
    return min(board_tuple, flipped)

def _minimax(board_tuple, depth, alpha, beta, maximizing, ai_player):
    use_cache = memo.is_enabled(GAME_ID)
    if use_cache:
        canon_board = _canonicalize_c4(board_tuple)
        key = (canon_board, depth, maximizing)
        if key in _memo_cache:
            _memo_stats["hits"] += 1; _memo_cache.move_to_end(key); return _memo_cache[key]
        _memo_stats["misses"] += 1

    board = [list(row) for row in board_tuple]
    if depth == 0 or _is_full(board): return _evaluate(board, ai_player)
    legal = _legal_columns(board)
    if not legal: return _evaluate(board, ai_player)

    legal.sort(key=lambda c: abs(c - COLS // 2))
    human = 3 - ai_player; current = ai_player if maximizing else human
    best_score = -float("inf") if maximizing else float("inf")

    for c in legal:
        r = _column_height(board, c)
        if r is None: continue
        board[r][c] = current; win = _find_win(board, r, c)
        if win:
            score = (100000 - (10 - depth)) if maximizing else (-100000 + (10 - depth))
            board[r][c] = EMPTY
            if maximizing and score > best_score: best_score = score
            elif not maximizing and score < best_score: best_score = score
            continue
        child_tuple = tuple(tuple(row) for row in board)
        child_score = _minimax(child_tuple, depth - 1, alpha, beta, not maximizing, ai_player)
        board[r][c] = EMPTY
        if maximizing:
            if child_score > best_score: best_score = child_score
            if child_score > alpha: alpha = child_score
        else:
            if child_score < best_score: best_score = child_score
            if child_score < beta: beta = child_score
        if alpha >= beta: break

    if use_cache and alpha < best_score < beta:
        _memo_cache[key] = best_score
        if len(_memo_cache) > memo.get_max_entries(GAME_ID): _memo_cache.popitem(last=False)

    return best_score

def choose_ai_move(board, ai_player, difficulty, use_book):
    legal = _legal_columns(board)
    if not legal: return None
    if _is_empty(board): return COLS // 2

    if difficulty == "Easy":
        win = _winning_column(board, ai_player)
        if win is not None: return win
        return random.choice(legal)

    if difficulty == "Medium":
        win = _winning_column(board, ai_player)
        if win is not None: return win
        block = _winning_column(board, 3 - ai_player)
        if block is not None: return block
        legal.sort(key=lambda c: abs(c - COLS // 2))
        return legal[0]

    if use_book and _opening_book:
        pos, mask = _board_to_bitboards(board, ai_player)
        key = _get_book_key(pos, mask)
        if key in _opening_book:
            target_score = _opening_book[key]
            for c in legal:
                r = _column_height(board, c); board[r][c] = ai_player
                c_pos, c_mask = _board_to_bitboards(board, 3 - ai_player)
                c_key = _get_book_key(c_pos, c_mask); board[r][c] = EMPTY
                if _opening_book.get(c_key) == -target_score: return c

    win = _winning_column(board, ai_player)
    if win is not None: return win
    block = _winning_column(board, 3 - ai_player)
    if block is not None: return block

    best_score = -float("inf"); best_col = legal[0]
    legal.sort(key=lambda c: abs(c - COLS // 2))
    for c in legal:
        r = _column_height(board, c); board[r][c] = ai_player
        child_tuple = tuple(tuple(row) for row in board)
        score = _minimax(child_tuple, 6, -float("inf"), float("inf"), False, ai_player)
        board[r][c] = EMPTY
        if score > best_score: best_score = score; best_col = c
    return best_col

# ============================================================ game window
class ConnectFour(tk.Toplevel):
    def __init__(self, master=None):
        super().__init__(master)
        self.title("Connect Four"); self.geometry("720x760"); self.minsize(420, 460)
        self.vs_computer = tk.BooleanVar(master=self, value=True)
        self.difficulty = tk.StringVar(master=self, value="Medium")
        self.use_book = tk.BooleanVar(master=self, value=True)
        self.board = _empty_board(); self.turn = PLAYER1; self.winner = None; self.is_draw = False
        self.win_cells = []; self.last_move = None; self.ai_thinking = False; self._ai_after_id = None
        self.cell = 60; self.offset_x = 0; self.offset_y = 0
        self.hover_col = None; self.keyboard_col = COLS // 2; self.use_keyboard_selector = False
        self._build(); self.apply_theme(); self.new_game(); self._update_memo_label()
        self.protocol("WM_DELETE_WINDOW", self._on_close); self._poll_book_status(); self.focus_set()

    def _on_close(self): save_memo_to_disk(); self.destroy()

    def _build(self):
        self.status = tk.Label(self); self.status.pack(pady=(12, 6))
        self.canvas = tk.Canvas(self, highlightthickness=0); self.canvas.pack(fill="both", expand=True, padx=12, pady=(0, 6))
        self.canvas.bind("<Configure>", self._on_canvas_resize); self.canvas.bind("<Button-1>", self.on_click); self.canvas.bind("<Motion>", self.on_hover); self.canvas.bind("<Leave>", lambda e: self._set_hover(None))
        self.bottom = tk.Frame(self); self.bottom.pack(fill="x", padx=12, pady=(0, 4))
        self.vs_cb = tk.Checkbutton(self.bottom, text="vs Computer", variable=self.vs_computer, command=self._on_vs_toggle, relief="flat", bd=0, highlightthickness=0); self.vs_cb.pack(side="left")
        self.book_cb = tk.Checkbutton(self.bottom, text="Use Book", variable=self.use_book, relief="flat", bd=0, highlightthickness=0); self.book_cb.pack(side="left", padx=(10, 0))
        self.diff_frame = tk.Frame(self.bottom); self.diff_frame.pack(side="left", padx=(10, 0))
        self.diff_label = tk.Label(self.diff_frame, text="AI:"); self.diff_label.pack(side="left", padx=(0, 4))
        self.diff_btns = {}
        for d in DIFFICULTIES:
            b = tk.Button(self.diff_frame, text=d, relief="flat", bd=0, padx=6, pady=2, command=lambda d=d: self._set_difficulty(d)); b.pack(side="left", padx=(2, 0)); self.diff_btns[d] = b
        self.new_btn = tk.Button(self.bottom, text="New", command=self.new_game, relief="flat", bd=0, padx=10, pady=3); self.new_btn.pack(side="right")
        self.load_btn = tk.Button(self.bottom, text="Load", command=self.load_game, relief="flat", bd=0, padx=10, pady=3); self.load_btn.pack(side="right", padx=(0, 4))
        self.save_btn = tk.Button(self.bottom, text="Save", command=self.save_game, relief="flat", bd=0, padx=10, pady=3); self.save_btn.pack(side="right", padx=(0, 4))
        self.hint_lbl = tk.Label(self, text="Click a column  •  Arrows + Enter  •  1-7 quick-drop  •  R to restart"); self.hint_lbl.pack(pady=(0, 4))
        self.memo_lbl = tk.Label(self, text="", anchor="center"); self.memo_lbl.pack(fill="x", padx=12, pady=(0, 12))
        self.bind("<KeyPress>", self.on_key)

    def apply_theme(self):
        bg, fg = theme.color("bg"), theme.color("fg"); btn_bg, btn_fg, hover = theme.color("button_bg"), theme.color("button_fg"), theme.color("button_hover")
        self.configure(bg=bg); self.status.configure(bg=bg, fg=fg, font=theme.font("status", "bold")); self.bottom.configure(bg=bg); self.diff_frame.configure(bg=bg)
        self.diff_label.configure(bg=bg, fg=theme.color("muted"), font=theme.font("small")); self.hint_lbl.configure(bg=bg, fg=theme.color("muted"), font=theme.font("small"))
        self.memo_lbl.configure(bg=bg, fg=theme.color("muted"), font=theme.font("small")); self.canvas.configure(bg=theme.color("canvas_bg"))
        self.vs_cb.configure(bg=bg, fg=fg, selectcolor=btn_bg, activebackground=bg, activeforeground=fg, font=theme.font("body"))
        self.book_cb.configure(bg=bg, fg=fg, selectcolor=btn_bg, activebackground=bg, activeforeground=fg, font=theme.font("body"))
        for btn in (self.new_btn, self.save_btn, self.load_btn): btn.configure(bg=btn_bg, fg=btn_fg, activebackground=hover, activeforeground=btn_fg, font=theme.font("button"))
        for d, b in self.diff_btns.items(): b.configure(bg=theme.color("accent_x") if d == self.difficulty.get() else btn_bg, fg=btn_fg, activebackground=hover, activeforeground=btn_fg, font=theme.font("button"))
        self.draw()

    def _set_difficulty(self, d):
        self.difficulty.set(d); btn_bg, btn_fg, hover = theme.color("button_bg"), theme.color("button_fg"), theme.color("button_hover")
        for name, b in self.diff_btns.items(): b.configure(bg=theme.color("accent_x") if name == d else btn_bg, fg=btn_fg, activebackground=hover, activeforeground=btn_fg)

    def new_game(self):
        self._cancel_ai(); self.board = _empty_board(); self.turn = PLAYER1; self.winner = None; self.is_draw = False
        self.win_cells = []; self.last_move = None; self.ai_thinking = False; self.hover_col = None; self.keyboard_col = COLS // 2; self.use_keyboard_selector = False
        self.update_status(); self.draw(); self._update_memo_label()

    def _on_vs_toggle(self):
        if (self.winner is None and not self.is_draw and self.vs_computer.get() and self.turn == PLAYER2): self._schedule_ai()
        else: self.update_status(); self.draw()

    def _player_name(self, p):
        if self.vs_computer.get(): return "You" if p == PLAYER1 else "Computer"
        return "Player 1" if p == PLAYER1 else "Player 2"

    def update_status(self):
        if self.is_draw: self.status.config(text="Draw - the board is full.")
        elif self.winner is not None: self.status.config(text=f"{self._player_name(self.winner)} wins! \U0001F389")
        elif self.ai_thinking: self.status.config(text="Computer thinking...")
        else: self.status.config(text=f"{self._player_name(self.turn)}'s turn")

    def on_key(self, event):
        if getattr(event, "state", 0) & 0x0004: return
        k = event.keysym.lower()
        if k == "r": self.new_game(); return
        if self.winner is not None or self.is_draw or self.ai_thinking: return
        if self.vs_computer.get() and self.turn == PLAYER2: return
        if k in ("left", "a"): self.keyboard_col = (self.keyboard_col - 1) % COLS; self.use_keyboard_selector = True; self.draw()
        elif k in ("right", "d"): self.keyboard_col = (self.keyboard_col + 1) % COLS; self.use_keyboard_selector = True; self.draw()
        elif k in ("return", "space", "kp_enter"): self._attempt_drop(self.keyboard_col)
        elif k.isdigit() and 1 <= int(k) <= COLS: self._attempt_drop(int(k) - 1)

    def on_click(self, event):
        if self.winner is not None or self.is_draw or self.ai_thinking: return
        if self.vs_computer.get() and self.turn == PLAYER2: return
        if self.cell <= 0: return
        c = int((event.x - self.offset_x) // self.cell)
        if 0 <= c < COLS: self._attempt_drop(c)

    def on_hover(self, event):
        if self.winner is not None or self.is_draw or self.ai_thinking: self._set_hover(None); return
        if self.vs_computer.get() and self.turn == PLAYER2: self._set_hover(None); return
        if self.cell <= 0: return
        c = int((event.x - self.offset_x) // self.cell)
        self._set_hover(c if 0 <= c < COLS else None); self.use_keyboard_selector = False

    def _set_hover(self, col):
        if self.hover_col != col: self.hover_col = col; self.draw()

    def _attempt_drop(self, c):
        if not (0 <= c < COLS) or self.board[0][c] != EMPTY: return
        self._drop(c)

    def _drop(self, c):
        r = _column_height(self.board, c)
        if r is None: return
        self.board[r][c] = self.turn; self.last_move = (r, c)
        win = _find_win(self.board, r, c)
        if win: self.winner = self.turn; self.win_cells = win
        elif _is_full(self.board): self.is_draw = True
        else:
            self.turn = 3 - self.turn
            if self.vs_computer.get() and self.turn == PLAYER2: self._schedule_ai()
        self.update_status(); self.draw()

    def _schedule_ai(self):
        self._cancel_ai(); self.ai_thinking = True; self.update_status(); self._ai_after_id = self.after(250, self._ai_move)

    def _cancel_ai(self):
        if self._ai_after_id is not None:
            try: self.after_cancel(self._ai_after_id)
            except tk.TclError: pass
            self._ai_after_id = None

    def _ai_move(self):
        self._ai_after_id = None
        if (self.winner is not None or self.is_draw or not self.vs_computer.get() or self.turn != PLAYER2): self.ai_thinking = False; return
        col = choose_ai_move(self.board, PLAYER2, self.difficulty.get(), self.use_book.get())
        self.ai_thinking = False
        if col is not None: self._drop(col); self._update_memo_label(); save_memo_to_disk()
        else: self.update_status(); self.draw()

    def get_state(self):
        return {"board": self.board, "turn": self.turn, "winner": self.winner, "is_draw": self.is_draw, "win_cells": self.win_cells, "last_move": list(self.last_move) if self.last_move else None, "vs_computer": self.vs_computer.get(), "difficulty": self.difficulty.get(), "use_book": self.use_book.get()}

    def set_state(self, data):
        self._cancel_ai(); self.board = [row[:] for row in data["board"]]; self.turn = data["turn"]
        self.winner = data.get("winner"); self.is_draw = bool(data.get("is_draw", False))
        self.win_cells = [tuple(cell) for cell in data.get("win_cells", [])]
        lm = data.get("last_move"); self.last_move = tuple(lm) if lm else None
        self.vs_computer.set(data.get("vs_computer", True)); self.difficulty.set(data.get("difficulty", "Medium")); self.use_book.set(data.get("use_book", True))
        self.ai_thinking = False; self.hover_col = None; self.use_keyboard_selector = False
        self.apply_theme(); self.update_status(); self.draw(); self._update_memo_label()
        if (self.winner is None and not self.is_draw and self.vs_computer.get() and self.turn == PLAYER2): self._schedule_ai()

    def save_game(self): save_manager.prompt_save(self, GAME_ID, self.get_state())
    def load_game(self):
        fname = save_manager.prompt_load(self, GAME_ID)
        if fname: self.set_state(save_manager.load_game(GAME_ID, fname))

    def _on_canvas_resize(self, event):
        if event.width < 40 or event.height < 40: return
        avail_w, avail_h = event.width - 20, event.height - 10
        self.cell = max(10, min(avail_w / COLS, avail_h / ROWS, 80))
        board_w, board_h = COLS * self.cell, ROWS * self.cell
        self.offset_x = (event.width - board_w) / 2; self.offset_y = (event.height - board_h) / 2
        self.draw()

    def _px(self, c): return self.offset_x + c * self.cell
    def _py(self, r): return self.offset_y + r * self.cell

    def _update_memo_label(self):
        if not memo.is_enabled(GAME_ID):
            self.memo_lbl.config(text="Memo: Disabled")
            return
        total = _memo_stats["hits"] + _memo_stats["misses"]
        pct_str = f"{100 * _memo_stats['hits'] / total:.0f}%" if total > 0 else "0%"
        loaded = "loaded" if _memo_loaded_from_file else "fresh"
        book_str = f"Book: {len(_opening_book):,} pos" if _book_loaded else "Book: loading..." if _book_loading else "Book: none"
        self.memo_lbl.config(text=(f"Memo: {loaded} ({len(_memo_cache)} states)  •  Hits: {_memo_stats['hits']}/{total} ({pct_str})  •  {book_str}"))
        
    def _poll_book_status(self):
        self._update_memo_label()
        if _book_loading: self.after(500, self._poll_book_status)

    def draw(self):
        if self.cell <= 0: return
        self.canvas.delete("all")
        self.canvas.create_rectangle(self._px(0), self._py(0), self._px(COLS), self._py(ROWS), fill=theme.color("card"), outline=theme.color("fg"), width=2)
        hole_r, disc_r = self.cell * 0.42, self.cell * 0.38
        selection_col = None
        if self.winner is None and not self.is_draw and not self.ai_thinking:
            if not (self.vs_computer.get() and self.turn == PLAYER2):
                if self.use_keyboard_selector: selection_col = self.keyboard_col
                elif self.hover_col is not None: selection_col = self.hover_col
        if selection_col is not None: self.canvas.create_rectangle(self._px(selection_col), self._py(0), self._px(selection_col + 1), self._py(ROWS), fill="", outline=theme.color("accent_x"), width=3)
        for r in range(ROWS):
            for c in range(COLS):
                cx, cy = self._px(c) + self.cell / 2, self._py(r) + self.cell / 2
                self.canvas.create_oval(cx - hole_r, cy - hole_r, cx + hole_r, cy + hole_r, fill=theme.color("canvas_bg"), outline=theme.color("divider"), width=2)
        for r in range(ROWS):
            for c in range(COLS):
                p = self.board[r][c]
                if p == EMPTY: continue
                cx, cy = self._px(c) + self.cell / 2, self._py(r) + self.cell / 2
                self.canvas.create_oval(cx - disc_r, cy - disc_r, cx + disc_r, cy + disc_r, fill=theme.color("accent_x") if p == PLAYER1 else theme.color("accent_o"), outline=theme.color("fg"), width=2)
        if self.last_move is not None and self.winner is None and not self.is_draw:
            r, c = self.last_move; cx, cy = self._px(c) + self.cell / 2, self._py(r) + self.cell / 2; inner = disc_r * 0.30
            self.canvas.create_oval(cx - inner, cy - inner, cx + inner, cy + inner, outline=theme.color("fg"), width=1)
        if self.win_cells:
            for (r, c) in self.win_cells:
                cx, cy = self._px(c) + self.cell / 2, self._py(r) + self.cell / 2; outer = disc_r + 3
                self.canvas.create_oval(cx - outer, cy - outer, cx + outer, cy + outer, outline=theme.color("fg"), width=3)

def run(master=None):
    if not _book_loaded and not _book_loading: threading.Thread(target=_load_opening_book, daemon=True).start()
    return ConnectFour(master)