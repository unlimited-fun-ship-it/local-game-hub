"""The search: iterative deepening, aspiration windows, PVS negamax,
quiescence, transposition table, null-move / futility pruning, LMR,
killer + history move ordering, repetition detection and real time control.

Scores are in centipawns from the point of view of the side to move.  Forced
mates are +/-(MATE_SCORE - plies_to_mate).

A `Searcher` is single-use: make a new one for each search.  Call `stop()`
from another thread to abort it; `search()` then returns the last *completed*
iteration.
"""

import math
import time

from .board import apply_move, make_null_move
from .constants import (
    EMPTY, PAWN, KNIGHT, BISHOP, ROOK, QUEEN, PIECE_VALUES,
    MATE_SCORE, MATE_BOUND, INFINITY, MAX_PLY, MAX_DEPTH, MOVE_TIME,
)
from .evaluation import evaluate
from .logger import log_debug
from .movegen import gen_pseudo_moves, gen_legal_moves, king_attacked
from .notation import move_uci

TT_EXACT, TT_LOWER, TT_UPPER = 0, 1, 2
TT_MAX_ENTRIES = 750_000


class TranspositionTable:
    """position hash -> (depth, score, bound flag, best move)."""

    def __init__(self):
        self.table = {}

    def __len__(self):
        return len(self.table)

    def clear(self):
        self.table.clear()


# One table shared by every search, so analysis made while you think is reused.
TRANSPOSITION_TABLE = TranspositionTable()

# Late-move-reduction table: _LMR[depth][moves_tried]
_LMR = [[0] * 64 for _ in range(64)]
for _d in range(1, 64):
    for _i in range(1, 64):
        _LMR[_d][_i] = int(0.6 + math.log(_d) * math.log(_i) / 2.2)

# Small piece values for MVV-LVA ordering (index = piece type).
_ORDER_VALUE = [0, 1, 3, 3, 5, 9, 10]
_WHITE_PIECES = frozenset((KNIGHT, BISHOP, ROOK, QUEEN))
_BLACK_PIECES = frozenset((-KNIGHT, -BISHOP, -ROOK, -QUEEN))


def _to_tt(score, ply):
    """Mate scores are stored relative to the node, not to the root."""
    if score >= MATE_BOUND:
        return score + ply
    if score <= -MATE_BOUND:
        return score - ply
    return score


def _from_tt(score, ply):
    if score >= MATE_BOUND:
        return score - ply
    if score <= -MATE_BOUND:
        return score + ply
    return score


class SearchResult:
    __slots__ = ("best_move", "score", "depth", "nodes", "elapsed", "pv")

    def __init__(self, best_move, score, depth, nodes, elapsed, pv):
        self.best_move = best_move
        self.score = score          # side-to-move point of view
        self.depth = depth
        self.nodes = nodes
        self.elapsed = elapsed
        self.pv = pv                # list of UCI strings


