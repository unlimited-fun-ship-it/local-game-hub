"""Static evaluation: PeSTO tapered piece-square tables plus a few extras."""

from .constants import PAWN, KNIGHT, BISHOP, ROOK, QUEEN, KING
from .pst import PST_MG, PST_EG

# PeSTO's tuned piece values (index = piece type, 0 unused).
MG_VALUE = [0, 82, 337, 365, 477, 1025, 0]
EG_VALUE = [0, 94, 281, 297, 512, 936, 0]
PHASE_WEIGHT = [0, 0, 1, 1, 2, 4, 0]     # knight/bishop 1, rook 2, queen 4 -> 24 total

BISHOP_PAIR_MG, BISHOP_PAIR_EG = 30, 45
TEMPO = 10

# Combined "piece value + square bonus" tables, signed by colour, indexed
# [piece + 6][square].  Black uses the vertically mirrored square (sq ^ 56).
_MG = [[0] * 64 for _ in range(13)]
_EG = [[0] * 64 for _ in range(13)]
_PHASE = [0] * 13
for _p in range(1, 7):
    _PHASE[_p + 6] = _PHASE[-_p + 6] = PHASE_WEIGHT[_p]
    for _sq in range(64):
        _MG[_p + 6][_sq] = MG_VALUE[_p] + PST_MG[_p][_sq]
        _EG[_p + 6][_sq] = EG_VALUE[_p] + PST_EG[_p][_sq]
        _MG[-_p + 6][_sq] = -(MG_VALUE[_p] + PST_MG[_p][_sq ^ 56])
        _EG[-_p + 6][_sq] = -(EG_VALUE[_p] + PST_EG[_p][_sq ^ 56])


def is_insufficient_material(board):
    """K vs K, or K + a single minor piece vs K (no side can ever mate)."""
    minors = 0
    for p in board:
        if p:
            k = p if p > 0 else -p
            if k == KNIGHT or k == BISHOP:
                minors += 1
                if minors > 1:
                    return False
            elif k != KING:
                return False                  # pawn, rook or queen on the board
    return True


def evaluate(state):
    """Score in centipawns from the point of view of the side to move."""
    board = state.board
    mg = eg = phase = 0
    cnt = [0] * 13
    for sq, p in enumerate(board):
        if p:
            mg += _MG[p + 6][sq]
            eg += _EG[p + 6][sq]
            phase += _PHASE[p + 6]
            cnt[p + 6] += 1

    if (not cnt[PAWN + 6] and not cnt[-PAWN + 6] and not cnt[ROOK + 6] and not cnt[-ROOK + 6]
            and not cnt[QUEEN + 6] and not cnt[-QUEEN + 6]
            and cnt[KNIGHT + 6] + cnt[-KNIGHT + 6] + cnt[BISHOP + 6] + cnt[-BISHOP + 6] <= 1):
        return 0                              # dead draw

    if cnt[BISHOP + 6] >= 2:
        mg += BISHOP_PAIR_MG
        eg += BISHOP_PAIR_EG
    if cnt[-BISHOP + 6] >= 2:
        mg -= BISHOP_PAIR_MG
        eg -= BISHOP_PAIR_EG

    if phase > 24:
        phase = 24
    score = (mg * phase + eg * (24 - phase)) // 24

    # Mop-up: when one side is far ahead in a thin endgame, drive the losing
    # king to the edge and bring the winning king closer.  Without this the
    # engine can see a won ending but not how to make progress in it.
    if phase <= 10 and (eg >= 400 or eg <= -400):
        wk, bk = board.index(KING), board.index(-KING)
        loser = bk if eg > 0 else wk
        lr, lc = loser >> 3, loser & 7
        center_dist = max(3 - lr, lr - 4) + max(3 - lc, lc - 4)
        king_dist = abs((wk >> 3) - (bk >> 3)) + abs((wk & 7) - (bk & 7))
        bonus = 10 * center_dist + 4 * (14 - king_dist)
        score += bonus if eg > 0 else -bonus

    return (score if state.turn == "w" else -score) + TEMPO
