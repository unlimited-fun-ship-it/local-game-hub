"""
Central theme configuration for the Mini Game Hub.

Edit the values below to change the look of the whole project, or use
the "Settings" button in the launcher to change them at runtime.

Every game reads from the shared `theme` object, so a change here
(or via the Settings dialog) is picked up everywhere.
"""

import json
import os

# Settings file lives next to this module, so it resolves reliably
# regardless of the directory the hub is launched from.
CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "settings.json")



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

    # ----------------------------------------------------- persistence
    def to_dict(self):
        """Serialisable snapshot of the current theme."""
        return {
            "font_family": self.font_family,
            "font_sizes": dict(self.font_sizes),
            "colors": dict(self.colors),
        }

    def from_dict(self, data):
        """Apply a snapshot. Unknown keys are ignored, wrong types are
        skipped — so a settings file written by an older (or newer) build
        degrades gracefully instead of crashing."""
        if isinstance(data.get("font_family"), str):
            self.font_family = data["font_family"]

        sizes = data.get("font_sizes")
        if isinstance(sizes, dict):
            for k, v in sizes.items():
                if k in self.font_sizes and isinstance(v, int) and v > 0:
                    self.font_sizes[k] = v

        colors = data.get("colors")
        if isinstance(colors, dict):
            for k, v in colors.items():
                if k in self.colors and isinstance(v, str):
                    self.colors[k] = v

    def save(self, path=None):
        """Write current settings. Returns True on success."""
        path = path or CONFIG_PATH
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self.to_dict(), f, indent=2)
            return True
        except OSError:
            # Read-only filesystem, permissions issue, etc.
            # Silently fall back — the app keeps working with in-memory theme.
            return False

    def load(self, path=None):
        """Read saved settings if present. Returns True if a file was found
        and parsed. Never raises — a corrupt/missing file means defaults."""
        path = path or CONFIG_PATH
        if not os.path.exists(path):
            return False
        try:
            with open(path, "r", encoding="utf-8") as f:
                self.from_dict(json.load(f))
            return True
        except (OSError, json.JSONDecodeError):
            return False

# The single shared instance everyone imports.
theme = Theme()

# Apply the user's saved settings on startup. If there is no settings file
# yet (first run) or it can't be read, `theme` keeps its hardcoded defaults.
theme.load()