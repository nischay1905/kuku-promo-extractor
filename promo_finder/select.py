"""Global ranking: pick the best promos across episodes, with diversity (no five near-identical dungeon scenes)."""
from __future__ import annotations

import math
import re
from collections import Counter

from .candidates import Candidate
from .features import EpisodeIndex


def bow(text: str) -> Counter:
    return Counter(w for w in re.findall(r"[a-z']{3,}", text.lower()))


def cos(a: Counter, b: Counter) -> float:
    num = sum(a[k] * b[k] for k in a if k in b)
    den = math.sqrt(sum(v * v for v in a.values())) * math.sqrt(sum(v * v for v in b.values()))
    return num / den if den else 0.0


def cand_text(ix: EpisodeIndex, c: Candidate) -> str:
    return " ".join(l.text for s, e in c.segments for l in ix.lines_in(s, e))


GATE_HOOK, GATE_CLIFF = 0.50, 0.45


def priority(c: Candidate, n_eps: int) -> float:
    """Posting-order priority: a stranger must be able to follow it (standalone), and late-arc clips spoil the premise."""
    return c.score + 0.25 * c.f.standalone - 0.10 * (c.ep - 1) / max(1, n_eps - 1)


def rank(cands: list[Candidate], idx: dict[int, EpisodeIndex], top_n: int = 10, mmr_lambda: float = 0.25,
         one_per_episode: bool = True) -> list[Candidate]:
    """Greedy MMR over `priority`: priority minus lambda * max text-similarity to already-picked promos."""
    n_eps = len(idx)
    pool = sorted(cands, key=lambda c: c.score, reverse=True)
    # gate = the brief's own definition of a promo: it must have BOTH a hook and an unresolved ending
    ok = [c for c in pool if c.f.hook >= GATE_HOOK and c.f.cliff >= GATE_CLIFF]
    if len(ok) >= top_n:
        pool = ok
    vec = {id(c): bow(cand_text(idx[c.ep], c)) for c in pool}
    picked: list[Candidate] = []
    used_eps: set[int] = set()
    while pool and len(picked) < top_n:
        best, best_v = None, -1e9
        for c in pool:
            if one_per_episode and c.ep in used_eps:
                continue
            sim = max((cos(vec[id(c)], vec[id(p)]) for p in picked), default=0.0)
            v = priority(c, n_eps) - mmr_lambda * sim
            if v > best_v:
                best, best_v = c, v
        if best is None:
            break
        picked.append(best)
        used_eps.add(best.ep)
        pool.remove(best)
    return picked
