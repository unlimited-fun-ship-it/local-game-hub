"""Checkers - standard 8x8 draughts with optional forced-capture rules."""

import atexit
import os
import pickle
import tkinter as tk
from collections import OrderedDict
from tkinter import messagebox

import save_manager
import memoization_manager as memo
from theme import theme

GAME_ID = "checkers"
BOARD_SIZE = 8
RED, BLACK = 1, -1
DIRECTIONS = [(-1, -1), (-1, 1), (1, -1), (1, 1)]

_CACHE_DIR = os.path.abspath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..", "memoization", "checkers",
))

_memo_cache = OrderedDict()
_memo_stats = {"hits": 0, "misses": 0}
_memo_loaded_from_file = False
_memo_loaded_rules = None

def _ensure_cache_dir():
    try: os.makedirs(_CACHE_DIR, exist_ok=True)
    except OSError: pass

def _get_cache_path(forced_captures, forced_promotions):
    return os.path.join(_CACHE_DIR, f"memo_caps{int(forced_captures)}_promo{int(forced_promotions)}.pkl")

def load_memo_from_disk(settings):
    global _memo_cache, _memo_loaded_from_file, _memo_loaded_rules
    if not memo.is_enabled(GAME_ID):
        _memo_cache = OrderedDict()
        _memo_loaded_from_file = False
        return False

    path = _get_cache_path(settings.forced_captures, settings.forced_promotions)
    if _memo_loaded_rules == (settings.forced_captures, settings.forced_promotions):
        return _memo_loaded_from_file

    _memo_cache = OrderedDict()
    _memo_loaded_from_file = False
    _memo_loaded_rules = (settings.forced_captures, settings.forced_promotions)

    if not os.path.exists(path): return False
    try:
        with open(path, "rb") as f:
            data = pickle.load(f)
        cache = data.get("cache")
        if not isinstance(cache, dict): return False
        _memo_cache = OrderedDict(cache)
        _memo_loaded_from_file = True
        return True
    except Exception: return False

def save_memo_to_disk(settings):
    if not memo.is_enabled(GAME_ID): return False
    _ensure_cache_dir()
    path = _get_cache_path(settings.forced_captures, settings.forced_promotions)
    try:
        with open(path, "wb") as f:
            pickle.dump({"version": 1, "cache": dict(_memo_cache)}, f)
        return True
    except OSError: return False

def _in_bounds(r, c): return 0 <= r < BOARD_SIZE and 0 <= c < BOARD_SIZE
def _is_king(p): return abs(p) == 2
def _sign(p): return 1 if p > 0 else (-1 if p < 0 else 0)
def _forward_dirs(piece): return [(-1, -1), (-1, 1)] if piece > 0 else [(1, -1), (1, 1)]

def _canonicalize(board_tuple, side):
    if side == RED:
        b = tuple(tuple(-board_tuple[BOARD_SIZE - 1 - r][c] for c in range(BOARD_SIZE)) for r in range(BOARD_SIZE))
    else: b = board_tuple
    flipped = tuple(tuple(row[BOARD_SIZE - 1 - c] for c in range(BOARD_SIZE)) for row in b)
    return min(b, flipped)

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
    fr, fc, tr, tc, _cap = move
    piece = board[fr][fc]
    if piece == RED and tr == 0: return True
    if piece == BLACK and tr == BOARD_SIZE - 1: return True
    return False

def _all_legal_moves(board, side, forced_captures=True, forced_promotions=False):
    captures, quiets = [], []
    for r in range(BOARD_SIZE):
        for c in range(BOARD_SIZE):
            p = board[r][c]
            if p == 0 or _sign(p) != side: continue
            for tr, tc, cr, cc in _captures_for(board, r, c):
                captures.append((r, c, tr, tc, (cr, cc)))
            for tr, tc in _quiet_moves_for(board, r, c):
                quiets.append((r, c, tr, tc, None))

    if forced_captures and captures: pool = captures
    else: pool = captures + quiets
    if forced_promotions and pool:
        promoting = [m for m in pool if _move_promotes(board, m)]
        if promoting: return promoting
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
    for r in range(BOARD_SIZE):
        for c in range(BOARD_SIZE):
            p = board[r][c]
            if p == 0 or _sign(p) != side: continue
            if _captures_for(board, r, c) or _quiet_moves_for(board, r, c): return True
    return False

