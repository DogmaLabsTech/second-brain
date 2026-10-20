"""The check-up says in plain words when private.json cannot be read: python3 -I eval/test_checkup.py"""
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import checkup  # noqa: E402


class PrivateList(unittest.TestCase):
    def problem(self, text=None):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "private.json")
            if text is not None:
                with open(path, "w") as f:
                    f.write(text)
            return checkup.private_list_problem(path)

    def test_a_good_file_and_no_file_are_fine(self):
        self.assertIsNone(self.problem('{"words": ["rex"]}'))
        self.assertIsNone(self.problem())

    def test_a_typo_is_said_in_plain_words(self):
        said = self.problem('{"words": ["rex"],}')
        self.assertIn("can't be read", said)
        self.assertIn("not kept private", said)


if __name__ == "__main__":
    unittest.main()
