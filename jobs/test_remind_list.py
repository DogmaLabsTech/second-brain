"""Tests for bin/remind-list (reading and marking the remember list, the agent command): python3 jobs/test_remind_list.py"""
import os
import tempfile
import unittest
from importlib.machinery import SourceFileLoader

HERE = os.path.dirname(os.path.abspath(__file__))
rl = SourceFileLoader("remind_list", os.path.join(HERE, "bin", "remind-list")).load_module()

LIST = """# Remembered

Intro line.

- 2026-10-15 22:55: Build a drawing app for Max
- 2026-10-14: Fix the bar clock → started with Codex 2026-10-15
- 2026-10-16 09:01: Ask Sam about Friday
"""


class RemindList(unittest.TestCase):
    def setUp(self):
        self.path = os.path.join(tempfile.mkdtemp(), "remembered.md")
        open(self.path, "w").write(LIST)

    def test_open_items_skip_started(self):
        got = rl.items(self.path)
        self.assertEqual([t for _, _, t in got], ["Build a drawing app for Max", "Ask Sam about Friday"])
        self.assertEqual(got[0][1], "2026-10-15")

    def test_tick_boxes(self):
        open(self.path, "w").write("- [ ] 2026-10-18 10:00: Open item\n- [x] 2026-10-18 10:01: Done item\n"
                                   "- [X] 2026-10-18: Also done\n- 2026-10-17: Old style\n")
        self.assertEqual([t for _, _, t in rl.items(self.path)], ["Open item", "Old style"])
        self.assertEqual(rl.items(self.path)[0][1], "2026-10-18")
        rl.mark(rl.items(self.path)[0][0], "claude", self.path)
        self.assertEqual([t for _, _, t in rl.items(self.path)], ["Old style"])

    def test_mark(self):
        line = rl.items(self.path)[0][0]
        rl.mark(line, "gemini", self.path)
        self.assertEqual([t for _, _, t in rl.items(self.path)], ["Ask Sam about Friday"])
        self.assertIn("→ started with Gemini", open(self.path).read().splitlines()[line])

    def test_mark_finds_the_item_again_by_its_text(self):
        pick = rl.items(self.path)[1]                      # "Ask Sam about Friday"
        open(self.path, "w").write("- 2026-10-20: A brand new thing\n" + LIST)   # the list grew above it meanwhile
        self.assertTrue(rl.mark(pick[0], "claude", self.path, text=pick[2]))
        lines = open(self.path).read().splitlines()
        self.assertIn("→ started with Claude", [l for l in lines if "Ask Sam" in l][0])
        self.assertNotIn("→", [l for l in lines if "brand new" in l][0])

    def test_mark_of_a_vanished_item_changes_nothing_and_does_not_crash(self):
        before = open(self.path).read()
        self.assertFalse(rl.mark(99, "claude", self.path, text="no such item"))
        self.assertFalse(rl.mark(0, "claude", self.path, text="Fix the bar clock"))   # already started: not open any more
        self.assertEqual(open(self.path).read(), before)

    def test_reading_and_marking_leave_no_file_open(self):
        import gc
        import warnings
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            item = rl.items(self.path)[0]
            rl.mark(item[0], "claude", self.path, text=item[2])
            gc.collect()
        self.assertEqual([w for w in caught if issubclass(w.category, ResourceWarning)], [])

    def test_every_agent_gets_the_task(self):
        for agent in rl.AGENTS:
            argv = rl.AGENTS[agent][1]("do the thing")
            self.assertEqual(argv[-1], "do the thing")
        self.assertIn("drawing app", rl.prompt_for("Develop a drawing app", "2026-10-15"))


if __name__ == "__main__":
    unittest.main()
