"""Tic-Tac-Toe - resizable, themeable."""

import tkinter as tk

from theme import theme

LINES = [(0, 1, 2), (3, 4, 5), (6, 7, 8),
         (0, 3, 6), (1, 4, 7), (2, 5, 8),
         (0, 4, 8), (2, 4, 6)]


def winner_of(board):
    for a, b, c in LINES:
        if board[a] and board[a] == board[b] == board[c]:
            return board[a]
    return None


class TicTacToe(tk.Toplevel):
    def __init__(self, master=None):
        super().__init__(master)
        self.title("Tic-Tac-Toe")
        self.geometry("380x440")
        self.minsize(260, 320)
        self.vs_computer = tk.BooleanVar(master=self, value=True)

        self._build()
        self.new_game()
        self.apply_theme()
        self.focus_set()

    # ------------------------------------------------------------------ build
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
            b = tk.Button(self.grid_frame, text=" ", relief="flat", bd=0,
                          command=lambda i=i: self.click(i))
            b.grid(row=i // 3, column=i % 3, padx=3, pady=3, sticky="nsew")
            self.cells.append(b)

        self.bottom = tk.Frame(self)
        self.bottom.pack(fill="x", padx=14, pady=14)

        self.vs_cb = tk.Checkbutton(self.bottom, text="vs Computer",
                                    variable=self.vs_computer,
                                    command=self.new_game,
                                    relief="flat", bd=0, highlightthickness=0)
        self.vs_cb.pack(side="left")

        self.new_btn = tk.Button(self.bottom, text="New Game",
                                 command=self.new_game, relief="flat", bd=0,
                                 padx=10, pady=4)
        self.new_btn.pack(side="right")

    # ------------------------------------------------------------------ theme
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

        for i, b in enumerate(self.cells):
            b.configure(bg=btn_bg, activebackground=hover,
                        font=theme.font("cell", "bold"))
            if self.board[i] == "X":
                b.configure(fg=theme.color("accent_x"))
            elif self.board[i] == "O":
                b.configure(fg=theme.color("accent_o"))
            else:
                b.configure(fg=fg)

        self.vs_cb.configure(bg=bg, fg=fg, selectcolor=btn_bg,
                             activebackground=bg, activeforeground=fg,
                             font=theme.font("body"))
        self.new_btn.configure(bg=btn_bg, fg=btn_fg,
                               activebackground=hover, activeforeground=btn_fg,
                               font=theme.font("button"))

    # -------------------------------------------------------------- game flow
    def new_game(self):
        self.board = [""] * 9
        self.turn = "X"
        self.over = False
        for b in self.cells:
            b.config(text=" ", fg=theme.color("fg"))
        self.update_status()

    def update_status(self):
        if self.over:
            return
        if self.turn == "X":
            self.status.config(text="Your turn (X)" if self.vs_computer.get() else "X's turn")
        else:
            self.status.config(text="Computer thinking..." if self.vs_computer.get() else "O's turn")

    def click(self, i):
        if self.over or self.board[i]:
            return
        if self.vs_computer.get() and self.turn != "X":
            return

        self.place(i, self.turn)
        if self.check_end():
            return

        self.turn = "O" if self.turn == "X" else "X"
        self.update_status()

        if self.vs_computer.get() and self.turn == "O":
            self.after(180, self.computer_move)

    def place(self, i, player):
        self.board[i] = player
        self.cells[i].config(
            text=player,
            fg=theme.color("accent_x") if player == "X" else theme.color("accent_o"))

    def check_end(self):
        w = winner_of(self.board)
        if w:
            self.over = True
            if self.vs_computer.get():
                self.status.config(text="You win! 🎉" if w == "X" else "Computer wins!")
            else:
                self.status.config(text=f"{w} wins! 🎉")
            return True
        if "" not in self.board:
            self.over = True
            self.status.config(text="It's a draw.")
            return True
        return False

    # ------------------------------------------------------------------- AI
    def computer_move(self):
        if self.over:
            return
        move = self.best_move()
        if move is None:
            return
        self.place(move, "O")
        if self.check_end():
            return
        self.turn = "X"
        self.update_status()

    def best_move(self):
        best_score, best = -2, None
        for i in range(9):
            if self.board[i] == "":
                self.board[i] = "O"
                score = self._minimax(self.board, "X")
                self.board[i] = ""
                if score > best_score:
                    best_score, best = score, i
        return best

    def _minimax(self, board, player):
        w = winner_of(board)
        if w == "O":
            return 1
        if w == "X":
            return -1
        if "" not in board:
            return 0

        if player == "O":
            best = -2
            for i in range(9):
                if board[i] == "":
                    board[i] = "O"
                    best = max(best, self._minimax(board, "X"))
                    board[i] = ""
            return best

        best = 2
        for i in range(9):
            if board[i] == "":
                board[i] = "X"
                best = min(best, self._minimax(board, "O"))
                board[i] = ""
        return best


def run(master=None):
    return TicTacToe(master)