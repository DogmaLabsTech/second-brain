"""ask.decide says what failed, and still answers the same "timeout" label: python3 -I ask/test_decide_error.py"""
import contextlib
import io
import json
import os
import subprocess
import sys
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ask  # noqa: E402

UNSURE = {"label": "unsure", "confidence": 0.0, "by": "timeout"}


class NoDeciderInThisCopy(unittest.TestCase):
    @unittest.skipIf(os.path.exists(os.path.join(os.path.dirname(HERE), "deciders", "brain_decide.py")), "this copy has a decider")
    def test_brain_decide_answers_unsure_quietly_when_the_decider_is_not_shipped(self):
        home = __import__("tempfile").mkdtemp()
        r = subprocess.run([os.path.join(os.path.dirname(HERE), "bin", "brain-decide"), "intent", "hello"],
                           capture_output=True, text=True, env=dict(os.environ, HOME=home), timeout=30)
        self.assertEqual(r.returncode, 0)
        self.assertEqual(r.stderr, "")
        self.assertEqual(json.loads(r.stdout)["label"], "unsure")


class Decide(unittest.TestCase):
    def decide(self, **run):
        err = io.StringIO()
        with mock.patch.object(ask.subprocess, "run", **run), contextlib.redirect_stderr(err):
            return ask.decide("intent", "hello"), err.getvalue()

    def test_a_good_answer_is_passed_on_quietly(self):
        out = subprocess.CompletedProcess([], 0, json.dumps({"label": "question", "confidence": 0.9}) + "\n", "")
        got, said = self.decide(return_value=out)
        self.assertEqual(got["label"], "question")
        self.assertEqual(said, "")

    def test_a_missing_decider_is_said_and_keeps_the_old_label(self):
        got, said = self.decide(side_effect=FileNotFoundError("brain-decide"))
        self.assertEqual(got, UNSURE)
        self.assertIn("the decider failed (FileNotFoundError brain-decide)", said)

    def test_nonsense_output_is_said_and_keeps_the_old_label(self):
        got, said = self.decide(return_value=subprocess.CompletedProcess([], 0, "not json\n", ""))
        self.assertEqual(got, UNSURE)
        self.assertIn("the decider failed (JSONDecodeError", said)

    def test_no_output_at_all_is_said_and_keeps_the_old_label(self):
        got, said = self.decide(return_value=subprocess.CompletedProcess([], 1, "", ""))
        self.assertEqual(got, UNSURE)
        self.assertIn("the decider failed (IndexError", said)

    def test_a_real_timeout_is_said_by_length_only_never_with_the_command(self):
        secret = ["brain-decide", "grounded", "what is the Smith invoice", "private note snippet"]
        got, said = self.decide(side_effect=subprocess.TimeoutExpired(secret, 2.5))
        self.assertEqual(got, UNSURE)
        self.assertIn("the decider failed (TimeoutExpired after 2.5 s)", said)
        self.assertNotIn("Smith", said)
        self.assertNotIn("snippet", said)

    def test_brain_decides_own_warning_reaches_our_stderr_but_the_rest_does_not(self):
        out = subprocess.CompletedProcess([], 0, json.dumps({"label": "question", "confidence": 0.9}) + "\n",
                                          "brain-decide: private.json is unreadable (x)\nTraceback: the Smith invoice\n")
        got, said = self.decide(return_value=out)
        self.assertEqual(got["label"], "question")
        self.assertEqual(said, "brain-decide: private.json is unreadable (x)\n")


if __name__ == "__main__":
    unittest.main()
