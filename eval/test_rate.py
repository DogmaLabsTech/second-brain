"""`brain rate good|bad` rates the last answer: python3 -I eval/test_rate.py (a temp state folder, nothing real is written)"""
import json
import os
import shutil
import subprocess
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BRAIN = os.path.join(ROOT, "bin", "brain")


class Rate(unittest.TestCase):
    def setUp(self):
        self.state = tempfile.mkdtemp(prefix="rate-test-")
        self.addCleanup(shutil.rmtree, self.state, True)
        with open(os.path.join(self.state, "asks.jsonl"), "w") as f:
            for i in ("a1", "a2"):
                f.write(json.dumps({"id": i, "at": "2026-10-27T10:00:00", "q": "q " + i, "kind": "answer"}) + "\n")

    def brain(self, *args):
        env = dict(os.environ, BRAIN_STATE=self.state)
        r = subprocess.run([BRAIN, "rate", *args], capture_output=True, text=True, env=env, timeout=30)
        return r.returncode, r.stdout, r.stderr

    def ratings(self):
        try:
            with open(os.path.join(self.state, "ratings.jsonl")) as f:
                return [json.loads(l) for l in f if l.strip()]
        except FileNotFoundError:
            return []

    def test_one_word_rates_the_last_answer(self):
        self.assertEqual(self.brain("good")[0], 0)
        self.assertEqual(self.brain("bad", "it", "missed", "the", "note")[0], 0)
        got = [(r["id"], r["verdict"], r["why"]) for r in self.ratings()]
        self.assertEqual(got, [("a2", "up", ""), ("a2", "down", "it missed the note")])

    def test_an_id_with_good_or_bad_and_the_old_up_down_still_work(self):
        self.assertEqual(self.brain("a1", "bad")[0], 0)
        self.assertEqual(self.brain("a1", "good")[0], 0)
        self.assertEqual(self.brain("last", "down")[0], 0)
        self.assertEqual(self.brain("a1", "up")[0], 0)
        self.assertEqual([(r["id"], r["verdict"]) for r in self.ratings()],
                         [("a1", "down"), ("a1", "up"), ("a2", "down"), ("a1", "up")])

    def test_nothing_asked_yet_or_a_wrong_word_is_said_not_written(self):
        os.remove(os.path.join(self.state, "asks.jsonl"))
        code, _, err = self.brain("good")
        self.assertEqual(code, 1)
        self.assertIn("nothing asked yet", err)
        self.assertEqual(self.brain()[0], 2)
        self.assertEqual(self.ratings(), [])


if __name__ == "__main__":
    unittest.main()
