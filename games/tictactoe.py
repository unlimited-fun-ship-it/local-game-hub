"""Tic-Tac-Toe - human vs human or human vs an unbeatable computer."""

import atexit
import os
import pickle
import tkinter as tk

import save_manager
import memoization_manager as memo
from theme import theme

GAME_ID = "tictactoe"

LINES = [(0, 1, 2), (3, 4, 5), (6, 7, 8),
         (0, 3, 6), (1, 4, 7), (2, 5, 8),
         (0, 4, 8), (2, 4, 6)]

_SYMMETRIES = [
    (0, 1, 2, 3, 4, 5, 6, 7, 8),
    (6, 3, 0, 7, 4, 1, 8, 5, 2),
    (8, 7, 6, 5, 4, 3, 2, 1, 0),
    (2, 5, 8, 1, 4, 7, 0, 3, 6),
    (2, 1, 0, 5, 4, 3, 8, 7, 6),
    (6, 7, 8, 3, 4, 5, 0, 1, 2),
    (0, 3, 6, 1, 4, 7, 2, 5, 8),
    (8, 5, 2, 7, 4, 1, 6, 3, 0),
]

def winner_of(board):
    for a, b, c in LINES:
        if board[a] and board[a] == board[b] == board[c]:
            return board[a]
    return None

def _canonicalize(board_tuple):
    return min(tuple(board_tuple[i] for i in perm) for perm in _SYMMETRIES)

# ======================================================================
# Persistent memo table
# ======================================================================
_CACHE_DIR = os.path.abspath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..", "memoization", "tictactoe",
))
_CACHE_PATH = os.path.join(_CACHE_DIR, "memo.pkl")

_memo_cache = {}
_memo_stats = {"hits": 0, "misses": 0}
_memo_loaded_from_file = False

def _ensure_cache_dir():
    try:
        os.makedirs(_CACHE_DIR, exist_ok=True)
    except OSError:
        pass

def load_memo_from_disk():
    global _memo_cache, _memo_loaded_from_file
    if not memo.is_enabled(GAME_ID):
        return False
    if not os.path.exists(_CACHE_PATH):
        return False
    try:
        with open(_CACHE_PATH, "rb") as f:
            data = pickle.load(f)
        if not isinstance(data, dict):
            return False
        cache = data.get("cache")
        if not isinstance(cache, dict):
            return False
        _memo_cache = cache
        _memo_loaded_from_file = True
        return True
    except Exception:
        return False

def save_memo_to_disk():
    if not memo.is_enabled(GAME_ID):
        return False
    _ensure_cache_dir()
    try:
        with open(_CACHE_PATH, "wb") as f:
            pickle.dump({"version": 1, "cache": _memo_cache}, f)
        return True
    except OSError:
        return False

def _minimax(board_tuple, player):
    if not memo.is_enabled(GAME_ID):
        board = list(board_tuple)
        w = winner_of(board)
        if w == "O": return 1
        elif w == "X": return -1
        elif "" not in board: return 0
        elif player == "O":
            best = -2
            for i in range(9):
                if board[i] == "":
                    board[i] = "O"
                    best = max(best, _minimax(tuple(board), "X"))
                    board[i] = ""
            return best
        else:
            best = 2
            for i in range(9):
                if board[i] == "":
                    board[i] = "X"
                    best = min(best, _minimax(tuple(board), "O"))
                    board[i] = ""
            return best

    canon_board = _canonicalize(board_tuple)
    key = (canon_board, player)
    
    if key in _memo_cache:
        _memo_stats["hits"] += 1
        return _memo_cache[key]

    _memo_stats["misses"] += 1
    board = list(board_tuple)
    w = winner_of(board)
    
    if w == "O": result = 1
    elif w == "X": result = -1
    elif "" not in board: result = 0
    elif player == "O":
        best = -2
        for i in range(9):
            if board[i] == "":
                board[i] = "O"
                best = max(best, _minimax(tuple(board), "X"))
                board[i] = ""
        result = best
    else:
        best = 2
        for i in range(9):
            if board[i] == "":
                board[i] = "X"
                best = min(best, _minimax(tuple(board), "O"))
                board[i] = ""
        result = best

    max_entries = memo.get_max_entries(GAME_ID)
    if len(_memo_cache) < max_entries:
        _memo_cache[key] = result
    return result

_memo_loaded_from_file = load_memo_from_disk()

if not _memo_cache and memo.is_enabled(GAME_ID):
    _minimax(tuple([""] * 9), "X")
    save_memo_to_disk()

atexit.register(save_memo_to_disk)

