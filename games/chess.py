"""Chess launcher - loads the game from the games/chess/ folder.

The folder is exposed as a private package (so the modules inside can use
relative imports) without needing an __init__.py.  An __init__.py would turn
games/chess/ into a regular package, which Python prefers over this chess.py
and would shadow it.
"""

import importlib
import os
import sys
import types

_PKG = "chess_game_pkg"
_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "chess")

if _PKG not in sys.modules:
    _pkg = types.ModuleType(_PKG)
    _pkg.__path__ = [_DIR]
    _pkg.__package__ = _PKG
    sys.modules[_PKG] = _pkg

_game = importlib.import_module(f"{_PKG}.game")

# Re-export so the game menu can keep calling chess.run(master)
run = _game.run
Chess = _game.Chess
