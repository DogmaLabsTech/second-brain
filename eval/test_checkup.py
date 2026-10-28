"""The check-up says in plain words when private.json cannot be read: python3 -I eval/test_checkup.py"""
import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.environ["BRAIN_STATE"] = tempfile.mkdtemp(prefix="checkup-test-state-")
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


def score(top1=7, top3=20, newer=2, n=34, misses=()):
    return {"top1": top1, "top3": top3, "n": n, "newer_ok": newer, "newer_n": 4, "by_use": {"howto": [top3, n]},
            "misses": [(m, "q " + m, []) for m in misses]}


def summary(**kw):
    base = {"s": score(), "it": None, "asks": 10, "up": 0, "down": 0, "marked": 0,
            "prev": {"top1": "7/34", "top3": "20/34", "newer": "2/4"}, "problem": None, "fresh": [], "problems": [],
            "days": 7}
    base.update(kw)
    return base


class Flags(unittest.TestCase):
    def test_a_quiet_week_has_no_flags(self):
        self.assertEqual(checkup.flags(summary(), ["h1"]), [])

    def test_a_lower_score_than_the_last_row_is_flagged(self):
        said = checkup.flags(summary(s=score(top1=6, top3=18, newer=1)))
        self.assertEqual(said, ["right note in the top 3 fell from 20/34 to 18/34",
                                "right note first fell from 7/34 to 6/34", "newer note wins fell from 2/4 to 1/4"])

    def test_a_better_score_or_a_different_test_size_is_not_a_fall(self):
        self.assertEqual(checkup.flags(summary(s=score(top3=21))), [])
        self.assertEqual(checkup.flags(summary(s=score(top3=5, n=10))), [])
        self.assertEqual(checkup.flags(summary(prev=None)), [])

    def test_newly_missed_questions_are_named(self):
        said = checkup.flags(summary(s=score(misses=["h1", "h7"])), ["h1"])
        self.assertEqual(said, ["newly missed in the fair test: h7"])

    def test_thumbs_down_warnings_and_broken_parts_are_flagged(self):
        said = checkup.flags(summary(down=3, marked=2, problem="x", fresh=["!! notes are late"],
                                     problems=["The intent fair test didn't run (OSError: x)"],
                                     it={"sure_wrong": 2, "n": 100}))
        self.assertIn("3 👎 in 7 days (2 marked on their own because they were asked again)", said)
        self.assertIn("the router was sure and wrong 2/100 times", said)
        self.assertIn("notes are late", said)
        self.assertIn("The intent fair test didn't run (OSError: x)", said)
        self.assertTrue(any("private names list" in f for f in said))

    def test_a_week_with_no_asks_is_flagged(self):
        self.assertIn("no asks in 7 days", checkup.flags(summary(asks=0))[0])


class PreviousRow(unittest.TestCase):
    def test_the_last_row_is_read_by_column_name(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "scores.tsv")
            self.assertIsNone(checkup.previous_row(path))
            with open(path, "w") as f:
                f.write("when\ttop1\ttop3\nthen\t1/2\t2/2\nlater\t3/4\t4/4\n")
            self.assertEqual(checkup.previous_row(path), {"when": "later", "top1": "3/4", "top3": "4/4"})
            with open(path, "w") as f:
                f.write("when\ttop1\n")
            self.assertIsNone(checkup.previous_row(path))

    def test_ratio(self):
        self.assertEqual(checkup.ratio("7/34"), (7, 34))
        self.assertIsNone(checkup.ratio("-"))
        self.assertIsNone(checkup.ratio(None))


