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
        self.assertIsNone(self.problem('{"words": ["zorblax"]}'))
        self.assertIsNone(self.problem())

    def test_a_typo_is_said_in_plain_words(self):
        said = self.problem('{"words": ["zorblax"],}')
        self.assertIn("is broken", said)
        self.assertIn("Nothing is sent to any online model", said)

    def test_an_empty_file_or_list_is_said_too(self):
        for text in ("", "  \n", "{}", '{"words": []}', '{"words": [" "], "_note": "x"}', '{"words": ["-", "a"]}'):
            with self.subTest(text=text):
                self.assertIn("Nothing is sent to any online model", self.problem(text))

    def test_a_file_of_the_wrong_shape_is_said_too(self):
        for text in ('["zorblax"]', '{"words": "zorblax"}', '{"words": [1, 2]}'):
            with self.subTest(text=text):
                self.assertIn("wrong shape", self.problem(text))


if __name__ == "__main__":
    unittest.main()
