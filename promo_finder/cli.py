"""CLI:  python -m promo_finder run --input DIR --out DIR [--per-ep 2] [--min-score 0.6] [--weights w.json] [--llm anthropic|openai|mock]"""
from __future__ import annotations

import argparse
import csv
import json
import time
from collections import Counter
from pathlib import Path

from . import __version__
from .candidates import DEFAULT_WEIGHTS, find_for_episode
from .explain import describe
from .features import EpisodeIndex
from .parse import canon_name, fmt, load_dir
from .select import rank


def build_indexes(eps):
    first: dict[str, int] = {}
    cnt: Counter = Counter()
    for e in eps:
        for d in e.dialogue():
            first.setdefault(canon_name(d.speaker), e.number)
            cnt[canon_name(d.speaker)] += 1
    lead = cnt.most_common(1)[0][0] if cnt else ""
    return {e.number: EpisodeIndex(e, first, lead) for e in eps}, lead


def seg_json(ix, c):
    out = []
    for s, e in c.segments:
        out.append({"episode": c.ep, "start_s": round(s, 2), "end_s": round(e, 2), "start": fmt(s), "end": fmt(e)})
    return out


def transcript(ix, c):
    rows = []
    for s, e in c.segments:
        for l in ix.lines_in(s, e):
            rows.append(f"[{fmt(l.start)}] {l.who.title()}: {l.text}")
    return rows


def run(input_dir, out_dir, per_ep=2, cands_per_ep=3, min_score=0.60, weights=None, use_stitch=True, llm=None, top_n=10):
    t0 = time.time()
    eps = load_dir(input_dir)
    idx, lead = build_indexes(eps)
    w = {**DEFAULT_WEIGHTS, **(weights or {})}
    out = Path(out_dir)
    (out / "episode_candidates").mkdir(parents=True, exist_ok=True)
    all_c = []
    for e in eps:
        ix = idx[e.number]
        cands = find_for_episode(ix, w, per_ep=cands_per_ep, use_stitch=use_stitch)
        if llm:
            from .llm import rerank
            cands = rerank(llm, ix, cands)
        for r, c in enumerate(cands, 1):
            c.parts["ep_rank"] = r
        all_c += cands
        rows = []
        for c in cands:
            d = describe(ix, c)
            rows.append({"ep_rank": c.parts["ep_rank"], "kind": c.kind, "score": round(c.score, 4), "duration_s": round(c.duration, 1),
                         "segments": seg_json(ix, c), "feature_scores": {k: round(v, 3) for k, v in c.parts.items() if k != "ep_rank"},
                         "flags": c.f.flags, **d, "transcript": transcript(ix, c)})
        (out / "episode_candidates" / f"ep_{e.number:02d}.json").write_text(
            json.dumps({"episode": e.number, "logline": e.logline, "duration_s": round(e.duration, 1), "candidates": rows}, indent=2, ensure_ascii=False))

    # final selection: <= per_ep per episode and above threshold; always keep each episode's best so no episode is silently skipped
    selected = []
    for e in eps:
        mine = [c for c in all_c if c.ep == e.number][:per_ep]
        keep = [c for i, c in enumerate(mine) if c.score >= min_score]
        selected += keep
    top = rank(selected, idx, top_n=top_n)
    top_ids = {id(c): i + 1 for i, c in enumerate(top)}
    ordered = sorted(selected, key=lambda c: -c.score)
    # global rank: diversity-aware top-N first, then the rest by score
    rest = [c for c in ordered if id(c) not in top_ids]
    ranked = top + rest
    promos = []
    for gi, c in enumerate(ranked, 1):
        ix = idx[c.ep]
        d = describe(ix, c)
        promos.append({"promo_id": f"P{gi:03d}", "global_rank": gi, "episode": c.ep, "kind": c.kind, "score": round(c.score, 4),
                       "duration_s": round(c.duration, 1), "segments": seg_json(ix, c), "flags": c.f.flags,
                       "feature_scores": {k: round(v, 3) for k, v in c.parts.items() if k != "ep_rank"}, **d,
                       "ep_rank": c.parts.get("ep_rank")})
    (out / "promos_all.json").write_text(json.dumps({"tool_version": __version__, "weights": w, "min_score": min_score,
                                                      "n_episodes": len(eps), "n_promos": len(promos), "promos": promos}, indent=2, ensure_ascii=False))
    with open(out / "promos_all.csv", "w", newline="", encoding="utf-8") as fh:
        wr = csv.writer(fh)
        wr.writerow(["promo_id", "global_rank", "episode", "segments (in order)", "duration_s", "kind", "score", "hook (first 3s)",
                     "cliffhanger (last line)", "why it works", "flags"])
        for p in promos:
            segs = " + ".join(f"Ep{s['episode']} {s['start']}-{s['end']}" for s in p["segments"])
            wr.writerow([p["promo_id"], p["global_rank"], p["episode"], segs, p["duration_s"], p["kind"], p["score"], p["hook"],
                         p["cliffhanger"], p["why"], ";".join(p["flags"])])
    from .report import write_ranked_md
    write_ranked_md(out / "promos_ranked_top.md", promos, top_n)
    (out / "run_log.json").write_text(json.dumps({"tool_version": __version__, "episodes": len(eps), "lead_detected": lead,
                                                   "seconds": round(time.time() - t0, 1), "weights": w, "min_score": min_score,
                                                   "per_ep": per_ep, "stitch": use_stitch, "llm": llm or "off (rule-based only)"}, indent=2))
    return promos


def cost(input_dir, per_ep=3):
    """Real prompt sizes from the scripts -> token/cost estimate for the LLM stage (no API call is made)."""
    from .llm import SYSTEM, build_prompt
    eps = load_dir(input_dir)
    idx, _ = build_indexes(eps)
    chars = n = 0
    for e in eps:
        for c in find_for_episode(idx[e.number], per_ep=per_ep):
            chars += len(SYSTEM) + len(build_prompt(idx[e.number], c))
            n += 1
    tin = chars / 4.0
    tout = n * 110
    print(f"{len(eps)} episodes, {n} LLM calls, ~{tin:,.0f} input tokens, ~{tout:,.0f} output tokens (chars/4 heuristic)")
    for name, pi, po in (("small model  @ $1/$5 per M", 1, 5), ("mid model    @ $3/$15 per M", 3, 15)):
        print(f"  {name}: ~${tin / 1e6 * pi + tout / 1e6 * po:.2f} for this {len(eps)}-episode show")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="promo_finder")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--input", required=True)
    r.add_argument("--out", required=True)
    r.add_argument("--per-ep", type=int, default=2)
    r.add_argument("--min-score", type=float, default=0.60)
    r.add_argument("--top", type=int, default=10)
    r.add_argument("--weights", help="JSON file overriding score weights")
    r.add_argument("--no-stitch", action="store_true")
    r.add_argument("--llm", choices=["anthropic", "openai", "mock"], help="optional LLM re-rank of the shortlisted candidates")
    c = sub.add_parser("cost")
    c.add_argument("--input", required=True)
    a = ap.parse_args(argv)
    if a.cmd == "cost":
        return cost(a.input)
    w = json.load(open(a.weights)) if a.weights else None
    promos = run(a.input, a.out, a.per_ep, 3, a.min_score, w, not a.no_stitch, a.llm, a.top)
    print(f"{len(promos)} promos written to {a.out}")


if __name__ == "__main__":
    main()
