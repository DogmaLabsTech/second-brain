"""Tests for day.py and the two day jobs. Run: python3 -I day/test_day.py (CRABBOX_LOCAL=1)."""
import datetime as dt
import os
import types
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
                                                   "MB_HANDLED", "HOME", "DONE_FILE", "JOBS_DIR", "AGENT_OS")}
        day.DATA, day.CHANGES, day.CLOSEOUTS = d, os.path.join(d, "c.jsonl"), os.path.join(d, "co.jsonl")
        day.OVERNIGHT, day.SNAPS, day.PAGES = os.path.join(d, "o.jsonl"), os.path.join(d, "s"), os.path.join(d, "p")
        day.MB_HANDLED = os.path.join(d, "handled.tsv")
        day.DONE_FILE, day.JOBS_DIR = os.path.join(d, "done.md"), os.path.join(d, "jobs")
        day.AGENT_OS = os.path.join(d, "no-agent-os")   # never the real agent-os

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

    def test_bed_after_5_am_still_counts_for_this_morning(self):
        day.append_jsonl(day.CLOSEOUTS, {"t": ts("2026-10-14 23:00"), "day": "2026-10-14"})
        day.append_jsonl(day.CLOSEOUTS, {"t": ts("2026-10-16 06:10"), "day": "2026-10-16"})
        self.assertEqual(day.last_goodnight(ts("2026-10-16 09:00"))["day"], "2026-10-16")
        self.assertIsNone(day.last_goodnight(ts("2026-10-16 06:00")))

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
            commit("old copy", "2026-10-15T12:00:00", branch="gone")
            subprocess.run(["git", "-C", r, "update-ref", "refs/local-backup/x", "gone"], check=True)
            subprocess.run(["git", "-C", r, "checkout", "-q", "side"], check=True)
            subprocess.run(["git", "-C", r, "branch", "-qD", "gone"], check=True)
            got = [s for _, s in day.git_commits(r, ts("2026-10-15 05:00"), ts("2026-10-16 05:00"))]
            self.assertEqual(got, ["inside main", "inside branch"])   # not the backup ref's copy


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

    def test_eod_run_end_to_end(self):
        path = os.path.join(self.tmp.name, "remembered.md")
        day.write(path, "- [ ] 2026-10-15: build the thing\n- [x] 2026-10-15 09:00: dentist friday\n"
                        "- [ ] 2026-10-15: research x\n")
        old_job = os.path.join(day.JOBS_DIR, "2026-10-15-old")
        day.write(os.path.join(old_job, "report.md"), "done\n")
        os.utime(os.path.join(old_job, "report.md"), (time.time() - 7200, time.time() - 7200))
        day.write(os.path.join(day.JOBS_DIR, "2026-10-18-busy", "brief.md"), "working\n")
        today = day.day_of(time.time()).isoformat()
        write_tray(day.JOBS_DIR, [("new", today, "2026-10-15-old", "fix the clock", "the clock is fixed")])
        real = day.remind_list()
        real.PATH = path
        real.items = lambda p=path, f=real.items: f(p)
        real.menu = lambda prompt, options: "1. build the thing" if "1. build the thing" in options else options[0]
        calls = []
        saved = (day.remind_list, day.say, day.busy, day.save_snapshot, day.all_commits, day.subprocess.run)
        day.remind_list, day.say = (lambda: real), (lambda text, wait=True: calls.append(("say", text)))
        day.busy = lambda: ["example-game"]
        day.save_snapshot, day.all_commits = (lambda d, overwrite=True: None), (lambda s, e: {})
        day.subprocess.run = lambda argv, **k: calls.append(("run", argv[:2])) or subprocess.CompletedProcess(argv, 0)
        try:
            self.assertEqual(day.cmd_eod(["--run"]), 0)
        finally:
            (day.remind_list, day.say, day.busy, day.save_snapshot, day.all_commits, day.subprocess.run) = saved
        c = day.read_jsonl(day.CLOSEOUTS)[-1]
        self.assertEqual((c["picked"], c["running"]), (["build the thing"], ["example-game"]))
        self.assertEqual((c["cleared"], c["finished"]), (["dentist friday"], ["2026-10-15-old"]))
        self.assertNotIn("filed", c)
        # the in-tray is made again first, then the summary with what was tidied, then the close; no lock
        self.assertEqual(calls[0], ("run", [day.AGENT_OS, "intray"]))
        self.assertTrue(calls[1][1].startswith(("Nothing moved today.", "Today:")), calls[1][1])
        self.assertIn("1 ticked item cleared and 1 job finished, in your in-tray.", calls[1][1])
        self.assertIn("The day is closed. 1 thing will run tonight", calls[2][1])
        self.assertEqual(calls[3], ("run", ["systemd-inhibit", "--what=sleep:idle"]))
        self.assertNotIn(("lock",), calls)
        lines = open(path).read().splitlines()
        self.assertEqual(len(lines), 2)                       # the ticked line left; open ones stay queued
        self.assertIn("→ started with Claude overnight", lines[0])
        self.assertEqual(lines[1], "- [ ] 2026-10-15: research x")
        self.assertIn("dentist friday", open(day.DONE_FILE).read())
        # nothing is moved: the job folders stay where agent-os keeps them, and there is no done/ folder
        self.assertTrue(os.path.isdir(old_job))
        self.assertTrue(os.path.isdir(os.path.join(day.JOBS_DIR, "2026-10-18-busy")))
        self.assertFalse(os.path.exists(os.path.join(day.JOBS_DIR, "done")))
        self.assertEqual(len(os.listdir(day.PAGES)), 1)
        page = open(os.path.join(day.PAGES, os.listdir(day.PAGES)[0])).read()
        self.assertIn("Cleared from the remember list: dentist friday", page)
        self.assertIn("Jobs finished today: 2026-10-15-old (the clock is fixed)", page)

    def test_flag_value_and_picks_from_flag(self):
        self.assertEqual(day._flag_value(["--run", "--picks=3,7"], "--picks"), "3,7")
        self.assertEqual(day._flag_value(["--run", "--picks="], "--picks"), "")
        self.assertIsNone(day._flag_value(["--run"], "--picks"))
        mod = types.SimpleNamespace(items=lambda: [(2, "d", "a"), (5, "d", "b"), (9, "d", "c")])
        self.assertEqual(day.picks_from_flag(mod, "5, 9,x"), [(5, "d", "b"), (9, "d", "c")])
        self.assertEqual(day.picks_from_flag(mod, ""), [])
        self.assertEqual(day.picks_from_flag(mod, "4"), [])        # a line that is not an open item is ignored

    def test_eod_run_with_picks_and_silent_asks_nothing_and_says_nothing(self):
        path = os.path.join(self.tmp.name, "remembered.md")
        day.write(path, "- [ ] 2026-10-15: build the thing\n- [ ] 2026-10-15: research x\n")
        real = day.remind_list()
        real.PATH = path
        real.items = lambda p=path, f=real.items: f(p)
        real.menu = lambda prompt, options: self.fail("the menu must not open when picks are given")
        calls = []
        saved = (day.remind_list, day.say, day.busy, day.save_snapshot, day.all_commits, day.subprocess.run)
        day.remind_list, day.say = (lambda: real), (lambda text, wait=True: calls.append(("say", text)))
        day.busy = lambda: ["example-game"]
        day.save_snapshot, day.all_commits = (lambda d, overwrite=True: None), (lambda s, e: {})
        day.subprocess.run = lambda argv, **k: calls.append(("run", argv[:2])) or subprocess.CompletedProcess(argv, 0)
        try:
            self.assertEqual(day.cmd_eod(["--run", "--silent", "--picks=1"]), 0)
        finally:
            (day.remind_list, day.say, day.busy, day.save_snapshot, day.all_commits, day.subprocess.run) = saved
        self.assertEqual([c for c in calls if c[0] == "say"], [])            # silent
        self.assertEqual(calls, [("run", [day.AGENT_OS, "intray"]),
                                 ("run", ["systemd-inhibit", "--what=sleep:idle"])])   # busy helpers keep running
        c = day.read_jsonl(day.CLOSEOUTS)[-1]
        self.assertEqual((c["picked"], c["running"]), (["research x"], ["example-game"]))
        lines = open(path).read().splitlines()
        self.assertEqual(lines[0], "- [ ] 2026-10-15: build the thing")      # not picked: stays on the list
        self.assertIn("→ started with Claude overnight", lines[1])

    def test_goodnight_is_eod(self):
        self.assertIs(day.cmd_goodnight, day.cmd_eod)

    def test_end_of_day_never_files_jobs(self):
        self.assertFalse(hasattr(day, "file_finished_jobs"))
        with open(day.__file__) as f:
            self.assertNotIn('"done"', f.read())


