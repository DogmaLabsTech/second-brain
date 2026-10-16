"""Small tests for the check-up pieces (no network, no models): python3 ask/test_ask_units.py
(not `-m unittest ask/…`: that imports the ask/ folder as `ask` instead of ask.py)."""
import json
import os
import sys
import tempfile
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.environ["BRAIN_STATE"] = tempfile.mkdtemp()
import ask  # noqa: E402
import asklog  # noqa: E402
from expand import expanded_document  # noqa: E402


class Expand(unittest.TestCase):
    def test_question_is_searched_as_said(self):
        lines = expanded_document("how do I reload the bar after editing").splitlines()
        self.assertTrue(lines[0].startswith("lex: "))
        self.assertEqual(lines[1], "vec: how do I reload the bar after editing")
        self.assertLessEqual(len(lines), 3)


class FirstSentence(unittest.TestCase):
    def setUp(self):
        self.got = []
        ask.EMIT[:] = [self.got.append]

    def tearDown(self):
        ask.EMIT[:] = []

    def test_waits_for_winner_and_question(self):
        f = ask.First()
        f.feed(text="Your Top bar note says restart the shell. Then")
        self.assertEqual(self.got, [])
        f.feed(winner=True)
        self.assertEqual(self.got, [])
        f.feed(question=True)
        self.assertEqual(self.got, [{"event": "first", "text": "Your Top bar note says restart the shell."}])
        f.feed(text="Your Top bar note says restart the shell. Then more. And more.")
        self.assertEqual(len(self.got), 1)

    def test_no_early_sentence_before_it_ends(self):
        f = ask.First()
        f.feed(text="Your Top bar note says restart", winner=True, question=True)
        self.assertEqual(self.got, [])


class Record(unittest.TestCase):
    def test_log_and_rate(self):
        qid = asklog.new_id()
        asklog.log_ask(qid, "q?", {"kind": "answer", "answer": "a.", "writer": "haiku",
                                   "sources": [{"path": "~/x.md"}], "ms": 5, "steps": {}}, "test")
        asklog.rate(qid, "down", "wrong note")
        self.assertEqual(asklog.read(asklog.ASKS)[-1]["id"], qid)
        self.assertEqual(asklog.read(asklog.RATINGS)[-1], {**asklog.read(asklog.RATINGS)[-1], "id": qid, "verdict": "down"})
        self.assertEqual(oct(os.stat(asklog.STATE).st_mode & 0o777), "0o700")
        with self.assertRaises(ValueError):
            asklog.rate(qid, "meh")


class NewerFirst(unittest.TestCase):
    def test_new_note_wins_a_close_call_only(self):
        d = tempfile.mkdtemp()
        old, new = os.path.join(d, "old.md"), os.path.join(d, "new.md")
        for p in (old, new):
            open(p, "w").close()
        os.utime(old, (time.time() - 200 * 86400,) * 2)
        close = ask.newer_first([{"path": old, "score": 0.5}, {"path": new, "score": 0.45}])
        self.assertEqual(close[0]["path"], new)
        clear = ask.newer_first([{"path": old, "score": 1.0}, {"path": new, "score": 0.33}])
        self.assertEqual(clear[0]["path"], old)


class SayAgain(unittest.TestCase):
    """Router upgrade 2: a decider's own "unsure", or the local decider under its sure-bar, gets "Sorry, say that again?"."""

    def run_ask(self, q, intent):
        saved = ask.decide, ask.search, ask.answer_question
        ask.decide = lambda *a, **k: intent
        ask.search = lambda *a, **k: []
        ask.answer_question = lambda *a, **k: (ask.NOT_FOUND, "none")
        try:
            return ask.ask(q)
        finally:
            ask.decide, ask.search, ask.answer_question = saved

    def test_unsure_from_local_decider_or_below_bar(self):
        for intent in ({"label": "unsure", "confidence": 0.97, "by": "local_decider"},
                       {"label": "unsure", "confidence": 0.9, "by": "fallback", "reason": "below-bar"}):
            out = self.run_ask("I've seen this so like", intent)
            self.assertEqual((out["answer"], out.get("again")), (ask.SAY_AGAIN, True))

    def test_timeout_or_rule_keeps_the_old_way(self):
        out = self.run_ask("what port does rockceen run on", {"label": "unsure", "confidence": 0.0, "by": "timeout"})
        self.assertEqual(out["answer"], ask.NOT_FOUND)
        out = self.run_ask("what port does rockceen run on", {"label": "unsure", "confidence": 0.3, "by": "fallback"})
        self.assertEqual(out["answer"], ask.NOT_FOUND)
        out = self.run_ask("pause the music", {"label": "unsure", "confidence": 0.9, "by": "local_decider"})
        self.assertEqual(out["kind"], "job")   # a word rule fits: the rule still wins


if __name__ == "__main__":
    unittest.main()
