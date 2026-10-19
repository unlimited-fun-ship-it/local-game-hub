"""Game-ending rules (checkmate, stalemate and the automatic draws)."""

from .evaluation import is_insufficient_material
from .movegen import gen_legal_moves, king_attacked


def get_game_result(state, position_hashes=()):
    """Return a result message if the game is over, otherwise None.

    `position_hashes` holds the hash of every position reached in the game
    (including the current one) and is used for threefold repetition.
    """
    if not gen_legal_moves(state):
        if king_attacked(state.board, state.turn == "w"):
            return f"Checkmate \u2014 {'Black' if state.turn == 'w' else 'White'} wins!"
        return "Stalemate \u2014 draw."
    if is_insufficient_material(state.board):
        return "Draw \u2014 insufficient material."
    if state.halfmove >= 100:
        return "Draw \u2014 fifty-move rule."
    if list(position_hashes).count(state.hash) >= 3:
        return "Draw \u2014 threefold repetition."
    return None
