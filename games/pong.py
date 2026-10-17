import math
import random
import tkinter as tk
import save_manager
from theme import theme

GAME_ID = "pong"
W, H = 640, 420
PADDLE_W, PADDLE_H = 12, 78
PADDLE_MARGIN = 18
BALL = 14
BALL_SPEED = 5.5
PADDLE_SPEED = 6
WIN_SCORE = 7

class Pong(tk.Toplevel):
    def __init__(self, master=None):
        super().__init__(master)
        self.title("Pong")
        self.geometry("680x560")
        self.minsize(360, 320)

        self.scale = 1.0
        self.offset_x = 0
        self.offset_y = 0

        self._build()
        self.bind("<KeyPress>", self.on_key_press)
        self.bind("<KeyRelease>", lambda e: self.keys.discard(e.keysym.lower()))
        self.focus_set()

        self._after_id = None
        self.new_game()

    def _build(self):
        self.score_lbl = tk.Label(self, text="0  :  0")
        self.score_lbl.pack(pady=(12, 4))

        self.canvas = tk.Canvas(self, highlightthickness=0)
        self.canvas.pack(fill="both", expand=True, padx=12, pady=(0, 6))
        self.canvas.bind("<Configure>", self._on_canvas_resize)

        self.bottom = tk.Frame(self)
        self.bottom.pack(fill="x", padx=12, pady=(0, 8))

        self.hint_lbl = tk.Label(self.bottom, text="W / S to move   •   first to 7 wins")
        self.hint_lbl.pack(side="left")

        self.new_btn = tk.Button(self.bottom, text="New", command=self.new_game, relief="flat", bd=0, padx=10, pady=3)
        self.new_btn.pack(side="right")

        self.load_btn = tk.Button(self.bottom, text="Load", command=self.load_game, relief="flat", bd=0, padx=10, pady=3)
        self.load_btn.pack(side="right", padx=(0, 4))

        self.save_btn = tk.Button(self.bottom, text="Save", command=self.save_game, relief="flat", bd=0, padx=10, pady=3)
        self.save_btn.pack(side="right", padx=(0, 4))

        self.keys = set()

    def _on_canvas_resize(self, event):
        self.scale = min(event.width / W, event.height / H)
        self.offset_x = (event.width - W * self.scale) / 2
        self.offset_y = (event.height - H * self.scale) / 2
        self.draw()

    def apply_theme(self):
        bg = theme.color("bg")
        fg = theme.color("fg")
        btn_bg = theme.color("button_bg")
        btn_fg = theme.color("button_fg")
        hover = theme.color("button_hover")

        self.configure(bg=bg)
        self.score_lbl.configure(bg=bg, fg=fg, font=theme.font("title", "bold"))
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

        self.left_y = H / 2 - PADDLE_H / 2
        self.right_y = H / 2 - PADDLE_H / 2
        self.left_score = 0
        self.right_score = 0
        self.over = False
        self.keys.clear()
        self.reset_ball()
        self.update_score()
        self._after_id = self.after(16, self.loop)

    def get_state(self):
        return {
            "left_y": self.left_y, "right_y": self.right_y,
            "left_score": self.left_score, "right_score": self.right_score,
            "over": self.over, "ball_x": self.ball_x, "ball_y": self.ball_y,
            "ball_dx": self.ball_dx, "ball_dy": self.ball_dy
        }

    def set_state(self, data):
        if self._after_id:
            self.after_cancel(self._after_id)
            self._after_id = None
        self.left_y = data["left_y"]
        self.right_y = data["right_y"]
        self.left_score = data["left_score"]
        self.right_score = data["right_score"]
        self.over = data["over"]
        self.ball_x = data["ball_x"]
        self.ball_y = data["ball_y"]
        self.ball_dx = data["ball_dx"]
        self.ball_dy = data["ball_dy"]
        self.update_score()
        self.draw()
        if not self.over:
            self._after_id = self.after(16, self.loop)

    def save_game(self):
        save_manager.prompt_save(self, GAME_ID, self.get_state())

    def load_game(self):
        fname = save_manager.prompt_load(self, GAME_ID)
        if fname:
            data = save_manager.load_game(GAME_ID, fname)
            self.set_state(data)

    def reset_ball(self, direction=None):
        self.ball_x = W / 2
        self.ball_y = H / 2
        d = direction if direction is not None else random.choice([-1, 1])
        angle = random.uniform(-0.6, 0.6)
        self.ball_dx = d * BALL_SPEED * math.cos(angle)
        self.ball_dy = BALL_SPEED * math.sin(angle)

    def update_score(self):
        self.score_lbl.config(text=f"{self.left_score}  :  {self.right_score}")

    def on_key_press(self, event):
        key = event.keysym.lower()
        if key == "r":
            self.new_game()
            return
        self.keys.add(key)

    def loop(self):
        self._after_id = None
        if self.over: return
        self.move_paddles()
        self.move_ball()
        self.draw()
        self._after_id = self.after(16, self.loop)

    def move_paddles(self):
        if "w" in self.keys or "up" in self.keys:
            self.left_y -= PADDLE_SPEED
        if "s" in self.keys or "down" in self.keys:
            self.left_y += PADDLE_SPEED
        self.left_y = max(0, min(H - PADDLE_H, self.left_y))

        target = self.ball_y - PADDLE_H / 2
        if self.ball_dx > 0:
            if self.right_y < target - 4: self.right_y += PADDLE_SPEED * 0.85
            elif self.right_y > target + 4: self.right_y -= PADDLE_SPEED * 0.85
        self.right_y = max(0, min(H - PADDLE_H, self.right_y))

    def move_ball(self):
        self.ball_x += self.ball_dx
        self.ball_y += self.ball_dy
        if self.ball_y <= BALL / 2:
            self.ball_y = BALL / 2
            self.ball_dy = abs(self.ball_dy)
        elif self.ball_y >= H - BALL / 2:
            self.ball_y = H - BALL / 2
            self.ball_dy = -abs(self.ball_dy)

        if (self.ball_dx < 0 and self.ball_x - BALL / 2 <= PADDLE_MARGIN + PADDLE_W and self.ball_x > PADDLE_MARGIN and self.left_y <= self.ball_y <= self.left_y + PADDLE_H):
            self.ball_x = PADDLE_MARGIN + PADDLE_W + BALL / 2
            self.ball_dx = abs(self.ball_dx) * 1.04
            offset = (self.ball_y - (self.left_y + PADDLE_H / 2)) / (PADDLE_H / 2)
            self.ball_dy += offset * 1.8
        elif (self.ball_dx > 0 and self.ball_x + BALL / 2 >= W - PADDLE_MARGIN - PADDLE_W and self.ball_x < W - PADDLE_MARGIN and self.right_y <= self.ball_y <= self.right_y + PADDLE_H):
            self.ball_x = W - PADDLE_MARGIN - PADDLE_W - BALL / 2
            self.ball_dx = -abs(self.ball_dx) * 1.04
            offset = (self.ball_y - (self.right_y + PADDLE_H / 2)) / (PADDLE_H / 2)
            self.ball_dy += offset * 1.8

        limit = BALL_SPEED * 1.8
        self.ball_dy = max(-limit, min(limit, self.ball_dy))

        if self.ball_x < -BALL: self.point("right")
        elif self.ball_x > W + BALL: self.point("left")

    def point(self, side):
        if side == "left": self.left_score += 1
        else: self.right_score += 1
        self.update_score()

        if self.left_score >= WIN_SCORE or self.right_score >= WIN_SCORE:
            self.over = True
            self.draw()
            return
        self.reset_ball(direction=-1 if side == "left" else 1)

    def sx(self, x): return self.offset_x + x * self.scale
    def sy(self, y): return self.offset_y + y * self.scale

    def draw(self):
        if self.scale <= 0: return
        self.canvas.delete("all")
        dash_h, step, cx, bar = 13 * self.scale, 26 * self.scale, self.sx(W / 2), max(1, 2 * self.scale)
        y = self.offset_y
        while y < self.offset_y + H * self.scale:
            self.canvas.create_rectangle(cx - bar, y, cx + bar, y + dash_h, fill=theme.color("divider"), outline="")
            y += step

        self.canvas.create_rectangle(self.sx(PADDLE_MARGIN), self.sy(self.left_y), self.sx(PADDLE_MARGIN + PADDLE_W), self.sy(self.left_y + PADDLE_H), fill=theme.color("accent_x"), outline="")
        self.canvas.create_rectangle(self.sx(W - PADDLE_MARGIN - PADDLE_W), self.sy(self.right_y), self.sx(W - PADDLE_MARGIN), self.sy(self.right_y + PADDLE_H), fill=theme.color("accent_o"), outline="")
        
        r = BALL / 2
        self.canvas.create_oval(self.sx(self.ball_x - r), self.sy(self.ball_y - r), self.sx(self.ball_x + r), self.sy(self.ball_y + r), fill=theme.color("ball"), outline="")

        if self.over:
            text = ("You win!  Press R" if self.left_score >= WIN_SCORE else "Computer wins!  Press R")
            size = max(14, int(22 * self.scale))
            self.canvas.create_text(self.offset_x + W * self.scale / 2, self.offset_y + H * self.scale / 2, text=text, fill=theme.color("fg"), font=(theme.font_family, size, "bold"))

def run(master=None):
    return Pong(master)