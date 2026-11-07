import json, sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from promo_finder.parse import parse_text, canon_name
from promo_finder.features import EpisodeIndex
from promo_finder.candidates import continuous, find_for_episode, DEFAULT_WEIGHTS
from promo_finder import llm

FIX = (Path(__file__).parent / "fixture_ep.txt").read_text()


def index():
    ep = parse_text(FIX)
    return EpisodeIndex(ep, {"MARA": 1, "DEV": 1}, "MARA")


class TestParse(unittest.TestCase):
    def test_counts_and_fields(self):
        ep = parse_text(FIX)
        self.assertEqual(ep.number, 1)
        d = ep.dialogue()
        self.assertEqual(len(d), 6)
        self.assertEqual(d[0].speaker, "MARA")
        self.assertIn("Furious", d[0].tags)
        self.assertEqual(d[0].text, "You sold my shop behind my back!")
        self.assertAlmostEqual(ep.duration, 30.0)

    def test_canon_name_strips_titles(self):
        self.assertEqual(canon_name("LADY JULIANA"), "JULIANA")


class TestBoundaries(unittest.TestCase):
    def test_no_cut_inside_a_spoken_line(self):
        ix = index()
        self.assertTrue(ix.crossing(2.0))      # Mara is mid-line at 2.0s
        self.assertFalse(ix.start_ok(2.0))
        self.assertFalse(ix.end_ok(6.0))       # Dev is mid-line at 6.0s

    def test_split_sentence_is_not_cut_between_halves(self):
        ix = index()
        dev, mara = ix.lines[1], ix.lines[2]
        self.assertTrue(dev.ell_end and mara.cont_prev and dev.cont_next)
        self.assertFalse(ix.start_ok(9.0))     # would open on '...and I will never sign.'

    def test_candidates_respect_duration_and_legality(self):
        ix = index()
        cs = continuous(ix, DEFAULT_WEIGHTS, 20.0, 60.0)
        self.assertTrue(cs, "expected at least one candidate")
        for c in cs:
            (s, e), = c.segments
            self.assertTrue(20.0 <= e - s <= 60.0)
            self.assertTrue(ix.start_ok(s) and ix.end_ok(e))


class TestScoring(unittest.TestCase):
    def test_cliffhanger_ending_beats_warm_ending(self):
        ix = index()
        from promo_finder.features import WindowFeatures
        f1, f2 = WindowFeatures(), WindowFeatures()
        hot = ix.cliff(30.0, 9.0, f1)
        last_cam = [e for e in ix.ep.events if e.kind == "CAMERA"][-1]       # the closing camera cue (not the last dialogue line)
        last_cam.text = "Warm, peaceful, tender embrace as the music fades out softly, content and safe."
        cool = ix.cliff(30.0, 9.0, f2)
        self.assertGreater(hot, cool)


class TestLLMStage(unittest.TestCase):
    def test_parse_json_handles_fences_and_garbage(self):
        good = '```json\n{"hook":4,"cliffhanger":5,"standalone":3,"boundary_ok":true,"why":"x"}\n```'
        self.assertEqual(llm.parse_json(good)["cliffhanger"], 5)
        self.assertIsNone(llm.parse_json("sorry, no"))
        self.assertIsNone(llm.parse_json('{"hook":"high"}'))

    def test_rerank_blends_and_falls_back(self):
        ix = index()
        cands = find_for_episode(ix, use_stitch=False)
        before = [c.score for c in cands]
        out = llm.rerank("mock", ix, cands)
        self.assertEqual(len(out), len(before))
        self.assertTrue(all(c.llm for c in out))

        def boom(*a, **k): raise RuntimeError("network down")
        ix2 = index(); c2 = find_for_episode(ix2, use_stitch=False); s0 = [c.score for c in c2]
        out2 = llm.rerank("mock", ix2, c2, caller=boom)
        self.assertEqual(sorted(s0), sorted(c.score for c in out2))   # rule scores untouched on failure
        self.assertTrue(all("error" in c.llm for c in out2))


if __name__ == "__main__":
    unittest.main(verbosity=2)
