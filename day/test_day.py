"""Tests for day.py and the two day jobs. Run: python3 -I day/test_day.py (CRABBOX_LOCAL=1)."""
import datetime as dt
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "jobs"))
import day  # noqa: E402
import jobs  # noqa: E402


def ts(s):
    return dt.datetime.strptime(s, "%Y-%m-%d %H:%M").timestamp()


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = self.tmp.name
        self.old = {k: getattr(day, k) for k in ("DATA", "CHANGES", "CLOSEOUTS", "OVERNIGHT", "SNAPS", "PAGES",
                                                   "MB_HANDLED", "HOME")}
        day.DATA, day.CHANGES, day.CLOSEOUTS = d, os.path.join(d, "c.jsonl"), os.path.join(d, "co.jsonl")
        day.OVERNIGHT, day.SNAPS, day.PAGES = os.path.join(d, "o.jsonl"), os.path.join(d, "s"), os.path.join(d, "p")
        day.MB_HANDLED = os.path.join(d, "handled.tsv")

    def tearDown(self):
        for k, v in self.old.items():
            setattr(day, k, v)
        self.tmp.cleanup()


class Time(Base):
    def test_day_runs_5_to_5(self):
        self.assertEqual(day.day_of(ts("2026-10-16 01:30")), dt.date(2026, 10, 15))
        self.assertEqual(day.day_of(ts("2026-10-16 04:59")), dt.date(2026, 10, 15))
        self.assertEqual(day.day_of(ts("2026-10-16 05:00")), dt.date(2026, 10, 16))

    def test_goodnight_ends_the_day(self):
        d = dt.date(2026, 10, 15)
        start, end, closed = day.window(d, now=ts("2026-10-16 10:00"))
        self.assertEqual((start, end, closed), (ts("2026-10-15 05:00"), ts("2026-10-16 05:00"), False))
        day.append_jsonl(day.CLOSEOUTS, {"t": ts("2026-10-16 01:40"), "day": "2026-10-15", "picked": []})
        self.assertEqual(day.window(d, now=ts("2026-10-16 10:00"))[1:], (ts("2026-10-16 01:40"), True))

    def test_never_past_now(self):
        d = dt.date(2026, 10, 15)
        self.assertEqual(day.window(d, now=ts("2026-10-15 12:00"))[1], ts("2026-10-15 12:00"))


class Git(Base):
    def test_commits_on_every_branch_in_the_window(self):
        with tempfile.TemporaryDirectory() as r:
            env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t", GIT_COMMITTER_NAME="t",
                       GIT_COMMITTER_EMAIL="t@t")

            def commit(msg, when, branch=None):
                if branch:
                    subprocess.run(["git", "-C", r, "checkout", "-qb", branch], check=True, env=env)
                e = dict(env, GIT_AUTHOR_DATE=when, GIT_COMMITTER_DATE=when)
                subprocess.run(["git", "-C", r, "commit", "-q", "--allow-empty", "-m", msg], check=True, env=e)
            subprocess.run(["git", "init", "-q", r], check=True)
            commit("before", "2026-10-15T04:00:00")
            commit("inside main", "2026-10-15T10:00:00")
            commit("inside branch", "2026-10-15T23:00:00", branch="side")
            commit("after", "2026-10-16T06:00:00")
            got = [s for _, s in day.git_commits(r, ts("2026-10-15 05:00"), ts("2026-10-16 05:00"))]
            self.assertEqual(got, ["inside main", "inside branch"])


class Page(Base):
    def g(self, commits=None, notes=(), appeared=(), gone=()):
        return {"commits": commits or {}, "notes": list(notes), "appeared": list(appeared), "gone": list(gone)}

    def test_grouped_short_and_capped(self):
        commits = {f"repo{i}": [(i, f"change {i}.{k}") for k in range(5)] for i in range(12)}
        text = day.page("T", self.g(commits))
        self.assertIn("Saved changes: 60 in 12 projects", text)
        self.assertIn("- repo0 (5): change 0.4; change 0.3; change 0.2 (+2 more)", text)
        self.assertIn("- also: repo8 (5), repo9 (5), repo10 (5), repo11 (5)", text)
        self.assertLess(len(text.splitlines()), 15)

    def test_long_subjects_are_cut(self):
        text = day.page("T", self.g({"r": [(1, "x" * 200)]}))
        self.assertIn("x" * 69 + "…", text)
        self.assertNotIn("x" * 71, text)

    def test_spoken(self):
        g = self.g({"omarchy-setup": [(1, "a"), (2, "b")], "decider": [(1, "c")]},
                   notes=[{"t": 1, "kind": "move", "what": "~/.npm to the big drive"}])
        s = day.say_line("today", g)
        self.assertTrue(s.startswith("Today: 3 saved changes in 2 projects, most in omarchy setup (2), then decider."))
        self.assertIn("1 logged change, the last: ~/.npm to the big drive.", s)
        self.assertEqual(day.say_line("yesterday", self.g()), "Nothing moved yesterday.")


class Folders(Base):
    def test_unnoted_moves_only(self):
        day.write(os.path.join(day.SNAPS, "2026-10-14.txt"), "Downloads/a\nDownloads/old\nProjects/keep\n")
        day.write(os.path.join(day.SNAPS, "2026-10-15.txt"), "Downloads/a\nProjects/keep\nProjects/new\nProjects/logged\n")
        notes = [{"t": 1, "kind": "move", "what": "made ~/projects/logged"}]
        appeared, gone = day.folder_changes(dt.date(2026, 10, 15), notes)
        self.assertEqual((appeared, gone), (["Projects/new"], ["Downloads/old"]))

    def test_no_list_yet_means_nothing(self):
        self.assertEqual(day.folder_changes(dt.date(2026, 10, 15), []), ([], []))


