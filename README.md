# promo-finder

Reads timestamped microdrama screenplays and shortlists **20-60 s promo clips**: a hook in the first 3 s, an unresolved ending,
and (as far as a script alone can tell) understandable by a stranger. It outputs exact episode + start/end timestamps for every
segment, the hook, the cliffhanger and a one-line reason, then ranks them for posting.

It is a **shortlister for an editor**, not an autopilot. See "Quality" for measured numbers and known failures.

## Run it (Python 3.10+, standard library only)
```bash
# put the screenplay .txt files in ./data  (NOT included: the pack is confidential)
python -m promo_finder run --input data --out outputs          # rule-based, offline, ~20 s for 50 episodes
python eval/validate_outputs.py outputs data                   # hard-rule check on every promo
python -m unittest discover -s tests                           # tests use a tiny invented script, not the real pack
python -m promo_finder cost --input data                       # token/$ estimate for the optional LLM stage (no API call)
```
Useful flags: `--per-ep 2` `--min-score 0.60` `--top 10` `--no-stitch` `--weights w.json` (override scoring weights).

## Web app (Streamlit / Hugging Face Space)
```bash
pip install -r requirements.txt
streamlit run app.py        # upload episode .txt files in the sidebar, press 'Find promos'
```
To deploy: see `hf_space.zip` (Space-ready folder) or point Streamlit Community Cloud at this repo (`app.py` + `requirements.txt` at root).

## What it does
1. **Parse** (`parse.py`): every block (`CAMERA / ACTION / SOUND FX / SPEAKER (tags)` + `Start|End`) becomes a typed event. Checked on
   all 50 files: 3,727 timing lines in, 3,727 events out. Duplicate episode files are de-duplicated by episode number.
2. **Legal cut points** (`features.py`): a clip may only start on a camera cut and end on a camera/line end, and may **never chop a
   spoken line or a split sentence** ("...far too plain..." / "...and I will not"). Enforced in code, not by the model.
3. **Candidates** (`candidates.py`): every legal 20-60 s window, plus *stitched* "teaser + skip + payoff" clips (>= 8 s skipped,
   same speakers in both halves, extra penalty so they must clearly beat a continuous cut). Cross-episode joins are not generated.
4. **Score** (rules, explainable): `0.28 hook + 0.28 cliffhanger + 0.14 intensity + 0.10 pace + 0.12 standalone + 0.08 duration`,
   minus penalties for flagged content. Hook = delivery tags / stakes words / accusation patterns / physical action in the first 3 s,
   penalised if it opens on a reply, a continuation ("And...", "...but") or a voice-over. Cliffhanger = episode-end beat,
   unanswered question / threat in the last line, tense closing visuals, minus warm/resolved tone. Standalone = stakes/relationship
   words present + "context debt" (how many characters/episodes of prior story it leans on).
5. **Select** (`select.py`): non-max suppression inside an episode; across episodes a posting-order priority with a diversity
   penalty, max one per episode, and a gate that the top 10 must have both a hook and an open ending.
6. **Optional LLM stage** (`llm.py`, `--llm anthropic|openai|mock`): judges only the shortlist (about 3 candidates/episode), returns
   hook / cliffhanger / standalone scores, a boundary check, a one-line reason and an optional on-screen caption. The LLM never
   invents timestamps; it can only score windows whose cut points code already validated. Model is swappable by env var
   (`PROMO_LLM_MODEL`, `OPENAI_BASE_URL` for any OpenAI-compatible endpoint). **Only the `mock` provider is exercised by tests; live
   endpoints are untested here (no API key was available). All reported results are rule-based only.**

## Outputs (`outputs/`, produced by the command above on the full 50-episode pack)
`promos_all.csv|json` (every selected promo: segments in order, hook, cliffhanger, why, flags, feature scores) -
`promos_ranked_top.md` (posting order) - `episode_candidates/ep_XX.json` (top 3 per episode with transcripts) - `run_log.json`.

## Quality (details and failures in the solution doc)
A tiny golden set (22 episodes, labelled by one labeller - the AI assistant that built this, **no human editor review** - written **before** any code ran; `eval/golden_set.json`). Dev half used while
building, held-out half scored once. Held-out v4 (clean): top-1 5/12, top-2 10/12, top-3 12/12. After I fixed three defects found by
auditing the output, v5 held-out is 5/12, 11/12, 12/12 but is **optimistic** (I had seen the failures). Full change history:
`eval/iteration_log.md`. Manual audit of the top 10 (by the same AI): about half post-ready as-is.

## Scaling to every show
Runtime is seconds per show and the rule stage costs nothing. LLM stage on this 50-episode pack: ~63k input / ~15k output tokens
(measured from real prompts, `eval/cost_estimate.txt`), roughly $0.14-0.42 depending on model price. Humans only review ~1 promo per
episode instead of watching every episode. Per new show you need: the same screenplay format; a quick check that the lead is detected.

## Known limitations
- **English-only lexicons** and melodrama-tuned; other languages/genres need their own word lists or the LLM stage.
- Scoring uses **text only**: no audio, no picture. Cannot see a face, an expression, or whether a shot is visually striking.
- Speaker aliases are not resolved (the same person appears as "Former Groom", "Gerald"); "context debt" is therefore approximate.
- Rewards emotional *delivery tags*, so it can pick emotive-but-low-stakes scenes (ep 20) and resolved speeches (ep 2).
- Starts only on camera cuts, so it can miss a hook that begins mid-shot (ep 24: the whip crack starts 1 s before the cut).
- Absolute 0.60 cut-off drops some good clips (4 of 12 held-out golden beats missing from the final list); the ranked candidates
  per episode still contain them. No spoiler awareness beyond a mild late-episode penalty. Platform-safety flags are crude regexes.
- One AI labeller, 22 episodes, no human editor: the evaluation is a sanity check, not a benchmark. Replace `eval/golden_set.json` with real editor picks (or past promos that performed) before trusting any number.