class TicTacToe(tk.Toplevel):
    def __init__(self, master=None):
        super().__init__(master)
        self.title("Tic-Tac-Toe")
        self.geometry("420x510")
        self.minsize(300, 400)
        self.vs_computer = tk.BooleanVar(master=self, value=True)

        self._build()
        self.new_game()
        self.apply_theme()
        self._update_memo_label()

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.focus_set()

    def _on_close(self):
        save_memo_to_disk()
        self.destroy()

    def _build(self):
        self.status = tk.Label(self, text="")
        self.status.pack(pady=(14, 8))

        self.grid_frame = tk.Frame(self)
        self.grid_frame.pack(fill="both", expand=True, padx=14, pady=(0, 6))
        for i in range(3):
            self.grid_frame.columnconfigure(i, weight=1, uniform="cell")
            self.grid_frame.rowconfigure(i, weight=1, uniform="cell")

        self.cells = []
        for i in range(9):
            b = tk.Button(self.grid_frame, text=" ", relief="flat", bd=0, command=lambda i=i: self.click(i))
            b.grid(row=i // 3, column=i % 3, padx=3, pady=3, sticky="nsew")
            self.cells.append(b)

        self.bottom = tk.Frame(self)
        self.bottom.pack(fill="x", padx=14, pady=(10, 4))

        self.vs_cb = tk.Checkbutton(self.bottom, text="vs Computer", variable=self.vs_computer, command=self.new_game, relief="flat", bd=0, highlightthickness=0)
        self.vs_cb.pack(side="left")

        self.new_btn = tk.Button(self.bottom, text="New Game", command=self.new_game, relief="flat", bd=0, padx=10, pady=4)
        self.new_btn.pack(side="right")

        self.load_btn = tk.Button(self.bottom, text="Load", command=self.load_game, relief="flat", bd=0, padx=10, pady=4)
        self.load_btn.pack(side="right", padx=(0, 4))

        self.save_btn = tk.Button(self.bottom, text="Save", command=self.save_game, relief="flat", bd=0, padx=10, pady=4)
        self.save_btn.pack(side="right", padx=(0, 4))

        self.memo_lbl = tk.Label(self, text="", anchor="center")
        self.memo_lbl.pack(fill="x", padx=14, pady=(0, 14))

    def apply_theme(self):
        bg = theme.color("bg")
        fg = theme.color("fg")
        btn_bg = theme.color("button_bg")
        btn_fg = theme.color("button_fg")
        hover = theme.color("button_hover")

        self.configure(bg=bg)
        self.status.configure(bg=bg, fg=fg, font=theme.font("status", "bold"))
        self.grid_frame.configure(bg=bg)
        self.bottom.configure(bg=bg)
        self.memo_lbl.configure(bg=bg, fg=theme.color("muted"), font=theme.font("small"))

        for i, b in enumerate(self.cells):
            b.configure(bg=btn_bg, activebackground=hover, font=theme.font("cell", "bold"))
            if self.board[i] == "X": b.configure(fg=theme.color("accent_x"))
            elif self.board[i] == "O": b.configure(fg=theme.color("accent_o"))
            else: b.configure(fg=fg)

        self.vs_cb.configure(bg=bg, fg=fg, selectcolor=btn_bg, activebackground=bg, activeforeground=fg, font=theme.font("body"))
        for btn in (self.new_btn, self.save_btn, self.load_btn):
            btn.configure(bg=btn_bg, fg=btn_fg, activebackground=hover, activeforeground=btn_fg, font=theme.font("button"))

    def new_game(self):
        self.board = [""] * 9
        self.turn = "X"
        self.over = False
        for b in self.cells: b.config(text=" ", fg=theme.color("fg"))
        self.update_status()

    def get_state(self):
        return {"board": self.board, "turn": self.turn, "over": self.over, "vs_computer": self.vs_computer.get()}

    def set_state(self, data):
        self.board = data["board"]
        self.turn = data["turn"]
        self.over = data["over"]
        self.vs_computer.set(data["vs_computer"])
        for i, cell in enumerate(self.cells):
            cell.config(text=self.board[i] or " ", fg=theme.color("accent_x") if self.board[i] == "X" else theme.color("accent_o") if self.board[i] == "O" else theme.color("fg"))
        self.update_status()

    def save_game(self):
        save_manager.prompt_save(self, GAME_ID, self.get_state())

    def load_game(self):
        fname = save_manager.prompt_load(self, GAME_ID)
        if fname:
            data = save_manager.load_game(GAME_ID, fname)
            self.set_state(data)

    def update_status(self):
        if self.over: return
        if self.turn == "X": self.status.config(text="Your turn (X)" if self.vs_computer.get() else "X's turn")
        else: self.status.config(text="Computer thinking..." if self.vs_computer.get() else "O's turn")

    def click(self, i):
        if self.over or self.board[i]: return
        if self.vs_computer.get() and self.turn != "X": return
        self.place(i, self.turn)
        if self.check_end(): return
        self.turn = "O" if self.turn == "X" else "X"
        self.update_status()
        if self.vs_computer.get() and self.turn == "O": self.after(180, self.computer_move)

    def place(self, i, player):
        self.board[i] = player
        self.cells[i].config(text=player, fg=theme.color("accent_x") if player == "X" else theme.color("accent_o"))

    def check_end(self):
        w = winner_of(self.board)
        if w:
            self.over = True
            if self.vs_computer.get(): self.status.config(text="You win! 🎉" if w == "X" else "Computer wins!")
            else: self.status.config(text=f"{w} wins! 🎉")
            return True
        if "" not in self.board:
            self.over = True
            self.status.config(text="It's a draw.")
            return True
        return False

    def computer_move(self):
        if self.over: return
        move = self.best_move()
        if move is None:
            self._update_memo_label()
            return
        self.place(move, "O")
        if self.check_end():
            self._update_memo_label()
            save_memo_to_disk()
            return
        self.turn = "X"
        self.update_status()
        self._update_memo_label()
        save_memo_to_disk()

    def best_move(self):
        best_score, best = -2, None
        for i in range(9):
            if self.board[i] == "":
                self.board[i] = "O"
                score = _minimax(tuple(self.board), "X")
                self.board[i] = ""
                if score > best_score:
                    best_score, best = score, i
        return best

    def _update_memo_label(self):
        if not memo.is_enabled(GAME_ID):
            self.memo_lbl.config(text="Memo: Disabled")
            return
        total = _memo_stats["hits"] + _memo_stats["misses"]
        pct_str = f"{100 * _memo_stats['hits'] / total:.0f}%" if total > 0 else "0%"
        loaded = "loaded" if _memo_loaded_from_file else "fresh"
        self.memo_lbl.config(text=(f"Memo: {loaded} ({len(_memo_cache)} unique classes)  •  Hits: {_memo_stats['hits']}/{total} ({pct_str})"))

def run(master=None):
    return TicTacToe(master)