"""
Central theme configuration for the Mini Game Hub.

Edit the values below to change the look of the whole project, or use
the "Settings" button in the launcher to change them at runtime.

Every game reads from the shared `theme` object, so a change here
(or via the Settings dialog) is picked up everywhere.
"""


class Theme:
    def __init__(self):
        # ---------------------------------------------------------------- Fonts
        self.font_family = "Segoe UI"
        self.font_sizes = {
            "title":     22,   # launcher title
            "subtitle":  10,   # launcher subtitle
            "heading":   13,   # card / panel headings
            "body":      10,
            "small":      9,
            "button":    10,
            "status":    13,   # game status line
            "cell":      26,   # big symbols (tic-tac-toe / memory)
            "big":       20,   # game-over overlay
        }

        # --------------------------------------------------------------- Colors
        self.colors = {
            "bg":           "#1e1e2e",   # main window background
            "card":         "#2a2a3c",   # card background
            "card_hover":   "#35354d",   # card hover
            "button_bg":    "#2a2a3c",   # generic button background
            "button_hover": "#35354d",
            "button_fg":    "#f5f5f5",
            "fg":           "#f5f5f5",   # primary text
            "muted":        "#a0a0b0",   # secondary text
            "subtle":       "#6a6a7a",   # tertiary text
            "canvas_bg":    "#12121c",   # canvas games background
            "accent_x":     "#7aa2f7",   # X / left paddle / snake head
            "accent_o":     "#f7768e",   # O / right paddle / food
            "snake_body":   "#9ece6a",
            "card_up":      "#3a3a52",   # memory: flipped card
            "divider":      "#2a2a3c",   # pong centre line
            "ball":         "#f5f5f5",

            # Chess-specific
            "piece_white":  "#ffffff",   # interior of white pieces
            "piece_black":  "#000000",   # interior of black pieces
            "board_light":  "#ececec",   # light square
            "board_dark":   "#1c1c1c",   # dark square
        }

    # ------------------------------------------------------------- convenience
    def font(self, role, weight="normal"):
        size = self.font_sizes.get(role, 10)
        if weight == "normal":
            return (self.font_family, size)
        return (self.font_family, size, weight)

    def color(self, role):
        return self.colors.get(role, "#ff00ff")


# The single shared instance everyone imports.
theme = Theme()