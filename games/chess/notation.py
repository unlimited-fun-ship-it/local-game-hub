"""Move notation: UCI ("e2e4") and SAN ("Nxf3+")."""

from .board import apply_move
from .constants import EMPTY, PAWN, KING, FILES, PIECE_TO_CHAR
from .movegen import gen_legal_moves, king_attacked


def move_uci(m):
    s = f"{FILES[m.fc]}{8 - m.fr}{FILES[m.tc]}{8 - m.tr}"
    if m.promo:
        s += PIECE_TO_CHAR[m.promo].lower()
    return s


def format_move(state, move):
    """Standard algebraic notation for `move`, played from `state`."""
    board = state.board
    piece = board[move.fr * 8 + move.fc]
    kind = abs(piece)
    target = board[move.tr * 8 + move.tc]
    is_capture = target != EMPTY or (kind == PAWN and move.fc != move.tc)
    after = apply_move(state, move)

    if kind == KING and abs(move.tc - move.fc) == 2:
        s = "O-O" if move.tc > move.fc else "O-O-O"
    else:
        s = ""
        if kind != PAWN:
            s += PIECE_TO_CHAR[kind]
            rivals = [m for m in gen_legal_moves(state)
                      if (m.tr, m.tc) == (move.tr, move.tc) and (m.fr, m.fc) != (move.fr, move.fc)
                      and board[m.fr * 8 + m.fc] == piece]
            if rivals:
                if all(m.fc != move.fc for m in rivals):
                    s += FILES[move.fc]
                elif all(m.fr != move.fr for m in rivals):
                    s += str(8 - move.fr)
                else:
                    s += FILES[move.fc] + str(8 - move.fr)
        elif is_capture:
            s += FILES[move.fc]
        if is_capture:
            s += "x"
        s += f"{FILES[move.tc]}{8 - move.tr}"
        if move.promo:
            s += "=" + PIECE_TO_CHAR[move.promo]

    if king_attacked(after.board, after.turn == "w"):
        s += "#" if not gen_legal_moves(after) else "+"
    return s
