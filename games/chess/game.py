"""The chess window: board drawing, input, save/load and the computer opponent.

Engine pieces live in the sibling modules:
    constants / zobrist / board / movegen / notation / rules   - the rules of chess
    evaluation / pst / search                                  - the engine
    widgets                                                    - history window, FEN dialog, captured panels
"""

import queue
import random
import threading
import tkinter as tk
import traceback
from tkinter import messagebox

import save_manager
import memoization_manager as memo
from theme import theme

from .board import (
    ChessState, Move, apply_move, board_to_fen, castling_from_dict, castling_to_dict,
    fen_to_state, initial_state,
)
from .constants import (
    ANALYSIS_DEPTH, ANALYSIS_TIME, CHAR_TO_PIECE, EMPTY, GAME_ID, MATE_BOUND,
    MATE_SCORE, MATERIAL_UNITS, MAX_DEPTH, MOVE_TIME, PAWN, PIECE_TO_CHAR,
    SOLID_GLYPH, UNICODE, FILES, QUEEN, ROOK, BISHOP, KNIGHT,
)
from .logger import log_debug
from .movegen import find_king, gen_legal_moves, in_check, validate_position
from .notation import format_move
from .rules import get_game_result
from .search import TRANSPOSITION_TABLE, Searcher
from .widgets import CapturedPanel, FenDialog, MoveHistoryWindow, sort_captured


def _fmt_eval_white(score):
    """Format a White-point-of-view score: +0.35, or +M3 / -M3 for forced mates."""
    if abs(score) >= MATE_BOUND:
        moves = (MATE_SCORE - abs(score) + 1) // 2
        return f"{'+' if score > 0 else '-'}M{moves}"
    return f"{score / 100:+.2f}"


