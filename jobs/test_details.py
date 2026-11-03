"""Tests for details pulled out by the local writer (details.py, jobs.build_with_details), with a fake writer:
no Ollama needed. python3 jobs/test_details.py"""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ["BRAIN_DETAILS"] = "1"
import details  # noqa: E402
import jobs  # noqa: E402

PROJECTS = ["example-game", "example-rpg", "example-board"]


class Ground(unittest.TestCase):
    def test_projects(self):
        f = details.ground("start-claude", {"project": "example-classifier"}, "start a claude on the moon base project")
        self.assertEqual(f["project"], "none")
        f = details.ground("start-claude", {"project": "example-flights"}, "get a helper going on the flight thing")
        self.assertEqual(f["project"], "example-flights")

    def test_as_text(self):
        self.assertEqual(details.as_text("start-claude", {"project": "example-game"}), "start a claude on example-game")
        self.assertEqual(details.as_text("start-claude", {"project": "none"}), None)
        self.assertEqual(details.as_text("remember", {"text": "x"}), None)


class WithDetails(unittest.TestCase):
    def setUp(self):
        patch = mock.patch.object(jobs, "project_names", return_value=PROJECTS)
        patch.start()
        self.addCleanup(patch.stop)

    def test_rules_first(self):
        def never(*a):
            raise AssertionError("the writer must not be asked when the word rules found it")
        r = jobs.build_with_details("start-claude", "start a claude on example-game: tidy the logs", fill=never)
        self.assertEqual((r["details"], r["job"]["args"]["project"]), ("rules", "example-game"))

    def test_writer_fills_what_rules_missed(self):
        r = jobs.build_with_details("start-claude", "get a helper going on the whole shebang",
                                    fill=lambda *a: {"project": "desk"})
        self.assertEqual((r["details"], r["job"]["id"], r["job"]["args"]["project"]), ("local", "start-claude", "desk"))

    def test_nothing_useful_keeps_the_rules_answer(self):
        r = jobs.build_with_details("start-claude", "get a helper going", fill=lambda *a: {"project": "none"})
        self.assertEqual((r["kind"], r["details"]), ("answer", "none"))
        r = jobs.build_with_details("start-claude", "get a helper going", fill=lambda *a: None)   # not loaded or too slow
        self.assertEqual(r["kind"], "answer")

    def test_switched_off(self):
        os.environ["BRAIN_DETAILS"] = "0"
        try:
            r = jobs.build_with_details("start-claude", "get a helper going on the whole shebang",
                                        fill=lambda *a: {"project": "desk"})
            self.assertEqual((r["kind"], r["details"]), ("answer", "rules"))
        finally:
            os.environ["BRAIN_DETAILS"] = "1"


if __name__ == "__main__":
    unittest.main()
