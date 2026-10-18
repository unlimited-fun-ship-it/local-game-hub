"""Chess - A complete, full-rules chess engine in Python.

Features:
  * 1D Integer Board Representation with Zobrist Hashing.
  * PeSTO Tapered Evaluation (Midgame / Endgame).
  * Negamax with PVS (Principal Variation Search) & Alpha-Beta.
  * Iterative Deepening with Aspiration Windows.
  * Transposition Table (TT) with Exact/Lower/Upper bounds.
  * Quiescence Search (captures only).
  * Null Move Pruning.
  * Late Move Reductions (LMR).
  * Killer Moves & History Heuristic for move ordering.
  * Toggleable Algebraic Coordinates UI.
  * FEN import/export.
  * Play as White or Black.
  * Extensive debug logging.
"""

import os
import random
import threading
import time
from collections import namedtuple
from datetime import datetime
import traceback

import tkinter as tk
from tkinter import messagebox
import save_manager
import memoization_manager as memo
from theme import theme

GAME_ID = "chess"
MATE_SCORE = 1_000_000
MAX_DEPTH = 6

# Create a unique log file for every launch
LOG_FILE = os.path.join(save_manager.SAVE_DIR, GAME_ID, f"debug_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")

def log_debug(msg):
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")

# ============================================================ pieces
EMPTY = 0
PAWN, KNIGHT, BISHOP, ROOK, QUEEN, KING = 1, 2, 3, 4, 5, 6

PIECE_TO_CHAR = {
    0: ".", 1: "P", 2: "N", 3: "B", 4: "R", 5: "Q", 6: "K",
    -1: "p", -2: "n", -3: "b", -4: "r", -5: "q", -6: "k"
}
CHAR_TO_PIECE = {v: k for k, v in PIECE_TO_CHAR.items()}
UNICODE = {
    1: "\u2659", 2: "\u2658", 3: "\u2657", 4: "\u2656", 5: "\u2655", 6: "\u2654",
    -1: "\u265F", -2: "\u265E", -3: "\u265D", -4: "\u265C", -5: "\u265B", -6: "\u265A"
}
SOLID_UNICODE = {
    -1: "\u265F", -2: "\u265E", -3: "\u265D", -4: "\u265C", -5: "\u265B", -6: "\u265A"
}

PIECE_VALUES = [0, 100, 320, 330, 500, 900, 20000]
KNIGHT_DELTAS = [(-2, -1), (-2, 1), (-1, -2), (-1, 2), (1, -2), (1, 2), (2, -1), (2, 1)]
KING_DELTAS = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]
BISHOP_DIRS = [(-1, -1), (-1, 1), (1, -1), (1, 1)]
ROOK_DIRS = [(-1, 0), (1, 0), (0, -1), (0, 1)]
FILES = "abcdefgh"

# ============================================================ PeSTO Evaluation
MG_PAWN_TABLE = [
     0,   0,   0,   0,   0,   0,   0,   0,
    98, 134,  61,  95,  68, 126,  34, -11,
    -6,   7,  26,  31,  65,  56,  25, -20,
   -14,  13,   6,  21,  23,  12,  17, -23,
   -27,  -2,  -5,  12,  17,   6,  10, -25,
   -26,  -4,  -4, -10,   3,   3,  33, -12,
   -35,  -1, -20, -23, -15,  24,  38, -22,
     0,   0,   0,   0,   0,   0,   0,   0
]
EG_PAWN_TABLE = [
     0,   0,   0,   0,   0,   0,   0,   0,
   178, 173, 158, 134, 147, 132, 165, 187,
    94, 100,  85,  67,  56,  53,  82,  84,
    32,  24,  13,   5,  -2,   4,  17,  17,
    13,   9,  -3,  -7,  -7,  -8,   3,  -1,
     4,   7,  -6,   1,   0,  -5,  -1,  -8,
    13,   8,   8,  10,  13,   0,   2,  -7,
     0,   0,   0,   0,   0,   0,   0,   0
]
MG_KNIGHT_TABLE = [
  -167, -89, -34, -49,  61, -97, -15, -107,
   -73, -41,  72,  36,  23,  62,   7,  -17,
   -47,  60,  37,  65,  84, 129,  73,   44,
    -9,  17,  19,  53,  37,  69,  18,   22,
   -13,   4,  16,  13,  28,  19,  21,   -8,
   -23,  -9,  12,  10,  19,  17,  25,  -16,
   -29, -53, -12,  -3,  -1,  18, -14,  -19,
  -105, -21, -58, -33, -17, -28, -19,  -23
]
EG_KNIGHT_TABLE = [
   -58, -38, -13, -28, -31, -27, -63, -99,
   -25,  -8, -25,  -2,  -9, -25, -24, -52,
   -24, -20,  10,   9,  -1,  -9, -19, -41,
   -17,   3,  22,  22,  22,  11,   8, -18,
   -18,  -6,  16,  25,  16,  17,   4, -18,
   -23,  -3,  -1,  15,  10,  -3, -20, -22,
   -42, -20, -10,  -5,  -2, -20, -23, -44,
   -29, -51, -23, -15, -22, -18, -50, -64
]
MG_BISHOP_TABLE = [
   -29,   4, -82, -37, -25, -42,   7,  -8,
   -26,  16, -18, -13,  30,  59,  18, -47,
   -16,  37,  43,  40,  35,  50,  37,  -2,
    -4,   5,  19,  50,  37,  37,   7,  -2,
    -6,  13,  13,  26,  34,  12,  10,   4,
     0,  15,  15,  15,  14,  27,  18,  10,
     4,  15,  16,   0,   7,  21,  33,   1,
   -33,  -3, -14, -21, -13, -12, -39, -21
]
EG_BISHOP_TABLE = [
   -14, -21, -11,  -8,  -7,  -9, -17, -24,
    -8,  -4,   7, -12,  -3, -13,  -4, -14,
     2,  -8,   0,  -1,  -2,   6,   0,   4,
    -3,   9,  12,   9,  14,  10,   3,   2,
    -6,   3,  13,  19,   7,  10,  -3,  -9,
   -12,  -3,   8,  10,  13,   3,  -7, -15,
   -14, -18,  -7,  -1,   4,  -9, -15, -27,
   -23,  -9, -23, -26, -16, -11, -25, -39
]
MG_ROOK_TABLE = [
    32,  42,  32,  51,  63,   9,  31,  43,
    27,  32,  58,  62,  80,  67,  26,  44,
    -5,  19,  26,  36,  17,  45,  61,  16,
   -24, -11,   7,  26,  24,  35,  -8, -20,
   -36, -26, -12,  -1,   9,  -7,   6, -23,
   -45, -25, -16, -17,   3,   0,  -5, -33,
   -44, -16, -20,  -9,  -1,  11,  -6, -71,
   -56, -42, -30, -31, -32, -46, -19, -13
]
EG_ROOK_TABLE = [
    13,  10,  18,  15,  12,  12,   8,   5,
    11,  13,  13,  11,  -3,   3,   8,   3,
     7,   7,   7,   5,   4,  -3,  -5,  -3,
     4,   3,  13,   1,   2,   1,  -1,   2,
     3,   5,   8,   4,  -5,  -6,  -8, -11,
    -4,   0,  -5,  -1,  -7, -12,  -8, -16,
    -6,  -6,   0,   2,  -9,  -9, -11,  -3,
    -9,  -9,   3,   2,  -1,  -5, -13,   4
]
MG_QUEEN_TABLE = [
   -28,   0,  29,  12,  59,  44,  43,  45,
   -24, -39,  -5,   1, -16,  57,  28,  54,
   -13, -17,   7,   8,  29,  56,  47,  57,
   -27, -27, -16, -16,  -1,  17,  -2,   1,
    -9, -26,  -9, -10,  -2,  -4,   3,  -3,
   -14,   2, -11,  -2,  -5,   2,  14,   2,
   -35,  -8,  11,   2,   8,  15,  -3,   1,
    -1, -18,  -9,  10, -15, -25, -31, -50
]
EG_QUEEN_TABLE = [
    -9,  22,  22,  27,  27,  19,  10,  20,
   -17,  20,  32,  41,  58,  25,  30,   0,
   -20,   6,   9,  49,  47,  35,  19,   9,
     3,  22,  24,  45,  57,  40,  57,  36,
   -18,  28,  19,  47,  31,  34,  39,  23,
   -16, -27,  15,   6,   9,  17,  10,   5,
   -22, -23, -30, -16, -16, -23, -36, -32,
   -33, -44, -18, -34, -21, -16, -27, -39
]
MG_KING_TABLE = [
   -65,  23,  16, -15, -56, -34,   2,  13,
    29,  -1, -20,  -7,  -8,  -4, -38, -29,
    -9,  24,   2, -16, -20,   6,  22, -22,
   -17, -20, -12, -27, -30, -25, -14, -36,
   -49,  -1, -27, -39, -46, -44, -33, -51,
   -14, -14, -22, -46, -44, -30, -15, -27,
     1,   7,  -8, -64, -43, -16,   9,   8,
   -15, -63, -34, -14, -36, -50, -30, -13
]
EG_KING_TABLE = [
   -74, -35, -18, -18, -11,  15,   4, -17,
   -12,  17,  14,  17,  17,  38,  23,  11,
    10,  17,  23,  15,  20,  45,  44,  13,
    -8,  22,  24,  27,  26,  33,  26,   3,
   -18,  -4,  21,  24,  27,  23,   9, -11,
   -19,  -3,  11,  21,  23,  16,   7,  -9,
   -27, -11,   4,  13,  14,   4,  -5, -17,
   -53, -34, -21, -11, -28, -14, -24, -43
]

