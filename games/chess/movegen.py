"""Attack detection and move generation.

Square tables (knight jumps, king steps, slider rays, pawn attackers) are
computed once at import time so the hot loops are plain list lookups.
"""

from .board import Move
from .constants import (
    EMPTY, PAWN, KNIGHT, BISHOP, ROOK, QUEEN, KING,
    CASTLE_WK, CASTLE_WQ, CASTLE_BK, CASTLE_BQ,
)

# ------------------------------------------------------------------ precomputed tables
_KNIGHT_DELTAS = [(-2, -1), (-2, 1), (-1, -2), (-1, 2), (1, -2), (1, 2), (2, -1), (2, 1)]
_KING_DELTAS = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]
_BISHOP_DIRS = [(-1, -1), (-1, 1), (1, -1), (1, 1)]
_ROOK_DIRS = [(-1, 0), (1, 0), (0, -1), (0, 1)]

ROW = [sq >> 3 for sq in range(64)]
COL = [sq & 7 for sq in range(64)]


def _steps(sq, deltas):
    r, c = ROW[sq], COL[sq]
    return [(r + dr) * 8 + (c + dc) for dr, dc in deltas
            if 0 <= r + dr < 8 and 0 <= c + dc < 8]


def _rays(sq, dirs):
    r, c = ROW[sq], COL[sq]
    rays = []
    for dr, dc in dirs:
        ray, rr, cc = [], r + dr, c + dc
        while 0 <= rr < 8 and 0 <= cc < 8:
            ray.append(rr * 8 + cc)
            rr += dr
            cc += dc
        if ray:
            rays.append(ray)
    return rays


KNIGHT_TARGETS = [_steps(sq, _KNIGHT_DELTAS) for sq in range(64)]
KING_TARGETS = [_steps(sq, _KING_DELTAS) for sq in range(64)]
BISHOP_RAYS = [_rays(sq, _BISHOP_DIRS) for sq in range(64)]
ROOK_RAYS = [_rays(sq, _ROOK_DIRS) for sq in range(64)]
QUEEN_RAYS = [BISHOP_RAYS[sq] + ROOK_RAYS[sq] for sq in range(64)]
# Squares from which a white / black pawn would attack `sq`.
WPAWN_ATTACKERS = [[(ROW[sq] + 1) * 8 + COL[sq] + dc for dc in (-1, 1)
                    if ROW[sq] + 1 < 8 and 0 <= COL[sq] + dc < 8] for sq in range(64)]
BPAWN_ATTACKERS = [[(ROW[sq] - 1) * 8 + COL[sq] + dc for dc in (-1, 1)
                    if ROW[sq] - 1 >= 0 and 0 <= COL[sq] + dc < 8] for sq in range(64)]

_PROMOTIONS = (QUEEN, ROOK, BISHOP, KNIGHT)


# ------------------------------------------------------------------ attacks / check
def is_attacked(board, sq, by_white):
    """Is square `sq` attacked by any piece of the given colour?"""
    if by_white:
        for s in WPAWN_ATTACKERS[sq]:
            if board[s] == PAWN: return True
        for s in KNIGHT_TARGETS[sq]:
            if board[s] == KNIGHT: return True
        for s in KING_TARGETS[sq]:
            if board[s] == KING: return True
        for ray in BISHOP_RAYS[sq]:
            for s in ray:
                p = board[s]
                if p:
                    if p == BISHOP or p == QUEEN: return True
                    break
        for ray in ROOK_RAYS[sq]:
            for s in ray:
                p = board[s]
                if p:
                    if p == ROOK or p == QUEEN: return True
                    break
    else:
        for s in BPAWN_ATTACKERS[sq]:
            if board[s] == -PAWN: return True
        for s in KNIGHT_TARGETS[sq]:
            if board[s] == -KNIGHT: return True
        for s in KING_TARGETS[sq]:
            if board[s] == -KING: return True
        for ray in BISHOP_RAYS[sq]:
            for s in ray:
                p = board[s]
                if p:
                    if p == -BISHOP or p == -QUEEN: return True
                    break
        for ray in ROOK_RAYS[sq]:
            for s in ray:
                p = board[s]
                if p:
                    if p == -ROOK or p == -QUEEN: return True
                    break
    return False


def king_attacked(board, white):
    """Is the king of the given colour currently attacked?"""
    try:
        ksq = board.index(KING if white else -KING)
    except ValueError:
        return False
    return is_attacked(board, ksq, not white)


def find_king(board, color):
    target = KING if color == "w" else -KING
    try:
        return divmod(board.index(target), 8)
    except ValueError:
        return None


def in_check(state, color):
    return king_attacked(state.board, color == "w")


