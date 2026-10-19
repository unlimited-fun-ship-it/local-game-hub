"""Zobrist hashing keys.

The keys come from a *seeded* generator, so the same position always gets the
same hash - across restarts as well - which lets saved games store hashes for
repetition detection.
"""

import random

_rng = random.Random(0xC4E55_2026)

# Indexed [piece + 6][square]; piece runs -6..6 so the table has 13 rows
# (row 6, the empty square, is never used).
ZOBRIST_PIECES = [[_rng.getrandbits(64) for _ in range(64)] for _ in range(13)]
ZOBRIST_CASTLE = [_rng.getrandbits(64) for _ in range(16)]
ZOBRIST_EP = [_rng.getrandbits(64) for _ in range(8)]
ZOBRIST_TURN = _rng.getrandbits(64)


def compute_hash(board, turn, castling, ep_square):
    """Hash a position from scratch (apply_move updates it incrementally)."""
    h = 0
    for sq, p in enumerate(board):
        if p:
            h ^= ZOBRIST_PIECES[p + 6][sq]
    h ^= ZOBRIST_CASTLE[castling]
    if ep_square:
        h ^= ZOBRIST_EP[ep_square[1]]
    if turn == "b":
        h ^= ZOBRIST_TURN
    return h