class InTray(Base):
    """End of day and the standup read agent-os's in-tray (jobs/in-tray.md) and history files (jobs/history/)."""

    def test_finished_on_the_day_from_tray_and_history(self):
        write_tray(day.JOBS_DIR, [("new", "2026-10-15", "a-job", "ask a", "result a"),
                                  ("read", "2026-10-15", "b-job", "ask b", "result | with bar"),
                                  ("new", "2026-10-14", "old-new", "x", "y"),
                                  ("old", "2026-10-15", "c-job", "ask c", "result c")])
        write_history(day.JOBS_DIR, "2026-10", [("2026-10-15", "c-job", "ask c", "result c"),
                                                ("2026-10-15", "d-job", "ask d", "result d"),
                                                ("2026-10-13", "e-job", "ask e", "result e")])
        got = day.finished_jobs(day.JOBS_DIR, dt.date(2026, 10, 15))
        self.assertEqual(got, [("a-job", "result a"), ("b-job", "result / with bar"), ("c-job", "result c"),
                               ("d-job", "result d")])
        self.assertEqual(day.new_reports(day.JOBS_DIR), 2)

    def test_after_midnight_counts_for_the_day(self):
        write_history(day.JOBS_DIR, "2026-11", [("2026-11-01", "late", "ask", "done late")])
        self.assertEqual(day.finished_jobs(day.JOBS_DIR, dt.date(2026, 10, 31), today=dt.date(2026, 11, 1)),
                         [("late", "done late")])
        self.assertEqual(day.finished_jobs(day.JOBS_DIR, dt.date(2026, 10, 31)), [])

    def test_missing_or_broken_files_are_nothing(self):
        self.assertEqual(day.finished_jobs(day.JOBS_DIR, dt.date(2026, 10, 15)), [])
        self.assertEqual(day.new_reports(day.JOBS_DIR), 0)
        day.write(os.path.join(day.JOBS_DIR, "in-tray.md"), "| new | not a date | x | y | z | | r |\n| a | b |\n")
        day.write(os.path.join(day.JOBS_DIR, "history", "notes.md"), "| 2026-10-15 | x | y | z | | r |\n")
        self.assertEqual(day.finished_jobs(day.JOBS_DIR, dt.date(2026, 10, 15)), [])
        self.assertEqual(day.new_reports(day.JOBS_DIR), 0)

    def test_refresh_failure_is_quiet(self):
        day.refresh_intray()   # day.AGENT_OS does not exist: nothing raised

    def test_refresh_runs_agent_os_intray_on_the_jobs_folder(self):
        fake = os.path.join(self.tmp.name, "fake-agent-os")
        seen = os.path.join(self.tmp.name, "seen")
        day.write(fake, "#!/bin/sh\necho \"$* $AGENT_OS_HOME\" > %s\n" % seen)
        os.chmod(fake, 0o755)
        day.AGENT_OS = fake
        day.refresh_intray()
        self.assertEqual(open(seen).read().strip(), "intray " + day.JOBS_DIR)

    def test_standup_names_new_reports(self):
        write_tray(day.JOBS_DIR, [("new", "2026-10-15", "a-job", "ask a", "result a")])
        saved = (day.all_commits, day.waiting_line, day.remind_list)
        day.all_commits, day.waiting_line = (lambda s, e: {}), (lambda: "")
        day.remind_list = lambda: types.SimpleNamespace(items=lambda: [])
        try:
            text, spoken = day.standup(ts("2026-10-16 09:00"))
        finally:
            day.all_commits, day.waiting_line, day.remind_list = saved
        self.assertIn("- In-tray: 1 new finished report.", text)
        self.assertIn("1 new report in your in-tray.", spoken)


