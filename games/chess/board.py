"""Board state, FEN import/export and move application."""

from collections import namedtuple

from .constants import (
    EMPTY, PAWN, KING, ROOK, FILES, PIECE_TO_CHAR, CHAR_TO_PIECE,
    CASTLE_WK, CASTLE_WQ, CASTLE_BK, CASTLE_BQ,
)
from .zobrist import (
    ZOBRIST_PIECES, ZOBRIST_CASTLE, ZOBRIST_EP, ZOBRIST_TURN, compute_hash,
)

# A move is (from_row, from_col, to_row, to_col, promotion_piece_type_or_None).
Move = namedtuple("Move", "fr fc tr tc promo")

START_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"

# Moving from or to one of these squares removes the matching castling rights.
CASTLE_MASK = [15] * 64
CASTLE_MASK[60] = 15 & ~(CASTLE_WK | CASTLE_WQ)   # e1
CASTLE_MASK[63] = 15 & ~CASTLE_WK                  # h1
CASTLE_MASK[56] = 15 & ~CASTLE_WQ                  # a1
CASTLE_MASK[4] = 15 & ~(CASTLE_BK | CASTLE_BQ)     # e8
CASTLE_MASK[7] = 15 & ~CASTLE_BK                   # h8
CASTLE_MASK[0] = 15 & ~CASTLE_BQ                   # a8


class ChessState:
    """An immutable-by-convention position.  apply_move() returns a new one."""
    __slots__ = ("board", "turn", "castling", "ep_square", "halfmove", "fullmove", "hash")

    def __init__(self, board, turn="w", castling=15, ep_square=None,
                 halfmove=0, fullmove=1, hash_val=None):
        self.board = board
        self.turn = turn                # "w" or "b"
        self.castling = castling        # 4-bit mask, see CASTLE_* constants
        self.ep_square = ep_square      # (row, col) of the en-passant target, or None
        self.halfmove = halfmove
        self.fullmove = fullmove
        self.hash = compute_hash(board, turn, castling, ep_square) if hash_val is None else hash_val


# ------------------------------------------------------------------ castling helpers
def castling_to_dict(mask):
    """Mask -> {"K": bool, ...} (the format used in save files)."""
    return {"K": bool(mask & CASTLE_WK), "Q": bool(mask & CASTLE_WQ),
            "k": bool(mask & CASTLE_BK), "q": bool(mask & CASTLE_BQ)}


def castling_from_dict(d):
    """Accepts a save-file dict (or an int mask) and returns a mask."""
    if isinstance(d, int):
        return d
    return ((CASTLE_WK if d.get("K") else 0) | (CASTLE_WQ if d.get("Q") else 0)
            | (CASTLE_BK if d.get("k") else 0) | (CASTLE_BQ if d.get("q") else 0))


# ------------------------------------------------------------------ construction / FEN
def initial_state():
    return fen_to_state(START_FEN)


def board_to_fen(state):
    rows = []
    for r in range(8):
        row, empty = "", 0
        for c in range(8):
            p = state.board[r * 8 + c]
            if p == EMPTY:
                empty += 1
            else:
                if empty:
                    row += str(empty)
                    empty = 0
                row += PIECE_TO_CHAR[p]
        if empty:
            row += str(empty)
        rows.append(row)
    cm = state.castling
    castling = (("K" if cm & CASTLE_WK else "") + ("Q" if cm & CASTLE_WQ else "")
                + ("k" if cm & CASTLE_BK else "") + ("q" if cm & CASTLE_BQ else "")) or "-"
    ep = f"{FILES[state.ep_square[1]]}{8 - state.ep_square[0]}" if state.ep_square else "-"
    return f"{'/'.join(rows)} {state.turn} {castling} {ep} {state.halfmove} {state.fullmove}"


