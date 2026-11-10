"""index/structq.py turns a question into search lines: python3 -I index/test_structq.py"""
import os
import subprocess
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import structq  # noqa: E402


class Structq(unittest.TestCase):
    def test_accented_words_are_kept_whole(self):
        self.assertEqual(structq.keywords("the café résumé"), "café résumé")
        self.assertEqual(structq.keywords("Zürich"), "Zürich")
        self.assertIn("lex: projet été", structq.document("où est le projet été"))

    def test_plain_english_questions_are_unchanged(self):
        self.assertEqual(structq.keywords("how do I reload the bar after editing"), "reload bar editing")
        self.assertEqual(structq.keywords("find config.yml in my-notes"), "find config.yml my-notes")

    def test_an_empty_question_gives_no_search_lines(self):
        self.assertEqual(structq.document(""), "")
        self.assertEqual(structq.document("   "), "")

    def test_the_command_line_says_how_to_use_it_when_given_nothing(self):
        out = subprocess.run([sys.executable, "-I", os.path.join(HERE, "structq.py")], capture_output=True, text=True, timeout=30)
        self.assertEqual(out.returncode, 2)
        self.assertIn("usage", out.stderr)
        self.assertNotIn("vec:", out.stdout)


if __name__ == "__main__":
    unittest.main()
