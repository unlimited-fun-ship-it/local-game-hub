import random
import tkinter as tk
import save_manager
from theme import theme

GAME_ID = "memory"
SYMBOLS = ["🍎", "🍌", "🍇", "🍒", "🍉", "🍋", "🥝", "🍑"]
COLS = 4

class Memory(tk.Toplevel):
    def __init__(self, master=None):
        super().__init__(master)
        self.title("Memory Match")
        self.geometry("420x480")
        self.minsize(260, 320)

        self._build()
        self.new_game()
        self.apply_theme()
        self.focus_set()

    def _build(self):
        self.status = tk.Label(self, text="")
        self.status.pack(pady=(14, 8))

        self.grid_frame = tk.Frame(self)
        self.grid_frame.pack(fill="both", expand=True, padx=14, pady=(0, 6))
        for c in range(COLS):
            self.grid_frame.columnconfigure(c, weight=1, uniform="card")
        for r in range(4):
            self.grid_frame.rowconfigure(r, weight=1, uniform="card")

        self.buttons = []
        for i in range(16):
            b = tk.Button(self.grid_frame, text="?", relief="flat", bd=0,
                          command=lambda i=i: self.flip(i))
            b.grid(row=i // COLS, column=i % COLS, padx=4, pady=4, sticky="nsew")
            self.buttons.append(b)

        self.bottom = tk.Frame(self)
        self.bottom.pack(fill="x", padx=14, pady=14)

        self.new_btn = tk.Button(self.bottom, text="New Game", command=self.new_game,
                                 relief="flat", bd=0, padx=12, pady=4)
        self.new_btn.pack(side="right")

        self.load_btn = tk.Button(self.bottom, text="Load", command=self.load_game,
                                  relief="flat", bd=0, padx=12, pady=4)
        self.load_btn.pack(side="right", padx=(0, 4))

        self.save_btn = tk.Button(self.bottom, text="Save", command=self.save_game,
                                  relief="flat", bd=0, padx=12, pady=4)
        self.save_btn.pack(side="right", padx=(0, 4))

    def apply_theme(self):
        bg = theme.color("bg")
        fg = theme.color("fg")
        btn_bg = theme.color("button_bg")
        hover = theme.color("button_hover")
        card_up = theme.color("card_up")

        self.configure(bg=bg)
        self.status.configure(bg=bg, fg=fg, font=theme.font("status", "bold"))
        self.grid_frame.configure(bg=bg)
        self.bottom.configure(bg=bg)

        for i, b in enumerate(self.buttons):
            b.configure(activebackground=hover, fg=fg,
                        font=theme.font("cell", "bold"))
            if b.cget("text") == "?":
                b.configure(bg=btn_bg)
            else:
                b.configure(bg=card_up)

        for btn in (self.new_btn, self.save_btn, self.load_btn):
            btn.configure(bg=btn_bg, fg=theme.color("button_fg"),
                          activebackground=hover,
                          activeforeground=theme.color("button_fg"),
                          font=theme.font("button"))

    def new_game(self):
        self.deck = SYMBOLS * 2
        random.shuffle(self.deck)
        self.revealed = set()
        self.first = None
        self.lock = False
        self.moves = 0
        self.status.config(text="Find all 8 pairs")
        for b in self.buttons:
            b.config(text="?", bg=theme.color("button_bg"), fg=theme.color("fg"))

    def get_state(self):
        return {
            "deck": self.deck,
            "revealed": list(self.revealed),
            "moves": self.moves,
            "status": self.status.cget("text")
        }

    def set_state(self, data):
        self.deck = data["deck"]
        self.revealed = set(data["revealed"])
        self.moves = data["moves"]
        self.first = None
        self.lock = False
        for i, b in enumerate(self.buttons):
            if i in self.revealed:
                b.config(text=self.deck[i], bg=theme.color("card_up"))
            else:
                b.config(text="?", bg=theme.color("button_bg"))
        self.status.config(text=data["status"])

    def save_game(self):
        save_manager.prompt_save(self, GAME_ID, self.get_state())

    def load_game(self):
        fname = save_manager.prompt_load(self, GAME_ID)
        if fname:
            data = save_manager.load_game(GAME_ID, fname)
            self.set_state(data)

    def flip(self, i):
        if self.lock or i in self.revealed or i == self.first:
            return

        self.buttons[i].config(text=self.deck[i], bg=theme.color("card_up"))

        if self.first is None:
            self.first = i
            return

        self.moves += 1
        a, b = self.first, i
        self.first = None

        if self.deck[a] == self.deck[b]:
            self.revealed.update((a, b))
            pairs = len(self.revealed) // 2
            if len(self.revealed) == len(self.deck):
                self.status.config(text=f"🎉 You won in {self.moves} moves!")
            else:
                self.status.config(text=f"Moves: {self.moves}  •  Pairs: {pairs}/8")
        else:
            self.lock = True
            self.after(700, lambda: self.hide(a, b))

    def hide(self, a, b):
        for i in (a, b):
            self.buttons[i].config(text="?", bg=theme.color("button_bg"))
        self.lock = False

def run(master=None):
    return Memory(master)