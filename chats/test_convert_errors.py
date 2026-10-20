"""convert.py says when it cannot read a session file (it used to skip it silently): python3 -I chats/test_convert_errors.py"""
import contextlib
import io
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import convert  # noqa: E402


class Signature(unittest.TestCase):
    def test_a_file_that_vanished_is_said_and_left_out_of_the_signature(self):
        with tempfile.TemporaryDirectory() as d:
            here = os.path.join(d, "a.jsonl")
            with open(here, "w") as f:
                f.write("{}\n")
            gone = os.path.join(d, "gone.jsonl")
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                sig = convert.Session("k", here, [gone], d).signature()
            self.assertEqual([s[0] for s in sig], ["a.jsonl"])
            self.assertIn(f"could not stat {gone}", err.getvalue())


if __name__ == "__main__":
    unittest.main()