def _evaluate_for_black(board):
    score = 0
    for r in range(BOARD_SIZE):
        for c in range(BOARD_SIZE):
            p = board[r][c]
            if p == 0: continue
            if _is_king(p): v = 300
            else:
                v = 100
                if p == RED: v += (7 - r) * 3
                else: v += r * 3
            if c == 0 or c == 7: v += 5
            if p < 0: score += v
            else: score -= v
    return score

def _minimax(board_tuple, depth, alpha, beta, side, forced_captures, forced_promotions):
    use_cache = memo.is_enabled(GAME_ID)
    if use_cache:
        canon = _canonicalize(board_tuple, side)
        key = (canon, depth, forced_captures, forced_promotions)
        if key in _memo_cache:
            _memo_stats["hits"] += 1
            _memo_cache.move_to_end(key)
            val = _memo_cache[key]
            return val if side == BLACK else -val
        _memo_stats["misses"] += 1

    board = [list(row) for row in board_tuple]
    legal = _all_legal_moves(board, side, forced_captures, forced_promotions)
    
    if not legal: return -100000
    if depth == 0:
        val = _evaluate_for_black(board)
        if use_cache:
            _memo_cache[key] = (-val if side == RED else val)
            if len(_memo_cache) > memo.get_max_entries(GAME_ID): _memo_cache.popitem(last=False)
        return val

    best_score = -float("inf")
    legal.sort(key=lambda m: 1 if m[4] is not None else 0, reverse=True)

    for m in legal:
        child_board, promoted = _apply_move(board, m)
        fr, fc, tr, tc, cap = m
        child_tuple = tuple(tuple(row) for row in child_board)
        
        if cap is not None and not promoted and _captures_for(child_board, tr, tc):
            child_score = _minimax(child_tuple, depth - 1, -beta, -alpha, side, forced_captures, forced_promotions)
        else:
            child_score = _minimax(child_tuple, depth - 1, -beta, -alpha, -side, forced_captures, forced_promotions)

        score = -child_score
        if score > best_score: best_score = score
        if score > alpha: alpha = score
        if alpha >= beta: break

    if use_cache:
        _memo_cache[key] = (-best_score if side == RED else best_score)
        if len(_memo_cache) > memo.get_max_entries(GAME_ID): _memo_cache.popitem(last=False)

    return best_score

def choose_ai_move(board, side, difficulty, settings, chain_from=None):
    if chain_from is not None:
        fr, fc = chain_from
        legal = [(fr, fc, tr, tc, (cr, cc)) for tr, tc, cr, cc in _captures_for(board, fr, fc)]
    else:
        legal = _all_legal_moves(board, side, settings.forced_captures, settings.forced_promotions)
        
    if not legal: return None

    depth = 1 if difficulty == "Easy" else 3 if difficulty == "Medium" else 5
    best_score, best_move = -float("inf"), legal[0]

    for m in legal:
        child_board, promoted = _apply_move(board, m)
        fr, fc, tr, tc, cap = m
        child_tuple = tuple(tuple(row) for row in child_board)
        
        if cap is not None and not promoted and _captures_for(child_board, tr, tc):
            score = _minimax(child_tuple, depth - 1, -float("inf"), float("inf"), side, settings.forced_captures, settings.forced_promotions)
        else:
            score = _minimax(child_tuple, depth - 1, -float("inf"), float("inf"), -side, settings.forced_captures, settings.forced_promotions)

        if score > best_score:
            best_score, best_move = score, m
    return best_move

