"""Parse the screenplay .txt format into typed, timestamped events.

Format (per block):
    **CAMERA:** | **ACTION:** | **SOUND FX:** | **SPEAKER (tags):**
    Start: (mm:ss.ff) | End: (mm:ss.ff)
    free text (dialogue is in quotes)
Scene headers: 'SCENE 01', 'Scene heading: ...' (case varies), 'Scene start/end: ...'.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

TS_RE = re.compile(r"(\d+):(\d{1,2}(?:\.\d+)?)")
TIME_LINE = re.compile(
    r"Start:\s*\(\s*(\d+:\d{1,2}(?:\.\d+)?)\s*\)\s*\|\s*End:\s*\(\s*(\d+:\d{1,2}(?:\.\d+)?)\s*\)", re.I
)
HEADER = re.compile(r"^\*\*(.+?):\*\*\s*$")
STAGE_DIR = re.compile(r"\[[^\]]*\]")          # [chuckles], [A firm tap...]
TITLES = {"LADY", "LORD", "THE", "DOWAGER", "SIR", "MISS", "MRS", "MR", "DUCHESS", "DUKE"}


def to_sec(s: str) -> float:
    m = TS_RE.search(s)
    return int(m.group(1)) * 60 + float(m.group(2))


def fmt(t: float) -> str:
    t = max(0.0, t)
    return f"{int(t // 60):02d}:{t % 60:05.2f}"


@dataclass
class Event:
    kind: str                 # CAMERA | ACTION | SFX | DIALOGUE
    start: float
    end: float
    text: str
    speaker: str = ""         # DIALOGUE only (raw label, e.g. "LADY JULIANA")
    tags: list[str] = field(default_factory=list)   # e.g. ["Cold", "Commanding", "O.S."]
    scene: int = 0
    idx: int = 0

    @property
    def dur(self) -> float:
        return max(0.0, self.end - self.start)

    @property
    def is_vo(self) -> bool:
        t = " ".join(self.tags).lower()
        return "v.o" in t


@dataclass
class Scene:
    idx: int
    heading: str
    start: float
    end: float


@dataclass
class Episode:
    number: int
    logline: str
    continuity: str
    events: list[Event]
    scenes: list[Scene]
    path: str = ""

    @property
    def duration(self) -> float:
        return max((e.end for e in self.events), default=0.0)

    def dialogue(self) -> list[Event]:
        return [e for e in self.events if e.kind == "DIALOGUE"]


def canon_name(label: str) -> str:
    """'LADY JULIANA' / 'JULIANA' -> 'JULIANA'. Cheap alias merge; real aliasing needs a character list."""
    toks = [t for t in re.sub(r"[^A-Za-z' ]", " ", label).upper().split() if t not in TITLES]
    return " ".join(toks) if toks else label.upper()


def _classify(label: str) -> tuple[str, str, list[str]]:
    up = label.strip().upper()
    if up.startswith("CAMERA"):
        return "CAMERA", "", []
    if up.startswith("ACTION"):
        return "ACTION", "", []
    if up.startswith("SOUND FX") or up.startswith("SFX"):
        return "SFX", "", []
    m = re.match(r"^([^()]+?)\s*(\(.*)?$", label.strip())
    speaker = (m.group(1) if m else label).strip().upper()
    tags: list[str] = []
    for grp in re.findall(r"\(([^)]*)\)", label):
        tags += [t.strip() for t in grp.split(",") if t.strip()]
    return "DIALOGUE", speaker, tags


def parse_text(raw: str, path: str = "") -> Episode:
    lines = raw.replace("\r", "").split("\n")
    number, logline, continuity = 0, "", ""
    events: list[Event] = []
    scenes: list[Scene] = []
    scene_idx = 0
    cur_scene: dict | None = None
    i = 0
    n = len(lines)
    while i < n:
        ln = lines[i].strip()
        up = ln.upper()
        if up.startswith("EPISODE NUMBER"):
            m = re.search(r"(\d+)", ln)
            number = int(m.group(1)) if m else 0
        elif up.startswith("EPISODE LOGLINE"):
            logline = ln.split(":", 1)[1].strip()
        elif up.startswith("CONTINUITY NOTES"):
            continuity = ln.split(":", 1)[1].strip()
        elif re.match(r"^SCENE\s+\d+\s*$", up):
            scene_idx += 1
            cur_scene = {"idx": scene_idx, "heading": "", "start": 0.0, "end": 0.0}
            scenes.append(Scene(scene_idx, "", 0.0, 0.0))
        elif up.startswith("SCENE HEADING") and scenes:
            scenes[-1].heading = ln.split(":", 1)[1].strip()
        elif up.startswith("SCENE START") and scenes:
            scenes[-1].start = to_sec(ln.split(":", 1)[1])
        elif up.startswith("SCENE END") and scenes:
            scenes[-1].end = to_sec(ln.split(":", 1)[1])
        else:
            m = HEADER.match(ln)
            if m and i + 1 < n:
                label = m.group(1).strip()
                # find timing line (next non-empty)
                j = i + 1
                while j < n and not lines[j].strip():
                    j += 1
                tm = TIME_LINE.search(lines[j]) if j < n else None
                if tm:
                    start, end = to_sec(tm.group(1)), to_sec(tm.group(2))
                    k = j + 1
                    buf = []
                    while k < n:
                        s = lines[k].strip()
                        if not s:
                            break
                        if HEADER.match(s) or re.match(r"^SCENE\s+\d+\s*$", s.upper()):
                            break
                        buf.append(s)
                        k += 1
                    text = " ".join(buf).strip()
                    kind, speaker, tags = _classify(label)
                    if kind == "DIALOGUE":
                        text = text.strip().strip('"\u201c\u201d').strip()
                    text = STAGE_DIR.sub("", text).strip() if kind in ("DIALOGUE",) else text
                    events.append(Event(kind, start, end, text, speaker, tags, scene=scene_idx))
                    i = k
                    continue
        i += 1
    events.sort(key=lambda e: (e.start, {"CAMERA": 0, "ACTION": 1, "SFX": 2, "DIALOGUE": 3}[e.kind], e.end))
    for k, e in enumerate(events):
        e.idx = k
    return Episode(number, logline, continuity, events, scenes, path)


def load_dir(directory: str | Path) -> list[Episode]:
    """Load every episode-*.txt in a directory; de-duplicate by episode number (keeps first file)."""
    eps: dict[int, Episode] = {}
    for p in sorted(Path(directory).glob("*.txt")):
        ep = parse_text(p.read_text(encoding="utf-8", errors="replace"), str(p))
        if ep.number and ep.number not in eps and ep.events:
            eps[ep.number] = ep
    return [eps[k] for k in sorted(eps)]
