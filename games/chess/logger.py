"""Debug logging - one log file per launch, written under the save directory."""

import os
from datetime import datetime

import save_manager

from .constants import GAME_ID

LOG_FILE = os.path.join(
    save_manager.SAVE_DIR, GAME_ID,
    f"debug_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log",
)


def log_debug(msg):
    try:
        os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")
    except OSError:
        pass        # logging must never be able to crash the game or a search