PST_MG = {
    PAWN: MG_PAWN_TABLE, KNIGHT: MG_KNIGHT_TABLE, BISHOP: MG_BISHOP_TABLE,
    ROOK: MG_ROOK_TABLE, QUEEN: MG_QUEEN_TABLE, KING: MG_KING_TABLE
}
PST_EG = {
    PAWN: EG_PAWN_TABLE, KNIGHT: EG_KNIGHT_TABLE, BISHOP: EG_BISHOP_TABLE,
    ROOK: EG_ROOK_TABLE, QUEEN: EG_QUEEN_TABLE, KING: EG_KING_TABLE
}

PHASE_VALUES = [0, 0, 1, 1, 2, 4, 0]

# ============================================================ Zobrist Hashing
ZOBRIST_PIECES = [[random.getrandbits(64) for _ in range(64)] for _ in range(13)]
ZOBRIST_CASTLE = [random.getrandbits(64) for _ in range(16)]
ZOBRIST_EP = [random.getrandbits(64) for _ in range(8)]
ZOBRIST_TURN = random.getrandbits(64)

def get_piece_idx(p):
    if p == EMPTY: return 0
    if p > 0: return p - 1
    return 6 - p

# ============================================================ TT & Search Globals
TT_EXACT, TT_LOWER, TT_UPPER = 0, 1, 2
class TTEntry:
    __slots__ = ("depth", "score", "flag", "move")
    def __init__(self, depth, score, flag, move):
        self.depth = depth
        self.score = score
        self.flag = flag
        self.move = move

_transposition_table = {}
_killers = [[None, None] for _ in range(64)]
_history = [[0]*64 for _ in range(64)]
_stop_search = False
_nodes_searched = 0

# ============================================================ engine
Move = namedtuple("Move", "fr fc tr tc promo")

def move_uci(m):
    s = f"{FILES[m.fc]}{8 - m.fr}{FILES[m.tc]}{8 - m.tr}"
    if m.promo: s += PIECE_TO_CHAR[m.promo].lower()
    return s

class ChessState:
    __slots__ = ("board", "turn", "castling", "ep_square", "halfmove", "fullmove", "hash")
    def __init__(self, board, turn="w", castling=None, ep_square=None, halfmove=0, fullmove=1, hash_val=0):
        self.board = board
        self.turn = turn
        self.castling = castling if castling is not None else {"K": True, "Q": True, "k": True, "q": True}
        self.ep_square = ep_square
        self.halfmove = halfmove
        self.fullmove = fullmove
        self.hash = hash_val

def initial_state():
    b_str = "rnbqkbnrpppppppp................................PPPPPPPPRNBQKBNR"
    b = [CHAR_TO_PIECE[c] for c in b_str]
    h = 0
    for i, p in enumerate(b):
        if p != EMPTY: h ^= ZOBRIST_PIECES[get_piece_idx(p)][i]
    h ^= ZOBRIST_CASTLE[15]
    return ChessState(b, hash_val=h)

def board_to_fen(state):
    fen = ""
    for r in range(8):
        empty = 0
        for c in range(8):
            p = state.board[r*8+c]
            if p == EMPTY:
                empty += 1
            else:
                if empty > 0:
                    fen += str(empty)
                    empty = 0
                fen += PIECE_TO_CHAR[p]
        if empty > 0: fen += str(empty)
        if r < 7: fen += "/"
    fen += f" {state.turn} "
    castling = ""
    if state.castling["K"]: castling += "K"
    if state.castling["Q"]: castling += "Q"
    if state.castling["k"]: castling += "k"
    if state.castling["q"]: castling += "q"
    if not castling: castling = "-"
    fen += castling + " "
    if state.ep_square:
        fen += f"{FILES[state.ep_square[1]]}{8 - state.ep_square[0]}"
    else:
        fen += "-"
    fen += f" {state.halfmove} {state.fullmove}"
    return fen

def fen_to_state(fen):
    parts = fen.split()
    board_part = parts[0]
    turn = parts[1] if len(parts) > 1 else "w"
    castling_part = parts[2] if len(parts) > 2 else "-"
    ep_part = parts[3] if len(parts) > 3 else "-"
    halfmove = int(parts[4]) if len(parts) > 4 else 0
    fullmove = int(parts[5]) if len(parts) > 5 else 1
    
    board = [EMPTY] * 64
    r, c = 0, 0
    for char in board_part:
        if char == "/":
            r += 1
            c = 0
        elif char.isdigit():
            c += int(char)
        else:
            board[r*8+c] = CHAR_TO_PIECE[char]
            c += 1
            
    castling = {"K": "K" in castling_part, "Q": "Q" in castling_part, "k": "k" in castling_part, "q": "q" in castling_part}
    ep_square = None
    if ep_part != "-":
        ep_square = (8 - int(ep_part[1]), FILES.index(ep_part[0]))
        
    h = 0
    for i, p in enumerate(board):
        if p != EMPTY: h ^= ZOBRIST_PIECES[get_piece_idx(p)][i]
    c_str = (int(castling["K"]) | int(castling["Q"])<<1 | int(castling["k"])<<2 | int(castling["q"])<<3)
    h ^= ZOBRIST_CASTLE[c_str]
    if ep_square:
        h ^= ZOBRIST_EP[ep_square[1]]
    if turn == "b":
        h ^= ZOBRIST_TURN
        
    return ChessState(board, turn, castling, ep_square, halfmove, fullmove, h)

