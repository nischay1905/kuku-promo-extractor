
# 🎬 Promo Finder

Reads timestamped microdrama screenplays and shortlists **20–60 second promo clips** featuring a strong hook in the first 3 seconds, an unresolved ending, and (as far as a script alone can tell) enough context for a stranger to understand.

It outputs the exact episode, start/end timestamps for every segment, the hook, the cliffhanger, and a one-line explanation, then ranks clips for posting.

**Promo Finder is a shortlisting tool for human editors, not an autopilot.** See [Quality](#-quality) for measured results and known limitations.

---

## 🌐 Live Demo

🚀 **Try Promo Finder:** [Launch Streamlit App](https://kuku-promo-extractor-5zuy3r98thtngxeybcdsft.streamlit.app/)

Upload screenplay `.txt` files and generate ranked promo clips directly through the web application.

## 🚀 Run It

**Requirements:** Python 3.10+ (standard library only).

Place screenplay `.txt` files inside the `./data` directory. The confidential screenplay pack is not included in this repository.

```bash
# Run the rule-based pipeline (offline, approximately 20 seconds for 50 episodes)
python -m promo_finder run --input data --out outputs

# Validate every generated promo against hard rules
python eval/validate_outputs.py outputs data

# Run unit tests (uses a tiny invented screenplay)
python -m unittest discover -s tests

# Estimate token usage and cost for the optional LLM stage (no API call)
python -m promo_finder cost --input data
```

### Useful CLI Flags

| Flag | Description |
|---|---|
| `--per-ep 2` | Maximum number of candidates per episode |
| `--min-score 0.60` | Minimum promo score threshold |
| `--top 10` | Number of top-ranked promos |
| `--no-stitch` | Disable stitched teaser-payoff clips |
| `--weights w.json` | Override scoring weights |

---

## 🌐 Web App (Streamlit)

Install dependencies and launch the web application:

```bash
pip install -r requirements.txt
streamlit run app.py
```

**How to use:**
1. Open the Streamlit application.
2. Upload episode `.txt` files using the sidebar.
3. Press **Find Promos**.
4. Review the shortlisted promo clips and their rankings.

### Deployment

Deploy directly using [Streamlit Community Cloud](https://streamlit.io/cloud).

The repository must contain `app.py` and `requirements.txt` at its root.

---

## ⚙️ What It Does

### 1. Parse (`parse.py`)

Converts timestamped screenplay blocks into structured events.

- Supports `CAMERA`, `ACTION`, `SOUND FX`, and `SPEAKER (tags)` blocks.
- Extracts `Start` and `End` timestamps.
- Converts each block into a typed event.
- Deduplicates episode files using episode numbers.

**Validation on the complete 50-episode pack:**
- 3,727 timing lines processed.
- 3,727 events successfully extracted.

### 2. Legal Cut Points (`features.py`)

Ensures every selected clip respects screenplay boundaries.

- Clips can only start at a camera cut.
- Clips can end at a camera cut or line end.
- Spoken lines are never chopped.
- Split sentences are never cut mid-thought.

These constraints are enforced directly in code, not left to the language model.

### 3. Candidate Generation (`candidates.py`)

Generates two types of promo candidates:

**Continuous clips**
- Every legal window between 20 and 60 seconds.

**Stitched teaser-payoff clips**
- Combines an opening teaser with a later payoff.
- Requires at least 8 seconds of skipped content.
- Requires the same speakers in both segments.
- Applies an additional scoring penalty so stitched clips must clearly outperform continuous alternatives.

Cross-episode joins are not generated.

### 4. Explainable Scoring

Each candidate receives a rule-based score using the following weighted features:

| Feature | Weight |
|---|---:|
| Hook | 0.28 |
| Cliffhanger | 0.28 |
| Intensity | 0.14 |
| Pace | 0.10 |
| Standalone | 0.12 |
| Duration | 0.08 |

Additional penalties apply to flagged content.

**Hook Detection**
- Delivery tags.
- High-stakes vocabulary.
- Accusation patterns.
- Physical action within the first 3 seconds.
- Penalties for opening with a reply, continuation (e.g., "...but", "And..."), or voice-over.

**Cliffhanger Detection**
- Episode-ending beats.
- Unanswered questions.
- Threats in the final line.
- Tense closing visuals.
- Penalties for warm or resolved endings.

**Standalone Score**
- Detects stakes and relationship-related vocabulary.
- Estimates context debt: how much prior story information a new viewer would need to understand the scene.

### 5. Promo Selection (`select.py`)

Ranks and selects the strongest candidates.

- Applies non-maximum suppression within each episode.
- Uses posting-order priority across episodes.
- Applies a diversity penalty to avoid repetitive selections.
- Selects a maximum of one promo per episode.
- Requires the top 10 to contain both a strong hook and an open ending.

### 6. Optional LLM Evaluation (`llm.py`)

Supports three providers:

- `anthropic`
- `openai`
- `mock`

The LLM evaluates only the shortlisted candidates (approximately 3 candidates per episode).

It returns:
- Hook score.
- Cliffhanger score.
- Standalone score.
- Boundary validation.
- One-line explanation.
- Optional on-screen caption.

**Important:** The LLM cannot invent timestamps. It can only evaluate windows whose cut points have already been validated by the code.

The model is configurable using environment variables:

```bash
PROMO_LLM_MODEL
OPENAI_BASE_URL
```

The OpenAI-compatible endpoint can be switched using `OPENAI_BASE_URL`.

**Testing status:** Only the `mock` provider is exercised by the tests. Live API endpoints remain untested because no API key was available. All reported evaluation results are rule-based only.

---

## 📂 Output Files

The pipeline generates the following files inside `outputs/`:

| File | Description |
|---|---|
| `promos_all.csv` | All selected promos in CSV format |
| `promos_all.json` | All selected promos in JSON format |
| `promos_ranked_top.md` | Ranked promo posting order |
| `episode_candidates/ep_XX.json` | Top 3 candidates per episode, including transcripts |
| `run_log.json` | Execution logs and run details |

Each selected promo includes:
- Episode number.
- Segment timestamps and ordering.
- Hook description.
- Cliffhanger description.
- One-line explanation.
- Content flags.
- Individual feature scores.

---

## 📊 Quality

Evaluation was conducted using a small synthetic golden set of 22 episodes.

The labels were generated synthetically using AI, without human editor review, before the code was developed.

The dataset was divided into development and held-out subsets.

### Held-out Evaluation

| Version | Top-1 | Top-2 | Top-3 |
|---|---:|---:|---:|
| v4 (clean evaluation) | 5/12 | 10/12 | 12/12 |
| v5 (after defect fixes) | 5/12 | 11/12 | 12/12 |

**Evaluation caveat:** The v5 results are optimistic because three defects were identified and fixed after reviewing the earlier outputs. The failures were therefore no longer completely unseen.

### Manual Audit

An AI-assisted manual audit of the top 10 selected promos found that approximately half were post-ready without further editing.

For the complete iteration history, see:

`eval/iteration_log.md`

---

## 📈 Scaling to Every Show

The rule-based pipeline runs in seconds per show and has no inference cost.

### LLM Cost Estimate

For the complete 50-episode screenplay pack:

| Metric | Estimate |
|---|---:|
| Input tokens | ~63,000 |
| Output tokens | ~15,000 |
| Estimated API cost | $0.14–$0.42 |

These token figures were measured from actual prompts and recorded in:

`eval/cost_estimate.txt`

The workflow reduces manual effort by allowing editors to review approximately one shortlisted promo per episode instead of watching every episode in full.

### Requirements for a New Show

1. Screenplays must follow the same timestamped format.
2. Verify that the lead character is detected correctly.
3. Adjust vocabulary lists if the show's genre or language differs.
4. Replace synthetic evaluation labels with real editor selections or historical promo performance data.

---

## ⚠️ Known Limitations

1. **English-only lexicons:** The current scoring vocabulary is English-only and tuned for melodrama. Other languages and genres require customized word lists or LLM evaluation.

2. **Text-only scoring:** The system cannot analyze audio or actual video. It cannot recognize facial expressions, acting quality, or visually striking shots.

3. **Speaker alias limitations:** Speaker aliases are not resolved. For example, the same character may appear as "Former Groom" and "Gerald", making context-debt estimation approximate.

4. **Emotional delivery bias:** The system rewards emotional delivery tags and may select emotionally intense but low-stakes scenes (Episode 20) or resolved speeches (Episode 2).

5. **Camera-cut dependency:** Clips can only start at camera cuts. This may miss hooks that begin during an existing shot (e.g., Episode 24, where the whip crack begins one second before the cut).

6. **Fixed score threshold:** The absolute 0.60 cutoff can exclude good clips. Four of the twelve held-out golden beats were missing from the final list, although some remained in the ranked episode candidates.

7. **Limited spoiler awareness:** The system uses only a mild late-episode penalty and does not perform comprehensive spoiler detection.

8. **Basic content safety detection:** Platform-safety flags rely on crude regex-based matching.

9. **Small synthetic evaluation set:** The evaluation uses one synthetic AI labeller and 22 episodes, without human editor validation. It should be treated as a sanity check, not a reliable benchmark.

**Recommendation:** Before relying on the system in production, replace `eval/golden_set.json` with real editor-selected clips or historical high-performing promos and conduct a human-reviewed evaluation.

---

## 🛠️ Technology Stack

- **Language:** Python 3.10+
- **Interface:** Streamlit
- **Scoring:** Explainable rule-based ranking
- **Optional AI:** Anthropic / OpenAI-compatible APIs
- **Testing:** Python `unittest`
- **Data Formats:** TXT, CSV, JSON, Markdown

---

## 🎯 Project Objective

Promo Finder aims to make short-form microdrama promotion more efficient by automatically identifying potentially engaging, self-contained, and emotionally compelling scenes.

It combines deterministic screenplay parsing, legally validated clip boundaries, explainable scoring, and optional LLM-based evaluation to create an editor-friendly promo shortlist.

**The final creative decision remains with the human editor.**
