"""Tests for bin/remember (project tags). Never touches the real list: python3 -I jobs/test_remember.py"""
import os
import re
import subprocess
import sys
import tempfile
import unittest
from importlib.machinery import SourceFileLoader

HERE = os.path.dirname(os.path.abspath(__file__))
REMEMBER = os.path.join(HERE, "bin", "remember")
rl = SourceFileLoader("remind_list", os.path.join(HERE, "bin", "remind-list")).load_module()
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "day"))
sys.path.insert(0, HERE)
import day  # noqa: E402


class Remember(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.file = os.path.join(self.tmp, "remembered.md")
        self.proj = os.path.join(self.tmp, "Projects")
        for d in ("omarchy-setup", "example-game", "example", "factory", "second-brain", "example-game", ".hidden-thing"):
            os.makedirs(os.path.join(self.proj, d))
        open(os.path.join(self.proj, "notes-file"), "w").close()

    def run_it(self, text):
        env = dict(os.environ, BRAIN_REMEMBER_FILE=self.file, BRAIN_PROJECTS_DIR=self.proj)
        r = subprocess.run([sys.executable, "-I", REMEMBER, text], env=env, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        return open(self.file).read().splitlines()[-1]

    def test_said_tag_normalised_at_end(self):
        line = self.run_it("remember that (Repo:Omarchy-Setup) the island mic sticks")
        self.assertTrue(line.endswith("the island mic sticks (repo: omarchy-setup)"), line)
        self.assertEqual(line.lower().count("(repo:"), 1)

    def test_only_first_said_tag(self):
        line = self.run_it("a (repo: x) b (repo: y)")
        self.assertEqual(line.lower().count("(repo:"), 1)
        self.assertTrue(line.endswith("(repo: x)"), line)

    def test_untagged_old_format(self):
        line = self.run_it("buy milk on the way home")
        self.assertRegex(line, r"^- \d{4}-\d{2}-\d{2} \d{2}:\d{2}: buy milk on the way home$")

    def test_auto_tag(self):
        self.assertTrue(self.run_it("the example-game boss fight needs a pass").endswith("(repo: example-game)"))
        self.assertTrue(self.run_it("fix omarchy-setup bar").endswith("(repo: omarchy-setup)"))
        self.assertTrue(self.run_it("fix omarchy setup bar").endswith("(repo: omarchy-setup)"))

    def test_common_words_not_tagged(self):
        for t in ("remember to check the example levels", "the factory reset code is 1234"):
            self.assertNotIn("(repo:", self.run_it(t))

    def test_common_word_list(self):
        words = SourceFileLoader("remember_mod", REMEMBER).load_module().COMMON_WORDS
        self.assertLessEqual({"factory", "digest", "example", "expedition", "bullpen"}, words)

    def test_said_common_word_kept(self):
        self.assertTrue(self.run_it("fix the reply style (repo: example)").endswith("(repo: example)"))

    def test_said_wins_over_words(self):
        line = self.run_it("example-game thing (repo: omarchy-setup)")
        self.assertEqual(line.count("(repo:"), 1)
        self.assertTrue(line.endswith("(repo: omarchy-setup)"), line)

    def test_no_partial_words(self):
        self.assertNotIn("(repo:", self.run_it("titanium is a metal"))
        self.assertTrue(self.run_it("the example-game fight").endswith("(repo: example-game)"))

    def test_said_tag_must_look_like_a_folder(self):
        self.assertTrue(self.run_it("bar gap (repo: omarchy setup)").endswith("bar gap (repo: omarchy-setup)"))
        line = self.run_it("odd one (repo: x → started with Claude 2026-10-16)")
        self.assertEqual(line.split(": ", 1)[1], "odd one (repo x → started with Claude 2026-10-16)")
        self.assertEqual(len(rl.items(self.file)), 1)   # still open: the said text was kept as it was
        self.assertTrue(self.run_it("x (repo: ../../etc)").endswith(": x (repo ../../etc)"))

    def test_cap_500_then_tag(self):
        line = self.run_it("a" * 600 + " (repo: x)")
        self.assertEqual(len(line.split(": ", 1)[1]), 500 + len(" (repo: x)"))


LIST = """# Remembered

- 2026-10-15 22:55: Build a drawing app (repo: omarchy-setup)
- 2026-10-14: Fix the bar clock → started with Codex 2026-10-15
- 2026-10-16 09:01: Ask Sam about Friday
"""
PLAIN = LIST.replace(" (repo: omarchy-setup)", "")


class Downstream(unittest.TestCase):
    def mk(self, text):
        p = os.path.join(tempfile.mkdtemp(), "remembered.md")
        open(p, "w").write(text)
        return p

    def test_remind_list_counts_same(self):
        self.assertEqual(len(rl.items(self.mk(LIST))), 2)
        self.assertEqual(len(rl.items(self.mk(PLAIN))), 2)

    def test_remind_list_mark_keeps_tag(self):
        p = self.mk(LIST)
        rl.mark(rl.items(p)[0][0], "gemini", p)
        got = open(p).read()
        self.assertRegex(got, r"\(repo: omarchy-setup\) → started with Gemini")
        self.assertEqual(len(rl.items(p)), 1)

    def test_day_mark_keeps_tag(self):
        p = self.mk(LIST)
        day.mark_overnight(rl.items(p)[0][0], p)
        self.assertRegex(open(p).read(), r"\(repo: omarchy-setup\) → started with Claude overnight")
        self.assertEqual(len(rl.items(p)), 1)


if __name__ == "__main__":
    unittest.main()
