"""The agent memory part of the weekly check-up (eval/memory_week.py, eval/checkup.py): the list and the two numbers.
Made-up jobs, a temp store; the real store and ~/agent-os/jobs are never read.
Run: CRABBOX_LOCAL=1 python3 -I eval/test_memory_week.py   (no network, no model)"""
import json
import os
import shutil
import sys
import tempfile
import time
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.environ["BRAIN_MEMORY_DECIDER"] = "off"   # tests never ask the decider (the second decider); test_memory_decide.py tests it with a fake
os.environ["BRAIN_STATE"] = tempfile.mkdtemp(prefix="mweek-test-state-")
os.environ["BRAIN_DRAFT_WRITER"] = "fixed"   # tests never call the real Haiku
import checkup  # noqa: E402
import memory_drafts  # noqa: E402
import memory_flagfile  # noqa: E402
import memory_week  # noqa: E402

TODAY = "2026-10-28"
NOW = time.mktime(time.strptime("2026-10-28 12:00", "%Y-%m-%d %H:%M"))


def read(path):
    with open(path) as f:
        return f.read()


def stamp(path, days_ago):
    when = NOW - days_ago * 86400
    os.utime(path, (when, when))


class Case(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="mweek-test-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.store, self.jobs = os.path.join(self.tmp, "shared"), os.path.join(self.tmp, "jobs")
        for d in (os.path.join(self.store, "drafts"), os.path.join(self.jobs, "done")):
            os.makedirs(d)
        p = mock.patch.dict(os.environ, {"BRAIN_MEMORY_STORE": self.store, "AGENT_OS_HOME": self.jobs,
                                         "BRAIN_PROJECTS_DIR": os.path.join(self.tmp, "none")})
        p.start()
        self.addCleanup(p.stop)

    def job(self, name, records, days_ago=1, done=False):
        folder = os.path.join(self.jobs, "done" if done else "", name)
        os.makedirs(folder)
        for file, text in records.items():
            with open(os.path.join(folder, file), "w") as f:
                f.write(text)
            stamp(os.path.join(folder, file), days_ago)
        return folder

    def log(self, **row):
        with open(os.path.join(self.store, memory_drafts.LOG), "a") as f:
            f.write(json.dumps(dict({"week": "2026-W44"}, **row)) + "\n")


class SecondRound(Case):
    def test_jobs_finished_this_week_with_fix_2_or_more_over_all_finished_jobs(self):
        self.job("j1", {"check-aaaaaaa.md": "result: fail\nfix: 1\n", "check-bbbbbbb.md": "result: pass\nfix: 2\n"})
        self.job("j2", {"check-ccccccc.md": "- **result:** pass\n- **fix:** 1\n"})
        self.job("j3", {"check-ddddddd.md": "# Check\n\n## Result\n\nPASS, all green\n\n- **fix:** 3\n"}, done=True)
        self.assertEqual(memory_week.second_round_rate(7, TODAY), (2, 3))

    def test_a_job_not_finished_or_finished_outside_the_week_does_not_count(self):
        self.job("open", {"check-aaaaaaa.md": "result: fail\nfix: 2\n"})                       # never passed
        self.job("old", {"check-bbbbbbb.md": "result: pass\nfix: 2\n"}, days_ago=20)             # last month
        self.job("none", {"report.md": "result: done\n"})                                       # no check record at all
        self.job("unreadable", {"check-ccccccc.md": "just words about the check\n"})
        self.assertEqual(memory_week.second_round_rate(7, TODAY), (0, 0))

    def test_no_jobs_folder_is_zero_of_zero(self):
        self.assertEqual(memory_week.second_round_rate(7, TODAY, home=os.path.join(self.tmp, "nope")), (0, 0))

    def test_a_real_check_record_shape(self):
        self.job("real", {"check-d5d1231.md": "# Check record: x\n\n- **commit:** `d5d1231`\n- **fix:** 1 (the lead's round; "
                          "this check sends it back for fix 2)\n\n## Result\n\nPASS\n"})
        self.assertEqual(memory_week.second_round_rate(7, TODAY), (0, 1))


class Repeats(Case):
    def test_only_known_and_pushed_drafts_of_the_week_count(self):
        self.log(date="2026-10-27", already_known="yes", was_pushed="yes")
        self.log(date="2026-10-28", already_known="yes", was_pushed="yes")
        self.log(date="2026-10-28", already_known="yes", was_pushed="no")
        self.log(date="2026-10-28", already_known="yes", was_pushed="unknown")
        self.log(date="2026-10-28", already_known="no", was_pushed="no")
        self.log(date="2026-10-10", already_known="yes", was_pushed="yes")   # last month
        self.assertEqual(memory_week.repeat_count(self.store, 7, TODAY), 2)


class Report(Case):
    def test_the_list_has_drafts_flags_pinned_and_the_two_numbers(self):
        os.makedirs(os.path.join(self.store, "projects", "demo", "lessons"))
        for name, pinned, date in (("flagged.md", "false", "2026-09-01"), ("pin.md", "true", "2026-06-01")):
            with open(os.path.join(self.store, "projects", "demo", "lessons", name), "w") as f:
                f.write("---\nproject: demo\nkind: lesson\ndate: %s\nsummary: Note %s\nfiles: []\npinned: %s\n---\nB\n" % (date, name, pinned))
        memory_flagfile.append(self.store, [{"note": "projects/demo/lessons/flagged.md", "state": "flagged", "at": "2026-10-20",
                                             "kind": "file-gone", "reason": "src/x.py is not in demo any more"}])
        with mock.patch.object(drafts_scrub(), "scrub", lambda t: t):
            memory_drafts.add("projects/demo/lessons", "jx", "Wait in the queue", "job jx", "Body text about the queue and waiting.",
                              store=self.store, today=TODAY, search=None, hook_rows=[])
        self.job("j1", {"check-aaaaaaa.md": "result: pass\nfix: 2\n"})
        with mock.patch.object(memory_week.memory_flags, "look", lambda store, today=None, search="qmd": {
                "new": [], "flagged": memory_flagfile.flagged(store), "pins_due": [("projects/demo/lessons/pin.md", 149)]}):
            got = memory_week.report(7, TODAY)
        text = "\n".join(got["lines"])
        self.assertIn("new draft demo-lesson-wait-in-the-queue.md", text)
        self.assertIn("Keep: brain drafts keep demo-lesson-wait-in-the-queue.md", text)
        self.assertIn("flag projects/demo/lessons/flagged.md (8 days): src/x.py is not in demo any more", text)
        self.assertIn("Keep: brain memory-flags confirm flagged.md", text)
        self.assertIn("Retire: brain memory-flags retire flagged.md", text)
        self.assertIn("pinned, still true? last checked 149 days ago", text)
        self.assertIn("repeats that got through (already known and pushed): 0", text)
        self.assertIn("second-round rate (desk jobs finished with fix 2 or more): 1/1", text)
        self.assertEqual((got["repeats"], got["second_round"]), (0, (1, 1)))

    def test_a_week_with_nothing_says_so_and_a_missing_store_does_not_crash(self):
        with mock.patch.object(memory_week.memory_flags, "look", lambda store, today=None, search="qmd": {
                "new": [], "flagged": {}, "pins_due": []}):
            self.assertIn("  nothing waits", memory_week.report(7, TODAY)["lines"])
        shutil.rmtree(self.store)
        got = memory_week.report(7, TODAY)
        self.assertIn("no store at", got["lines"][0])
        self.assertIsNone(got["repeats"])

    def test_old_drafts_are_moved_by_the_report(self):
        with mock.patch.object(drafts_scrub(), "scrub", lambda t: t):
            got = memory_drafts.add("projects/demo/lessons", "jold", "An old lesson", "job", "Body.", store=self.store,
                                    today="2026-09-01", search=None, hook_rows=[])
        with mock.patch.object(memory_week.memory_flags, "look", lambda store, today=None, search="qmd": {
                "new": [], "flagged": {}, "pins_due": []}):
            text = "\n".join(memory_week.report(7, TODAY)["lines"])
        self.assertIn("moved to history/expired-drafts/", text)
        self.assertTrue(os.path.exists(os.path.join(self.store, "history", "expired-drafts", got["name"])))


def drafts_scrub():
    import drafts
    return drafts


class InTheCheckup(unittest.TestCase):
    def test_the_two_numbers_go_into_the_score_row_and_the_header_has_their_names(self):
        tmp = tempfile.mkdtemp(prefix="mweek-row-")
        self.addCleanup(shutil.rmtree, tmp, True)
        s = {"top1": 1, "top3": 2, "n": 4, "newer_ok": 0, "newer_n": 0}
        with mock.patch.object(checkup, "HERE", tmp):
            checkup._append_scores(s, None, [], [], [], None, ([], 2, "1/5"))
            checkup._append_scores(s, None, [], [], [], None, None)
        rows = [l.split("\t") for l in read(os.path.join(tmp, "scores.tsv")).splitlines()]
        head = rows[0]
        self.assertEqual(head[-3:], ["repeats", "second_round", "note"])
        self.assertEqual([rows[1][head.index("repeats")], rows[1][head.index("second_round")]], ["2", "1/5"])
        self.assertEqual([rows[2][head.index("repeats")], rows[2][head.index("second_round")]], ["-", "-"])

    def test_memory_block_returns_the_lines_and_the_numbers(self):
        fake = {"lines": ["Agent memory for <user>:"], "repeats": 1, "second_round": (2, 5)}
        with mock.patch.object(checkup.memory_week, "report", lambda days: fake):
            self.assertEqual(checkup.memory_block(7), (["Agent memory for <user>:"], 1, "2/5"))
        with mock.patch.object(checkup.memory_week, "report", lambda days: dict(fake, repeats=None, second_round=None)):
            self.assertEqual(checkup.memory_block(7), (["Agent memory for <user>:"], None, None))

    def test_the_old_scores_file_still_lines_up(self):
        path = os.path.join(os.path.dirname(HERE), "eval", "scores.tsv")
        rows = [l.split("\t") for l in read(path).splitlines()]
        self.assertEqual({len(r) for r in rows}, {len(rows[0])})


if __name__ == "__main__":
    unittest.main()
