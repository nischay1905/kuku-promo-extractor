"""Streamlit front-end for promo-finder (runs locally or on a Hugging Face Space).

Upload screenplay .txt files -> shortlist of 20-60 s promos with hook, cliffhanger, why, ranked for posting.
Nothing is stored: uploads are processed in a temp folder for the session.
"""
import hashlib
import json
import os
import tempfile
from pathlib import Path

import pandas as pd
import streamlit as st

from promo_finder.cli import run

st.set_page_config(page_title="Promo Finder", page_icon="🎬", layout="wide")
DEMO = Path(__file__).parent / "tests" / "fixture_ep.txt"

st.title("🎬 Promo Finder")
st.caption("Finds 20–60 s promo clips (hook in 3 s → unresolved ending → makes sense alone) in microdrama screenplays. "
           "A shortlist for an editor, not final picks.")

with st.sidebar:
    st.header("1 · Input")
    files = st.file_uploader("Screenplay .txt files (one per episode)", type=["txt"], accept_multiple_files=True)
    use_demo = st.button("Use the tiny invented demo script")
    st.header("2 · Settings")
    min_score = st.slider("Minimum score", 0.0, 0.9, 0.60, 0.01, help="Lower = more promos, more weak ones.")
    per_ep = st.slider("Max promos per episode", 1, 3, 2)
    top_n = st.slider("Size of 'post first' list", 3, 20, 10)
    stitch = st.checkbox("Allow stitched 'teaser + payoff' clips", True)
    st.header("3 · Optional LLM re-rank")
    provider = st.selectbox("Provider", ["off (rule-based only)", "anthropic", "openai"])
    api_key = st.text_input("API key (kept in this session only)", type="password") if provider != "off (rule-based only)" else ""
    model = st.text_input("Model name (blank = default)") if provider != "off (rule-based only)" else ""
    if provider != "off (rule-based only)":
        st.warning("The LLM stage is implemented but was only tested with a mock provider. Results below are rule-based unless you add a key.")
    go = st.button("Find promos", type="primary")

if use_demo:
    st.session_state["demo"] = True
if files:
    st.session_state["demo"] = False

sources = {f.name: f.getvalue() for f in files} if files else ({DEMO.name: DEMO.read_bytes()} if st.session_state.get("demo") else {})
if not sources:
    st.info("Upload episode files (or click the demo button) in the sidebar, then press **Find promos**. "
            "Expected format: blocks of `**CAMERA:**`, `**ACTION:**`, `**SPEAKER (tags):**` each followed by `Start: (mm:ss.ff) | End: (mm:ss.ff)`.")
    st.stop()
st.write(f"**{len(sources)} file(s) loaded.**" + (" (demo script: a 30-second invented scene, so expect only a couple of clips)" if st.session_state.get("demo") else ""))


@st.cache_data(show_spinner=False)
def analyse(blob_key: str, blobs: dict, min_score, per_ep, top_n, stitch, provider, model):
    with tempfile.TemporaryDirectory() as td:
        inp, out = Path(td, "in"), Path(td, "out")
        inp.mkdir()
        for name, data in blobs.items():
            (inp / name).write_bytes(data)
        if model:
            os.environ["PROMO_LLM_MODEL"] = model
        llm = None if provider.startswith("off") else provider
        run(str(inp), str(out), per_ep=per_ep, min_score=min_score, use_stitch=stitch, llm=llm, top_n=top_n)
        data = json.loads((out / "promos_all.json").read_text())
        cands = {}
        for p in (out / "episode_candidates").glob("ep_*.json"):
            d = json.loads(p.read_text())
            cands[d["episode"]] = d["candidates"]
        return data["promos"], cands, (out / "promos_all.csv").read_text(), (out / "promos_ranked_top.md").read_text(), json.loads((out / "run_log.json").read_text())


if go or st.session_state.get("last_key"):
    if provider != "off (rule-based only)" and api_key:
        os.environ["ANTHROPIC_API_KEY" if provider == "anthropic" else "OPENAI_API_KEY"] = api_key
    key = hashlib.md5(b"".join(sorted(k.encode() + v for k, v in sources.items()))).hexdigest()
    st.session_state["last_key"] = key
    with st.spinner("Parsing, scoring every legal window…"):
        promos, cands, csv_text, md_text, log = analyse(key, sources, min_score, per_ep, top_n, stitch, provider, model)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Episodes", log["episodes"])
    c2.metric("Promos found", len(promos))
    c3.metric("Episodes with a promo", len({p["episode"] for p in promos}))
    c4.metric("Run time (s)", log["seconds"])
    if not promos:
        st.warning("No clip scored above the minimum. Lower the slider in the sidebar.")
        st.stop()

    def transcript_for(p):
        for c in cands.get(p["episode"], []):
            if [(s["start_s"], s["end_s"]) for s in c["segments"]] == [(s["start_s"], s["end_s"]) for s in p["segments"]]:
                return c["transcript"]
        return []

    tab1, tab2, tab3 = st.tabs([f"Post first (top {min(top_n, len(promos))})", "All promos", "Download"])
    with tab1:
        for p in promos[:top_n]:
            segs = "  +  ".join(f"Ep {s['episode']}  {s['start']} → {s['end']}" for s in p["segments"])
            with st.container(border=True):
                st.markdown(f"### #{p['global_rank']} · {segs}  \n`{p['duration_s']} s` · {p['kind']} · score **{p['score']}**")
                st.markdown(f"**Hook:** {p['hook']}  \n**Cliffhanger:** {p['cliffhanger']}  \n**Why it works:** {p['why']}")
                if p["flags"]:
                    st.warning("Editor flag: " + ", ".join(p["flags"]))
                if p["context_note"]:
                    st.caption("Context: " + p["context_note"])
                fs = p["feature_scores"]
                st.progress(min(1.0, p["score"]), text="hook {hook} · cliffhanger {cliff} · intensity {intensity} · standalone {standalone}".format(**fs))
                with st.expander("Show transcript of this clip"):
                    st.code("\n".join(transcript_for(p)) or "(no dialogue captured)", language=None)
    with tab2:
        df = pd.DataFrame([{"rank": p["global_rank"], "episode": p["episode"],
                            "segments": " + ".join(f"{s['start']}–{s['end']}" for s in p["segments"]), "sec": p["duration_s"],
                            "kind": p["kind"], "score": p["score"], "hook": p["hook"], "cliffhanger": p["cliffhanger"],
                            "flags": ", ".join(p["flags"])} for p in promos])
        st.dataframe(df, width="stretch", hide_index=True)
    with tab3:
        st.download_button("⬇ promos_all.csv", csv_text, "promos_all.csv", "text/csv")
        st.download_button("⬇ promos_all.json", json.dumps(promos, indent=2, ensure_ascii=False), "promos_all.json", "application/json")
        st.download_button("⬇ promos_ranked_top.md", md_text, "promos_ranked_top.md", "text/markdown")
else:
    st.info("Press **Find promos** in the sidebar.")
