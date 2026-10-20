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
        self.assertIn("the decider failed (FileNotFoundError: brain-decide)", said)

    def test_nonsense_output_is_said_and_keeps_the_old_label(self):
        got, said = self.decide(return_value=subprocess.CompletedProcess([], 0, "not json\n", ""))
        self.assertEqual(got, UNSURE)
        self.assertIn("the decider failed (JSONDecodeError", said)

    def test_no_output_at_all_is_said_and_keeps_the_old_label(self):
        got, said = self.decide(return_value=subprocess.CompletedProcess([], 1, "", ""))
        self.assertEqual(got, UNSURE)
        self.assertIn("the decider failed (IndexError", said)

    def test_a_real_timeout_is_said_too(self):
        got, said = self.decide(side_effect=subprocess.TimeoutExpired("brain-decide", 2.5))
        self.assertEqual(got, UNSURE)
        self.assertIn("TimeoutExpired", said)


if __name__ == "__main__":
    unittest.main()