class ChangeLog(Base):
    def test_changed_appends_one_line(self):
        self.assertEqual(day.cmd_changed(["Move!", "~/x", "->", "/mnt/backup/home/x"]), 0)
        self.assertEqual(day.cmd_changed(["move"]), 2)
        rows = day.read_jsonl(day.CHANGES)
        self.assertEqual(len(rows), 1)
        self.assertEqual((rows[0]["kind"], rows[0]["what"]), ("move", "~/x -> /mnt/backup/home/x"))


class Goodnight(Base):
    class FakeRemind:
        PATH = None

        def __init__(self, texts):
            self._items = [(i, "2026-10-15", t) for i, t in enumerate(texts)]

        def items(self):
            return self._items

        @staticmethod
        def short(t, n=60):
            return t[:n]

    def test_tick_one_at_a_time_then_done(self):
        mod = self.FakeRemind(["build the thing", "dentist friday", "research x"])
        answers = iter(["3. research x", "1. build the thing", "Done (2 picked)"])
        seen = []

        def menu(prompt, options):
            seen.append(options)
            return next(answers)
        picked = day.pick_overnight(mod, menu)
        self.assertEqual([t for _, _, t in picked], ["research x", "build the thing"])
        self.assertEqual(seen[0][0], "Nothing tonight")
        self.assertEqual(seen[1], ["Done (1 picked)", "1. build the thing", "2. dentist friday"])

    def test_esc_picks_nothing(self):
        self.assertEqual(day.pick_overnight(self.FakeRemind(["a"]), lambda p, o: None), [])

    def test_marked_lines_are_skipped_by_the_reminder(self):
        path = os.path.join(self.tmp.name, "remembered.md")
        day.write(path, "# list\n- 2026-10-15: build the thing\n")
        day.mark_overnight(1, path)
        line = open(path).read().splitlines()[1]
        self.assertRegex(line, r"→ started with Claude overnight \d{4}-\d{2}-\d{2}$")
        sys.path.insert(0, os.path.join(os.path.dirname(HERE), "jobs"))
        self.assertEqual(day.remind_list().items(path), [])

    def test_goodnight_run_end_to_end(self):
        path = os.path.join(self.tmp.name, "remembered.md")
        day.write(path, "- 2026-10-15: build the thing\n- 2026-10-15: dentist friday\n")
        real = day.remind_list()
        real.PATH = path
        real.items = lambda p=path, f=real.items: f(p)
        real.menu = lambda prompt, options: "1. build the thing" if "1. build the thing" in options else options[0]
        calls = []
        saved = (day.remind_list, day.say, day.lock_and_dark, day.helpers, day.save_snapshot, day.all_commits,
                 day.subprocess.run)
        day.remind_list, day.say = (lambda: real), (lambda text, wait=True: calls.append(("say", text)))
        day.lock_and_dark, day.helpers = (lambda: calls.append(("lock",))), (lambda: [("example-game", 0)])
        day.save_snapshot, day.all_commits = (lambda d, overwrite=True: None), (lambda s, e: {})
        day.subprocess.run = lambda argv, **k: calls.append(("run", argv[:2])) or subprocess.CompletedProcess(argv, 0)
        try:
            self.assertEqual(day.cmd_goodnight(["--run"]), 0)
        finally:
            (day.remind_list, day.say, day.lock_and_dark, day.helpers, day.save_snapshot, day.all_commits,
             day.subprocess.run) = saved
        c = day.read_jsonl(day.CLOSEOUTS)[-1]
        self.assertEqual((c["picked"], c["running"]), (["build the thing"], ["example-game"]))
        self.assertIn("1 thing will run tonight", calls[0][1])
        self.assertEqual(calls[1], ("lock",))
        self.assertEqual(calls[2], ("run", ["systemd-inhibit", "--what=sleep:idle"]))
        self.assertIn("→ started with Claude overnight", open(path).read().splitlines()[0])
        self.assertEqual(len(os.listdir(day.PAGES)), 1)

    def test_result_read_back_from_morning_build(self):
        day.write(day.MB_HANDLED, "# note id\tverdict\thandled at\twhere / why\tnote\n"
                  "x\tbuilt:done\t2026-10-16 02:10\t/runs/abc\tbuild the thing\n")
        self.assertEqual(day.handled_since("build the thing", ts("2026-10-16 02:00")), ("built:done", "/runs/abc"))
        self.assertIsNone(day.handled_since("build the thing", ts("2026-10-16 03:00")))


class Jobs(unittest.TestCase):
    def job(self, text):
        jid = jobs.match_rule(text)
        return jid and jobs.build(jid, text)["job"]

    def test_what_changed(self):
        self.assertEqual(self.job("what moved today")["args"], {"when": "today"})
        self.assertEqual(self.job("hey claude, what happened overnight?")["args"], {"when": "overnight"})
        self.assertEqual(self.job("what did I get done yesterday")["args"], {"when": "yesterday"})
        self.assertIsNone(jobs.match_rule("what changed in the bar config"))

    def test_goodnight_asks_first(self):
        for t in ("goodnight", "ok I'm going to bed", "close out the day", "bedtime"):
            j = self.job(t)
            self.assertEqual((j["id"], j["needs_confirm"]), ("goodnight", True), t)
        self.assertNotEqual(jobs.match_rule("good night light on"), "goodnight")

    def test_run_checks_when(self):
        with self.assertRaises(ValueError):
            jobs._check("what-changed", {"when": "; rm -rf ~"})


if __name__ == "__main__":
    unittest.main()