class Auto(unittest.TestCase):
    """`brain checkup --auto`: the row, the saved report, the notice, the failure notice (pretend search and models)."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="checkup-auto-")
        self.state = os.path.join(self.tmp, "state")
        os.makedirs(self.state)
        self.notes = []
        self.learn = mock.Mock()
        patches = [mock.patch.object(checkup, "HERE", self.tmp), mock.patch.object(checkup.asklog, "STATE", self.state),
                   mock.patch.object(checkup, "load", lambda name: [{"id": "h1", "use": "howto", "q": "q"}]),
                   mock.patch.object(checkup, "search_score", lambda rows: score(misses=["h1"])),
                   mock.patch.object(checkup, "freshness_lines", lambda *a: []),
                   mock.patch.object(checkup, "private_list_problem", lambda *a: None),
                   mock.patch.object(checkup, "intent_score", lambda *a, **k: None),
                   mock.patch.object(checkup, "_print_tuning", lambda: None),
                   mock.patch.object(checkup, "week", lambda days: ([{"id": "a1", "q": "x", "kind": "answer"}], {})),
                   mock.patch.object(checkup, "learn", self.learn),
                   mock.patch.object(checkup, "drafts_lines", lambda days: []),
                   mock.patch.object(checkup, "memory_block", lambda days: ([], None, None)),
                   mock.patch.object(checkup.drafts, "auto_rate", lambda days: []),
                   mock.patch.object(checkup, "notify", lambda t, b: self.notes.append((t, b))),
                   mock.patch.dict(os.environ, {"CHECKUP_NOTE": ""})]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        self.addCleanup(__import__("shutil").rmtree, self.tmp, True)

    def run_auto(self, argv=("--auto",)):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = checkup.auto_main(list(argv))
        return code, out.getvalue()

    def test_it_adds_a_row_saves_the_report_and_sends_a_notice(self):
        code, out = self.run_auto()
        self.assertEqual(code, 0)
        rows = open(os.path.join(self.tmp, "scores.tsv")).read().splitlines()
        self.assertEqual(len(rows), 2)   # header + this run
        self.assertTrue(rows[1].endswith("\tauto"))
        self.assertIn("7/34\t20/34\t2/4", rows[1])
        day = __import__("time").strftime("%Y-%m-%d")
        report = open(os.path.join(self.state, "checkups", day + ".txt")).read()
        self.assertIn("Fair test (search", report)
        self.assertIn("Flags: none", report)
        self.assertEqual(json.load(open(os.path.join(self.state, "checkups", day + ".json")))["miss_ids"], ["h1"])
        self.assertEqual(self.notes[0][0], "Brain check-up done")
        self.assertIn("All quiet.", self.notes[0][1])

    def test_it_never_learns_online_or_trains(self):
        self.run_auto()
        self.learn.assert_not_called()

    def test_the_second_run_flags_a_lower_score(self):
        self.run_auto()
        with mock.patch.object(checkup, "search_score", lambda rows: score(top3=18, misses=["h1", "h2"])):
            self.run_auto()
        title, body = self.notes[1]
        self.assertIn("look at this", title)
        self.assertIn("fell from 20/34 to 18/34", body)
        self.assertIn("newly missed in the fair test: h2", body)

    def test_a_broken_part_does_not_lose_the_row(self):
        def boom(*a, **k):
            raise OSError("decider is down")
        with mock.patch.object(checkup, "intent_score", boom):
            code, out = self.run_auto()
        self.assertEqual(code, 0)
        self.assertIn("The intent fair test didn't run", out)
        self.assertEqual(len(open(os.path.join(self.tmp, "scores.tsv")).read().splitlines()), 2)
        self.assertIn("The intent fair test didn't run", self.notes[0][1])

    def test_a_dead_search_says_so_instead_of_leaving_a_silent_gap(self):
        def boom(rows):
            raise RuntimeError("qmd is not answering")
        with mock.patch.object(checkup, "search_score", boom):
            code, out = self.run_auto()
        self.assertEqual(code, 3)
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "scores.tsv")))
        self.assertEqual(self.notes[0][0], "Brain check-up failed")
        self.assertIn("qmd is not answering", self.notes[0][1])


if __name__ == "__main__":
    unittest.main()