class Searcher:
    def __init__(self, tt=None):
        self.tt = (tt or TRANSPOSITION_TABLE).table
        self.stopped = False
        self.nodes = 0
        self.completed_depth = 0
        self.deadline = float("inf")
        self.killers = [[None, None] for _ in range(MAX_PLY + 4)]
        self.history = [[0] * 64 for _ in range(64)]
        self.rep_stack = []

    def stop(self):
        self.stopped = True

    # ------------------------------------------------------------ public entry
    def search(self, state, max_depth=MAX_DEPTH, time_limit=MOVE_TIME, history=()):
        """Search `state`.  `history` = hashes of the positions played before it."""
        start = time.perf_counter()
        self.deadline = start + time_limit
        if len(self.tt) > TT_MAX_ENTRIES:
            self.tt.clear()
        self.rep_stack = list(history) + [state.hash]

        root_moves = gen_legal_moves(state)
        if not root_moves:
            mated = king_attacked(state.board, state.turn == "w")
            return SearchResult(None, -MATE_SCORE if mated else 0, 0, 0, 0.0, [])
        if len(root_moves) == 1:                       # forced move: don't waste time
            return SearchResult(root_moves[0], evaluate(state), 1, 1, 0.0, [move_uci(root_moves[0])])

        log_debug(f"--- Search | {len(root_moves)} legal moves ---")
        self._order(state, root_moves, None, 0)
        best_move, best_score, done = root_moves[0], 0, 0

        for depth in range(1, max_depth + 1):
            # Each iteration costs ~3x the last one: don't start one we can't finish.
            if depth > 1 and time.perf_counter() - start > time_limit * 0.55:
                break

            alpha, beta, delta = -INFINITY, INFINITY, 40
            if depth >= 4 and abs(best_score) < MATE_BOUND:
                alpha, beta = best_score - delta, best_score + delta
            fails = 0
            while True:
                score, move = self._search_root(state, root_moves, depth, alpha, beta)
                if self.stopped:
                    break
                failed_low = score <= alpha and alpha > -INFINITY
                failed_high = score >= beta and beta < INFINITY
                if not (failed_low or failed_high):
                    break
                fails += 1
                delta *= 3
                if fails >= 3:
                    alpha, beta = -INFINITY, INFINITY
                elif failed_low:
                    alpha = max(-INFINITY, score - delta)
                else:
                    beta = min(INFINITY, score + delta)
            if self.stopped:
                break                                   # discard the unfinished iteration

            best_move, best_score, done = move, score, depth
            self.completed_depth = depth
            self.tt[state.hash] = (depth, _to_tt(score, 0), TT_EXACT, move)
            root_moves.remove(move)
            root_moves.insert(0, move)
            elapsed = time.perf_counter() - start
            log_debug(f"Depth {depth} | Best: {move_uci(move)} | Score: {score} | Nodes: {self.nodes} "
                      f"| NPS: {int(self.nodes / elapsed) if elapsed else 0} "
                      f"| PV: {' '.join(self._extract_pv(state, move))}")
            if abs(score) >= MATE_BOUND and MATE_SCORE - abs(score) <= depth:
                break                                   # forced mate found and proven

        elapsed = time.perf_counter() - start
        return SearchResult(best_move, best_score, done, self.nodes, elapsed,
                            self._extract_pv(state, best_move))

    # ------------------------------------------------------------ helpers
    def _check_time(self):
        # Always finish depth 1 so there is a move to play.
        if self.completed_depth >= 1 and time.perf_counter() >= self.deadline:
            self.stopped = True

    def _extract_pv(self, state, first_move, limit=12):
        pv = [move_uci(first_move)]
        seen = {state.hash}
        cur = apply_move(state, first_move)
        while len(pv) < limit and cur.hash not in seen:
            seen.add(cur.hash)
            entry = self.tt.get(cur.hash)
            if not entry or entry[3] is None or entry[3] not in gen_legal_moves(cur):
                break
            pv.append(move_uci(entry[3]))
            cur = apply_move(cur, entry[3])
        return pv

    def _is_repetition(self, state):
        """True if this position already occurred since the last irreversible move."""
        stack = self.rep_stack
        n = len(stack)
        h = state.hash
        lowest = max(0, n - 1 - state.halfmove)
        i = n - 3
        while i >= lowest:
            if stack[i] == h:
                return True
            i -= 2
        return False

    def _order(self, state, moves, tt_move, ply):
        board = state.board
        k0, k1 = self.killers[ply]
        hist = self.history

        def key(m):
            if m == tt_move:
                return 1_000_000
            src = m.fr * 8 + m.fc
            dst = m.tr * 8 + m.tc
            victim = board[dst]
            if victim:
                return 100_000 + 10 * _ORDER_VALUE[abs(victim)] - _ORDER_VALUE[abs(board[src])]
            if m.promo:
                return 95_000 + m.promo
            if abs(board[src]) == PAWN and m.fc != m.tc:        # en passant
                return 100_009
            if m == k0:
                return 90_000
            if m == k1:
                return 89_000
            return hist[src][dst]

        moves.sort(key=key, reverse=True)

    @staticmethod
    def _has_pieces(board, white):
        group = _WHITE_PIECES if white else _BLACK_PIECES
        return any(p in group for p in board)

    # ------------------------------------------------------------ root
    def _search_root(self, state, moves, depth, alpha, beta):
        best_score, best_move = -INFINITY, moves[0]
        for i, m in enumerate(moves):
            child = apply_move(state, m)
            self.rep_stack.append(child.hash)
            if i == 0:
                score = -self.negamax(child, depth - 1, -beta, -alpha, 1)
            else:
                score = -self.negamax(child, depth - 1, -alpha - 1, -alpha, 1)
                if alpha < score < beta:
                    score = -self.negamax(child, depth - 1, -beta, -alpha, 1)
            self.rep_stack.pop()
            if self.stopped:
                return 0, best_move
            if score > best_score:
                best_score, best_move = score, m
                if score > alpha:
                    alpha = score
                    if alpha >= beta:
                        break
        return best_score, best_move

    # ------------------------------------------------------------ main search
    def negamax(self, state, depth, alpha, beta, ply, allow_null=True):
        self.nodes += 1
        if not self.nodes & 255:
            self._check_time()
        if self.stopped:
            return 0

        if state.halfmove >= 100 or self._is_repetition(state):
            return 0
        if ply >= MAX_PLY:
            return evaluate(state)

        # Mate-distance pruning: no line can beat a mate we already know about.
        alpha = max(alpha, -MATE_SCORE + ply)
        beta = min(beta, MATE_SCORE - ply - 1)
        if alpha >= beta:
            return alpha

        board = state.board
        white = state.turn == "w"
        in_chk = king_attacked(board, white)
        if in_chk:
            depth += 1                                   # check extension
        if depth <= 0:
            return self.qsearch(state, alpha, beta, ply)

        is_pv = beta - alpha > 1
        orig_alpha = alpha            # needed to pick the right TT bound at the end

        # ---- transposition table
        key = state.hash
        entry = self.tt.get(key)
        tt_move = None
        if entry is not None:
            e_depth, e_score, e_flag, tt_move = entry
            if e_depth >= depth and (not is_pv or e_flag == TT_EXACT):
                s = _from_tt(e_score, ply)
                if e_flag == TT_EXACT:
                    return s
                if e_flag == TT_LOWER and s >= beta:
                    return s
                if e_flag == TT_UPPER and s <= alpha:
                    return s

        # ---- pruning that needs a static evaluation
        static_eval = None
        if not in_chk and not is_pv:
            static_eval = evaluate(state)
            # Reverse futility ("static null move"): so far ahead that it holds anyway.
            if depth <= 4 and abs(beta) < MATE_BOUND and static_eval - 100 * depth >= beta:
                return static_eval - 100 * depth
            # Null move: if passing still beats beta, a real move will too.
            # Not in pawn-only endings, where zugzwang makes it unsound.
            if (allow_null and depth >= 3 and static_eval >= beta
                    and self._has_pieces(board, white)):
                reduction = 3 if depth >= 6 else 2
                null = make_null_move(state)
                self.rep_stack.append(null.hash)
                score = -self.negamax(null, depth - 1 - reduction, -beta, -beta + 1, ply + 1, False)
                self.rep_stack.pop()
                if self.stopped:
                    return 0
                if score >= beta:
                    return beta if score >= MATE_BOUND else score

        # ---- move loop
        moves = gen_pseudo_moves(state)
        self._order(state, moves, tt_move, ply)
        killers = self.killers[ply]
        best, best_move, legal = -INFINITY, None, 0

        for m in moves:
            child = apply_move(state, m)
            if king_attacked(child.board, white):
                continue                                 # pseudo-legal but illegal
            legal += 1
            src = m.fr * 8 + m.fc
            dst = m.tr * 8 + m.tc
            piece = board[src]
            is_quiet = (board[dst] == EMPTY and not m.promo
                        and not (abs(piece) == PAWN and m.fc != m.tc))

            # Futility: a quiet move at low depth can't lift a hopeless position to alpha.
            if (is_quiet and static_eval is not None and best > -INFINITY and depth <= 2
                    and abs(alpha) < MATE_BOUND
                    and static_eval + 130 + 120 * depth <= alpha
                    and not king_attacked(child.board, child.turn == "w")):
                continue

            self.rep_stack.append(child.hash)
            if legal == 1:
                score = -self.negamax(child, depth - 1, -beta, -alpha, ply + 1)
            else:
                # Late move reductions for quiet moves that are tried late.
                r = 0
                if depth >= 3 and legal > 3 and is_quiet and not in_chk:
                    r = _LMR[min(depth, 63)][min(legal, 63)]
                    if is_pv:
                        r -= 1
                    if m == killers[0] or m == killers[1]:
                        r -= 1
                    if r > 0 and king_attacked(child.board, child.turn == "w"):
                        r = 0                            # never reduce checking moves
                    r = max(0, min(r, depth - 2))
                score = -self.negamax(child, depth - 1 - r, -alpha - 1, -alpha, ply + 1)
                if r and score > alpha:
                    score = -self.negamax(child, depth - 1, -alpha - 1, -alpha, ply + 1)
                if alpha < score < beta:
                    score = -self.negamax(child, depth - 1, -beta, -alpha, ply + 1)
            self.rep_stack.pop()
            if self.stopped:
                return 0

            if score > best:
                best, best_move = score, m
                if score > alpha:
                    alpha = score
                    if alpha >= beta:
                        if is_quiet:
                            if killers[0] != m:
                                killers[1] = killers[0]
                                killers[0] = m
                            h = self.history[src][dst] + depth * depth
                            self.history[src][dst] = h if h < 80_000 else 80_000
                        break

        if legal == 0:
            return -MATE_SCORE + ply if in_chk else 0

        if best <= orig_alpha:
            flag = TT_UPPER
        elif best >= beta:
            flag = TT_LOWER
        else:
            flag = TT_EXACT
        self.tt[key] = (depth, _to_tt(best, ply), flag, None if flag == TT_UPPER else best_move)
        return best

    # ------------------------------------------------------------ quiescence
    def qsearch(self, state, alpha, beta, ply):
        """Resolve captures/promotions so the evaluation only sees quiet positions."""
        self.nodes += 1
        if not self.nodes & 255:
            self._check_time()
        if self.stopped:
            return 0

        stand_pat = evaluate(state)
        if ply >= MAX_PLY or stand_pat >= beta:
            return stand_pat
        if stand_pat > alpha:
            alpha = stand_pat
        best = stand_pat

        board = state.board
        white = state.turn == "w"
        moves = gen_pseudo_moves(state, True)

        def key(m):
            victim = abs(board[m.tr * 8 + m.tc]) or (PAWN if m.fc != m.tc and abs(board[m.fr * 8 + m.fc]) == PAWN else 0)
            return 10 * _ORDER_VALUE[victim] - _ORDER_VALUE[abs(board[m.fr * 8 + m.fc])] + (50 if m.promo else 0)

        moves.sort(key=key, reverse=True)
        for m in moves:
            victim = abs(board[m.tr * 8 + m.tc])
            if not victim and not m.promo:
                victim = PAWN                            # en passant
            # Delta pruning: even winning this piece can't reach alpha.
            if not m.promo and stand_pat + PIECE_VALUES[victim] + 200 < alpha:
                continue
            child = apply_move(state, m)
            if king_attacked(child.board, white):
                continue
            score = -self.qsearch(child, -beta, -alpha, ply + 1)
            if self.stopped:
                return 0
            if score > best:
                best = score
                if score > alpha:
                    alpha = score
                    if alpha >= beta:
                        break
        return best
