"""Tests for day/tests_week.py (the week's test failures page). Run: python3 -I day/test_tests_week.py. Made-up data."""
import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import tests_week  # noqa: E402


def row(when, test, outcome="old", job="j1", where="testbox", sig="AssertionError: boom"):
    return {"when": when, "job": job, "commit": job + "-c", "test": test, "sig": sig, "where": where,
            "outcome": outcome, "count": 1}


class Week(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        t = self.tmp.name
        self.old = {k: getattr(tests_week, k) for k in ("FAILURES", "FLAKY", "PAGES")}
        tests_week.FAILURES, tests_week.FLAKY = os.path.join(t, "failures"), os.path.join(t, "flaky")
        tests_week.PAGES = os.path.join(t, "pages")
        os.makedirs(tests_week.FAILURES)
        os.makedirs(tests_week.FLAKY)
        rows = [row("2026-10-27T07:00:00-04:00", "t.a", "new"), row("2026-10-28T07:00:00-04:00", "t.a"),
                row("2026-10-28T08:00:00-04:00", "t.a", job="j2"), row("2026-10-29T09:00:00-04:00", "t.b", "flaky"),
                row("2026-10-20T09:00:00-04:00", "t.lastweek")]
        with open(os.path.join(tests_week.FAILURES, "agent-os.jsonl"), "w") as f:
            f.writelines(json.dumps(r) + "\n" for r in rows)
            f.write("broken\n")
        with open(os.path.join(tests_week.FLAKY, "agent-os.json"), "w") as f:
            json.dump({"tests": {"t.b": {"listed": True}, "t.c": {"listed": False}}}, f)

    def tearDown(self):
        for k, v in self.old.items():
            setattr(tests_week, k, v)
        self.tmp.cleanup()

    def test_page(self):
        with open(tests_week.write_week("2026-W44")) as f:
            p = f.read()
        self.assertIn("# Tests: week 2026-W44 (26 Oct to 1 Nov 2026)", p)
        self.assertIn("4 failing tests in 4 test runs across 1 project", p)
        self.assertIn("- new failures:\n  - t.a [testbox]: AssertionError: boom", p)
        self.assertIn("- failed again:\n  - t.a x2 [testbox]", p)
        self.assertIn("- flaky (passed on rerun):\n  - t.b", p)
        self.assertIn("- on the flaky list (1): t.b", p)
        self.assertNotIn("t.lastweek", p)
        self.assertNotIn("t.c", p)

    def test_quiet_week_and_rerun(self):
        path = tests_week.write_week("2026-W40")
        tests_week.write_week("2026-W40")
        with open(path) as f:
            self.assertEqual(f.read().count("No test failed"), 1)

    def test_bad_week(self):
        self.assertEqual(tests_week.main(["44"]), 2)


if __name__ == "__main__":
    unittest.main()