def fen_to_state(fen):
    """Parse a FEN string.  Raises ValueError for anything malformed."""
    parts = fen.split()
    if not parts:
        raise ValueError("empty FEN")
    ranks = parts[0].split("/")
    if len(ranks) != 8:
        raise ValueError("board part must have 8 ranks")

    board = []
    for rank in ranks:
        count = 0
        for ch in rank:
            if ch.isdigit():
                n = int(ch)
                if not 1 <= n <= 8:
                    raise ValueError(f"bad empty-square count '{ch}'")
                board.extend([EMPTY] * n)
                count += n
            elif ch in CHAR_TO_PIECE and ch != ".":
                board.append(CHAR_TO_PIECE[ch])
                count += 1
            else:
                raise ValueError(f"unknown piece '{ch}'")
        if count != 8:
            raise ValueError("every rank must describe exactly 8 squares")

    if board.count(KING) != 1 or board.count(-KING) != 1:
        raise ValueError("each side needs exactly one king")
    if any(abs(board[i]) == PAWN for i in (*range(0, 8), *range(56, 64))):
        raise ValueError("pawns cannot stand on the first or last rank")

    turn = parts[1] if len(parts) > 1 else "w"
    if turn not in ("w", "b"):
        raise ValueError("side to move must be 'w' or 'b'")

    # Only keep castling rights that the piece placement actually allows.
    cpart = parts[2] if len(parts) > 2 else "-"
    castling = 0
    if "K" in cpart and board[60] == KING and board[63] == ROOK: castling |= CASTLE_WK
    if "Q" in cpart and board[60] == KING and board[56] == ROOK: castling |= CASTLE_WQ
    if "k" in cpart and board[4] == -KING and board[7] == -ROOK: castling |= CASTLE_BK
    if "q" in cpart and board[4] == -KING and board[0] == -ROOK: castling |= CASTLE_BQ

    # Only keep an en-passant square if a capture is geometrically possible.
    ep_square = None
    epart = parts[3] if len(parts) > 3 else "-"
    if epart != "-":
        if len(epart) != 2 or epart[0] not in FILES or epart[1] not in "36":
            raise ValueError("bad en-passant square")
        r, c = 8 - int(epart[1]), FILES.index(epart[0])
        pawn_row, pawn = (r + 1, -PAWN) if turn == "w" else (r - 1, PAWN)
        wanted_row = 2 if turn == "w" else 5
        if r == wanted_row and board[pawn_row * 8 + c] == pawn and board[r * 8 + c] == EMPTY:
            ep_square = (r, c)

    try:
        halfmove = int(parts[4]) if len(parts) > 4 else 0
        fullmove = int(parts[5]) if len(parts) > 5 else 1
    except ValueError:
        raise ValueError("move counters must be numbers")

    return ChessState(board, turn, castling, ep_square, halfmove, fullmove)


# ------------------------------------------------------------------ making moves
def apply_move(state, move):
    """Return the position after `move`.  The move must be pseudo-legal."""
    fr, fc, tr, tc, promo = move
    src, dst = fr * 8 + fc, tr * 8 + tc
    board = state.board.copy()
    piece, captured = board[src], board[dst]
    white = piece > 0
    kind = piece if white else -piece

    h = state.hash ^ ZOBRIST_PIECES[piece + 6][src]
    if captured:
        h ^= ZOBRIST_PIECES[captured + 6][dst]

    # En passant: a pawn moving diagonally onto an empty square.
    if kind == PAWN and fc != tc and not captured:
        cap_sq = fr * 8 + tc
        captured = board[cap_sq]
        board[cap_sq] = EMPTY
        h ^= ZOBRIST_PIECES[captured + 6][cap_sq]

    placed = (promo if white else -promo) if promo else piece
    board[src] = EMPTY
    board[dst] = placed
    h ^= ZOBRIST_PIECES[placed + 6][dst]

    # Castling: also move the rook.
    if kind == KING and abs(tc - fc) == 2:
        row = tr * 8
        rook_from, rook_to = (row + 7, row + 5) if tc > fc else (row, row + 3)
        rook = board[rook_from]
        board[rook_from] = EMPTY
        board[rook_to] = rook
        h ^= ZOBRIST_PIECES[rook + 6][rook_from] ^ ZOBRIST_PIECES[rook + 6][rook_to]

    old_c = state.castling
    new_c = old_c & CASTLE_MASK[src] & CASTLE_MASK[dst]
    if new_c != old_c:
        h ^= ZOBRIST_CASTLE[old_c] ^ ZOBRIST_CASTLE[new_c]

    if state.ep_square:
        h ^= ZOBRIST_EP[state.ep_square[1]]
    new_ep = None
    if kind == PAWN and abs(tr - fr) == 2:
        new_ep = ((tr + fr) // 2, fc)
        h ^= ZOBRIST_EP[fc]

    black_moved = not white
    return ChessState(
        board, "w" if black_moved else "b", new_c, new_ep,
        0 if (kind == PAWN or captured) else state.halfmove + 1,
        state.fullmove + (1 if black_moved else 0),
        h ^ ZOBRIST_TURN,
    )


def make_null_move(state):
    """Pass the turn without moving (used by null-move pruning in search)."""
    h = state.hash ^ ZOBRIST_TURN
    if state.ep_square:
        h ^= ZOBRIST_EP[state.ep_square[1]]
    return ChessState(state.board, "b" if state.turn == "w" else "w", state.castling,
                      None, state.halfmove + 1, state.fullmove, h)