# ------------------------------------------------------------------ generation
def _gen_castling(board, castling, white, out):
    if white:
        if board[60] != KING:
            return
        if (castling & CASTLE_WK and board[61] == EMPTY and board[62] == EMPTY and board[63] == ROOK
                and not is_attacked(board, 60, False) and not is_attacked(board, 61, False)
                and not is_attacked(board, 62, False)):
            out.append(Move(7, 4, 7, 6, None))
        if (castling & CASTLE_WQ and board[59] == EMPTY and board[58] == EMPTY and board[57] == EMPTY
                and board[56] == ROOK
                and not is_attacked(board, 60, False) and not is_attacked(board, 59, False)
                and not is_attacked(board, 58, False)):
            out.append(Move(7, 4, 7, 2, None))
    else:
        if board[4] != -KING:
            return
        if (castling & CASTLE_BK and board[5] == EMPTY and board[6] == EMPTY and board[7] == -ROOK
                and not is_attacked(board, 4, True) and not is_attacked(board, 5, True)
                and not is_attacked(board, 6, True)):
            out.append(Move(0, 4, 0, 6, None))
        if (castling & CASTLE_BQ and board[3] == EMPTY and board[2] == EMPTY and board[1] == EMPTY
                and board[0] == -ROOK
                and not is_attacked(board, 4, True) and not is_attacked(board, 3, True)
                and not is_attacked(board, 2, True)):
            out.append(Move(0, 4, 0, 2, None))


def gen_pseudo_moves(state, captures_only=False):
    """Pseudo-legal moves (they may leave the own king in check).

    With captures_only=True only captures, en passant and queen promotions are
    produced - that is what quiescence search needs.
    """
    board = state.board
    white = state.turn == "w"
    ep = state.ep_square
    ep_sq = ep[0] * 8 + ep[1] if ep else -1
    out = []
    add = out.append

    for sq in range(64):
        p = board[sq]
        if not p or (p > 0) != white:
            continue
        r, c = ROW[sq], COL[sq]
        kind = p if white else -p

        if kind == PAWN:
            nr = r - 1 if white else r + 1
            promo_row = 0 if white else 7
            fwd = nr * 8 + c
            if board[fwd] == EMPTY:
                if nr == promo_row:
                    if captures_only:
                        add(Move(r, c, nr, c, QUEEN))
                    else:
                        for pr in _PROMOTIONS:
                            add(Move(r, c, nr, c, pr))
                elif not captures_only:
                    add(Move(r, c, nr, c, None))
                    if r == (6 if white else 1):
                        nr2 = nr - 1 if white else nr + 1
                        if board[nr2 * 8 + c] == EMPTY:
                            add(Move(r, c, nr2, c, None))
            for nc in (c - 1, c + 1):
                if 0 <= nc < 8:
                    tsq = nr * 8 + nc
                    t = board[tsq]
                    if t:
                        if (t > 0) != white:
                            if nr == promo_row:
                                if captures_only:
                                    add(Move(r, c, nr, nc, QUEEN))
                                else:
                                    for pr in _PROMOTIONS:
                                        add(Move(r, c, nr, nc, pr))
                            else:
                                add(Move(r, c, nr, nc, None))
                    elif tsq == ep_sq:
                        add(Move(r, c, nr, nc, None))

        elif kind == KNIGHT or kind == KING:
            for t in (KNIGHT_TARGETS[sq] if kind == KNIGHT else KING_TARGETS[sq]):
                tp = board[t]
                if tp == EMPTY:
                    if not captures_only:
                        add(Move(r, c, ROW[t], COL[t], None))
                elif (tp > 0) != white:
                    add(Move(r, c, ROW[t], COL[t], None))
            if kind == KING and not captures_only:
                _gen_castling(board, state.castling, white, out)

        else:  # bishop, rook, queen
            rays = BISHOP_RAYS[sq] if kind == BISHOP else ROOK_RAYS[sq] if kind == ROOK else QUEEN_RAYS[sq]
            for ray in rays:
                for t in ray:
                    tp = board[t]
                    if tp == EMPTY:
                        if not captures_only:
                            add(Move(r, c, ROW[t], COL[t], None))
                    else:
                        if (tp > 0) != white:
                            add(Move(r, c, ROW[t], COL[t], None))
                        break
    return out


def is_legal_move(state, move):
    """Would `move` leave the mover's own king safe?"""
    board = state.board
    fr, fc, tr, tc, _ = move
    src, dst = fr * 8 + fc, tr * 8 + tc
    piece = board[src]
    b = board.copy()
    if abs(piece) == PAWN and fc != tc and b[dst] == EMPTY:
        b[fr * 8 + tc] = EMPTY                      # en-passant victim
    b[dst] = piece
    b[src] = EMPTY
    white = piece > 0
    if abs(piece) == KING:
        ksq = dst
    else:
        ksq = b.index(KING if white else -KING)
    return not is_attacked(b, ksq, not white)


def gen_legal_moves(state):
    return [m for m in gen_pseudo_moves(state) if is_legal_move(state, m)]


def validate_position(state):
    """Raise ValueError for positions that can't arise in a real game."""
    # The side that is NOT to move must not be in check (it could be captured).
    if king_attacked(state.board, state.turn != "w"):
        raise ValueError("the side not to move is in check - illegal position")
