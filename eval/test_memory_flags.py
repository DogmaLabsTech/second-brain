"""brain memory-flags (eval/memory_flags.py, ask/memory_flagfile.py) and what a flag does to `brain memory` and the push.
Temp stores and temp project repos only; the real store and projects are never touched.
Run: CRABBOX_LOCAL=1 python3 -I eval/test_memory_flags.py   (no network, no model)"""
import contextlib
import io
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.environ["BRAIN_MEMORY_DECIDER"] = "off"   # tests never ask the decider (the second decider); test_memory_decide.py tests it with a fake
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "ask"))
import memory  # noqa: E402
import memory_flagfile  # noqa: E402
import memory_flags  # noqa: E402

GIT_ENV = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.invalid"}
NOTE = "projects/demo/lessons/a.md"


def git(cwd, *args, env=None):
    return subprocess.run(["git", "-C", cwd, *args], capture_output=True, text=True, check=True,
                          env=dict(os.environ, **(env or {}))).stdout


def note(store, rel, summary="Run the tests on the test machine", date="2026-09-01", files=(), pinned=False):
    path = os.path.join(store, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fm = ["---", "project: x", "kind: lesson", "date: " + date, "summary: " + summary]
    fm += ["files:"] + ["  - " + f for f in files] if files else ["files: []"]
    fm += ["pinned: " + ("true" if pinned else "false"), "---", "Body.", ""]
    with open(path, "w") as f:
        f.write("\n".join(fm))
    return path


class Case(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="mflags-test-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.store, self.projects = os.path.join(self.tmp, "shared"), os.path.join(self.tmp, "Projects")
        os.makedirs(self.store)
        os.makedirs(os.path.join(self.projects, "demo"))
        self.repo = os.path.join(self.projects, "demo")
        git(self.repo, "init", "-q", "-b", "main")
        p = mock.patch.dict(os.environ, {"BRAIN_MEMORY_STORE": self.store, "BRAIN_PROJECTS_DIR": self.projects, **GIT_ENV})
        p.start()
        self.addCleanup(p.stop)

    def commit(self, name, text, date):
        with open(os.path.join(self.repo, name), "w") as f:
            f.write(text)
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "change " + name,
            env={"GIT_AUTHOR_DATE": date + "T12:00:00", "GIT_COMMITTER_DATE": date + "T12:00:00"})

    def look(self, today="2026-10-28", search=None):
        return memory_flags.look(self.store, today, search)

    def reasons(self, result):
        return {rel: (kind, why) for rel, kind, why in result["new"]}


class Files(Case):
    def test_a_file_that_is_gone_flags_the_note(self):
        note(self.store, NOTE, files=["src/gone.py"])
        got = self.reasons(self.look())
        self.assertEqual(got[NOTE][0], "file-gone")
        self.assertIn("src/gone.py is not in demo any more", got[NOTE][1])

    def test_a_note_kept_in_the_last_3_days_is_not_checked_for_a_gone_file(self):
        note(self.store, NOTE, files=["src/new.py"], date="2026-10-27")
        self.assertEqual(self.look()["new"], [])

    def test_a_file_that_is_there_and_little_changed_is_fine(self):
        self.commit("a.py", "".join("line %d\n" % i for i in range(100)), "2026-08-01")
        self.commit("a.py", "".join("line %d\n" % i for i in range(100)) + "one more\n", "2026-10-10")
        note(self.store, NOTE, files=["a.py"])
        self.assertEqual(self.look()["new"], [])

    def test_a_file_changed_a_lot_since_the_note_flags_it(self):
        self.commit("a.py", "".join("line %d\n" % i for i in range(100)), "2026-08-01")
        self.commit("a.py", "".join("new %d\n" % i for i in range(100)), "2026-10-10")   # 200 lines changed of 100
        note(self.store, NOTE, files=["a.py"])
        kind, why = self.reasons(self.look())[NOTE]
        self.assertEqual(kind, "file-changed")
        self.assertIn("a.py: 200 lines changed since 2026-09-01 (the file has 100 now)", why)

    def test_a_note_with_files_but_no_date_does_not_stop_the_pass(self):
        self.commit("a.py", "".join("line %d\n" % i for i in range(100)), "2026-08-01")
        self.commit("a.py", "".join("new %d\n" % i for i in range(100)), "2026-10-10")
        note(self.store, "projects/demo/lessons/nodate.md", date="", files=["a.py"])
        note(self.store, NOTE, files=["b-gone.py"])   # a normal note that must still be looked at
        result = self.look()                           # used to raise "time data '' does not match format"
        self.assertIn(NOTE, self.reasons(result))

    def test_changes_before_the_note_do_not_count(self):
        self.commit("a.py", "".join("line %d\n" % i for i in range(100)), "2026-08-01")
        self.commit("a.py", "".join("new %d\n" % i for i in range(100)), "2026-08-20")
        note(self.store, NOTE, files=["a.py"])
        self.assertEqual(self.look()["new"], [])

    def test_a_big_change_to_a_big_file_that_is_a_small_share_is_not_enough(self):
        self.commit("a.py", "".join("line %d\n" % i for i in range(1000)), "2026-08-01")
        self.commit("a.py", "".join("line %d\n" % i for i in range(1000)) + "".join("x%d\n" % i for i in range(30)), "2026-10-10")
        note(self.store, NOTE, files=["a.py"])
        self.assertEqual(self.look()["new"], [])

    def test_a_path_that_leaves_the_repo_and_a_missing_repo_are_ignored(self):
        note(self.store, NOTE, files=["../outside.py", "/etc/passwd"])
        note(self.store, "projects/norepo/lessons/b.md", files=["x.py"])
        self.assertEqual(self.look()["new"], [])


class Opposite(Case):
    def test_a_newer_note_that_negates_flags_the_older_one(self):
        note(self.store, NOTE, "Run the tests on the test machine with crabbox", date="2026-09-01")
        note(self.store, "projects/demo/lessons/b.md", "Never run the tests on the test machine with crabbox", date="2026-10-20")
        got = self.reasons(self.look())
        self.assertEqual(list(got), [NOTE])   # only the older one
        self.assertEqual(got[NOTE][0], "newer-opposite")
        self.assertIn("projects/demo/lessons/b.md", got[NOTE][1])

    def test_two_notes_that_agree_or_are_about_other_things_are_left_alone(self):
        note(self.store, NOTE, "Run the tests on the test machine with crabbox", date="2026-09-01")
        note(self.store, "projects/demo/lessons/b.md", "Run the tests on the test machine with crabbox again", date="2026-10-20")
        note(self.store, "projects/demo/lessons/c.md", "Never commit the secret token files", date="2026-10-21")
        self.assertEqual(self.look()["new"], [])

    def test_another_project_is_not_compared(self):
        note(self.store, NOTE, "Run the tests on the test machine with crabbox", date="2026-09-01")
        note(self.store, "projects/other/lessons/b.md", "Never run the tests on the test machine with crabbox", date="2026-10-20")
        self.assertEqual(self.look()["new"], [])

    def test_search_proposes_the_candidates_when_it_answers(self):
        note(self.store, NOTE, "Run the tests on the test machine with crabbox", date="2026-09-01")
        note(self.store, "projects/demo/lessons/b.md", "Never run the tests on the test machine with crabbox", date="2026-10-20")
        self.assertEqual(self.look(search=lambda summary: [])["new"], [])   # search proposed nothing
        self.assertEqual(len(self.look(search=lambda summary: ["projects/demo/lessons/b.md"])["new"]), 1)

    def test_one_failed_search_is_enough_and_the_rest_fall_back_to_the_notes(self):
        note(self.store, NOTE, "Run the tests on the test machine with crabbox", date="2026-09-01")
        note(self.store, "projects/demo/lessons/b.md", "Never run the tests on the test machine with crabbox", date="2026-10-20")
        calls = []

        def down(*a, **k):
            calls.append(1)
            raise OSError("qmd is down")
        with mock.patch.object(memory, "search", down):
            result = memory_flags.look(self.store, "2026-10-28")   # the default search: the brain's
        self.assertEqual(len(calls), 1)
        self.assertEqual([rel for rel, _, _ in result["new"]], [NOTE])

    def test_the_rule_on_two_summaries(self):
        yes = memory_flags.opposite
        self.assertTrue(yes("Use git mv on tracked folders", "Do not use git mv on tracked folders"))
        self.assertFalse(yes("Use git mv on tracked folders", "Use git mv on tracked files"))
        self.assertFalse(yes("Use git mv", "Never use git mv"))   # too few words in common


class Flags(Case):
    def setUp(self):
        super().setUp()
        note(self.store, NOTE, files=["src/gone.py"])

    def test_a_note_is_flagged_once_and_the_flags_file_says_why(self):
        self.look()
        self.assertEqual(self.look()["new"], [])
        rows = memory_flagfile.rows(self.store)
        self.assertEqual([(r["note"], r["state"], r["kind"], r["at"]) for r in rows], [(NOTE, "flagged", "file-gone", "2026-10-28")])
        self.assertEqual(memory_flagfile.flagged(self.store), {NOTE: "2026-10-28"})

    def test_confirm_clears_the_flag_and_the_same_cause_does_not_flag_it_again(self):
        self.look()
        self.assertEqual(memory_flags.confirm(self.store, "a.md", "2026-10-29"), ["confirmed"])
        self.assertEqual(memory_flagfile.flagged(self.store), {})
        self.assertEqual(self.look("2026-11-20")["new"], [])

    def test_confirm_of_a_note_with_nothing_to_confirm_is_a_plain_error(self):
        note(self.store, "projects/demo/lessons/z.md")
        with self.assertRaisesRegex(ValueError, "nothing to confirm"):
            memory_flags.confirm(self.store, "z.md")
        with self.assertRaisesRegex(ValueError, "no kept note called nope.md"):
            memory_flags.confirm(self.store, "nope.md")

    def test_retire_moves_the_note_to_history_and_commits(self):
        subprocess.run(["git", "init", "-q", self.store], check=True)
        git(self.store, "add", "-A")
        git(self.store, "commit", "-q", "-m", "start")
        self.look()
        dest = memory_flags.retire(self.store, NOTE, "the file went away", "2026-10-29")
        self.assertEqual(dest, os.path.join(self.store, "history", NOTE))
        self.assertFalse(os.path.exists(os.path.join(self.store, NOTE)))
        self.assertTrue(os.path.exists(dest))
        self.assertEqual(git(self.store, "status", "--porcelain"), "")
        self.assertIn("retire: " + NOTE + ": the file went away", git(self.store, "log", "-1", "--format=%s"))
        self.assertEqual(memory_flagfile.flagged(self.store), {})
        self.assertEqual(memory.scope_notes(self.store, "demo"), {})   # out of the search scope, not deleted

    def test_retire_a_note_that_was_never_committed(self):
        subprocess.run(["git", "init", "-q", self.store], check=True, timeout=30)
        dest = memory_flags.retire(self.store, NOTE, "made by hand", "2026-10-29")
        self.assertTrue(os.path.exists(dest))
        self.assertEqual(git(self.store, "status", "--porcelain", "--", "history"), "")   # the move is committed
        self.assertIn("retire: " + NOTE, git(self.store, "log", "-1", "--format=%s"))

    def test_retire_does_not_overwrite_a_note_already_in_history(self):
        note(self.store, os.path.join("history", NOTE))
        with self.assertRaisesRegex(ValueError, "already there"):
            memory_flags.retire(self.store, NOTE)
        self.assertTrue(os.path.exists(os.path.join(self.store, NOTE)))

    def test_the_flags_are_committed_in_a_git_store_and_only_the_flags_file(self):
        subprocess.run(["git", "init", "-q", self.store], check=True)
        git(self.store, "add", "-A")
        git(self.store, "commit", "-q", "-m", "start")
        with open(os.path.join(self.store, "untracked.md"), "w") as f:
            f.write("x")
        self.look()
        self.assertEqual(git(self.store, "log", "-1", "--name-only", "--format=%s").split("\n")[:2],
                         ["flags: 1 note may be out of date", ""])
        self.assertEqual(git(self.store, "status", "--porcelain").strip(), "?? untracked.md")


class Pins(Case):
    def test_a_pinned_note_is_due_after_90_days_and_confirm_restarts_it(self):
        note(self.store, NOTE, date="2026-07-01", pinned=True)
        self.assertEqual(self.look("2026-10-28")["pins_due"], [(NOTE, 119)])
        self.assertEqual(memory_flags.confirm(self.store, NOTE, "2026-10-28"), ["still-true"])
        self.assertEqual(self.look("2026-11-27")["pins_due"], [])
        self.assertEqual(self.look("2027-01-27")["pins_due"], [(NOTE, 91)])

    def test_a_young_or_unpinned_note_is_not_due(self):
        note(self.store, NOTE, date="2026-09-01", pinned=True)
        note(self.store, "projects/demo/lessons/u.md", date="2026-01-01")
        self.assertEqual(self.look("2026-10-28")["pins_due"], [])


class WhatAFlagDoes(Case):
    def setUp(self):
        super().setUp()
        note(self.store, NOTE, "Wait for the test machine queue", date="2026-09-01")
        note(self.store, "projects/demo/lessons/b.md", "Use git mv for folders", date="2026-09-02")
        memory_flagfile.append(self.store, [{"note": NOTE, "state": "flagged", "at": "2026-10-20", "kind": "file-gone", "reason": "r"}])

    def find(self, **kw):
        return memory.find("demo", store=self.store, **kw)

    def test_memory_marks_a_flagged_note(self):
        out = self.find()
        self.assertIn("(may be out of date, check first)", out["text"])
        marked = [n for n in out["notes"] if n["flagged"]]
        self.assertEqual([n["path"] for n in marked], [os.path.join(self.store, NOTE)])
        self.assertEqual(out["text"].count("may be out of date"), 1)   # the other note is not marked

    def test_a_flag_over_30_days_is_out_of_the_push_not_out_of_the_store(self):
        with mock.patch.object(memory_flagfile, "lapsed", lambda since, today=None: bool(since)):
            pushed = self.find(for_push=True)
            shown = self.find()
        self.assertNotIn("Wait for the test machine queue", pushed["text"])
        self.assertIn("Use git mv for folders", pushed["text"])
        self.assertIn("Wait for the test machine queue", shown["text"])   # `brain memory` still shows it
        self.assertIn("flag over 30 days old, not pushed", shown["text"])
        self.assertTrue(os.path.exists(os.path.join(self.store, NOTE)))

    def test_a_younger_flag_is_still_pushed_with_the_mark(self):
        self.assertIn("(may be out of date, check first)", self.find(for_push=True)["text"])

    def test_30_days_exactly_lapses_and_29_does_not(self):
        self.assertFalse(memory_flagfile.lapsed("2026-10-01", "2026-10-30"))
        self.assertTrue(memory_flagfile.lapsed("2026-10-01", "2026-10-31"))

    def test_a_confirmed_note_is_not_marked_any_more(self):
        memory_flags.confirm(self.store, NOTE, "2026-10-21")
        self.assertNotIn("may be out of date", self.find()["text"])

    def test_the_hook_push_leaves_out_a_lapsed_note_and_logs_the_paths(self):
        import memory_hook
        memory_flagfile.append(self.store, [{"note": "projects/demo/lessons/b.md", "state": "flagged", "at": "2000-01-01"}])
        with mock.patch.object(memory.ask, "BRAIN_URL", "http://127.0.0.1:9"):
            out = memory_hook.push("demo", None)
        self.assertEqual(out["_log"]["paths"], [os.path.join(self.store, NOTE)])
        self.assertEqual(out["_log"]["notes"], 1)


class Command(Case):
    def test_run_list_confirm_and_retire_from_the_command_line(self):
        note(self.store, NOTE, files=["src/gone.py"])
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(memory_flags.main(["run"]), 0)
            self.assertEqual(memory_flags.main(["list"]), 0)
            self.assertEqual(memory_flags.main(["confirm", "a.md"]), 0)
            self.assertEqual(memory_flags.main(["retire", "a.md", "--why", "old"]), 0)
        text = out.getvalue()
        self.assertIn("new flag: " + NOTE, text)
        self.assertIn("flagged since", text)
        self.assertIn("confirmed a.md (confirmed)", text)
        self.assertIn("retired: moved to", text)

    def test_a_bad_call_and_an_unknown_note_are_plain(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            self.assertEqual(memory_flags.main(["retire", "nope.md"]), 1)
            self.assertEqual(memory_flags.main(["wat"]), 2)
        self.assertIn("no kept note called nope.md", err.getvalue())


if __name__ == "__main__":
    unittest.main()