class CheckersSettings:
    def __init__(self):
        self.forced_captures = True
        self.forced_promotions = False
    def to_dict(self): return {"forced_captures": self.forced_captures, "forced_promotions": self.forced_promotions}
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
        bg, fg = theme.color("bg"), theme.color("fg")
        btn_bg, btn_fg, hover = theme.color("button_bg"), theme.color("button_fg"), theme.color("button_hover")
        self.configure(bg=bg)
        body = tk.Frame(self, bg=bg)
        body.pack(fill="both", expand=True, padx=20, pady=16)

        tk.Label(body, text="Rule settings", bg=bg, fg=fg, font=theme.font("heading", "bold")).pack(anchor="w", pady=(0, 10))

        self._forced_captures_var = tk.BooleanVar(value=current.forced_captures)
        self._forced_promotions_var = tk.BooleanVar(value=current.forced_promotions)
        tk.Checkbutton(body, text="Forced captures", variable=self._forced_captures_var, bg=bg, fg=fg, selectcolor=btn_bg, activebackground=bg, activeforeground=fg, font=theme.font("body")).pack(anchor="w", pady=4)
        tk.Checkbutton(body, text="Forced promotions", variable=self._forced_promotions_var, bg=bg, fg=fg, selectcolor=btn_bg, activebackground=bg, activeforeground=fg, font=theme.font("body")).pack(anchor="w", pady=4)

        tk.Frame(body, bg=bg, height=2).pack(fill="x", pady=10)
        
        self._memo_enabled_var = tk.BooleanVar(value=memo.is_enabled(GAME_ID))
        tk.Checkbutton(body, text="Enable Memoization", variable=self._memo_enabled_var, bg=bg, fg=fg, selectcolor=btn_bg, activebackground=bg, activeforeground=fg, font=theme.font("body")).pack(anchor="w", pady=4)
        self._memo_size_lbl = tk.Label(body, text="", bg=bg, fg=theme.color("muted"), font=theme.font("small"))
        self._memo_size_lbl.pack(anchor="w", pady=2)
        tk.Button(body, text="Clear Memoized Data", command=self._clear_memo, bg=btn_bg, fg=btn_fg, activebackground=hover, activeforeground=btn_fg, relief="flat", bd=0, padx=8, pady=2, font=theme.font("small")).pack(anchor="w", pady=4)
        self._update_memo_size()

        btns = tk.Frame(body, bg=bg)
        btns.pack(fill="x", pady=(16, 0))
        tk.Button(btns, text="Apply", command=self._ok, bg=btn_bg, fg=btn_fg, activebackground=hover, activeforeground=btn_fg, relief="flat", bd=0, padx=14, pady=4, font=theme.font("button")).pack(side="right", padx=(6, 0))
        tk.Button(btns, text="Cancel", command=self._cancel, bg=btn_bg, fg=btn_fg, activebackground=hover, activeforeground=btn_fg, relief="flat", bd=0, padx=14, pady=4, font=theme.font("button")).pack(side="right")

        self.bind("<Return>", lambda e: self._ok())
        self.bind("<Escape>", lambda e: self._cancel())
        self.update_idletasks()
        try: self.wait_visibility(); self.grab_set()
        except tk.TclError: pass
        self.focus_set()

    def _clear_memo(self):
        memo.clear_game(GAME_ID)
        self._update_memo_size()

    def _update_memo_size(self):
        size = memo.get_disk_usage(GAME_ID)
        size_str = f"{size / (1024 * 1024):.1f} MB" if size > 1024 * 1024 else f"{size / 1024:.1f} KB" if size > 1024 else f"{size} bytes"
        self._memo_size_lbl.config(text=f"Current disk usage: {size_str}")

    def _ok(self):
        s = CheckersSettings()
        s.forced_captures = self._forced_captures_var.get()
        s.forced_promotions = self._forced_promotions_var.get()
        memo.set_game_override(GAME_ID, enabled=self._memo_enabled_var.get())
        self.result = s
        self.destroy()

    def _cancel(self):
        self.result = None
        self.destroy()