def apply_move(state, move):
    fr, fc, tr, tc, promo = move
    fr_idx, tr_idx = fr*8+fc, tr*8+tc
    new_board = state.board.copy()
    piece, captured = new_board[fr_idx], new_board[tr_idx]
    is_white = piece > 0
    
    h = state.hash
    h ^= ZOBRIST_PIECES[get_piece_idx(piece)][fr_idx]
    h ^= ZOBRIST_PIECES[get_piece_idx(piece)][tr_idx]
    if captured != EMPTY: h ^= ZOBRIST_PIECES[get_piece_idx(captured)][tr_idx]
    
    if state.ep_square:
        h ^= ZOBRIST_EP[state.ep_square[1]]

    if abs(piece) == PAWN and fc != tc and captured == EMPTY:
        cap_idx = fr * 8 + tc
        new_board[cap_idx] = EMPTY
        captured = PAWN if is_white else -PAWN
        h ^= ZOBRIST_PIECES[get_piece_idx(captured)][cap_idx]

    new_board[tr_idx] = piece
    new_board[fr_idx] = EMPTY
    if promo: 
        new_board[tr_idx] = promo if is_white else -promo
        h ^= ZOBRIST_PIECES[get_piece_idx(new_board[tr_idx])][tr_idx]

    if abs(piece) == KING and abs(tc - fc) == 2:
        if tc > fc: 
            new_board[tr * 8 + 5], new_board[tr * 8 + 7] = new_board[tr * 8 + 7], EMPTY
            h ^= ZOBRIST_PIECES[get_piece_idx(ROOK if is_white else -ROOK)][tr*8+7]
            h ^= ZOBRIST_PIECES[get_piece_idx(ROOK if is_white else -ROOK)][tr*8+5]
        else: 
            new_board[tr * 8 + 3], new_board[tr * 8 + 0] = new_board[tr * 8 + 0], EMPTY
            h ^= ZOBRIST_PIECES[get_piece_idx(ROOK if is_white else -ROOK)][tr*8+0]
            h ^= ZOBRIST_PIECES[get_piece_idx(ROOK if is_white else -ROOK)][tr*8+3]

    old_c_str = (int(state.castling["K"]) | int(state.castling["Q"])<<1 | int(state.castling["k"])<<2 | int(state.castling["q"])<<3)
    new_castling = dict(state.castling)
    if piece == KING: new_castling["K"] = new_castling["Q"] = False
    elif piece == -KING: new_castling["k"] = new_castling["q"] = False
    if (fr, fc) == (7, 0) or (tr, tc) == (7, 0): new_castling["Q"] = False
    if (fr, fc) == (7, 7) or (tr, tc) == (7, 7): new_castling["K"] = False
    if (fr, fc) == (0, 0) or (tr, tc) == (0, 0): new_castling["q"] = False
    if (fr, fc) == (0, 7) or (tr, tc) == (0, 7): new_castling["k"] = False
    new_c_str = (int(new_castling["K"]) | int(new_castling["Q"])<<1 | int(new_castling["k"])<<2 | int(new_castling["q"])<<3)
    if old_c_str != new_c_str:
        h ^= ZOBRIST_CASTLE[old_c_str]
        h ^= ZOBRIST_CASTLE[new_c_str]

    new_ep = None
    if abs(piece) == PAWN and abs(tr - fr) == 2:
        new_ep = ((tr + fr) // 2, fc)
        h ^= ZOBRIST_EP[fc]

    new_halfmove = state.halfmove + 1
    if abs(piece) == PAWN or captured != EMPTY: new_halfmove = 0

    h ^= ZOBRIST_TURN

    return ChessState(
        board=new_board, turn="b" if state.turn == "w" else "w", castling=new_castling,
        ep_square=new_ep, halfmove=new_halfmove, fullmove=state.fullmove + (1 if state.turn == "b" else 0), hash_val=h
    )

def find_king(board, color):
    target = KING if color == "w" else -KING
    for i in range(64):
        if board[i] == target: return divmod(i, 8)
    return None

def is_attacked(board, r, c, by_white):
    pawn = PAWN if by_white else -PAWN
    pr = r + (1 if by_white else -1)
    if 0 <= pr < 8:
        for dc in (-1, 1):
            pc = c + dc
            if 0 <= pc < 8 and board[pr * 8 + pc] == pawn: return True

    knight = KNIGHT if by_white else -KNIGHT
    for dr, dc in KNIGHT_DELTAS:
        rr, cc = r + dr, c + dc
        if 0 <= rr < 8 and 0 <= cc < 8 and board[rr * 8 + cc] == knight: return True

    king = KING if by_white else -KING
    for dr, dc in KING_DELTAS:
        rr, cc = r + dr, c + dc
        if 0 <= rr < 8 and 0 <= cc < 8 and board[rr * 8 + cc] == king: return True

    bishop = BISHOP if by_white else -BISHOP
    rook = ROOK if by_white else -ROOK
    queen = QUEEN if by_white else -QUEEN

    for dr, dc in BISHOP_DIRS:
        rr, cc = r + dr, c + dc
        while 0 <= rr < 8 and 0 <= cc < 8:
            p = board[rr * 8 + cc]
            if p != EMPTY:
                if p == bishop or p == queen: return True
                break
            rr += dr; cc += dc
    for dr, dc in ROOK_DIRS:
        rr, cc = r + dr, c + dc
        while 0 <= rr < 8 and 0 <= cc < 8:
            p = board[rr * 8 + cc]
            if p != EMPTY:
                if p == rook or p == queen: return True
                break
            rr += dr; cc += dc
    return False

def in_check(state, color):
    kp = find_king(state.board, color)
    if kp is None: return False
    return is_attacked(state.board, kp[0], kp[1], by_white=(color == "b"))

def _gen_pawn(state, r, c, is_white):
    moves, board, d = [], state.board, -1 if is_white else 1
    start_row, promo_row = (6, 0) if is_white else (1, 7)
    nr = r + d
    if 0 <= nr < 8 and board[nr * 8 + c] == EMPTY:
        if nr == promo_row:
            for p in (QUEEN, ROOK, BISHOP, KNIGHT): moves.append(Move(r, c, nr, c, p))
        else:
            moves.append(Move(r, c, nr, c, None))
            if r == start_row:
                nr2 = r + 2 * d
                if board[nr2 * 8 + c] == EMPTY: moves.append(Move(r, c, nr2, c, None))
    for dc in (-1, 1):
        nc = c + dc
        if not (0 <= nc < 8 and 0 <= nr < 8): continue
        target = board[nr * 8 + nc]
        if target != EMPTY and (target > 0) != is_white:
            if nr == promo_row:
                for p in (QUEEN, ROOK, BISHOP, KNIGHT): moves.append(Move(r, c, nr, nc, p))
            else: moves.append(Move(r, c, nr, nc, None))
        elif state.ep_square == (nr, nc): moves.append(Move(r, c, nr, nc, None))
    return moves

def _gen_slide(state, r, c, dirs, is_white):
    moves, board = [], state.board
    for dr, dc in dirs:
        rr, cc = r + dr, c + dc
        while 0 <= rr < 8 and 0 <= cc < 8:
            t = board[rr * 8 + cc]
            if t == EMPTY: moves.append(Move(r, c, rr, cc, None))
            else:
                if (t > 0) != is_white: moves.append(Move(r, c, rr, cc, None))
                break
            rr += dr; cc += dc
    return moves

def _gen_castling(state, r, c, is_white):
    moves = []
    if is_white:
        if (r, c) != (7, 4): return []
        back, enemy_is_white, rights = 7, False, (state.castling["K"], state.castling["Q"])
    else:
        if (r, c) != (0, 4): return []
        back, enemy_is_white, rights = 0, True, (state.castling["k"], state.castling["q"])
    board = state.board
    if rights[0]:
        if (board[back * 8 + 5] == EMPTY and board[back * 8 + 6] == EMPTY
                and not is_attacked(board, back, 4, enemy_is_white)
                and not is_attacked(board, back, 5, enemy_is_white)
                and not is_attacked(board, back, 6, enemy_is_white)):
            moves.append(Move(r, c, back, 6, None))
    if rights[1]:
        if (board[back * 8 + 1] == EMPTY and board[back * 8 + 2] == EMPTY and board[back * 8 + 3] == EMPTY
                and not is_attacked(board, back, 4, enemy_is_white)
                and not is_attacked(board, back, 3, enemy_is_white)
                and not is_attacked(board, back, 2, enemy_is_white)):
            moves.append(Move(r, c, back, 2, None))
    return moves

def gen_pseudo_moves(state):
    moves, board, turn = [], state.board, state.turn
    for r in range(8):
        for c in range(8):
            p = board[r * 8 + c]
            if p == EMPTY: continue
            is_white = p > 0
            if (turn == "w") != is_white: continue
            low = abs(p)
            if low == PAWN: moves.extend(_gen_pawn(state, r, c, is_white))
            elif low == KNIGHT:
                for dr, dc in KNIGHT_DELTAS:
                    rr, cc = r + dr, c + dc
                    if 0 <= rr < 8 and 0 <= cc < 8:
                        t = board[rr * 8 + cc]
                        if t == EMPTY or (t > 0) != is_white: moves.append(Move(r, c, rr, cc, None))
            elif low == BISHOP: moves.extend(_gen_slide(state, r, c, BISHOP_DIRS, is_white))
            elif low == ROOK: moves.extend(_gen_slide(state, r, c, ROOK_DIRS, is_white))
            elif low == QUEEN: moves.extend(_gen_slide(state, r, c, BISHOP_DIRS + ROOK_DIRS, is_white))
            elif low == KING:
                for dr, dc in KING_DELTAS:
                    rr, cc = r + dr, c + dc
                    if 0 <= rr < 8 and 0 <= cc < 8:
                        t = board[rr * 8 + cc]
                        if t == EMPTY or (t > 0) != is_white: moves.append(Move(r, c, rr, cc, None))
                moves.extend(_gen_castling(state, r, c, is_white))
    return moves

def gen_legal_moves(state):
    legal = []
    side = state.turn
    for m in gen_pseudo_moves(state):
        if not in_check(apply_move(state, m), side): legal.append(m)
    return legal

def gen_captures(state):
    legal = []
    side = state.turn
    for m in gen_pseudo_moves(state):
        if abs(state.board[m.tr*8+m.tc]) > PAWN or m.promo:
            if not in_check(apply_move(state, m), side): legal.append(m)
    return legal

def eval_pesto(state):
    mg_score, eg_score, phase = 0, 0, 0
    for i, p in enumerate(state.board):
        if p == EMPTY: continue
        
        if p > 0:
            mg_score += PST_MG[p][i]
            eg_score += PST_EG[p][i]
            mg_score += PIECE_VALUES[p]
            eg_score += PIECE_VALUES[p]
        else:
            flipped_i = (7 - i // 8) * 8 + (i % 8)
            mg_score -= PST_MG[-p][flipped_i]
            eg_score -= PST_EG[-p][flipped_i]
            mg_score -= PIECE_VALUES[-p]
            eg_score -= PIECE_VALUES[-p]
            
        phase += PHASE_VALUES[abs(p)]
    
    phase = min(24, phase)
    final = (mg_score * phase + eg_score * (24 - phase)) // 24
    return final if state.turn == "w" else -final

def get_pv_line(state, max_length=10):
    pv = []
    temp_state = state
    for _ in range(max_length):
        tt_entry = _transposition_table.get(temp_state.hash)
        if not tt_entry or not tt_entry.move:
            break
        # Verify the move is legal to avoid cycles
        legal = gen_legal_moves(temp_state)
        if tt_entry.move not in legal:
            break
        pv.append(move_uci(tt_entry.move))
        temp_state = apply_move(temp_state, tt_entry.move)
    return pv

# ============================================================ AI Search
def qsearch(state, alpha, beta):
    stand_pat = eval_pesto(state)
    if stand_pat >= beta: return beta
    if alpha < stand_pat: alpha = stand_pat
    
    for m in gen_captures(state):
        score = -qsearch(apply_move(state, m), -beta, -alpha)
        if score >= beta: return beta
        if score > alpha: alpha = score
    return alpha

def negamax(state, depth, alpha, beta, null_move=True):
    global _nodes_searched
    _nodes_searched += 1
    
    if _stop_search: return 0
    
    tt_entry = _transposition_table.get(state.hash)
    if tt_entry and tt_entry.depth >= depth:
        if tt_entry.flag == TT_EXACT: return tt_entry.score
        if tt_entry.flag == TT_LOWER and tt_entry.score > alpha: alpha = tt_entry.score
        elif tt_entry.flag == TT_UPPER and tt_entry.score < beta: beta = tt_entry.score
        if alpha >= beta: return tt_entry.score

    if depth <= 0: return qsearch(state, alpha, beta)
    
    in_check_now = in_check(state, state.turn)
    if in_check_now: depth += 1 # Check extension
    
    # Null Move Pruning
    if null_move and not in_check_now and depth >= 3:
        null_turn = "b" if state.turn == "w" else "w"
        null_state = ChessState(state.board, null_turn, state.castling, None, state.halfmove, state.fullmove, state.hash ^ ZOBRIST_TURN)
        score = -negamax(null_state, depth - 3, -beta, -beta + 1, False)
        if score >= beta: return beta

    best_score = -MATE_SCORE
    best_move = None
    legal_moves = gen_legal_moves(state)
    if not legal_moves: return -MATE_SCORE + depth if in_check_now else 0

    # Move Ordering
    tt_move = tt_entry.move if tt_entry else None
    def order_key(m):
        if m == tt_move: return 999999
        cap = state.board[m.tr*8+m.tc]
        if cap != EMPTY: return 100000 + PIECE_VALUES[abs(cap)] * 10 - PIECE_VALUES[abs(state.board[m.fr*8+m.fc])]
        if m in _killers[depth]: return 90000
        return _history[m.fr*8+m.fc][m.tr*8+m.tc]
    
    legal_moves.sort(key=order_key, reverse=True)

    for i, m in enumerate(legal_moves):
        is_quiet = state.board[m.tr*8+m.tc] == EMPTY and m.promo is None
        
        # LMR (Late Move Reduction)
        reduction = 0
        if depth >= 3 and i >= 3 and is_quiet and not in_check_now:
            reduction = 1 if i < 6 else 2
            
        child = apply_move(state, m)
        
        if i == 0:
            score = -negamax(child, depth - 1, -beta, -alpha)
        else:
            score = -negamax(child, depth - 1 - reduction, -alpha - 1, -alpha)
            if score > alpha and score < beta:
                score = -negamax(child, depth - 1, -beta, -alpha)
                
        if score > best_score:
            best_score, best_move = score, m
            
        if score > alpha:
            alpha = score
            if score >= beta:
                if is_quiet:
                    if _killers[depth][0] != m:
                        _killers[depth][1] = _killers[depth][0]
                        _killers[depth][0] = m
                    _history[m.fr*8+m.fc][m.tr*8+m.tc] += depth * depth
                break

    flag = TT_EXACT
    if best_score <= alpha: flag = TT_UPPER
    elif best_score >= beta: flag = TT_LOWER
    
    _transposition_table[state.hash] = TTEntry(depth, best_score, flag, best_move)
    return best_score

def analyze_position(state, max_depth=5):
    global _stop_search, _nodes_searched
    _stop_search = False
    _nodes_searched = 0
    
    log_debug(f"--- Starting analysis | FEN: {board_to_fen(state)} ---")
    start_time = time.time()
    best_move = None
    best_score = -MATE_SCORE
    
    for depth in range(1, max_depth + 1):
        if _stop_search or time.time() - start_time > 1.5:
            log_debug(f"Search stopped at depth {depth} due to time limit.")
            break
            
        moves = gen_legal_moves(state)
        if not moves:
            return []
            
        tt_entry = _transposition_table.get(state.hash)
        if tt_entry and tt_entry.move in moves:
            moves.remove(tt_entry.move)
            moves.insert(0, tt_entry.move)
            
        alpha, beta = -MATE_SCORE, MATE_SCORE
        iter_best_move = None
        iter_best_score = -MATE_SCORE
        
        for m in moves:
            child = apply_move(state, m)
            score = -negamax(child, depth - 1, -beta, -alpha)
            if score > iter_best_score:
                iter_best_score = score
                iter_best_move = m
            if score > alpha:
                alpha = score
                
        best_move = iter_best_move
        best_score = iter_best_score
        
        if best_move:
            _transposition_table[state.hash] = TTEntry(depth, best_score, TT_EXACT, best_move)
            elapsed = time.time() - start_time
            nps = int(_nodes_searched / elapsed) if elapsed > 0 else 0
            pv_str = " ".join(get_pv_line(state))
            log_debug(f"Depth {depth} | Best: {move_uci(best_move)} | Score: {best_score} | Nodes: {_nodes_searched} | NPS: {nps} | PV: {pv_str}")
            
        if best_score > MATE_SCORE - 100:
            log_debug(f"Forced mate detected at depth {depth}.")
            break
            
    if best_move:
        return [(best_move, best_score)]
    return []

# ============================================================ UI & Game
CAPTURE_ORDER = {QUEEN: 0, ROOK: 1, BISHOP: 2, KNIGHT: 3, PAWN: 4, KING: 5}
def _sort_captured(pieces): return sorted(pieces, key=lambda p: CAPTURE_ORDER.get(abs(p), 6))

def _fmt_eval_white(score_white_centipawns):
    if score_white_centipawns >= MATE_SCORE - 1000: return "+M"
    if score_white_centipawns <= -(MATE_SCORE - 1000): return "-M"
    return f"{score_white_centipawns / 100:+.2f}"

class MoveHistoryWindow(tk.Toplevel):
    def __init__(self, master, get_text_fn):
        super().__init__(master)
        self.title("Move History"); self.geometry("460x580"); self.minsize(280, 240)
        self._get_text = get_text_fn; bg, fg = theme.color("bg"), theme.color("fg")
        self.configure(bg=bg)
        tk.Label(self, text="Full game log  •  copyable", bg=bg, fg=theme.color("muted"), font=theme.font("small")).pack(pady=(10, 4))
        text_frame = tk.Frame(self, bg=bg); text_frame.pack(fill="both", expand=True, padx=10, pady=(0, 6))
        self.text = tk.Text(text_frame, bg=theme.color("canvas_bg"), fg=fg, font=("Consolas", 11), wrap="none", bd=0, highlightthickness=0, insertbackground=fg)
        self.text.pack(side="left", fill="both", expand=True)
        sb = tk.Scrollbar(text_frame, orient="vertical", command=self.text.yview); sb.pack(side="right", fill="y"); self.text.config(yscrollcommand=sb.set)
        btn_frame = tk.Frame(self, bg=bg); btn_frame.pack(fill="x", padx=10, pady=(0, 10))
        self.status_lbl = tk.Label(btn_frame, text="", bg=bg, fg=theme.color("accent_o"), font=theme.font("small")); self.status_lbl.pack(side="left")
        tk.Button(btn_frame, text="Close", command=self.destroy, bg=theme.color("button_bg"), fg=theme.color("button_fg"), activebackground=theme.color("button_hover"), activeforeground=theme.color("button_fg"), relief="flat", bd=0, padx=12, pady=4, font=theme.font("button")).pack(side="right")
        tk.Button(btn_frame, text="Copy", command=self._copy, bg=theme.color("button_bg"), fg=theme.color("button_fg"), activebackground=theme.color("button_hover"), activeforeground=theme.color("button_fg"), relief="flat", bd=0, padx=12, pady=4, font=theme.font("button")).pack(side="right", padx=(0, 4))
        self.refresh()
    def refresh(self):
        self.text.config(state="normal"); self.text.delete("1.0", "end"); self.text.insert("1.0", self._get_text()); self.text.config(state="disabled")
    def _copy(self):
        self.clipboard_clear(); self.clipboard_append(self.text.get("1.0", "end-1c")); self.status_lbl.config(text="Copied!"); self.after(1800, lambda: self.status_lbl.config(text=""))

class FenDialog(tk.Toplevel):
    def __init__(self, master, current_fen):
        super().__init__(master)
        self.title("FEN Position")
        self.transient(master)
        self.resizable(False, False)
        bg, fg = theme.color("bg"), theme.color("fg")
        self.configure(bg=bg)
        
        tk.Label(self, text="Forsyth-Edwards Notation (FEN):", bg=bg, fg=fg).pack(padx=14, pady=(12, 4))
        self.entry = tk.Entry(self, width=60)
        self.entry.insert(0, current_fen)
        self.entry.pack(padx=14, pady=4)
        
        self.result = None
        
        btns = tk.Frame(self, bg=bg)
        btns.pack(fill="x", padx=14, pady=12)
        
        def load():
            self.result = self.entry.get().strip()
            self.destroy()
            
        def copy():
            self.clipboard_clear()
            self.clipboard_append(self.entry.get())
            self.status_lbl.config(text="Copied!")
            
        self.status_lbl = tk.Label(btns, text="", bg=bg, fg=theme.color("accent_o"))
        self.status_lbl.pack(side="left")
            
        tk.Button(btns, text="Load Position", command=load, bg=theme.color("button_bg"), fg=theme.color("button_fg")).pack(side="right", padx=4)
        tk.Button(btns, text="Copy", command=copy, bg=theme.color("button_bg"), fg=theme.color("button_fg")).pack(side="right", padx=4)
        tk.Button(btns, text="Cancel", command=self.destroy, bg=theme.color("button_bg"), fg=theme.color("button_fg")).pack(side="right", padx=4)

class Chess(tk.Toplevel):
    def __init__(self, master=None):
        super().__init__(master)
        self.title("Chess"); self.geometry("860x800"); self.minsize(560, 540)
        self.vs_computer = tk.BooleanVar(master=self, value=True)
        self.play_as_black = tk.BooleanVar(master=self, value=False)
        self.show_coords = tk.BooleanVar(master=self, value=True)
        self.cell, self.offset_x, self.offset_y = 70, 0, 0
        self.state = initial_state()
        self.selected, self.legal_targets, self.last_move = None, {}, None
        self.game_over, self.game_over_text, self.ai_thinking = False, "", False
        self.white_taken, self.black_taken = [], []
        self.engine_depth, self.engine_analysis = MAX_DEPTH, []
        self.move_history = []; self._history_window = None
        
        log_debug("--- Chess Game Started ---")
        
        self._build(); self.apply_theme(); self.new_game(); self._update_memo_label(); self.focus_set()

    def _build(self):
        self.status = tk.Label(self); self.status.pack(pady=(12, 6))
        self.middle = tk.Frame(self); self.middle.pack(fill="both", expand=True, padx=8, pady=(0, 4)); self.middle.columnconfigure(1, weight=1); self.middle.rowconfigure(0, weight=1)
        self.left_panel = tk.Frame(self.middle, width=110); self.left_panel.grid(row=0, column=0, sticky="ns", padx=(0, 4)); self.left_panel.grid_propagate(False)
        self.left_title = tk.Label(self.left_panel, text="White\nhas taken"); self.left_title.pack(pady=(6, 2))
        self.left_pieces = tk.Label(self.left_panel, text="", justify="center"); self.left_pieces.pack(fill="both", expand=True, padx=4, pady=(0, 6), anchor="n")
        self.canvas = tk.Canvas(self.middle, highlightthickness=0); self.canvas.grid(row=0, column=1, sticky="nsew"); self.canvas.bind("<Configure>", self._on_canvas_resize); self.canvas.bind("<Button-1>", self.on_click)
        self.right_panel = tk.Frame(self.middle, width=110); self.right_panel.grid(row=0, column=2, sticky="ns", padx=(4, 0)); self.right_panel.grid_propagate(False)
        self.right_title = tk.Label(self.right_panel, text="Black\nhas taken"); self.right_title.pack(pady=(6, 2))
        self.right_pieces = tk.Label(self.right_panel, text="", justify="center"); self.right_pieces.pack(fill="both", expand=True, padx=4, pady=(0, 6), anchor="n")
        self.engine_frame = tk.Frame(self); self.engine_frame.pack(fill="x", padx=14, pady=(0, 4))
        self.engine_lbl = tk.Label(self.engine_frame, text="", justify="left", anchor="w"); self.engine_lbl.pack(fill="x")
        self.bottom = tk.Frame(self); self.bottom.pack(fill="x", padx=12, pady=(0, 6))
        self.vs_cb = tk.Checkbutton(self.bottom, text="vs Computer", variable=self.vs_computer, command=self.on_vs_toggle, relief="flat", bd=0, highlightthickness=0); self.vs_cb.pack(side="left")
        self.color_cb = tk.Checkbutton(self.bottom, text="Play as Black", variable=self.play_as_black, command=self.on_color_toggle, relief="flat", bd=0, highlightthickness=0); self.color_cb.pack(side="left", padx=(8, 0))
        self.coords_cb = tk.Checkbutton(self.bottom, text="Coords", variable=self.show_coords, command=self.draw, relief="flat", bd=0, highlightthickness=0); self.coords_cb.pack(side="left", padx=(8, 0))
        self.new_btn = tk.Button(self.bottom, text="New", command=self.new_game, relief="flat", bd=0, padx=10, pady=3); self.new_btn.pack(side="right")
        self.history_btn = tk.Button(self.bottom, text="History", command=self.open_history, relief="flat", bd=0, padx=10, pady=3); self.history_btn.pack(side="right", padx=(0, 4))
        self.load_btn = tk.Button(self.bottom, text="Load", command=self.load_game, relief="flat", bd=0, padx=10, pady=3); self.load_btn.pack(side="right", padx=(0, 4))
        self.save_btn = tk.Button(self.bottom, text="Save", command=self.save_game, relief="flat", bd=0, padx=10, pady=3); self.save_btn.pack(side="right", padx=(0, 4))
        self.fen_btn = tk.Button(self.bottom, text="FEN", command=self.open_fen, relief="flat", bd=0, padx=10, pady=3); self.fen_btn.pack(side="right", padx=(0, 4))
        self.settings_btn = tk.Button(self.bottom, text="Settings", command=self.open_settings, relief="flat", bd=0, padx=10, pady=3); self.settings_btn.pack(side="right", padx=(0, 4))
        self.hint_lbl = tk.Label(self, text="Click a piece, then a highlighted square  •  R to restart"); self.hint_lbl.pack(pady=(0, 4))
        self.memo_lbl = tk.Label(self, text="", anchor="center"); self.memo_lbl.pack(fill="x", padx=12, pady=(0, 12)); self.bind("<KeyPress>", self.on_key)

    def apply_theme(self):
        bg, fg, btn_bg, btn_fg, hover = theme.color("bg"), theme.color("fg"), theme.color("button_bg"), theme.color("button_fg"), theme.color("button_hover")
        self.configure(bg=bg); self.status.configure(bg=bg, fg=fg, font=theme.font("status", "bold")); self.middle.configure(bg=bg)
        for p in (self.left_panel, self.right_panel): p.configure(bg=bg)
        for lbl in (self.left_title, self.right_title): lbl.configure(bg=bg, fg=theme.color("muted"), font=theme.font("small"))
        self.left_pieces.configure(bg=bg, fg=theme.color("piece_black"), font=theme.font("heading"))
        self.right_pieces.configure(bg=bg, fg=theme.color("piece_white"), font=theme.font("heading"))
        self.engine_frame.configure(bg=bg); self.engine_lbl.configure(bg=bg, fg=theme.color("muted"), font=theme.font("small"))
        self.bottom.configure(bg=bg); self.hint_lbl.configure(bg=bg, fg=theme.color("muted"), font=theme.font("small")); self.memo_lbl.configure(bg=bg, fg=theme.color("muted"), font=theme.font("small"))
        self.canvas.configure(bg=theme.color("canvas_bg"))
        self.vs_cb.configure(bg=bg, fg=fg, selectcolor=btn_bg, activebackground=bg, activeforeground=fg, font=theme.font("body"))
        self.color_cb.configure(bg=bg, fg=fg, selectcolor=btn_bg, activebackground=bg, activeforeground=fg, font=theme.font("body"))
        self.coords_cb.configure(bg=bg, fg=fg, selectcolor=btn_bg, activebackground=bg, activeforeground=fg, font=theme.font("body"))
        for btn in (self.new_btn, self.history_btn, self.save_btn, self.load_btn, self.settings_btn, self.fen_btn): btn.configure(bg=btn_bg, fg=btn_fg, activebackground=hover, activeforeground=btn_fg, font=theme.font("button"))
        self.draw(); self._update_captures_display()

    def open_fen(self):
        fen = board_to_fen(self.state)
        dlg = FenDialog(self, fen)
        self.wait_window(dlg)
        if dlg.result:
            try:
                self.state = fen_to_state(dlg.result)
                self.selected, self.legal_targets, self.last_move = None, {}, None
                self.game_over, self.game_over_text, self.ai_thinking = False, "", False
                self.white_taken, self.black_taken = [], []
                self.move_history = []
                self.update_status(); self.draw(); self._update_captures_display(); self._update_memo_label()
                if self.vs_computer.get() and self.state.turn != self.player_color():
                    self.ai_thinking = True; self.after(50, self.ai_move)
            except Exception as e:
                messagebox.showerror("Invalid FEN", f"Could not parse FEN: {e}", parent=self)

    def open_settings(self):
        dlg = tk.Toplevel(self); dlg.title("Chess Settings"); dlg.transient(self); dlg.resizable(False, False); dlg.configure(bg=theme.color("bg"))
        body = tk.Frame(dlg, bg=theme.color("bg")); body.pack(padx=20, pady=16)
        memo_var = tk.BooleanVar(value=memo.is_enabled(GAME_ID))
        tk.Checkbutton(body, text="Enable Engine Memoization", variable=memo_var, bg=theme.color("bg"), fg=theme.color("fg"), selectcolor=theme.color("button_bg")).pack(anchor="w", pady=4)
        size_lbl = tk.Label(body, text=f"Current TT size: {len(_transposition_table)} states", bg=theme.color("bg"), fg=theme.color("muted")); size_lbl.pack(anchor="w", pady=2)
        def clear_cache():
            _transposition_table.clear(); size_lbl.config(text="Current TT size: 0 states"); self._update_memo_label()
        tk.Button(body, text="Clear Memory Cache", command=clear_cache, bg=theme.color("button_bg"), fg=theme.color("button_fg")).pack(anchor="w", pady=4)
        def apply():
            memo.set_game_override(GAME_ID, enabled=memo_var.get()); self._update_memo_label(); dlg.destroy()
        tk.Button(body, text="Close", command=apply, bg=theme.color("button_bg"), fg=theme.color("button_fg")).pack(anchor="e", pady=(12,0))

    def player_color(self):
        return "b" if self.play_as_black.get() else "w"

    def on_color_toggle(self):
        self.new_game()

    def new_game(self):
        self.state = initial_state(); self.selected, self.legal_targets, self.last_move = None, {}, None
        self.game_over, self.game_over_text, self.ai_thinking = False, "", False
        self.white_taken, self.black_taken = [], []
        self.engine_analysis, self.engine_depth = [], MAX_DEPTH; self.move_history = []
        log_debug(f"New game started | FEN: {board_to_fen(self.state)}")
        self.update_status(); self.draw(); self._update_captures_display(); self._update_memo_label()
        if self._history_window and self._history_window.winfo_exists(): self._history_window.refresh()
        
        if self.vs_computer.get() and self.state.turn != self.player_color():
            self.ai_thinking = True
            self.update_status()
            self.after(50, self.ai_move)
        else:
            self.after(10, self.refresh_engine)

    def on_vs_toggle(self):
        if self.vs_computer.get() and self.state.turn != self.player_color() and not self.game_over and not self.ai_thinking:
            self.ai_thinking = True; self.update_status(); self.after(50, self.ai_move)
        else: self.update_status()

    def get_state(self):
        return {"board": self.state.board, "turn": self.state.turn, "castling": self.state.castling, "ep_square": self.state.ep_square, "halfmove": self.state.halfmove, "fullmove": self.state.fullmove, "white_taken": [PIECE_TO_CHAR[p] for p in self.white_taken], "black_taken": [PIECE_TO_CHAR[p] for p in self.black_taken], "last_move": list(self.last_move) if self.last_move else None, "game_over": self.game_over, "game_over_text": self.game_over_text, "vs_computer": self.vs_computer.get(), "play_as_black": self.play_as_black.get(), "move_history": self.move_history}

    def set_state(self, data):
        b = [CHAR_TO_PIECE.get(c, 0) if isinstance(c, str) else c for c in data["board"]]
        h = 0
        for i, p in enumerate(b):
            if p != EMPTY: h ^= ZOBRIST_PIECES[get_piece_idx(p)][i]
        
        castling = data["castling"]
        c_str = (int(castling["K"]) | int(castling["Q"])<<1 | int(castling["k"])<<2 | int(castling["q"])<<3)
        h ^= ZOBRIST_CASTLE[c_str]
        
        if data["ep_square"]:
            h ^= ZOBRIST_EP[data["ep_square"][1]]
            
        if data["turn"] == "b":
            h ^= ZOBRIST_TURN
            
        self.state = ChessState(board=b, turn=data["turn"], castling=data["castling"], ep_square=tuple(data["ep_square"]) if data["ep_square"] else None, halfmove=data["halfmove"], fullmove=data["fullmove"], hash_val=h)
        self.white_taken, self.black_taken = [CHAR_TO_PIECE.get(c, 0) for c in data["white_taken"]], [CHAR_TO_PIECE.get(c, 0) for c in data["black_taken"]]
        self.last_move = Move(*data["last_move"]) if data["last_move"] else None
        self.game_over, self.game_over_text = data["game_over"], data["game_over_text"]
        self.vs_computer.set(data["vs_computer"]); self.play_as_black.set(data.get("play_as_black", False))
        self.move_history = [tuple(m) for m in data["move_history"]]
        self.selected, self.legal_targets, self.ai_thinking = None, {}, False
        log_debug(f"Game state loaded | FEN: {board_to_fen(self.state)}")
        self.check_game_over(); self.update_status(); self.draw(); self._update_captures_display(); self._update_memo_label()
        
        if self.vs_computer.get() and self.state.turn != self.player_color():
            self.ai_thinking = True; self.update_status(); self.after(50, self.ai_move)
        else:
            self.after(10, self.refresh_engine)
            
        if self._history_window and self._history_window.winfo_exists(): self._history_window.refresh()

    def save_game(self): save_manager.prompt_save(self, GAME_ID, self.get_state())
    def load_game(self):
        fname = save_manager.prompt_load(self, GAME_ID)
        if fname: self.set_state(save_manager.load_game(GAME_ID, fname))

    def on_key(self, event):
        if event.keysym.lower() == "r": self.new_game()
        elif event.keysym.lower() == "h": self.open_history()

    def on_click(self, event):
        if self.game_over or self.ai_thinking or (self.vs_computer.get() and self.state.turn != self.player_color()) or self.cell <= 0: return
        c, r = int((event.x - self.offset_x) // self.cell), int((event.y - self.offset_y) // self.cell)
        if not (0 <= r < 8 and 0 <= c < 8): return
        if (r, c) in self.legal_targets:
            moves = self.legal_targets[(r, c)]
            if len(moves) == 1: self.execute_move(moves[0])
            else:
                promo = self.ask_promotion(self.state.turn == "w")
                if promo is None: return
                self.execute_move(next(m for m in moves if m.promo == promo))
            return
        piece = self.state.board[r * 8 + c]
        if piece != EMPTY and (piece > 0) == (self.state.turn == "w"):
            self.selected = (r, c); self.recompute_targets(); self.draw(); return
        self.selected, self.legal_targets = None, {}; self.draw()

    def recompute_targets(self):
        self.legal_targets = {}
        if self.selected is None: return
        fr, fc = self.selected
        for m in gen_legal_moves(self.state):
            if m.fr == fr and m.fc == fc: self.legal_targets.setdefault((m.tr, m.tc), []).append(m)

    def _detect_capture(self, move):
        fr, fc, tr, tc, _ = move
        target = self.state.board[tr * 8 + tc]
        if target != EMPTY: return target
        piece = self.state.board[fr * 8 + fc]
        if abs(piece) == PAWN and fc != tc: return self.state.board[fr * 8 + tc]
        return None

    def _format_move(self, state_before, move):
        piece = state_before.board[move.fr * 8 + move.fc]
        cap = state_before.board[move.tr * 8 + move.tc]
        is_ep = (abs(piece) == PAWN and move.fc != move.tc and cap == EMPTY)
        is_capture = (cap != EMPTY) or is_ep
        if abs(piece) == KING and abs(move.tc - move.fc) == 2: return "O-O" if move.tc > move.fc else "O-O-O"
        
        s = ""
        if abs(piece) != PAWN: 
            s += PIECE_TO_CHAR[abs(piece)]
            # Disambiguation
            same_pieces = []
            for m in gen_legal_moves(state_before):
                if m.tr == move.tr and m.tc == move.tc and m.fr != move.fr and state_before.board[m.fr*8+m.fc] == piece:
                    same_pieces.append(m)
            if same_pieces:
                s += FILES[move.fc]
        elif is_capture: 
            s += FILES[move.fc]
            
        if is_capture: s += "x"
        s += f"{FILES[move.tc]}{8 - move.tr}"
        if move.promo: s += "=" + PIECE_TO_CHAR[move.promo]
        return s

    def execute_move(self, move):
        notation = self._format_move(self.state, move)
        self.move_history.append((self.state.fullmove, self.state.turn, notation))
        
        captured = self._detect_capture(move)
        if captured is not None:
            if captured > 0: self.black_taken.append(captured)
            else: self.white_taken.append(captured)
        self.state = apply_move(self.state, move)
        self.last_move, self.selected, self.legal_targets = move, None, {}
        log_debug(f"Move: {notation} | FEN: {board_to_fen(self.state)}")
        
        self.check_game_over(); self.update_status(); self.draw(); self._update_captures_display(); self._update_memo_label()
        if self._history_window and self._history_window.winfo_exists(): self._history_window.refresh()
        if self.game_over: self.after(10, self.refresh_engine); return
        
        if self.vs_computer.get() and self.state.turn != self.player_color():
            self.ai_thinking = True; self.update_status(); self.after(50, self.ai_move)
        else: self.after(10, self.refresh_engine)

    def ai_move(self):
        if self.game_over or self.state.turn == self.player_color() or not self.vs_computer.get(): 
            self.ai_thinking = False
            return
        self.ai_thinking = True
        self.update_status()
        
        def search_thread():
            try:
                analysis = analyze_position(self.state, MAX_DEPTH)
                if not analysis:
                    moves = gen_legal_moves(self.state)
                    if moves:
                        analysis = [(random.choice(moves), 0)]
                self.after(0, lambda: self._apply_ai_move(analysis))
            except Exception as e:
                log_debug(f"Search error: {traceback.format_exc()}")
                self.after(0, lambda: self._apply_ai_move([]))
            
        threading.Thread(target=search_thread, daemon=True).start()
        
    def _apply_ai_move(self, analysis):
        if not analysis:
            log_debug("AI returned no moves, picking random!")
            moves = gen_legal_moves(self.state)
            if moves:
                analysis = [(random.choice(moves), 0)]
            else:
                self.ai_thinking = False
                self.check_game_over()
                self.update_status()
                self.draw()
                return
                
        self._update_engine_display(analysis, MAX_DEPTH)
        move = analysis[0][0]
        self.ai_thinking = False
        self.execute_move(move)

    def check_game_over(self):
        if self.state.halfmove >= 100: self.game_over, self.game_over_text = True, "Draw — fifty-move rule."; return
        if not gen_legal_moves(self.state):
            if in_check(self.state, self.state.turn):
                self.game_over, self.game_over_text = True, f"Checkmate — {'Black' if self.state.turn == 'w' else 'White'} wins!"
            else: self.game_over, self.game_over_text = True, "Stalemate — draw."
            log_debug(f"Game over: {self.game_over_text} | FEN: {board_to_fen(self.state)}")

    def update_status(self):
        if self.game_over: self.status.config(text=self.game_over_text); return
        if self.ai_thinking: self.status.config(text="Computer thinking..."); return
        side = "White" if self.state.turn == "w" else "Black"
        if self.vs_computer.get():
            suffix = " — your turn" if self.state.turn == self.player_color() else ""
        else:
            suffix = "'s turn"
        self.status.config(text=f"{side}{suffix}" + ("  •  Check!" if in_check(self.state, self.state.turn) else ""))

    def _update_captures_display(self):
        self.left_pieces.config(text=" ".join(UNICODE[p] for p in _sort_captured(self.white_taken)) or "—")
        self.right_pieces.config(text=" ".join(UNICODE[p] for p in _sort_captured(self.black_taken)) or "—")

    def _update_memo_label(self):
        if not memo.is_enabled(GAME_ID): self.memo_lbl.config(text="Memo: Disabled"); return
        self.memo_lbl.config(text=f"Memo: {len(_transposition_table)} cached nodes")

    def refresh_engine(self):
        if self.game_over: self.engine_lbl.config(text="Game over — no further analysis."); return
        def search_thread():
            try:
                analysis = analyze_position(self.state, 3)
                self.after(0, lambda: self._update_engine_display(analysis, 3))
            except Exception:
                pass
        threading.Thread(target=search_thread, daemon=True).start()

    def _update_engine_display(self, analysis, depth):
        if not analysis: self.engine_lbl.config(text=f"Depth {depth}  •  No legal moves."); return
        side_sign, side_name = (1, "White") if self.state.turn == "w" else (-1, "Black")
        lines = [f"Depth {depth}  •  Eval {_fmt_eval_white(analysis[0][1] * side_sign)} (White POV)  •  Best for {side_name}:"]
        for i, (m, score) in enumerate(analysis[:3], start=1): lines.append(f"    {i}. {move_uci(m)}   {_fmt_eval_white(score * side_sign)}")
        self.engine_lbl.config(text="\n".join(lines))

    def _format_history_text(self):
        if not self.move_history: return "No moves have been played yet."
        lines = ["Chess game log", "=" * 13, ""]
        i = 0
        while i < len(self.move_history):
            num, side, notation = self.move_history[i]
            if side == "w":
                if i + 1 < len(self.move_history) and self.move_history[i + 1][1] == "b":
                    lines.append(f"{num:>3}. {notation:<10s} {self.move_history[i + 1][2]}"); i += 2
                else: lines.append(f"{num:>3}. {notation}"); i += 1
            else: lines.append(f"{num:>3}. ... {notation}"); i += 1
        lines.append(""); lines.append("Captured by White:  " + (" ".join(UNICODE[p] for p in _sort_captured(self.white_taken)) or "—"))
        lines.append("Captured by Black:  " + (" ".join(UNICODE[p] for p in _sort_captured(self.black_taken)) or "—"))
        if self.game_over: lines.append(""); lines.append(self.game_over_text)
        return "\n".join(lines)

    def open_history(self):
        if self._history_window and self._history_window.winfo_exists():
            self._history_window.refresh(); self._history_window.lift(); self._history_window.focus_force(); return
        self._history_window = MoveHistoryWindow(self, self._format_history_text)

    def ask_promotion(self, is_white):
        dlg = tk.Toplevel(self); dlg.title("Promote Pawn"); dlg.transient(self); dlg.resizable(False, False)
        result = [None]; bg, fg, btn_bg, btn_fg, hover = theme.color("bg"), theme.color("fg"), theme.color("button_bg"), theme.color("button_fg"), theme.color("button_hover")
        dlg.configure(bg=bg); tk.Label(dlg, text="Promote to:", bg=bg, fg=fg, font=theme.font("body")).pack(padx=14, pady=(12, 8))
        frame = tk.Frame(dlg, bg=bg); frame.pack(padx=14, pady=(0, 12))
        def choose(code): result[0] = code; dlg.destroy()
        for code, name in ((QUEEN, "Queen"), (ROOK, "Rook"), (BISHOP, "Bishop"), (KNIGHT, "Knight")):
            key = code if is_white else -code
            tk.Button(frame, text=f"{UNICODE[key]} {name}", width=11, bg=btn_bg, fg=btn_fg, activebackground=hover, activeforeground=btn_fg, relief="flat", bd=0, padx=8, pady=4, font=theme.font("button"), command=lambda c=code: choose(c)).pack(side="left", padx=3)
        dlg.update_idletasks()
        try: dlg.grab_set()
        except tk.TclError: pass
        dlg.wait_window(); return result[0]

    def _on_canvas_resize(self, event):
        # Reserve 80px for coordinates (40 top, 40 bottom) so they don't get clipped
        avail_w = event.width - 40
        avail_h = event.height - 80
        cell_w = avail_w / 8
        cell_h = avail_h / 8
        self.cell = max(10, min(cell_w, cell_h))
        
        board_w = self.cell * 8
        board_h = self.cell * 8
        
        self.offset_x = (event.width - board_w) / 2
        self.offset_y = (event.height - board_h) / 2
        self.draw()

    def _px(self, c): return self.offset_x + c * self.cell
    def _py(self, r): return self.offset_y + r * self.cell

    def draw(self):
        if self.cell <= 0: return
        self.canvas.delete("all")
        light, dark, fg, accent_x, accent_o = theme.color("board_light"), theme.color("board_dark"), theme.color("fg"), theme.color("accent_x"), theme.color("accent_o")
        for r in range(8):
            for c in range(8):
                self.canvas.create_rectangle(self._px(c), self._py(r), self._px(c + 1), self._py(r + 1), fill=light if (r + c) % 2 == 0 else dark, outline="")
        
        if self.show_coords.get():
            for i in range(8):
                self.canvas.create_text(self._px(i) + self.cell/2, self._py(8) + 15, text=FILES[i], fill=fg, font=(theme.font_family, max(8, int(self.cell*0.2))))
                self.canvas.create_text(self._px(0) - 15, self._py(i) + self.cell/2, text=str(8-i), fill=fg, font=(theme.font_family, max(8, int(self.cell*0.2))))

        if self.last_move is not None:
            lm = self.last_move
            for (rr, cc) in ((lm.fr, lm.fc), (lm.tr, lm.tc)):
                self.canvas.create_rectangle(self._px(cc) + 2, self._py(rr) + 2, self._px(cc + 1) - 2, self._py(rr + 1) - 2, outline=accent_o, width=2)
        if self.selected is not None:
            r, c = self.selected
            self.canvas.create_rectangle(self._px(c) + 1, self._py(r) + 1, self._px(c + 1) - 1, self._py(r + 1) - 1, outline=accent_x, width=3)
        if not self.game_over and in_check(self.state, self.state.turn):
            kp = find_king(self.state.board, self.state.turn)
            if kp: self.canvas.create_rectangle(self._px(kp[1]) + 1, self._py(kp[0]) + 1, self._px(kp[1] + 1) - 1, self._py(kp[0] + 1) - 1, outline=accent_o, width=3)
        for (tr, tc), moves in self.legal_targets.items():
            target, mv, src = self.state.board[tr * 8 + tc], moves[0], self.state.board[moves[0].fr * 8 + moves[0].fc]
            is_ep = (abs(src) == PAWN and mv.fc != tc and target == EMPTY)
            if target != EMPTY or is_ep: self.canvas.create_oval(self._px(tc) + self.cell * 0.08, self._py(tr) + self.cell * 0.08, self._px(tc + 1) - self.cell * 0.08, self._py(tr + 1) - self.cell * 0.08, outline=accent_o, width=3)
            else: self.canvas.create_oval(self._px(tc) + self.cell * 0.36, self._py(tr) + self.cell * 0.36, self._px(tc + 1) - self.cell * 0.36, self._py(tr + 1) - self.cell * 0.36, fill=accent_o, outline="")
        font_size, stroke = max(8, int(self.cell * 0.72)), max(1, int(self.cell * 0.028))
        offsets = [(-stroke, 0), (stroke, 0), (0, -stroke), (0, stroke), (-stroke, -stroke), (stroke, -stroke), (-stroke, stroke), (stroke, stroke)]
        for r in range(8):
            for c in range(8):
                p = self.state.board[r * 8 + c]
                if p == EMPTY: continue
                is_white = p > 0
                glyph, interior, outline = SOLID_UNICODE[-abs(p)], theme.color("piece_white") if is_white else theme.color("piece_black"), accent_x if is_white else accent_o
                cx, cy = self._px(c) + self.cell / 2, self._py(r) + self.cell / 2
                for dx, dy in offsets: self.canvas.create_text(cx + dx, cy + dy, text=glyph, fill=outline, font=(theme.font_family, font_size))
                self.canvas.create_text(cx, cy, text=glyph, fill=interior, font=(theme.font_family, font_size))
        self.canvas.create_rectangle(self._px(0), self._py(0), self._px(8), self._py(8), outline=fg, width=2)

def run(master=None):
    return Chess(master)