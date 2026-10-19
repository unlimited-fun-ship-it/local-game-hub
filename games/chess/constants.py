"""Constants shared by every module in the chess package."""

GAME_ID = "chess"

# ------------------------------------------------------------------ pieces
# The board is a flat list of 64 ints.  Index 0 is a8, index 63 is h1.
# White pieces are positive, Black pieces are negative, 0 is empty.
EMPTY = 0
PAWN, KNIGHT, BISHOP, ROOK, QUEEN, KING = 1, 2, 3, 4, 5, 6
FILES = "abcdefgh"

PIECE_TO_CHAR = {
    0: ".", 1: "P", 2: "N", 3: "B", 4: "R", 5: "Q", 6: "K",
    -1: "p", -2: "n", -3: "b", -4: "r", -5: "q", -6: "k",
}
CHAR_TO_PIECE = {v: k for k, v in PIECE_TO_CHAR.items()}

# Outlined glyphs (white-looking) and solid glyphs (black-looking).
UNICODE = {
    1: "\u2659", 2: "\u2658", 3: "\u2657", 4: "\u2656", 5: "\u2655", 6: "\u2654",
    -1: "\u265F", -2: "\u265E", -3: "\u265D", -4: "\u265C", -5: "\u265B", -6: "\u265A",
}
# Keyed by piece *type* (1..6).  Both colours are drawn with the solid glyph and
# coloured/outlined by the UI, which is how the board and captured panels look.
SOLID_GLYPH = {
    1: "\u265F", 2: "\u265E", 3: "\u265D", 4: "\u265C", 5: "\u265B", 6: "\u265A",
}

# Centipawn values used by move ordering / pruning (the evaluation has its own
# tuned PeSTO values) and small "pawn unit" values for the material display.
PIECE_VALUES = [0, 100, 320, 330, 500, 900, 20000]
MATERIAL_UNITS = {PAWN: 1, KNIGHT: 3, BISHOP: 3, ROOK: 5, QUEEN: 9, KING: 0}

# ------------------------------------------------------------------ castling
# Castling rights are a 4-bit mask (this also indexes the Zobrist table).
CASTLE_WK, CASTLE_WQ, CASTLE_BK, CASTLE_BQ = 1, 2, 4, 8

# ------------------------------------------------------------------ search
MATE_SCORE = 1_000_000
MAX_PLY = 64
MATE_BOUND = MATE_SCORE - 1000      # |score| >= this means "forced mate"
INFINITY = MATE_SCORE + 1

MAX_DEPTH = 10          # hard cap for the computer's iterative deepening
MOVE_TIME = 2.0         # seconds the computer may think per move
ANALYSIS_DEPTH = 4      # background analysis shown while it is your turn
ANALYSIS_TIME = 0.6
