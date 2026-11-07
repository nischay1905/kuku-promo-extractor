"""Hard-rule validator for a finished run. Exit code 1 if any promo breaks a rule.
usage: python eval/validate_outputs.py OUT_DIR INPUT_DIR
Rules: 20-60s total; segments in order, non-overlapping, inside the episode; no spoken line chopped at either cut;
       stitched promos skip >= 8s; no two selected promos from one episode overlap > 25%.
"""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from promo_finder.parse import load_dir
from promo_finder.cli import build_indexes

out, inp = Path(sys.argv[1]), sys.argv[2]
idx, _ = build_indexes(load_dir(inp))
promos = json.load(open(out / "promos_all.json"))["promos"]
bad = []
for p in promos:
    ix = idx[p["episode"]]
    segs = [(a["start_s"], a["end_s"]) for a in p["segments"]]
    tot = sum(e - s for s, e in segs)
    if not (19.99 <= tot <= 60.01): bad.append((p["promo_id"], f"duration {tot:.1f}"))
    for (s, e) in segs:
        if s < 0 or e > ix.duration + 0.5: bad.append((p["promo_id"], "outside episode"))
        if ix.crossing(s, 0.3) or ix.crossing(e, 0.3): bad.append((p["promo_id"], f"mid-line cut at {s}/{e}"))
    for (s1, e1), (s2, e2) in zip(segs, segs[1:]):
        if s2 < e1: bad.append((p["promo_id"], "segments overlap/out of order"))
        if s2 - e1 < 7.99: bad.append((p["promo_id"], f"stitch gap {s2 - e1:.1f}s"))
by_ep = {}
for p in promos: by_ep.setdefault(p["episode"], []).append(p)
for ep, ps in by_ep.items():
    for i in range(len(ps)):
        for j in range(i + 1, len(ps)):
            ov = sum(max(0, min(a[1], b[1]) - max(a[0], b[0])) for a in [(x["start_s"], x["end_s"]) for x in ps[i]["segments"]] for b in [(x["start_s"], x["end_s"]) for x in ps[j]["segments"]])
            if ov / min(ps[i]["duration_s"], ps[j]["duration_s"]) > 0.25 + 1e-6: bad.append((ps[i]["promo_id"], f"overlaps {ps[j]['promo_id']}"))
print(f"{len(promos)} promos checked, {len(bad)} violations")
for b in bad[:20]: print("  ", b)
sys.exit(1 if bad else 0)
