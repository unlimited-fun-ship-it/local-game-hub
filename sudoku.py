"""Sudoku - resizable, themeable, keyboard driven.

Controls:
  - Arrow keys to move the selection
  - 1-9 to place a number
  - Backspace / Delete / 0 to clear a cell
  - R to start a new game
  - Click any cell to select it
"""

import random
import tkinter as tk

from theme import theme


# ============================================================ puzzle logic
def _copy(board):
    return [row[:] for row in board]


def _is_valid(board, r, c, num):
    if num in board[r]:
        return False
    for row in range(9):
        if board[row][c] == num:
            return False
    br, bc = (r // 3) * 3, (c // 3) * 3
    for rr in range(br, br + 3):
        for cc in range(bc, bc + 3):
            if board[rr][cc] == num:
                return False
    return True


def _count_solutions(board, limit=2):
    """Count solutions of `board`, stopping as soon as we have `limit`.
    Uses a most-constrained-cell heuristic so uniqueness checks stay fast."""
    best = None
    best_opts = None
    for i in range(81):
        r, c = divmod(i, 9)
        if board[r][c] != 0:
            continue
        opts = [n for n in range(1, 10) if _is_valid(board, r, c, n)]
        if not opts:
            return 0
        if best is None or len(opts) < len(best_opts):
            best = (r, c)
            best_opts = opts
            if len(opts) == 1:
                break

    if best is None:
        return 1                              # solved

    r, c = best
    count = 0
    for num in best_opts:
        board[r][c] = num
        count += _count_solutions(board, limit - count)
        board[r][c] = 0
        if count >= limit:
            return count
    return count


def _generate_solution():
    board = [[0] * 9 for _ in range(9)]

    def fill(idx):
        if idx == 81:
            return True
        r, c = divmod(idx, 9)
        nums = list(range(1, 10))
        random.shuffle(nums)
        for num in nums:
            if _is_valid(board, r, c, num):
                board[r][c] = num
                if fill(idx + 1):
                    return True
                board[r][c] = 0
        return False

    fill(0)
    return board


def _make_puzzle(clues=33):
    solution = _generate_solution()
    puzzle = _copy(solution)
    filled = 81
    cells = [(r, c) for r in range(9) for c in range(9)]
    random.shuffle(cells)

    for r, c in cells:
        if filled <= clues:
            break
        removed = puzzle[r][c]
        puzzle[r][c] = 0
        if _count_solutions(_copy(puzzle), 2) != 1:
            puzzle[r][c] = removed       # restoring keeps the puzzle unique
        else:
            filled -= 1

    return puzzle, solution


DIFFICULTY_CLUES = {"Easy": 45, "Medium": 33, "Hard": 26}


# ================================================================== game
class Sudoku(tk.Toplevel):
    def __init__(self, master=None):
        super().__init__(master)
        self.title("Sudoku")
        self.geometry("640x720")
        self.minsize(360, 460)

        self.cell = 50
        self.offset_x = 0
        self.offset_y = 0

        self.puzzle = None
        self.solution = None
        self.fixed = None
        self.user = None
        self.selected = (0, 0)
        self.difficulty = "Medium"
        self.solved = False

        self._build()
        self.apply_theme()
        self.new_game()
        self.focus_set()
        self.bind("<KeyPress>", self.on_key)

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

        self.diff_btns = {}
        for d in ("Easy", "Medium", "Hard"):
            b = tk.Button(self.bottom, text=d, relief="flat", bd=0,
                          padx=10, pady=3,
                          command=lambda d=d: self.set_difficulty(d))
            b.pack(side="left", padx=2)
            self.diff_btns[d] = b

        self.new_btn = tk.Button(self.bottom, text="New Game",
                                 command=self.new_game, relief="flat", bd=0,
                                 padx=10, pady=3)
        self.new_btn.pack(side="right")

        self.hint_lbl = tk.Label(self,
                                 text="Arrows to move  •  1-9 to place  •  Del to clear  •  R to restart")
        self.hint_lbl.pack(pady=(0, 12))

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

        for d, b in self.diff_btns.items():
            selected = (d == self.difficulty)
            b.configure(
                bg=theme.color("accent_x") if selected else btn_bg,
                fg=btn_fg,
                activebackground=hover,
                activeforeground=btn_fg,
                font=theme.font("button"),
            )
        self.new_btn.configure(bg=btn_bg, fg=btn_fg,
                               activebackground=hover, activeforeground=btn_fg,
                               font=theme.font("button"))

        self.draw()

    # ---------------------------------------------------------- game flow
    def set_difficulty(self, d):
        self.difficulty = d
        self.apply_theme()
        self.new_game()

    def new_game(self):
        self.solved = False
        clues = DIFFICULTY_CLUES.get(self.difficulty, 33)
        self.puzzle, self.solution = _make_puzzle(clues)
        self.fixed = [[self.puzzle[r][c] != 0 for c in range(9)]
                      for r in range(9)]
        self.user = [[0] * 9 for _ in range(9)]
        self.selected = (0, 0)
        self.update_status()
        self.draw()

    def on_click(self, event):
        if self.cell <= 0:
            return
        c = int((event.x - self.offset_x) // self.cell)
        r = int((event.y - self.offset_y) // self.cell)
        if 0 <= r < 9 and 0 <= c < 9:
            self.selected = (r, c)
            self.focus_set()
            self.draw()

    def on_key(self, event):
        key = event.keysym

        if key in ("r", "R"):
            self.new_game()
            return
        if self.selected is None or self.puzzle is None:
            return

        r, c = self.selected

        if key in ("Up", "Down", "Left", "Right"):
            dr = {"Up": -1, "Down": 1, "Left": 0, "Right": 0}[key]
            dc = {"Up": 0, "Down": 0, "Left": -1, "Right": 1}[key]
            self.selected = ((r + dr) % 9, (c + dc) % 9)
            self.draw()
            return

        if key in ("BackSpace", "Delete", "0"):
            if not self.fixed[r][c]:
                self.user[r][c] = 0
                self.update_status()
                self.draw()
            return

        if len(key) == 1 and key in "123456789":
            if not self.fixed[r][c] and not self.solved:
                self.user[r][c] = int(key)
                self.update_status()
                if c < 8:
                    self.selected = (r, c + 1)
                elif r < 8:
                    self.selected = (r + 1, 0)
                self.draw()

    def update_status(self):
        filled = sum(
            1
            for r in range(9)
            for c in range(9)
            if self.fixed[r][c] or self.user[r][c]
        )
        self.status.config(text=f"{self.difficulty}  •  {filled}/81 filled")

        for r in range(9):
            for c in range(9):
                v = self.puzzle[r][c] if self.fixed[r][c] else self.user[r][c]
                if v != self.solution[r][c]:
                    return
        self.solved = True
        self.status.config(text="🎉 Solved!")

    # ------------------------------------------------------------ render
    def _on_canvas_resize(self, event):
        size = min(event.width, event.height) - 8
        self.cell = size / 9
        self.offset_x = (event.width - self.cell * 9) / 2
        self.offset_y = (event.height - self.cell * 9) / 2
        self.draw()

    def _px(self, c):
        return self.offset_x + c * self.cell

    def _py(self, r):
        return self.offset_y + r * self.cell

    def _cell_value(self, r, c):
        return self.puzzle[r][c] if self.fixed[r][c] else self.user[r][c]

    def _cell_has_error(self, r, c):
        v = self._cell_value(r, c)
        if v == 0:
            return False
        for i in range(9):
            if i != c and self._cell_value(r, i) == v:
                return True
            if i != r and self._cell_value(i, c) == v:
                return True
        br, bc = (r // 3) * 3, (c // 3) * 3
        for rr in range(br, br + 3):
            for cc in range(bc, bc + 3):
                if (rr, cc) != (r, c) and self._cell_value(rr, cc) == v:
                    return True
        return False

    def draw(self):
        if self.cell <= 0 or self.puzzle is None:
            return
        self.canvas.delete("all")

        # selected cell highlight
        if self.selected and not self.solved:
            r, c = self.selected
            self.canvas.create_rectangle(
                self._px(c) + 1, self._py(r) + 1,
                self._px(c + 1) - 1, self._py(r + 1) - 1,
                fill=theme.color("card_up"), outline="")

        # numbers
        fsize = max(8, int(self.cell * 0.55))
        for r in range(9):
            for c in range(9):
                v = self._cell_value(r, c)
                if v == 0:
                    continue
                if self.fixed[r][c]:
                    color = theme.color("fg")
                elif self._cell_has_error(r, c):
                    color = theme.color("accent_o")
                else:
                    color = theme.color("accent_x")
                self.canvas.create_text(
                    self._px(c) + self.cell / 2,
                    self._py(r) + self.cell / 2,
                    text=str(v), fill=color,
                    font=(theme.font_family, fsize, "bold"))

        # grid lines (thicker between 3x3 blocks)
        for i in range(10):
            w = 3 if i % 3 == 0 else 1
            self.canvas.create_line(
                self._px(i), self._py(0), self._px(i), self._py(9),
                fill=theme.color("divider"), width=w)
            self.canvas.create_line(
                self._px(0), self._py(i), self._px(9), self._py(i),
                fill=theme.color("divider"), width=w)

        # outer border
        self.canvas.create_rectangle(
            self._px(0), self._py(0), self._px(9), self._py(9),
            outline=theme.color("fg"), width=3)


def run(master=None):
    return Sudoku(master)