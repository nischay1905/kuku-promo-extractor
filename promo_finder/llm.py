"""Optional LLM stage: judge the SHORTLIST only (3 candidates/episode), never the whole script.

Why: code is cheap and exact for timestamps/boundaries; an LLM is better at the subjective calls
(is the hook arresting? is the ending really unresolved? would a stranger follow it?) and at writing the one-line reason.

Provider is pluggable via env vars so a stronger model can be swapped in without code changes:
  PROMO_LLM_PROVIDER=anthropic|openai|mock     (CLI --llm sets it)
  PROMO_LLM_MODEL=<model name>                 (default per provider below; check your provider's current model names)
  ANTHROPIC_API_KEY / OPENAI_API_KEY / OPENAI_BASE_URL (any OpenAI-compatible endpoint)
The LLM never invents timestamps: it only scores/annotates candidates whose cut points were already validated by code.
NOTE: only the 'mock' provider has been exercised in this repo's tests; live endpoints are untested here (no API key was available).
"""
from __future__ import annotations

import json
import os
import re
import urllib.request

from .candidates import Candidate
from .features import EpisodeIndex
from .parse import fmt

SYSTEM = (
    "You are a senior editor who cuts 20-60 second vertical promos for short-drama apps (ReelShort/DramaBox style). "
    "A good promo (1) opens on a hook inside 3 seconds, (2) ends on an UNRESOLVED moment, (3) makes sense to someone who has "
    "never seen the show. Judge the candidate clip below. Be strict; most clips are not great. "
    'Reply with ONLY compact JSON: {"hook":1-5,"cliffhanger":1-5,"standalone":1-5,"boundary_ok":true|false,'
    '"why":"one sentence, <=25 words","caption":"optional <=10 word on-screen context line or empty"}'
)
DEFAULTS = {"anthropic": "claude-haiku-5-5", "openai": "gpt-4o-mini", "mock": "mock"}


def build_prompt(ix: EpisodeIndex, c: Candidate) -> str:
    ep = ix.ep
    rows = []
    for s, e in c.segments:
        rows.append(f"--- clip segment {fmt(s)} to {fmt(e)} ---")
        for ev in ep.events:
            if ev.start >= s - 0.25 and ev.start < e and ev.kind in ("DIALOGUE", "ACTION"):
                if ev.kind == "DIALOGUE":
                    rows.append(f"[{fmt(ev.start)}] {ev.speaker.title()} ({', '.join(ev.tags[:2])}): {ev.text}")
                else:
                    rows.append(f"[{fmt(ev.start)}] (action) {ev.text[:160]}")
    return (f"Series context (episode {ep.number} logline): {ep.logline}\n"
            f"Clip is {c.duration:.0f}s ({c.kind}).\n" + "\n".join(rows))


def call(provider: str, system: str, user: str, model: str | None = None, timeout: int = 60) -> str:
    model = model or os.environ.get("PROMO_LLM_MODEL") or DEFAULTS[provider]
    if provider == "mock":
        return json.dumps({"hook": 3, "cliffhanger": 3, "standalone": 3, "boundary_ok": True, "why": "mock judgement", "caption": ""})
    if provider == "anthropic":
        body = {"model": model, "max_tokens": 300, "system": system, "messages": [{"role": "user", "content": user}]}
        req = urllib.request.Request("https://api.anthropic.com/v1/messages", json.dumps(body).encode(),
                                     {"content-type": "application/json", "x-api-key": os.environ["ANTHROPIC_API_KEY"],
                                      "anthropic-version": "2023-06-01"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return "".join(b.get("text", "") for b in json.load(r)["content"])
    if provider == "openai":
        base = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
        body = {"model": model, "max_tokens": 300, "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
        req = urllib.request.Request(base + "/chat/completions", json.dumps(body).encode(),
                                     {"content-type": "application/json", "authorization": "Bearer " + os.environ["OPENAI_API_KEY"]})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.load(r)["choices"][0]["message"]["content"]
    raise ValueError(provider)


def parse_json(txt: str) -> dict | None:
    txt = re.sub(r"^```(?:json)?|```$", "", txt.strip(), flags=re.M).strip()
    m = re.search(r"\{.*\}", txt, re.S)
    if not m:
        return None
    try:
        d = json.loads(m.group(0))
    except json.JSONDecodeError:
        return None
    for k in ("hook", "cliffhanger", "standalone"):
        if not isinstance(d.get(k), (int, float)):
            return None
    return d


def rerank(provider: str, ix: EpisodeIndex, cands: list[Candidate], blend: float = 0.5, caller=call) -> list[Candidate]:
    """Blend rule score with LLM judgement (blend = LLM share). Falls back to the rule score on any failure."""
    for c in cands:
        try:
            d = parse_json(caller(provider, SYSTEM, build_prompt(ix, c)))
        except Exception as ex:           # network/auth/timeout: keep the rule score, say so
            d = None
            c.llm = {"error": f"{type(ex).__name__}: {ex}"[:120]}
        if d:
            c.llm = d
            llm_score = (d["hook"] + d["cliffhanger"] + d["standalone"]) / 15.0
            if d.get("boundary_ok") is False:
                llm_score *= 0.7
            c.score = (1 - blend) * c.score + blend * llm_score
    return sorted(cands, key=lambda c: c.score, reverse=True)
