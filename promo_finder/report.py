from __future__ import annotations
from pathlib import Path


def write_ranked_md(path, promos, top_n=10):
    L = ["# Promo shortlist (rule-based run - a SHORTLIST for an editor, not final picks)", "",
         f"Top {top_n} = suggested posting order: must have a hook AND an open ending, favours clips a stranger can follow, max one per",
         "episode, with a diversity penalty so the feed doesn't show near-identical scenes back to back. In my manual review of a",
         "previous run only about half of the top 10 were post-ready as-is (see solution doc), so treat this as a first pass.",
         "Everything below is the long tail, ranked by score.", ""]
    for p in promos[:top_n]:
        segs = " + ".join(f"Ep{s['episode']} {s['start']}-{s['end']}" for s in p["segments"])
        L += [f"## #{p['global_rank']}  {segs}  ({p['duration_s']}s, {p['kind']}, score {p['score']})",
              f"- **Hook:** {p['hook']}", f"- **Cliffhanger:** {p['cliffhanger']}", f"- **Why it works:** {p['why']}"]
        if p["flags"]: L.append(f"- **Editor flag:** {', '.join(p['flags'])}")
        if p["context_note"]: L.append(f"- **Context:** {p['context_note']}")
        L.append("")
    L += ["## Long tail", "", "| rank | promo | duration | score | flags |", "|---|---|---|---|---|"]
    for p in promos[top_n:]:
        segs = " + ".join(f"Ep{s['episode']} {s['start']}-{s['end']}" for s in p["segments"])
        L.append(f"| {p['global_rank']} | {segs} | {p['duration_s']}s | {p['score']} | {', '.join(p['flags'])} |")
    Path(path).write_text("\n".join(L), encoding="utf-8")
