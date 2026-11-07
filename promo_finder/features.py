"""Per-episode index: per-line features, legal cut points, and window feature extraction."""
from __future__ import annotations

import bisect
import re
from dataclasses import dataclass, field

from . import lexicon as L
from .parse import Episode, Event, canon_name

FIGURATIVE = re.compile(r"burst\w* into|strikes? (?:deep|home|a chord)|freezing (?:in|into|as)|frozen in|points? (?:to|toward)|"
                        r"trembling (?:lips|hand)|tears? (?:welling|shimmering)|weeping|sobbing", re.I)
CONT_STARTERS = {"and", "but", "so", "then", "because", "or", "which", "that"}
GENERIC_SPEAKERS = {"GUARD", "CONSTABLE", "JUDGE", "PRIEST", "MAID", "BUTLER", "FOOTMAN", "TOWNSMAN", "VILLAGER",
                    "INFORMANT", "THUG", "BALD THUG", "TALL THUG", "THIRD THUG", "HOUSEKEEPER", "CONSPIRATOR", "OLD WOMAN",
                    "ROYAL SENTRY", "ROYAL GUARD", "CART DRIVER", "LOYALIST", "NOBLEMAN", "NOBLEWOMAN", "OFF-SCREEN VOICE"}


def clip(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


@dataclass
class Line:
    ev: Event
    inten: float = 0.3
    hookw: float = 0.0
    q: bool = False
    ex: bool = False
    ell_end: bool = False
    ell_start: bool = False
    words: int = 0
    cont_prev: bool = False
    cont_next: bool = False
    reply_to_q: bool = False
    who: str = ""

    @property
    def start(self): return self.ev.start
    @property
    def end(self): return self.ev.end
    @property
    def text(self): return self.ev.text


def line_features(ev: Event) -> Line:
    t = ev.text.strip()
    tagtxt = " ".join(ev.tags)
    # intensity = strongest matched delivery tag (default 0.3 if the label has none)
    matched = [w for w, rx in L.TAG_RX if rx.search(tagtxt)]
    inten = max(matched) if matched else 0.3
    if t.endswith("!") or "!" in t:
        inten = min(1.0, inten + 0.12)
    if t.isupper() and len(t) > 3:
        inten = min(1.0, inten + 0.1)
    hookw = len(L.STRONG.findall(t)) * 1.0 + len(L.MEDIUM.findall(t)) * 0.45 + (1.0 if L.ACCUSE.search(t) else 0.0)
    ell_end = t.endswith("...") or t.endswith("\u2026")
    ell_start = t.startswith("...") or t.startswith("\u2026")
    return Line(ev=ev, inten=inten, hookw=hookw, q=t.endswith("?"), ex=("!" in t), ell_end=ell_end, ell_start=ell_start,
                words=len(t.split()), who=canon_name(ev.speaker))


def shock_score(text: str) -> float:
    best = 0.0
    for w, rx in L.SHOCK_RX:
        if rx.search(text):
            best = max(best, w)
    return best


@dataclass
class WindowFeatures:
    hook: float = 0.0
    cliff: float = 0.0
    intensity: float = 0.0
    pace: float = 0.0
    standalone: float = 0.0
    dur_pref: float = 0.0
    flags: list[str] = field(default_factory=list)
    n_lines: int = 0
    speakers: list[str] = field(default_factory=list)
    hook_line: str = ""
    hook_t: float = 0.0
    cliff_line: str = ""
    cliff_t: float = 0.0
    cliff_reason: str = ""
    hook_reason: str = ""


class EpisodeIndex:
    def __init__(self, ep: Episode, first_seen: dict[str, int], lead: str):
        self.ep = ep
        self.first_seen = first_seen
        self.lead = lead
        self.lines = [line_features(e) for e in ep.dialogue()]
        self.lines.sort(key=lambda x: (x.start, x.end))
        for i, ln in enumerate(self.lines):
            prev = self.lines[i - 1] if i else None
            nxt = self.lines[i + 1] if i + 1 < len(self.lines) else None
            if prev and (ln.ell_start or (prev.ell_end and (ln.text[:1].islower() or ln.ell_start))) and ln.start - prev.end < 2.5:
                ln.cont_prev = True
            if nxt and (nxt.ell_start or (ln.ell_end and nxt.text[:1].islower())) and nxt.start - ln.end < 2.5:
                ln.cont_next = True
            if prev and prev.q and prev.who != ln.who and ln.start - prev.end < 2.0:
                ln.reply_to_q = True
        self.l_starts = [l.start for l in self.lines]
        self.others = [e for e in ep.events if e.kind != "DIALOGUE"]
        self.o_starts = [e.start for e in self.others]
        for e in self.others:
            # CAMERA text describes framing, so shock words there are often figurative ('betrayal strikes deep').
            # Full weight only for ACTION / SOUND FX; camera text counts half, after removing figurative phrases.
            sc = shock_score(FIGURATIVE.sub("", e.text))
            e.shock = sc * (0.5 if e.kind == "CAMERA" else 1.0)  # type: ignore[attr-defined]
        self.cams = [e for e in ep.events if e.kind == "CAMERA"]
        self.duration = ep.duration
        self.starts, self.ends = self._cut_points()

    # ---------------------------------------------------------------- legal cut points
    def _cut_points(self) -> tuple[list[float], list[float]]:
        starts = sorted({round(c.start, 2) for c in self.cams} | {round(sc.start, 2) for sc in self.ep.scenes})
        ends_raw = {round(c.end, 2) for c in self.cams} | {round(sc.end, 2) for sc in self.ep.scenes}
        ends_raw |= {round(l.end + 0.2, 2) for l in self.lines}
        ends = sorted(ends_raw)
        return [s for s in starts if self.start_ok(s)], [e for e in ends if self.end_ok(e)]

    def crossing(self, t: float, tol: float = 0.25) -> bool:
        """True if a spoken line is in progress at time t (a cut here would chop it)."""
        i = bisect.bisect_right(self.l_starts, t - tol)  # lines starting at/before t-tol
        for l in self.lines[max(0, i - 6):i]:
            if l.start < t - tol and l.end > t + tol:
                return True
        return False

    def start_ok(self, s: float) -> bool:
        if self.crossing(s):
            return False
        first = next((l for l in self.lines if l.start >= s - 0.25), None)
        if first and first.start - s < 3.0 and first.cont_prev:
            return False
        return True

    def end_ok(self, e: float) -> bool:
        if self.crossing(e):
            return False
        last = None
        for l in reversed(self.lines):
            if l.end <= e + 0.3:
                last = l
                break
        if last and last.cont_next and e - last.end < 2.0:
            return False
        return True

    # ---------------------------------------------------------------- window helpers
    def lines_in(self, s: float, e: float) -> list[Line]:
        lo = bisect.bisect_left(self.l_starts, s - 0.25)
        out = []
        for l in self.lines[lo:]:
            if l.start >= e:
                break
            if l.end <= e + 0.3:
                out.append(l)
        return out

    def others_in(self, s: float, e: float, kinds=None) -> list[Event]:
        lo = bisect.bisect_left(self.o_starts, s - 0.25)
        out = []
        for ev in self.others[lo:]:
            if ev.start >= e:
                break
            if kinds is None or ev.kind in kinds:
                out.append(ev)
        return out

    # ---------------------------------------------------------------- feature extraction
    def hook(self, s: float, f: WindowFeatures) -> float:
        win = self.lines_in(s, s + 3.0)
        first = win[0] if win else None
        strength = 0.0
        immediacy = 0.0
        if first and first.start - s <= 3.0:
            immediacy = 1 - max(0.0, first.start - s) / 3.0
            strength = 0.45 * first.inten + 0.35 * min(1.0, first.hookw / 1.5) + 0.20 * (1.0 if (first.ex or first.q) else 0.0)
            if first.words > 16:
                strength *= 0.85
            fw = first.text.lower().split()[0].strip(",.?!") if first.text else ""
            if fw in CONT_STARTERS:
                strength -= 0.2
            if first.reply_to_q:
                strength -= 0.2
            if first.words <= 2 and not first.ex:
                strength -= 0.2
            if first.ev.is_vo:
                strength -= 0.25
            strength = clip(strength)
        vis = 0.0
        vis_txt = ""
        for ev in self.others_in(s, s + 3.0):
            sc = getattr(ev, "shock", 0.0)
            if sc > vis:
                vis, vis_txt = sc, ev.text
        est = any("establishing" in c.text.lower() or c.text.lower().startswith("wide establishing") for c in self.cams
                  if s - 0.2 <= c.start <= s + 0.2)
        h = max(strength * (0.6 + 0.4 * immediacy), 0.85 * vis) + 0.1 * min(strength, vis)
        if est and not first:
            h -= 0.2
        h = clip(h)
        if first and strength * (0.6 + 0.4 * immediacy) >= 0.85 * vis:
            f.hook_line = f'{first.who.title()}: "{first.text}"'
            f.hook_t = first.start
            f.hook_reason = "opens on a charged line" + (" with a question" if first.q else (" shouted" if first.ex else ""))
        elif vis:
            f.hook_line = vis_txt[:140]
            f.hook_t = s
            f.hook_reason = "opens on a visual shock"
        elif first:
            f.hook_line = f'{first.who.title()}: "{first.text}"'
            f.hook_t = first.start
            f.hook_reason = "opens mid-dialogue (weak hook)"
        return h

    def cliff(self, e: float, s: float, f: WindowFeatures) -> float:
        # every non-dialogue event that is ON SCREEN during the last 7 s (a long closing shot may START earlier than that)
        tail = [ev for ev in self.others_in(s, e + 0.3) if ev.end > e - 7.0 and ev.start < e]
        tail_txt = " ".join(ev.text for ev in tail)
        tension = clip(len(L.TENSION.findall(tail_txt)) / 3.0)
        warm = clip(len(L.WARM.findall(tail_txt)) / 3.0)
        marker = 1.0 if L.CLIFF_MARKER.search(tail_txt) else 0.0
        at_end = 1.0 if e >= self.duration - 0.6 else 0.0
        at_scene = 1.0 if any(abs(sc.end - e) < 0.4 for sc in self.ep.scenes) else 0.0
        win = self.lines_in(s, e)
        last = win[-1] if win else None
        open_line = 0.0
        res = 0.0
        if last:
            t = last.text.strip()
            if t.endswith("?"):
                open_line = 0.7
            elif t.endswith("!"):
                open_line = 0.35
            elif last.ell_end:
                open_line = 0.5
            open_line += 0.3 * min(1.0, last.hookw / 1.2) + 0.2 * last.inten
            open_line = clip(open_line)
            if L.RESOLUTION.search(t):
                res = 0.25
            if e - last.end > 5.0:     # long dead tail after the last word weakens the cut
                open_line *= 0.7
        c = (0.30 * tension + 0.30 * open_line + 0.30 * marker * (1 - 0.6 * warm) + 0.25 * at_end + 0.05 * at_scene
             - 0.35 * warm - res)
        why = []
        if at_end: why.append("ends on the episode's own cliffhanger beat")
        if last and last.text.strip().endswith("?"): why.append("last line is an unanswered question")
        elif last and last.hookw >= 1.0: why.append("last line is a threat/reveal")
        if tension >= 0.6: why.append("tense closing visuals")
        if warm >= 0.4: why.append("WARNING: warm/resolved tone at the cut")
        f.cliff_reason = "; ".join(why) or "weak cut"
        if last:
            f.cliff_line = f'{last.who.title()}: "{last.text}"'
            f.cliff_t = last.start
        elif tail:
            f.cliff_line = tail[-1].text[:140]
            f.cliff_t = tail[-1].start
        return clip(c)

    def body(self, spans: list[tuple[float, float]], f: WindowFeatures) -> None:
        lines: list[Line] = []
        for s, e in spans:
            lines += self.lines_in(s, e)
        dur = sum(e - s for s, e in spans)
        f.n_lines = len(lines)
        if lines:
            f.intensity = clip(sum(l.inten for l in lines) / len(lines))
            seq = [l.who for l in lines]
            alt = sum(1 for a, b in zip(seq, seq[1:]) if a != b)
            conflict = 1.0 if (len(set(seq)) >= 2 and alt >= 3) else 0.5 if len(set(seq)) >= 2 else 0.2
            f.intensity = clip(0.8 * f.intensity + 0.2 * conflict)
        speech = sum(min(l.end, e) - max(l.start, s) for s, e in spans for l in lines if min(l.end, e) > max(l.start, s))
        sp = clip(speech / (0.6 * dur)) if dur else 0
        vo = sum(1 for l in lines if l.ev.is_vo) / len(lines) if lines else 0
        gap = 0.0
        for s, e in spans:
            ls = [l for l in lines if s <= l.start < e]
            marks = [s] + [x for l in ls for x in (l.start, l.end)] + [e]
            marks.sort()
            gap = max(gap, max((b - a) for a, b in zip(marks, marks[1:])) if len(marks) > 1 else 0)
        f.pace = clip(sp - (0.3 if gap > 8.0 else 0.0) - (0.3 if vo > 0.4 else 0.0))
        text = " ".join(l.text for l in lines)
        cues = len(set(m.lower() for m in L.PREMISE.findall(text)))
        speakers = []
        for l in lines:
            if l.who and l.who not in speakers:
                speakers.append(l.who)
        f.speakers = speakers
        # the lead is the show itself: a stranger learns who she is from the clip, so she carries no 'context debt'
        deb = [clip((self.ep.number - self.first_seen.get(w, self.ep.number)) / 15.0) for w in speakers
               if w not in GENERIC_SPEAKERS and w != self.lead]
        spk_debt = sum(deb) / len(deb) if deb else 0.0
        prior = clip((self.ep.number - 1) / 60.0)
        debt = 0.5 * prior + 0.5 * spk_debt
        lead_present = 1.0 if sum(1 for l in lines if l.who == self.lead) >= 2 else 0.0
        f.standalone = clip(0.45 * clip(cues / 4.0) + 0.30 * (1 - debt) + 0.25 * lead_present)
        mid = 42.0
        f.dur_pref = 1.0 - 0.5 * min(1.0, abs(dur - mid) / 30.0)
        ev_text = " ".join(ev.text for s, e in spans for ev in self.others_in(s, e))
        alltxt = ev_text + " " + text
        flags = []
        if L.SEXUAL.search(ev_text):
            flags.append("sexual-content")
        if len(L.VIOLENT.findall(alltxt)) >= 2:
            flags.append("violence/torture")
        f.flags = flags
