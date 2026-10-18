"""Centralized manager for AI memoization across all games."""

import json
import os
import shutil

_CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app_config.json")
_MEMO_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "memoization")

DEFAULT_CONFIG = {
    "memoization_enabled": True,
    "max_entries_per_game": 100_000,
    "game_overrides": {} # e.g., {"connect4": {"enabled": false, "max_entries": 1000}}
}

_config = {}

def _load():
    global _config
    if os.path.exists(_CONFIG_PATH):
        try:
            with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                # Merge with defaults to handle new keys
                _config = DEFAULT_CONFIG.copy()
                _config.update(data)
                return
        except Exception:
            pass
    _config = DEFAULT_CONFIG.copy()

def _save():
    try:
        with open(_CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(_config, f, indent=2)
    except Exception:
        pass

_load()

def is_enabled(game_id):
    """Check if memoization is enabled globally and for the specific game."""
    if not _config.get("memoization_enabled", True):
        return False
    override = _config.get("game_overrides", {}).get(game_id, {})
    return override.get("enabled", True)

def get_max_entries(game_id):
    """Get the maximum cache size for a specific game."""
    override = _config.get("game_overrides", {}).get(game_id, {})
    return override.get("max_entries", _config.get("max_entries_per_game", 100_000))

def set_global_enabled(enabled):
    _config["memoization_enabled"] = enabled
    _save()

def set_global_max_entries(max_entries):
    _config["max_entries_per_game"] = max_entries
    _save()

def set_game_override(game_id, enabled=None, max_entries=None):
    if game_id not in _config["game_overrides"]:
        _config["game_overrides"][game_id] = {}
    if enabled is not None:
        _config["game_overrides"][game_id]["enabled"] = enabled
    if max_entries is not None:
        _config["game_overrides"][game_id]["max_entries"] = max_entries
    _save()

def clear_game(game_id):
    """Delete the memoization folder for a specific game."""
    path = os.path.join(_MEMO_DIR, game_id)
    if os.path.exists(path):
        try:
            shutil.rmtree(path)
        except Exception:
            pass

def clear_all():
    """Delete the entire memoization folder."""
    if os.path.exists(_MEMO_DIR):
        try:
            shutil.rmtree(_MEMO_DIR)
        except Exception:
            pass

def get_disk_usage(game_id=None):
    """Returns the size of the memoization folder in bytes."""
    target = os.path.join(_MEMO_DIR, game_id) if game_id else _MEMO_DIR
    if not os.path.exists(target):
        return 0
    total = 0
    for dirpath, _, filenames in os.walk(target):
        for f in filenames:
            fp = os.path.join(dirpath, f)
            total += os.path.getsize(fp)
    return total