class Checkers(tk.Toplevel):
    def __init__(self, master=None):
        super().__init__(master)
        self.title("Checkers")
        self.geometry("640x760")
        self.minsize(360, 500)
        self.vs_computer = tk.BooleanVar(master=self, value=True)
        self.difficulty = tk.StringVar(master=self, value="Medium")
        self.settings = CheckersSettings()
        self.cell, self.offset_x, self.offset_y = 60, 0, 0
        self.board, self.turn, self.selected, self.legal_targets = None, RED, None, {}
        self.chain_from, self.game_over, self.winner = None, False, None
        load_memo_from_disk(self.settings)
        self._build()
        self.apply_theme()
        self.new_game()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.focus_set()

    def _on_close(self):
        save_memo_to_disk(self.settings)
        self.destroy()

    def _build(self):
        self.status = tk.Label(self); self.status.pack(pady=(12, 6))
        self.canvas = tk.Canvas(self, highlightthickness=0); self.canvas.pack(fill="both", expand=True, padx=12, pady=(0, 6))
        self.canvas.bind("<Configure>", self._on_canvas_resize); self.canvas.bind("<Button-1>", self.on_click)
        self.bottom = tk.Frame(self); self.bottom.pack(fill="x", padx=12, pady=(0, 4))
        self.vs_cb = tk.Checkbutton(self.bottom, text="vs Computer", variable=self.vs_computer, command=self.new_game, relief="flat", bd=0, highlightthickness=0); self.vs_cb.pack(side="left")
        self.settings_btn = tk.Button(self.bottom, text="Rules", command=self.open_settings, relief="flat", bd=0, padx=10, pady=3); self.settings_btn.pack(side="left", padx=(8, 0))
        self.diff_frame = tk.Frame(self.bottom); self.diff_frame.pack(side="left", padx=(10, 0))
        self.diff_label = tk.Label(self.diff_frame, text="AI:"); self.diff_label.pack(side="left", padx=(0, 4))
        self.diff_btns = {}
        for d in ("Easy", "Medium", "Hard"):
            b = tk.Button(self.diff_frame, text=d, relief="flat", bd=0, padx=6, pady=2, command=lambda d=d: self._set_difficulty(d)); b.pack(side="left", padx=(2, 0)); self.diff_btns[d] = b
        self.new_btn = tk.Button(self.bottom, text="New", command=self.new_game, relief="flat", bd=0, padx=10, pady=3); self.new_btn.pack(side="right")
        self.load_btn = tk.Button(self.bottom, text="Load", command=self.load_game, relief="flat", bd=0, padx=10, pady=3); self.load_btn.pack(side="right", padx=(0, 4))
        self.save_btn = tk.Button(self.bottom, text="Save", command=self.save_game, relief="flat", bd=0, padx=10, pady=3); self.save_btn.pack(side="right", padx=(0, 4))
        self.hint_lbl = tk.Label(self, text="Click a piece, then a highlighted square  •  R to restart"); self.hint_lbl.pack(pady=(0, 4))
        self.memo_lbl = tk.Label(self, text="", anchor="center"); self.memo_lbl.pack(fill="x", padx=12, pady=(0, 12))
        self.bind("<KeyPress>", self.on_key)

    def apply_theme(self):
        bg, fg = theme.color("bg"), theme.color("fg")
        btn_bg, btn_fg, hover = theme.color("button_bg"), theme.color("button_fg"), theme.color("button_hover")
        self.configure(bg=bg); self.status.configure(bg=bg, fg=fg, font=theme.font("status", "bold")); self.bottom.configure(bg=bg); self.diff_frame.configure(bg=bg)
        self.diff_label.configure(bg=bg, fg=theme.color("muted"), font=theme.font("small"))
        self.hint_lbl.configure(bg=bg, fg=theme.color("muted"), font=theme.font("small"))
        self.memo_lbl.configure(bg=bg, fg=theme.color("muted"), font=theme.font("small"))
        self.canvas.configure(bg=theme.color("canvas_bg"))
        self.vs_cb.configure(bg=bg, fg=fg, selectcolor=btn_bg, activebackground=bg, activeforeground=fg, font=theme.font("body"))
        for btn in (self.new_btn, self.save_btn, self.load_btn, self.settings_btn): btn.configure(bg=btn_bg, fg=btn_fg, activebackground=hover, activeforeground=btn_fg, font=theme.font("button"))
        for d, b in self.diff_btns.items():
            b.configure(bg=theme.color("accent_x") if d == self.difficulty.get() else btn_bg, fg=btn_fg, activebackground=hover, activeforeground=btn_fg, font=theme.font("button"))
        self.draw()

    def _set_difficulty(self, d):
        self.difficulty.set(d)
        btn_bg, btn_fg, hover = theme.color("button_bg"), theme.color("button_fg"), theme.color("button_hover")
        for name, b in self.diff_btns.items():
            b.configure(bg=theme.color("accent_x") if name == d else btn_bg, fg=btn_fg, activebackground=hover, activeforeground=btn_fg)

    def _update_memo_label(self):
        if not memo.is_enabled(GAME_ID):
            self.memo_lbl.config(text="Memo: Disabled")
            return
        total = _memo_stats["hits"] + _memo_stats["misses"]
        pct_str = f"{100 * _memo_stats['hits'] / total:.0f}%" if total > 0 else "0%"
        loaded = "loaded" if _memo_loaded_from_file else "fresh"
        rules = f"Caps:{int(self.settings.forced_captures)} Promo:{int(self.settings.forced_promotions)}"
        self.memo_lbl.config(text=(f"Memo: {loaded} ({len(_memo_cache)} states)  •  Hits: {_memo_stats['hits']}/{total} ({pct_str})  •  [{rules}]"))

    def open_settings(self):
        dlg = GameSettingsDialog(self, self.settings)
        self.wait_window(dlg)
        if dlg.result is not None:
            save_memo_to_disk(self.settings)
            self.settings = dlg.result
            load_memo_from_disk(self.settings)
            self.recompute_targets(); self.update_status(); self.draw(); self._update_memo_label()

    def new_game(self):
        self.board, self.turn, self.selected, self.legal_targets = _initial_board(), RED, None, {}
        self.chain_from, self.game_over, self.winner = None, False, None
        self.update_status(); self.draw(); self._update_memo_label()

    def get_state(self): return {"board": self.board, "turn": self.turn, "selected": self.selected, "chain_from": self.chain_from, "game_over": self.game_over, "winner": self.winner, "vs_computer": self.vs_computer.get(), "difficulty": self.difficulty.get(), "settings": self.settings.to_dict()}

    def set_state(self, data):
        self.board = data["board"]; self.turn = data["turn"]
        self.selected = tuple(data["selected"]) if data["selected"] else None
        self.chain_from = tuple(data["chain_from"]) if data["chain_from"] else None
        self.game_over = data["game_over"]; self.winner = data["winner"]
        self.vs_computer.set(data["vs_computer"]); self.difficulty.set(data.get("difficulty", "Medium"))
        self.settings = CheckersSettings.from_dict(data["settings"]) if "settings" in data else CheckersSettings()
        load_memo_from_disk(self.settings)
        self.recompute_targets(); self.update_status(); self.draw(); self._update_memo_label()
        if not self.game_over and self.vs_computer.get() and self.turn == BLACK: self.after(300, self.computer_move)

    def save_game(self): save_manager.prompt_save(self, GAME_ID, self.get_state())
    def load_game(self):
        fname = save_manager.prompt_load(self, GAME_ID)
        if fname: self.set_state(save_manager.load_game(GAME_ID, fname))

    def on_key(self, event):
        if event.keysym.lower() == "r": self.new_game()

    def on_click(self, event):
        if self.cell <= 0 or self.game_over: return
        if self.vs_computer.get() and self.turn == BLACK: return
        c, r = int((event.x - self.offset_x) // self.cell), int((event.y - self.offset_y) // self.cell)
        if not _in_bounds(r, c): return
        if (r, c) in self.legal_targets:
            self.execute_move(self.selected, (r, c)); return
        piece = self.board[r][c]
        if piece != 0 and _sign(piece) == self.turn and self.chain_from is None:
            self.selected = (r, c); self.recompute_targets(); self.draw(); return
        if self.chain_from is None:
            self.selected, self.legal_targets = None, {}; self.draw()

    def recompute_targets(self):
        self.legal_targets = {}
        if self.selected is None: return
        fr, fc = self.selected
        if self.chain_from is not None:
            for tr, tc, cr, cc in _captures_for(self.board, fr, fc): self.legal_targets[(tr, tc)] = (cr, cc)
            return
        for mr, mc, tr, tc, cap in _all_legal_moves(self.board, self.turn, self.settings.forced_captures, self.settings.forced_promotions):
            if (mr, mc) == (fr, fc): self.legal_targets[(tr, tc)] = cap

    def execute_move(self, frc, toc):
        fr, fc = frc; tr, tc = toc
        cap = self.legal_targets.get((tr, tc))
        self.board, promoted = _apply_move(self.board, (fr, fc, tr, tc, cap))
        self.selected, self.legal_targets = None, {}
        if cap is not None and not promoted:
            if _captures_for(self.board, tr, tc):
                self.selected, self.chain_from = (tr, tc), (tr, tc)
                self.recompute_targets(); self.update_status(); self.draw()
                if self.vs_computer.get() and self.turn == BLACK: self.after(300, self.computer_continue_chain)
                return
        self.chain_from = None; self.turn = -self.turn
        self.check_game_over(); self.update_status(); self.draw()
        if not self.game_over and self.vs_computer.get() and self.turn == BLACK: self.after(300, self.computer_move)

    def check_game_over(self):
        if not _has_any_move(self.board, self.turn): self.game_over, self.winner = True, -self.turn

    def _side_name(self, side):
        if self.vs_computer.get(): return "You" if side == RED else "Computer"
        return "Player 1" if side == RED else "Player 2"

    def _forced_hint(self, side):
        moves = _all_legal_moves(self.board, side, self.settings.forced_captures, self.settings.forced_promotions)
        if not moves: return ""
        hints = []
        if self.settings.forced_captures and all(m[4] is not None for m in moves): hints.append("must capture")
        if self.settings.forced_promotions and all(_move_promotes(self.board, m) for m in moves): hints.append("must promote")
        return " — " + " and ".join(hints) + "!" if hints else ""

    def update_status(self):
        if self.game_over:
            self.status.config(text=("You win! 🎉" if self.winner == RED else "Computer wins!") if self.vs_computer.get() else f"{self._side_name(self.winner)} wins! 🎉"); return
        if self.chain_from is not None: self.status.config(text="Continue jumping!"); return
        if self.vs_computer.get():
            self.status.config(text="Computer thinking..." if self.turn == BLACK else f"Your turn{self._forced_hint(RED)}")
        else: self.status.config(text=f"{self._side_name(self.turn)}'s turn{self._forced_hint(self.turn)}")

    def computer_move(self):
        if self.game_over or self.turn != BLACK: return
        move = choose_ai_move(self.board, BLACK, self.difficulty.get(), self.settings)
        if move is None: self.check_game_over(); self.update_status(); self.draw(); return
        fr, fc, tr, tc, cap = move
        self.selected, self.legal_targets = (fr, fc), {(tr, tc): cap}
        self.draw(); self.after(180, lambda: self.execute_move((fr, fc), (tr, tc)))
        self._update_memo_label(); save_memo_to_disk(self.settings)

    def computer_continue_chain(self):
        if self.game_over or self.turn != BLACK or self.selected is None: return
        move = choose_ai_move(self.board, BLACK, self.difficulty.get(), self.settings, chain_from=self.selected)
        if move is None: return
        fr, fc, tr, tc, cap = move
        self.after(180, lambda: self.execute_move((fr, fc), (tr, tc)))
        self._update_memo_label(); save_memo_to_disk(self.settings)

    def _on_canvas_resize(self, event):
        size = min(event.width, event.height) - 8; self.cell = size / BOARD_SIZE
        self.offset_x = (event.width - self.cell * BOARD_SIZE) / 2; self.offset_y = (event.height - self.cell * BOARD_SIZE) / 2
        self.draw()

    def _px(self, c): return self.offset_x + c * self.cell
    def _py(self, r): return self.offset_y + r * self.cell

    def draw(self):
        if self.cell <= 0 or self.board is None: return
        self.canvas.delete("all")
        light, dark = theme.color("card"), theme.color("canvas_bg")
        for r in range(BOARD_SIZE):
            for c in range(BOARD_SIZE):
                self.canvas.create_rectangle(self._px(c), self._py(r), self._px(c + 1), self._py(r + 1), fill=light if (r + c) % 2 == 0 else dark, outline="")
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
                self.canvas.create_oval(self._px(c) + pad, self._py(r) + pad, self._px(c + 1) - pad, self._py(r + 1) - pad, fill=theme.color("accent_o") if p > 0 else theme.color("accent_x"), outline=theme.color("fg"), width=2)
                if _is_king(p): self.canvas.create_oval(self._px(c) + crown, self._py(r) + crown, self._px(c + 1) - crown, self._py(r + 1) - crown, outline=theme.color("fg"), width=2)
        self.canvas.create_rectangle(self._px(0), self._py(0), self._px(BOARD_SIZE), self._py(BOARD_SIZE), outline=theme.color("fg"), width=2)

def run(master=None):
    return Checkers(master)