def write_tray(jobs_dir, rows):
    """An in-tray as agent-os writes it (engine/intray.py): state, date, job, ask, result, cost, report."""
    body = ["---", "standing: observation", "---", "# In-tray", "", "## New", "",
            "| state | date | job | ask | result | cost | report |", "|---|---|---|---|---|---|---|"]
    body += ["| %s | %s | %s | %s | %s |  | ~/agent-os/jobs/%s/report.md |" % (st, d, j, a, r.replace("|", "/"), j)
             for st, d, j, a, r in rows]
    day.write(os.path.join(jobs_dir, "in-tray.md"), "\n".join(body) + "\n")


def write_history(jobs_dir, month, rows):
    """A month file as agent-os writes it (engine/history.py): date, job, ask, result, cost, report."""
    body = ["# %s" % month, "", "| date | job | ask | result | cost | report |", "|---|---|---|---|---|---|"]
    body += ["| %s | %s | %s | %s |  | no report |" % row for row in rows]
    day.write(os.path.join(jobs_dir, "history", month + ".md"), "\n".join(body) + "\n")

    def test_clear_ticked_without_ticks_leaves_the_file(self):
        path = os.path.join(self.tmp.name, "r.md")
        day.write(path, "# list\n- [ ] 2026-10-15: a\n")
        before = os.path.getmtime(path)
        self.assertEqual(day.clear_ticked(path, day.DONE_FILE, dt.date(2026, 10, 15)), [])
        self.assertEqual(os.path.getmtime(path), before)
        self.assertFalse(os.path.exists(day.DONE_FILE))

    def test_result_read_back_from_morning_build(self):
        day.write(day.MB_HANDLED, "# note id\tverdict\thandled at\twhere / why\tnote\n"
                  "x\tbuilt:done\t2026-10-16 02:10\t/runs/abc\tbuild the thing\n")
        self.assertEqual(day.handled_since("build the thing", ts("2026-10-16 02:00")), ("built:done", "/runs/abc"))
        self.assertIsNone(day.handled_since("build the thing", ts("2026-10-16 03:00")))


