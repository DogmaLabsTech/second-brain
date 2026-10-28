"""brain memory-drafts (eval/memory_drafts.py): lesson drafts, already-known, was-pushed, the weekly cap, expiry, drop.
Everything runs in temp folders with made-up names; the real store, hook log and names list are never touched.
Run: CRABBOX_LOCAL=1 python3 -I eval/test_memory_drafts.py   (no network, no model)"""
import contextlib
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.environ["BRAIN_STATE"] = tempfile.mkdtemp(prefix="mdraft-test-state-")
import drafts  # noqa: E402
import memory_drafts  # noqa: E402
import memory_keep  # noqa: E402

GIT_ENV = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.invalid"}
BODY = "The tests were run on this computer and the test machine lane was busy, so the run waited.\nWait in the queue."


def fake_scrub(text):
    if "unsure" in text:
        raise drafts.Unsure("test")
    return re.sub(r"zorblax", "[NAME]", text, flags=re.I)


def write_note(store, rel, summary, date="2026-10-01", body="Body."):
    path = os.path.join(store, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write("---\nproject: x\nkind: lesson\ndate: %s\nsummary: %s\nfiles: []\npinned: false\n---\n%s\n" % (date, summary, body))
    return path


class Case(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="mdraft-test-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.store = os.path.join(self.tmp, "shared")
        os.makedirs(os.path.join(self.store, "drafts"))
        for p in (mock.patch.object(drafts, "scrub", fake_scrub),
                  mock.patch.dict(os.environ, {"BRAIN_MEMORY_STORE": self.store, "BRAIN_HOOK_STATE": self.tmp, **GIT_ENV})):
            p.start()
            self.addCleanup(p.stop)

    def add(self, job="job-1", title="test machine busy means wait in the queue", today="2026-10-28", **kw):
        kw.setdefault("search", None)
        kw.setdefault("hook_rows", [])
        return memory_drafts.add("projects/second-brain/lessons", job, title, "job %s: check records" % job,
                                 kw.pop("body", BODY), store=self.store, today=today, **kw)

    def text(self, got):
        with open(got["path"], encoding="utf-8") as f:
            return f.read()


class Add(Case):
    def test_a_draft_is_written_in_the_note_format_with_its_source(self):
        got = self.add(files=["eval/drafts.py"])
        self.assertEqual(got["path"], os.path.join(self.store, "drafts", "second-brain-lesson-testbox-busy-means-wait-in-the.md"))
        text = self.text(got)
        self.assertTrue(text.startswith("---\nto: projects/second-brain/lessons\nsummary: test machine busy means wait in the queue\n"
                                        "files:\n  - eval/drafts.py\npinned: false\nalready-known: no\nwas-pushed: no\n"), text)
        self.assertIn("date: 2026-10-28\njob: job-1\n---\n# test machine busy means wait in the queue\n\n" + BODY, text)
        self.assertTrue(text.endswith("\nSource: job job-1: check records\n"))
        self.assertEqual((got["already_known"], got["was_pushed"], got["same_as"]), (False, "no", None))

    def test_the_text_goes_through_the_names_filter_first(self):
        got = self.add(title="Zorblax broke the build", body="Zorblax pushed.")
        self.assertNotIn("orblax", self.text(got))
        self.assertIn("[NAME] broke the build", self.text(got))

    def test_an_unsure_filter_writes_nothing(self):
        with self.assertRaisesRegex(memory_drafts.DraftError, "names filter was not sure"):
            self.add(body="this is unsure")
        self.assertEqual(os.listdir(os.path.join(self.store, "drafts")), [])
        self.assertEqual(memory_drafts.log_rows(self.store), [])

    def test_a_missing_store_a_bad_target_and_empty_words_are_plain_refusals(self):
        with mock.patch.dict(os.environ, {"BRAIN_MEMORY_STORE": os.path.join(self.tmp, "nope")}):
            with self.assertRaisesRegex(memory_drafts.DraftError, "store is not there"):
                memory_drafts.add("projects/x/lessons", "j", "t", "s", "b", today="2026-10-28")
        with self.assertRaisesRegex(memory_drafts.DraftError, "not a place in the store"):
            memory_drafts.add("../x", "j", "t", "s", "b", store=self.store)
        with self.assertRaisesRegex(memory_drafts.DraftError, "needs --job"):
            self.add(job="")

    def test_two_drafts_with_one_title_get_two_names(self):
        a, b = self.add(job="j1"), self.add(job="j2")
        self.assertNotEqual(a["name"], b["name"])
        self.assertTrue(b["name"].endswith("-2.md"))

    def test_a_draft_can_be_kept_and_the_extra_fields_do_not_reach_the_note(self):
        got = self.add()
        subprocess.run(["git", "init", "-q", self.store], check=True)
        with mock.patch.object(memory_keep, "guard_problem", lambda: None):
            kept = memory_keep.keep(got["name"], "projects/second-brain/lessons", store=self.store, today="2026-10-29",
                                    summarize=lambda t: "Wait in the queue when the test machine is busy.")
        with open(kept["path"]) as f:
            note = f.read()
        self.assertTrue(note.startswith("---\nproject: second-brain\nkind: lesson\ndate: 2026-10-29\n"), note)
        for field in ("already-known", "was-pushed", "to:", "job:"):
            self.assertNotIn(field, note.split("---\n")[1])


class Known(Case):
    def test_a_note_that_says_the_same_makes_already_known_yes(self):
        write_note(self.store, "projects/second-brain/lessons/queue.md", "Wait in the queue when the test machine is busy")
        got = self.add()
        self.assertTrue(got["already_known"])
        self.assertEqual(got["same_as"], "projects/second-brain/lessons/queue.md")
        self.assertIn("already-known: yes\n", self.text(got))
        self.assertIn("same-as: projects/second-brain/lessons/queue.md\n", self.text(got))

    def test_the_opposite_of_a_note_is_not_the_same(self):
        write_note(self.store, "projects/second-brain/lessons/queue.md", "Never wait in the queue when the test machine is busy")
        self.assertFalse(self.add()["already_known"])

    def test_a_note_of_another_project_is_not_looked_at_but_all_projects_is(self):
        write_note(self.store, "projects/other/lessons/queue.md", "Wait in the queue when the test machine is busy")
        self.assertFalse(self.add()["already_known"])
        write_note(self.store, "all-projects/lessons/queue.md", "Wait in the queue when the test machine is busy")
        self.assertTrue(self.add(job="j2")["already_known"])

    def test_search_proposes_the_candidates_when_it_answers(self):
        write_note(self.store, "projects/second-brain/lessons/queue.md", "Wait in the queue when the test machine is busy")
        got = self.add(search=lambda title: [])   # search found nothing: nothing to compare
        self.assertFalse(got["already_known"])


class Pushed(Case):
    NOTE = "projects/second-brain/lessons/queue.md"

    def setUp(self):
        super().setUp()
        self.path = write_note(self.store, self.NOTE, "Wait in the queue when the test machine is busy")

    jobs = 0

    def pushed(self, rows, **kw):
        Pushed.jobs += 1
        return self.add(job="pj%d" % Pushed.jobs, hook_rows=rows, **kw)["was_pushed"]

    def push(self, when, paths, session="s1", repo="second-brain"):
        return {"repo": repo, "when": when, "session": session, "notes": len(paths), "paths": paths}

    def test_yes_when_the_note_was_in_a_push_in_the_jobs_window(self):
        rows = [self.push("2026-10-28T10:00:00", [self.path])]
        self.assertEqual(self.pushed(rows, window=("2026-10-28T09:00:00", "2026-10-28T12:00:00")), "yes")

    def test_no_when_pushes_were_there_but_not_this_note(self):
        rows = [self.push("2026-10-28T10:00:00", ["/elsewhere/other.md"])]
        self.assertEqual(self.pushed(rows, window=("2026-10-28T09:00:00", "2026-10-28T12:00:00")), "no")

    def test_unknown_without_a_push_line_or_with_old_lines_that_held_no_paths(self):
        window = ("2026-10-28T09:00:00", "2026-10-28T12:00:00")
        self.assertEqual(self.pushed([], window=window), "unknown")
        self.assertEqual(self.pushed([{"repo": "second-brain", "when": "2026-10-28T10:00:00", "notes": 3}], window=window), "unknown")
        self.assertEqual(self.pushed([self.push("2026-10-28T10:00:00", [self.path])]), "unknown")   # no window, no sessions

    def test_a_push_outside_the_window_or_for_another_project_does_not_count(self):
        window = ("2026-10-28T09:00:00", "2026-10-28T12:00:00")
        rows = [self.push("2026-10-27T10:00:00", [self.path]), self.push("2026-10-28T10:00:00", [self.path], repo="other")]
        self.assertEqual(self.pushed(rows, window=window), "unknown")

    def test_sessions_name_the_pushes_when_given(self):
        rows = [self.push("2026-01-01T00:00:00", [self.path], session="abc")]
        self.assertEqual(self.pushed(rows, sessions=["abc"]), "yes")
        self.assertEqual(self.pushed(rows, sessions=["zzz"]), "unknown")

    def test_the_real_hook_log_is_read_from_the_hook_state_folder(self):
        with open(os.path.join(self.tmp, "memory-hook.jsonl"), "w") as f:
            f.write('{"repo": "second-brain", "when": "2026-10-28T10:00:00", "session": "s", "paths": [%s]}\n'
                    % __import__("json").dumps(self.path))
        got = memory_drafts.add("projects/second-brain/lessons", "jx", "Wait in the queue when the test machine is busy", "src", BODY,
                                store=self.store, today="2026-10-28", search=None, window=("2026-10-28T09:00:00", "2026-10-28T12:00:00"))
        self.assertEqual((got["already_known"], got["was_pushed"]), (True, "yes"))


class Limits(Case):
    def test_five_drafts_a_week_and_a_sixth_is_refused_in_plain_words(self):
        for i in range(5):
            self.add(job="j%d" % i, title="lesson number %d is here" % i)
        with self.assertRaisesRegex(memory_drafts.DraftError, "5 drafts were already written in week 2026-W44"):
            self.add(job="j5", title="a sixth lesson")
        self.assertEqual(len(memory_drafts.waiting(self.store)), 5)

    def test_keeping_or_dropping_a_draft_does_not_free_a_place(self):
        for i in range(5):
            self.add(job="j%d" % i, title="lesson number %d is here" % i)
        memory_drafts.drop(memory_drafts.waiting(self.store)[0]["name"], self.store)
        with self.assertRaises(memory_drafts.DraftError):
            self.add(job="j5", title="a sixth lesson")

    def test_the_next_week_starts_again_by_the_drafts_date(self):
        for i in range(5):
            self.add(job="j%d" % i, title="lesson number %d is here" % i, today="2026-10-28")   # Wednesday, week 44
        self.add(job="j5", title="a lesson of the new week", today="2026-11-02")   # Monday, week 45

    def test_one_draft_per_job(self):
        self.add()
        with self.assertRaisesRegex(memory_drafts.DraftError, "already written for job job-1"):
            self.add(title="another")


class Inbox(Case):
    def test_drafts_older_than_30_days_move_to_expired_drafts_and_nothing_is_deleted(self):
        old, new = self.add(job="a", today="2026-09-20"), self.add(job="b", title="a newer one", today="2026-10-20")
        self.assertEqual(memory_drafts.expire(self.store, "2026-10-28"), [os.path.basename(old["path"])])
        self.assertTrue(os.path.exists(os.path.join(self.store, "history", "expired-drafts", os.path.basename(old["path"]))))
        self.assertTrue(os.path.exists(new["path"]))
        self.assertFalse(os.path.exists(old["path"]))
        self.assertEqual([d["name"] for d in memory_drafts.waiting(self.store)], [os.path.basename(new["path"])])

    def test_exactly_30_days_stays_and_a_draft_with_no_date_ages_by_its_file(self):
        self.add(today="2026-09-28")
        self.assertEqual(memory_drafts.expire(self.store, "2026-10-28"), [])
        undated = os.path.join(self.store, "drafts", "undated.md")
        with open(undated, "w") as f:
            f.write("just text\n")
        os.utime(undated, (1, 1))
        self.assertEqual(memory_drafts.expire(self.store, "2026-10-28"), ["undated.md"])

    def test_drop_moves_to_dropped_drafts(self):
        got = self.add()
        dest = memory_drafts.drop(os.path.basename(got["path"]), self.store)
        self.assertEqual(dest, os.path.join(self.store, "history", "dropped-drafts", os.path.basename(got["path"])))
        with self.assertRaisesRegex(memory_drafts.DraftError, "no memory draft called"):
            memory_drafts.drop("nope.md", self.store)

    def test_an_expired_draft_is_never_pushed(self):
        import memory
        got = self.add(today="2026-09-01")
        memory_drafts.expire(self.store, "2026-10-28")
        self.assertIn("No notes for", memory.find("second-brain", store=self.store)["text"])


class Command(Case):
    def test_add_reads_the_body_from_stdin_and_list_shows_it(self):
        out, err = io.StringIO(), io.StringIO()
        argv = ["add", "--to", "projects/second-brain/lessons", "--job", "j9", "--title", "Wait when the test machine is busy",
                "--source", "job j9", "--files", "a.py,b.py", "--sessions", "s1"]
        with mock.patch.object(sys, "stdin", io.StringIO(BODY)), mock.patch.object(memory_drafts, "already_known", lambda *a: None), \
                mock.patch.object(memory_drafts, "hook_log_rows", lambda: []), contextlib.redirect_stdout(out):
            self.assertEqual(memory_drafts.main(argv), 0)
        self.assertIn("draft written:", out.getvalue())
        self.assertIn("already known: no, was pushed: no)", out.getvalue())   # no kept note matches, so nothing was pushed
        listing = io.StringIO()
        with contextlib.redirect_stdout(listing):
            memory_drafts.main(["list"])
        self.assertIn("Wait when the test machine is busy", listing.getvalue())

    def test_a_refusal_is_a_plain_message_and_exit_1(self):
        err = io.StringIO()
        with mock.patch.object(sys, "stdin", io.StringIO("x")), contextlib.redirect_stderr(err):
            self.assertEqual(memory_drafts.main(["add", "--to", "projects/x/lessons"]), 1)
        self.assertIn("brain memory-drafts:", err.getvalue())


if __name__ == "__main__":
    unittest.main()