class Chess(tk.Toplevel):
    def __init__(self, master=None):
        super().__init__(master)
        self.title("Chess")
        self.geometry("900x800")
        self.minsize(620, 540)
        self.vs_computer = tk.BooleanVar(master=self, value=True)
        self.play_as_black = tk.BooleanVar(master=self, value=False)
        self.show_coords = tk.BooleanVar(master=self, value=True)
        self.cell, self.offset_x, self.offset_y = 70, 0, 0

        self.state = initial_state()
        self.position_hashes = [self.state.hash]        # every position reached (threefold rule)
        self.selected, self.legal_targets, self.last_move = None, {}, None
        self.game_over, self.game_over_text, self.ai_thinking = False, "", False
        self.white_taken, self.black_taken = [], []     # pieces captured BY white / BY black
        self.move_history = []
        self._history_window = None

        # Search plumbing: workers push (token, kind, result) onto a queue that the
        # Tk thread polls.  Bumping the token invalidates any search still running.
        self._search_token = 0
        self._searcher = None
        self._awaiting = False
        self._results = queue.Queue()
        self._poll_job = None

        log_debug("--- Chess Game Started ---")
        self._build()
        self.apply_theme()
        self.new_game()
        self.focus_set()

    # ================================================================== layout
    def _build(self):
        self.status = tk.Label(self)
        self.status.pack(pady=(12, 6))

        self.middle = tk.Frame(self)
        self.middle.pack(fill="both", expand=True, padx=8, pady=(0, 4))
        self.middle.columnconfigure(1, weight=1)
        self.middle.rowconfigure(0, weight=1)

        self.left_panel = CapturedPanel(self.middle, "White\nhas taken")
        self.left_panel.grid(row=0, column=0, sticky="ns", padx=(0, 4))
        self.canvas = tk.Canvas(self.middle, highlightthickness=0)
        self.canvas.grid(row=0, column=1, sticky="nsew")
        self.canvas.bind("<Configure>", self._on_canvas_resize)
        self.canvas.bind("<Button-1>", self.on_click)
        self.right_panel = CapturedPanel(self.middle, "Black\nhas taken")
        self.right_panel.grid(row=0, column=2, sticky="ns", padx=(4, 0))

        self.engine_frame = tk.Frame(self)
        self.engine_frame.pack(fill="x", padx=14, pady=(0, 4))
        self.engine_lbl = tk.Label(self.engine_frame, text="", justify="left", anchor="w")
        self.engine_lbl.pack(fill="x")

        self.bottom = tk.Frame(self)
        self.bottom.pack(fill="x", padx=12, pady=(0, 6))
        self.vs_cb = tk.Checkbutton(self.bottom, text="vs Computer", variable=self.vs_computer,
                                    command=self.on_vs_toggle, relief="flat", bd=0, highlightthickness=0)
        self.vs_cb.pack(side="left")
        self.color_cb = tk.Checkbutton(self.bottom, text="Play as Black", variable=self.play_as_black,
                                       command=self.new_game, relief="flat", bd=0, highlightthickness=0)
        self.color_cb.pack(side="left", padx=(8, 0))
        self.coords_cb = tk.Checkbutton(self.bottom, text="Coords", variable=self.show_coords,
                                        command=self.draw, relief="flat", bd=0, highlightthickness=0)
        self.coords_cb.pack(side="left", padx=(8, 0))

        self.buttons = []
        for i, (text, cmd) in enumerate((("New", self.new_game), ("History", self.open_history),
                                         ("Load", self.load_game), ("Save", self.save_game),
                                         ("FEN", self.open_fen), ("Settings", self.open_settings))):
            btn = tk.Button(self.bottom, text=text, command=cmd, relief="flat", bd=0, padx=10, pady=3)
            btn.pack(side="right", padx=(0, 4) if i else 0)
            self.buttons.append(btn)

        self.hint_lbl = tk.Label(self, text="Click a piece, then a highlighted square  \u2022  R to restart")
        self.hint_lbl.pack(pady=(0, 4))
        self.memo_lbl = tk.Label(self, text="", anchor="center")
        self.memo_lbl.pack(fill="x", padx=12, pady=(0, 12))
        self.bind("<KeyPress>", self.on_key)

    def apply_theme(self):
        bg, fg = theme.color("bg"), theme.color("fg")
        btn_bg, btn_fg, hover = theme.color("button_bg"), theme.color("button_fg"), theme.color("button_hover")
        muted = theme.color("muted")
        self.configure(bg=bg)
        self.status.configure(bg=bg, fg=fg, font=theme.font("status", "bold"))
        self.middle.configure(bg=bg)
        self.left_panel.apply_theme()
        self.right_panel.apply_theme()
        self.engine_frame.configure(bg=bg)
        self.engine_lbl.configure(bg=bg, fg=muted, font=theme.font("small"))
        self.bottom.configure(bg=bg)
        self.hint_lbl.configure(bg=bg, fg=muted, font=theme.font("small"))
        self.memo_lbl.configure(bg=bg, fg=muted, font=theme.font("small"))
        self.canvas.configure(bg=theme.color("canvas_bg"))
        for cb in (self.vs_cb, self.color_cb, self.coords_cb):
            cb.configure(bg=bg, fg=fg, selectcolor=btn_bg, activebackground=bg,
                         activeforeground=fg, font=theme.font("body"))
        for btn in self.buttons:
            btn.configure(bg=btn_bg, fg=btn_fg, activebackground=hover,
                          activeforeground=btn_fg, font=theme.font("button"))
        self.draw()
        self._update_captures_display()

    def destroy(self):
        self._invalidate_search()
        if self._poll_job is not None:
            try:
                self.after_cancel(self._poll_job)
            except tk.TclError:
                pass
        super().destroy()

    # ================================================================== dialogs
    def open_fen(self):
        dlg = FenDialog(self, board_to_fen(self.state))
        self.wait_window(dlg)
        if not dlg.result:
            return
        try:
            state = fen_to_state(dlg.result)
            validate_position(state)
        except Exception as e:
            messagebox.showerror("Invalid FEN", f"Could not use that position: {e}", parent=self)
            return
        self._reset_game_to(state)

    def open_settings(self):
        dlg = tk.Toplevel(self)
        dlg.title("Chess Settings")
        dlg.transient(self)
        dlg.resizable(False, False)
        dlg.configure(bg=theme.color("bg"))
        body = tk.Frame(dlg, bg=theme.color("bg"))
        body.pack(padx=20, pady=16)
        memo_var = tk.BooleanVar(value=memo.is_enabled(GAME_ID))
        tk.Checkbutton(body, text="Enable Engine Memoization", variable=memo_var, bg=theme.color("bg"),
                       fg=theme.color("fg"), selectcolor=theme.color("button_bg")).pack(anchor="w", pady=4)
        size_lbl = tk.Label(body, text=f"Current TT size: {len(TRANSPOSITION_TABLE)} states",
                            bg=theme.color("bg"), fg=theme.color("muted"))
        size_lbl.pack(anchor="w", pady=2)

        def clear_cache():
            TRANSPOSITION_TABLE.clear()
            size_lbl.config(text="Current TT size: 0 states")
            self._update_memo_label()

        def apply():
            memo.set_game_override(GAME_ID, enabled=memo_var.get())
            self._update_memo_label()
            dlg.destroy()

        tk.Button(body, text="Clear Memory Cache", command=clear_cache, bg=theme.color("button_bg"),
                  fg=theme.color("button_fg")).pack(anchor="w", pady=4)
        tk.Button(body, text="Close", command=apply, bg=theme.color("button_bg"),
                  fg=theme.color("button_fg")).pack(anchor="e", pady=(12, 0))

    def open_history(self):
        if self._history_window and self._history_window.winfo_exists():
            self._history_window.refresh()
            self._history_window.lift()
            self._history_window.focus_force()
            return
        self._history_window = MoveHistoryWindow(self, self._format_history_text)

    def ask_promotion(self, is_white):
        dlg = tk.Toplevel(self)
        dlg.title("Promote Pawn")
        dlg.transient(self)
        dlg.resizable(False, False)
        result = [None]
        bg, fg = theme.color("bg"), theme.color("fg")
        btn_bg, btn_fg, hover = theme.color("button_bg"), theme.color("button_fg"), theme.color("button_hover")
        dlg.configure(bg=bg)
        tk.Label(dlg, text="Promote to:", bg=bg, fg=fg, font=theme.font("body")).pack(padx=14, pady=(12, 8))
        frame = tk.Frame(dlg, bg=bg)
        frame.pack(padx=14, pady=(0, 12))

        def choose(code):
            result[0] = code
            dlg.destroy()

        for code, name in ((QUEEN, "Queen"), (ROOK, "Rook"), (BISHOP, "Bishop"), (KNIGHT, "Knight")):
            key = code if is_white else -code
            tk.Button(frame, text=f"{UNICODE[key]} {name}", width=11, bg=btn_bg, fg=btn_fg,
                      activebackground=hover, activeforeground=btn_fg, relief="flat", bd=0, padx=8,
                      pady=4, font=theme.font("button"), command=lambda c=code: choose(c)).pack(side="left", padx=3)
        dlg.update_idletasks()
        try:
            dlg.grab_set()
        except tk.TclError:
            pass
        dlg.wait_window()
        return result[0]

    # ================================================================== game flow
    def player_color(self):
        return "b" if self.play_as_black.get() else "w"

    def _computer_to_move(self):
        return (not self.game_over and self.vs_computer.get()
                and self.state.turn != self.player_color())

    def _reset_game_to(self, state):
        """Start fresh from `state` (used by New Game and FEN loading)."""
        self._invalidate_search()
        self.state = state
        self.position_hashes = [state.hash]
        self.selected, self.legal_targets, self.last_move = None, {}, None
        self.game_over, self.game_over_text, self.ai_thinking = False, "", False
        self.white_taken, self.black_taken = [], []
        self.move_history = []
        self.engine_lbl.config(text="")
        log_debug(f"Position set | FEN: {board_to_fen(state)}")
        self.check_game_over()
        self._refresh_all()
        self._next_turn()

    def new_game(self):
        self._reset_game_to(initial_state())

    def on_vs_toggle(self):
        self._invalidate_search()
        self.ai_thinking = False
        self.update_status()
        self._next_turn()

    def _refresh_all(self):
        self.update_status()
        self.draw()
        self._update_captures_display()
        self._update_memo_label()
        if self._history_window and self._history_window.winfo_exists():
            self._history_window.refresh()

    def _next_turn(self):
        """Start whatever should happen next: the computer's move, or background analysis."""
        if self.game_over:
            self.engine_lbl.config(text="Game over \u2014 no further analysis.")
            return
        if self._computer_to_move():
            self.ai_thinking = True
            self.update_status()
            self._launch_search("ai")
        else:
            self._launch_search("analysis")

    def check_game_over(self):
        result = get_game_result(self.state, self.position_hashes)
        if result:
            self.game_over, self.game_over_text = True, result
            log_debug(f"Game over: {result} | FEN: {board_to_fen(self.state)}")

    def execute_move(self, move):
        notation = format_move(self.state, move)
        self.move_history.append((self.state.fullmove, self.state.turn, notation))

        captured = self._detect_capture(move)
        if captured is not None:
            (self.black_taken if captured > 0 else self.white_taken).append(captured)

        self.state = apply_move(self.state, move)
        self.position_hashes.append(self.state.hash)
        self.last_move, self.selected, self.legal_targets = move, None, {}
        log_debug(f"Move: {notation} | FEN: {board_to_fen(self.state)}")

        self.check_game_over()
        self._refresh_all()
        self._next_turn()

    def _detect_capture(self, move):
        board = self.state.board
        target = board[move.tr * 8 + move.tc]
        if target != EMPTY:
            return target
        if abs(board[move.fr * 8 + move.fc]) == PAWN and move.fc != move.tc:
            return board[move.fr * 8 + move.tc]            # en passant
        return None

    # ================================================================== searching
    def _invalidate_search(self):
        """Forget any search in flight (its result will be discarded)."""
        self._search_token += 1
        if self._searcher is not None:
            self._searcher.stop()
            self._searcher = None
        self._awaiting = False

    def _launch_search(self, kind):
        """kind is "ai" (pick the computer's move) or "analysis" (just show an evaluation)."""
        self._invalidate_search()
        token = self._search_token
        state = self.state
        history = self.position_hashes[:-1]
        if kind == "ai":
            depth, limit = MAX_DEPTH, MOVE_TIME
        else:
            depth, limit = ANALYSIS_DEPTH, ANALYSIS_TIME
        if not memo.is_enabled(GAME_ID):
            TRANSPOSITION_TABLE.clear()                       # memoization switched off in Settings

        searcher = Searcher()
        self._searcher = searcher
        self._awaiting = True

        def worker():
            try:
                result = searcher.search(state, depth, limit, history)
            except Exception:
                log_debug(f"Search error: {traceback.format_exc()}")
                result = None
            self._results.put((token, kind, result))

        threading.Thread(target=worker, daemon=True).start()
        if self._poll_job is None:
            self._poll_job = self.after(30, self._poll_results)

    def _poll_results(self):
        self._poll_job = None
        try:
            while True:
                token, kind, result = self._results.get_nowait()
                if token == self._search_token:               # stale results are dropped
                    self._handle_result(kind, result)
        except queue.Empty:
            pass
        if self._awaiting and self._poll_job is None:
            self._poll_job = self.after(30, self._poll_results)

    def _handle_result(self, kind, result):
        self._searcher = None
        self._awaiting = False
        if kind == "analysis":
            self._show_engine(result)
            return

        self.ai_thinking = False
        if not self._computer_to_move():                      # situation changed while it thought
            self.update_status()
            return
        move = result.best_move if result else None
        if move is None:
            legal = gen_legal_moves(self.state)
            if not legal:
                self.check_game_over()
                self._refresh_all()
                return
            log_debug("Search returned no move - playing a random legal move")
            move = random.choice(legal)
        else:
            self._show_engine(result)
        self.execute_move(move)

    def _show_engine(self, result):
        if result is None or result.best_move is None:
            self.engine_lbl.config(text="No legal moves.")
            return
        sign, side = (1, "White") if self.state.turn == "w" else (-1, "Black")
        nps = int(result.nodes / result.elapsed) if result.elapsed > 0 else 0
        self.engine_lbl.config(text=(
            f"Depth {result.depth}  \u2022  Eval {_fmt_eval_white(result.score * sign)} (White POV)  "
            f"\u2022  {result.nodes:,} nodes  \u2022  {nps // 1000}k n/s\n"
            f"Best for {side}:  {'  '.join(result.pv[:6])}"))

    # ================================================================== status labels
    def update_status(self):
        if self.game_over:
            self.status.config(text=self.game_over_text)
            return
        if self.ai_thinking:
            self.status.config(text="Computer thinking...")
            return
        side = "White" if self.state.turn == "w" else "Black"
        if self.vs_computer.get():
            suffix = " \u2014 your turn" if self.state.turn == self.player_color() else ""
        else:
            suffix = "'s turn"
        check = "  \u2022  Check!" if in_check(self.state, self.state.turn) else ""
        self.status.config(text=f"{side}{suffix}{check}")

    def _material_lead(self):
        """White's material minus Black's, in pawns (promotions included)."""
        total = 0
        for p in self.state.board:
            if p:
                total += MATERIAL_UNITS[abs(p)] * (1 if p > 0 else -1)
        return total

    def _update_captures_display(self):
        lead = self._material_lead()
        self.left_panel.set_pieces(self.white_taken, lead if lead > 0 else 0)
        self.right_panel.set_pieces(self.black_taken, -lead if lead < 0 else 0)

    def _update_memo_label(self):
        if not memo.is_enabled(GAME_ID):
            self.memo_lbl.config(text="Memo: Disabled")
        else:
            self.memo_lbl.config(text=f"Memo: {len(TRANSPOSITION_TABLE)} cached nodes")

    # ================================================================== history text
    def _format_history_text(self):
        if not self.move_history:
            return "No moves have been played yet."
        lines = ["Chess game log", "=" * 13, ""]
        i = 0
        while i < len(self.move_history):
            num, side, notation = self.move_history[i]
            if side == "w":
                if i + 1 < len(self.move_history) and self.move_history[i + 1][1] == "b":
                    lines.append(f"{num:>3}. {notation:<10s} {self.move_history[i + 1][2]}")
                    i += 2
                else:
                    lines.append(f"{num:>3}. {notation}")
                    i += 1
            else:
                lines.append(f"{num:>3}. ... {notation}")
                i += 1
        taken_w = " ".join(UNICODE[p] for p in sort_captured(self.white_taken)) or "\u2014"
        taken_b = " ".join(UNICODE[p] for p in sort_captured(self.black_taken)) or "\u2014"
        lines += ["", f"Captured by White:  {taken_w}", f"Captured by Black:  {taken_b}"]
        if self.game_over:
            lines += ["", self.game_over_text]
        return "\n".join(lines)

    # ================================================================== save / load
    def get_state(self):
        s = self.state
        return {
            "board": s.board, "turn": s.turn, "castling": castling_to_dict(s.castling),
            "ep_square": s.ep_square, "halfmove": s.halfmove, "fullmove": s.fullmove,
            "white_taken": [PIECE_TO_CHAR[p] for p in self.white_taken],
            "black_taken": [PIECE_TO_CHAR[p] for p in self.black_taken],
            "last_move": list(self.last_move) if self.last_move else None,
            "game_over": self.game_over, "game_over_text": self.game_over_text,
            "vs_computer": self.vs_computer.get(), "play_as_black": self.play_as_black.get(),
            "move_history": self.move_history, "position_hashes": self.position_hashes,
        }

    def set_state(self, data):
        self._invalidate_search()
        board = [CHAR_TO_PIECE.get(c, 0) if isinstance(c, str) else c for c in data["board"]]
        ep = tuple(data["ep_square"]) if data["ep_square"] else None
        self.state = ChessState(board, data["turn"], castling_from_dict(data["castling"]), ep,
                                      data["halfmove"], data["fullmove"])
        saved = data.get("position_hashes")
        self.position_hashes = list(saved) if saved and saved[-1] == self.state.hash else [self.state.hash]

        self.white_taken = [CHAR_TO_PIECE.get(c, 0) for c in data["white_taken"]]
        self.black_taken = [CHAR_TO_PIECE.get(c, 0) for c in data["black_taken"]]
        self.last_move = Move(*data["last_move"]) if data["last_move"] else None
        self.game_over, self.game_over_text = data["game_over"], data["game_over_text"]
        self.vs_computer.set(data["vs_computer"])
        self.play_as_black.set(data.get("play_as_black", False))
        self.move_history = [tuple(m) for m in data["move_history"]]
        self.selected, self.legal_targets, self.ai_thinking = None, {}, False
        log_debug(f"Game state loaded | FEN: {board_to_fen(self.state)}")

        if not self.game_over:
            self.check_game_over()
        self._refresh_all()
        self._next_turn()

    def save_game(self):
        save_manager.prompt_save(self, GAME_ID, self.get_state())

    def load_game(self):
        fname = save_manager.prompt_load(self, GAME_ID)
        if fname:
            self.set_state(save_manager.load_game(GAME_ID, fname))

    # ================================================================== input
    def on_key(self, event):
        key = event.keysym.lower()
        if key == "r":
            self.new_game()
        elif key == "h":
            self.open_history()

    def on_click(self, event):
        if self.game_over or self.ai_thinking or self.cell <= 0:
            return
        if self.vs_computer.get() and self.state.turn != self.player_color():
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
                self.execute_move(next(m for m in moves if m.promo == promo))
            return
        piece = self.state.board[r * 8 + c]
        if piece != EMPTY and (piece > 0) == (self.state.turn == "w"):
            self.selected = (r, c)
            self.recompute_targets()
            self.draw()
            return
        self.selected, self.legal_targets = None, {}
        self.draw()

    def recompute_targets(self):
        self.legal_targets = {}
        if self.selected is None:
            return
        fr, fc = self.selected
        for m in gen_legal_moves(self.state):
            if m.fr == fr and m.fc == fc:
                self.legal_targets.setdefault((m.tr, m.tc), []).append(m)

    # ================================================================== drawing
    def _on_canvas_resize(self, event):
        # Reserve room for the coordinates (40px top and bottom) so they never get clipped.
        avail_w = event.width - 40
        avail_h = event.height - 80
        self.cell = max(10, min(avail_w / 8, avail_h / 8))
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
        cv = self.canvas
        cv.delete("all")
        light, dark = theme.color("board_light"), theme.color("board_dark")
        fg, accent_x, accent_o = theme.color("fg"), theme.color("accent_x"), theme.color("accent_o")
        cell = self.cell

        for r in range(8):
            for c in range(8):
                cv.create_rectangle(self._px(c), self._py(r), self._px(c + 1), self._py(r + 1),
                                    fill=light if (r + c) % 2 == 0 else dark, outline="")

        if self.show_coords.get():
            font = (theme.font_family, max(8, int(cell * 0.2)))
            for i in range(8):
                cv.create_text(self._px(i) + cell / 2, self._py(8) + 15, text=FILES[i], fill=fg, font=font)
                cv.create_text(self._px(0) - 15, self._py(i) + cell / 2, text=str(8 - i), fill=fg, font=font)

        if self.last_move is not None:
            lm = self.last_move
            for rr, cc in ((lm.fr, lm.fc), (lm.tr, lm.tc)):
                cv.create_rectangle(self._px(cc) + 2, self._py(rr) + 2, self._px(cc + 1) - 2,
                                    self._py(rr + 1) - 2, outline=accent_o, width=2)
        if self.selected is not None:
            r, c = self.selected
            cv.create_rectangle(self._px(c) + 1, self._py(r) + 1, self._px(c + 1) - 1,
                                self._py(r + 1) - 1, outline=accent_x, width=3)
        if not self.game_over and in_check(self.state, self.state.turn):
            kp = find_king(self.state.board, self.state.turn)
            if kp:
                cv.create_rectangle(self._px(kp[1]) + 1, self._py(kp[0]) + 1, self._px(kp[1] + 1) - 1,
                                    self._py(kp[0] + 1) - 1, outline=accent_o, width=3)

        for (tr, tc), moves in self.legal_targets.items():
            target = self.state.board[tr * 8 + tc]
            mv = moves[0]
            src = self.state.board[mv.fr * 8 + mv.fc]
            is_ep = abs(src) == PAWN and mv.fc != tc and target == EMPTY
            if target != EMPTY or is_ep:                       # capture: ring
                cv.create_oval(self._px(tc) + cell * 0.08, self._py(tr) + cell * 0.08,
                               self._px(tc + 1) - cell * 0.08, self._py(tr + 1) - cell * 0.08,
                               outline=accent_o, width=3)
            else:                                              # quiet move: dot
                cv.create_oval(self._px(tc) + cell * 0.36, self._py(tr) + cell * 0.36,
                               self._px(tc + 1) - cell * 0.36, self._py(tr + 1) - cell * 0.36,
                               fill=accent_o, outline="")

        font_size, stroke = max(8, int(cell * 0.72)), max(1, int(cell * 0.028))
        offsets = [(-stroke, 0), (stroke, 0), (0, -stroke), (0, stroke),
                   (-stroke, -stroke), (stroke, -stroke), (-stroke, stroke), (stroke, stroke)]
        for r in range(8):
            for c in range(8):
                p = self.state.board[r * 8 + c]
                if p == EMPTY:
                    continue
                white = p > 0
                glyph = SOLID_GLYPH[abs(p)]
                interior = theme.color("piece_white") if white else theme.color("piece_black")
                outline = accent_x if white else accent_o
                cx, cy = self._px(c) + cell / 2, self._py(r) + cell / 2
                for dx, dy in offsets:
                    cv.create_text(cx + dx, cy + dy, text=glyph, fill=outline, font=(theme.font_family, font_size))
                cv.create_text(cx, cy, text=glyph, fill=interior, font=(theme.font_family, font_size))
        cv.create_rectangle(self._px(0), self._py(0), self._px(8), self._py(8), outline=fg, width=2)


def run(master=None):
    return Chess(master)
