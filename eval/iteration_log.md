> Written by Claude (the AI assistant that built this tool) during the build session. 'I' / 'me' below = Claude. The golden set was
> labelled by Claude, not by a human editor.

# Iteration log (every change made after seeing results, in order)

Rule: tuning decisions use the DEV split only. HELD-OUT is scored once, at the end.

## v1 - initial weights (hook .28, cliff .28, intensity .14, pace .10, standalone .12, dur .08)
DEV: lenient hit@1 7/10, hit@2 10/10; strict (IoU>=0.4) hit@1 5/10, hit@3 9/10.
Manual audit of global top 14 found:
- BUG: 'visual shock' fires on camera-direction prose, not physical action. Ep3 #6 'hook' = "betrayal strikes deep"
  (figurative 'strikes'); ep27 #2 = "expression freezing". Several top hooks are camera descriptions, not speech or action.

## v2 - fix: shock words in CAMERA prose count half, figurative phrases stripped
DEV: lenient hit@1 6/10, hit@3 10/10; strict hit@1 3/10, hit@3 9/10.  (Went DOWN after a correct bug fix: metric is noisy at n=10,
ep9/ep27 swapped rank 1<->2 when a stitched candidate appeared. Kept the fix because it is right in principle; did NOT tune weights to recover.)
Reading: recall is good (golden beat in top 3 for 9/10 strict), ordering inside an episode is noisy -> this is a SHORTLISTER;
final pick per episode wants an LLM/human re-rank.
Audit of global top 10 (by score): includes a villains-tea-party scene (ep20) and several mid-scene starts that need context.

## v3 - posting-order policy (not a change to candidate scoring)
'Best clip' != 'first clip to post'. Top-10 ordering now uses priority = score + 0.25*standalone - 0.10*(ep-1)/(N-1):
a stranger must be able to follow it, and late-arc clips spoil the premise. Candidate scoring and shortlist unchanged.

## v4 - BUG FOUND BY A UNIT TEST: cliff() ignored closing shots that started >7s before the cut
`others_in(e-7, e)` filtered on event START, so a long final shot ('slow push-in ... cliffhanger hold') never reached the
cliffhanger-marker / tension / warmth checks. Fixed to include every event on screen during the last 7s.
DEV after v4: lenient hit@1 9/10, hit@2 10/10; strict hit@1 7/10, hit@3 9/10.   (improvement came from a bug fix, not weight tuning)

## FINAL (v4, min-score 0.60, <=2 per episode). Held-out scored once, no changes after seeing it.
HELD-OUT (n=12): lenient hit@1 5/12, hit@2 10/12, hit@3 12/12; strict (IoU>=0.4) hit@1 5/12, hit@3 11/12; golden beat inside the FINAL
selection (score>=0.60, <=2/ep) 7/12.   DEV (n=10, used while building): 9/10 / 10/10 / 10/10; strict 7/10, 9/10; in selection 8/10.
=> Dev flatters the tool (I fixed bugs while staring at dev misses). Trust held-out: top-1 ~42%, top-2 ~83%, top-3 100%.
=> The absolute 0.60 cut-off loses 5 of 12 held-out golden beats (ep 2,7,26,29,45). Not tuned afterwards.

## v5 - three defects found by AUDITING the final v4 output (held-out no longer clean after this point)
v4 held-out (clean, scored once): lenient hit@1 5/12, hit@2 10/12, hit@3 12/12; strict hit@1 5/12; in final selection 7/12.
Defects found by reading the output:
 D1 'context debt' treats the LEAD as an unknown character introduced N episodes ago and its prior saturates by ep ~30, so
    standalone ~ 0.0 for every late episode (ep41 explosion: standalone 0.00, score 0.56 -> dropped by the 0.60 cut-off).
    Fix: exclude the lead from speaker debt; prior = (ep-1)/60 instead of /30.
 D2 'bursts into a loud mocking laugh' counted as a visual shock (ep12 #2 hook). Fix: strip 'burst(s/ing) into ...' as figurative.
 D3 Top-10 posting list could contain a promo whose own explanation says 'weak cut' (ep1 #1). Fix: top-10 requires hook>=0.5 and
    cliff>=0.45 (the brief's own definition of a promo); falls back to the rest if fewer than 10 qualify.
v5 results: HELD-OUT (optimistic, I had seen the failures) lenient hit@1 5/12, hit@2 11/12, hit@3 12/12; strict hit@1 5/12, hit@3 11/12; in final selection 8/12.
            DEV unchanged (9/10, 10/10, 10/10; strict 7/10, 9/10; in selection 8/10).   49 promos. validator: 0 violations.
