"""Plain-language descriptions (template-based, offline). The optional LLM stage can overwrite 'why'."""
from __future__ import annotations

from .candidates import Candidate
from .features import EpisodeIndex
from .parse import fmt


def describe(ix: EpisodeIndex, c: Candidate) -> dict:
    f = c.f
    spk = [s.title() for s in f.speakers[:3]]
    hook = f"[{fmt(f.hook_t)}] {f.hook_line}" if f.hook_line else "(no clear hook)"
    cliff = f"[{fmt(f.cliff_t)}] {f.cliff_line}" if f.cliff_line else "(no clear closing line)"
    bits = [f.hook_reason or "weak opening"]
    if len(f.speakers) >= 2:
        bits.append(f"{len(f.speakers)}-way exchange ({', '.join(spk)})")
    bits.append(f.cliff_reason)
    if c.kind == "stitched":
        bits.append("stitched: short teaser, skip, then the payoff run")
    why = "; ".join(b for b in bits if b)
    # context note: who would a first-time viewer not know yet?
    late = [s.title() for s in f.speakers if s not in ("",) and ix.first_seen.get(s, ix.ep.number) < ix.ep.number - 3][:3]
    note = ""
    if f.standalone < 0.5:
        note = "Low standalone score" + (f"; leans on characters introduced earlier ({', '.join(late)})" if late else "") + \
               " - consider a 2-second on-screen caption naming the situation."
    elif late:
        note = f"Mildly context-dependent: {', '.join(late)} introduced several episodes earlier."
    out = {"hook": hook, "cliffhanger": cliff, "why": why, "context_note": note}
    if c.llm:
        out["why"] = c.llm.get("why") or why
        out["llm_scores"] = {k: c.llm.get(k) for k in ("hook", "cliffhanger", "standalone", "boundary_ok")}
        if c.llm.get("caption"):
            out["context_note"] = "Suggested caption: " + c.llm["caption"]
    return out
