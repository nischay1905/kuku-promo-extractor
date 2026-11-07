"""Score tool output against the hand-picked golden beats.

usage: python eval/evaluate.py OUT_DIR [--split dev|heldout|both]
Reads OUT_DIR/episode_candidates/ep_XX.json (top-k per episode, ranked) and OUT_DIR/promos_all.json.
"""
import json, sys, argparse
from pathlib import Path

def overlap_ratio(core, segs):
    ov = sum(max(0.0, min(core[1], e) - max(core[0], s)) for s, e in segs)
    seglen = sum(e - s for s, e in segs)
    return ov / max(1e-6, min(core[1] - core[0], seglen))

def iou(core, segs):
    ov = sum(max(0.0, min(core[1], e) - max(core[0], s)) for s, e in segs)
    seglen = sum(e - s for s, e in segs)
    union = (core[1] - core[0]) + seglen - ov
    return ov / max(1e-6, union)

def evaluate(out_dir, split="both", verbose=True, thresh=0.6):
    g = json.load(open(Path(__file__).parent / "golden_set.json"))
    items = (g["dev"] if split in ("dev", "both") else []) + (g["heldout"] if split in ("heldout", "both") else [])
    sel = json.load(open(Path(out_dir) / "promos_all.json"))
    sel_ids = {(p["episode"], tuple(map(tuple, [(a["start_s"], a["end_s"]) for a in p["segments"]]))): p for p in sel["promos"]}
    top10 = {p["episode"] for p in sel["promos"] if p.get("global_rank", 999) <= 10}
    res = []
    for it in items:
        ep = it["ep"]
        cands = json.load(open(Path(out_dir) / "episode_candidates" / f"ep_{ep:02d}.json"))["candidates"]
        best_rank = None
        strict_rank = None
        for c in cands:
            segs = [(a["start_s"], a["end_s"]) for a in c["segments"]]
            if best_rank is None and any(overlap_ratio(core, segs) >= thresh for core in it["cores"]):
                best_rank = c["ep_rank"]
            if strict_rank is None and any(iou(core, segs) >= 0.4 for core in it["cores"]):
                strict_rank = c["ep_rank"]
        in_selected = any(p["episode"] == ep and any(overlap_ratio(core, [(a["start_s"], a["end_s"]) for a in p["segments"]]) >= thresh for core in it["cores"]) for p in sel["promos"])
        res.append({"ep": ep, "hit_rank": best_rank, "strict_rank": strict_rank, "in_selected": in_selected})
    n = len(res)
    h1 = sum(1 for r in res if r["hit_rank"] == 1); h2 = sum(1 for r in res if r["hit_rank"] and r["hit_rank"] <= 2); h3 = sum(1 for r in res if r["hit_rank"])
    sel_n = sum(1 for r in res if r["in_selected"])
    s1 = sum(1 for r in res if r["strict_rank"] == 1); s3 = sum(1 for r in res if r["strict_rank"])
    summary = {"split": split, "n": n, "lenient_hit@1": h1, "lenient_hit@2": h2, "lenient_hit@3": h3,
               "strict_IoU>=0.4_hit@1": s1, "strict_hit@3": s3, "in_final_selection(lenient)": sel_n}
    if verbose:
        for r in res: print(f"  ep{r['ep']:02d}  lenient_rank={r['hit_rank']}  strict_rank={r['strict_rank']}  selected={r['in_selected']}")
        print(summary)
    return summary, res

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("out"); ap.add_argument("--split", default="both")
    a = ap.parse_args(); evaluate(a.out, a.split)