class Standup(Base):
    def run_once(self):
        saved = (day.standup, day.say, day.notify_open)
        calls = []
        day.standup = lambda now=None: (calls.append(1) or "page\n", "spoken")
        day.say, day.notify_open = (lambda *a, **k: None), (lambda *a, **k: None)
        try:
            day.cmd_standup(["--once"])
        finally:
            day.standup, day.say, day.notify_open = saved
        return len(calls)

    def test_once_a_day_and_only_in_the_morning(self):
        old = day.STANDUP_BEFORE
        try:
            day.STANDUP_BEFORE = 25          # any hour counts as morning
            self.assertEqual(self.run_once(), 1)
            self.assertEqual(self.run_once(), 0)   # already done today
            for f in os.listdir(day.DATA):
                if f.startswith("standup-done-"):
                    os.remove(os.path.join(day.DATA, f))
            day.STANDUP_BEFORE = 0           # every hour is past 11:00 (the 12:00 and 18:00 reminders)
            self.assertEqual(self.run_once(), 0)
        finally:
            day.STANDUP_BEFORE = old

    def test_result_words(self):
        self.assertEqual(day.result_words("built:done"), "built")
        self.assertEqual(day.result_words("built:failed"), "build failed")
        self.assertEqual(day.result_words("not_idea"), "skipped, not something to build")


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
        for t in ("goodnight", "ok I'm going to bed", "close out the day", "bedtime", "end of day", "EOD",
                  "okay end of the day"):
            j = self.job(t)
            self.assertEqual((j["id"], j["needs_confirm"]), ("goodnight", True), t)
            self.assertIn("day eod", j["command"])
        self.assertNotEqual(jobs.match_rule("good night light on"), "goodnight")
        self.assertNotEqual(jobs.match_rule("remind me at the end of the day to call mom"), "goodnight")

    def test_yesterday_asks(self):
        for t in ("what about yesterday?", "how was yesterday", "what did we do yesterday", "tell me about yesterday"):
            self.assertEqual(self.job(t)["args"], {"when": "yesterday"}, t)

    def test_run_checks_when(self):
        with self.assertRaises(ValueError):
            jobs._check("what-changed", {"when": "; rm -rf ~"})


if __name__ == "__main__":
    unittest.main()
