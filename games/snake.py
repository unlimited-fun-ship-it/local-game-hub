import random
import tkinter as tk
import save_manager
from theme import theme

GAME_ID = "snake"
COLS, ROWS = 22, 18
DIRECTIONS = {
    "up": (0, -1), "w": (0, -1),
    "down": (0, 1), "s": (0, 1),
    "left": (-1, 0), "a": (-1, 0),
    "right": (1, 0), "d": (1, 0),
}

class Snake(tk.Toplevel):
    def __init__(self, master=None):
        super().__init__(master)
        self.title("Snake")
        self.geometry("560x520")
        self.minsize(300, 280)

        self.cell = 22
        self.offset_x = 0
        self.offset_y = 0

        self._build()
        self.bind("<KeyPress>", self.on_key)
        self.focus_set()

        self._after_id = None
        self.new_game()

    def _build(self):
        self.score_lbl = tk.Label(self, text="Score: 0")
        self.score_lbl.pack(pady=(12, 4))

        self.canvas = tk.Canvas(self, highlightthickness=0)
        self.canvas.pack(fill="both", expand=True, padx=12, pady=(0, 6))
        self.canvas.bind("<Configure>", self._on_canvas_resize)

        self.bottom = tk.Frame(self)
        self.bottom.pack(fill="x", padx=12, pady=(0, 8))

        self.hint_lbl = tk.Label(self.bottom, text="Arrow keys / WASD to move   •   R to restart")
        self.hint_lbl.pack(side="left")

        self.new_btn = tk.Button(self.bottom, text="New", command=self.new_game, relief="flat", bd=0, padx=10, pady=3)
        self.new_btn.pack(side="right")
        
        self.load_btn = tk.Button(self.bottom, text="Load", command=self.load_game, relief="flat", bd=0, padx=10, pady=3)
        self.load_btn.pack(side="right", padx=(0, 4))

        self.save_btn = tk.Button(self.bottom, text="Save", command=self.save_game, relief="flat", bd=0, padx=10, pady=3)
        self.save_btn.pack(side="right", padx=(0, 4))

    def _on_canvas_resize(self, event):
        self.cell = min(event.width / COLS, event.height / ROWS)
        self.offset_x = (event.width - self.cell * COLS) / 2
        self.offset_y = (event.height - self.cell * ROWS) / 2
        self.draw()

    def apply_theme(self):
        bg = theme.color("bg")
        fg = theme.color("fg")
        btn_bg = theme.color("button_bg")
        btn_fg = theme.color("button_fg")
        hover = theme.color("button_hover")

        self.configure(bg=bg)
        self.score_lbl.configure(bg=bg, fg=fg, font=theme.font("heading", "bold"))
        self.hint_lbl.configure(bg=bg, fg=theme.color("muted"), font=theme.font("small"))
        self.bottom.configure(bg=bg)
        self.canvas.configure(bg=theme.color("canvas_bg"))

        for btn in (self.new_btn, self.save_btn, self.load_btn):
            btn.configure(bg=btn_bg, fg=btn_fg, activebackground=hover, activeforeground=btn_fg, font=theme.font("button"))

        self.draw()

    def new_game(self):
        if self._after_id:
            self.after_cancel(self._after_id)
            self._after_id = None

        mid = ROWS // 2
        self.snake = [(5, mid), (4, mid), (3, mid)]
        self.direction = (1, 0)
        self.next_direction = (1, 0)
        self.score = 0
        self.delay = 130
        self.alive = True
        self.food = self.spawn_food()
        self.score_lbl.config(text="Score: 0")

        self.draw()
        self._after_id = self.after(self.delay, self.tick)

    def get_state(self):
        return {
            "snake": self.snake,
            "direction": self.direction,
            "next_direction": self.next_direction,
            "score": self.score,
            "delay": self.delay,
            "food": self.food,
            "alive": self.alive
        }

    def set_state(self, data):
        if self._after_id:
            self.after_cancel(self._after_id)
            self._after_id = None
        self.snake = [tuple(x) for x in data["snake"]]
        self.direction = tuple(data["direction"])
        self.next_direction = tuple(data["next_direction"])
        self.score = data["score"]
        self.delay = data["delay"]
        self.food = tuple(data["food"])
        self.alive = data["alive"]
        self.score_lbl.config(text=f"Score: {self.score}")
        self.draw()
        if self.alive:
            self._after_id = self.after(self.delay, self.tick)

    def save_game(self):
        save_manager.prompt_save(self, GAME_ID, self.get_state())

    def load_game(self):
        fname = save_manager.prompt_load(self, GAME_ID)
        if fname:
            data = save_manager.load_game(GAME_ID, fname)
            self.set_state(data)

    def spawn_food(self):
        free = [(x, y) for x in range(COLS) for y in range(ROWS) if (x, y) not in self.snake]
        return random.choice(free) if free else self.snake[0]

    def on_key(self, event):
        key = event.keysym.lower()
        if key == "r":
            self.new_game()
            return
        if key in DIRECTIONS:
            d = DIRECTIONS[key]
            if (d[0] + self.direction[0], d[1] + self.direction[1]) != (0, 0):
                self.next_direction = d

    def tick(self):
        self._after_id = None
        if not self.alive:
            return

        self.direction = self.next_direction
        hx, hy = self.snake[0]
        head = (hx + self.direction[0], hy + self.direction[1])

        if not (0 <= head[0] < COLS and 0 <= head[1] < ROWS) or head in self.snake:
            self.alive = False
            self.draw()
            return

        self.snake.insert(0, head)
        if head == self.food:
            self.score += 10
            self.score_lbl.config(text=f"Score: {self.score}")
            self.food = self.spawn_food()
            self.delay = max(60, self.delay - 4)
        else:
            self.snake.pop()

        self.draw()
        self._after_id = self.after(self.delay, self.tick)

    def _px(self, gx): return self.offset_x + gx * self.cell
    def _py(self, gy): return self.offset_y + gy * self.cell

    def draw(self):
        if self.cell <= 0: return
        self.canvas.delete("all")
        pad = max(1, self.cell * 0.09)

        fx, fy = self.food
        self.canvas.create_oval(self._px(fx) + pad, self._py(fy) + pad, self._px(fx + 1) - pad, self._py(fy + 1) - pad, fill=theme.color("accent_o"), outline="")

        for i, (x, y) in enumerate(self.snake):
            color = theme.color("accent_x") if i == 0 else theme.color("snake_body")
            self.canvas.create_rectangle(self._px(x) + pad, self._py(y) + pad, self._px(x + 1) - pad, self._py(y + 1) - pad, fill=color, outline="")

        if not self.alive:
            size = max(12, int(self.cell * 0.95))
            self.canvas.create_text(self.canvas.winfo_width() / 2, self.canvas.winfo_height() / 2, text="GAME OVER\nPress R to play again", fill=theme.color("fg"), font=(theme.font_family, size, "bold"), justify="center")

def run(master=None):
    return Snake(master)