"""`brain drafts keep <draft> --to <path>` (eval/memory_keep.py): a memory draft moves into the store and is committed.
Everything runs in temp folders with a made-up name; the real store is never touched.
Run: python3 -I eval/test_memory_keep.py   (no network, no model)"""
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
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
os.environ["BRAIN_STATE"] = tempfile.mkdtemp(prefix="keep-test-state-")
import drafts  # noqa: E402
import memory_keep  # noqa: E402

GIT_ENV = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.invalid"}
NOTE = "# git rm lost the file\n\nZorblax ran git rm on a tracked folder and the files were gone.\nUse git mv.\n"


def fake_scrub(text):
    if "unsure" in text:
        raise drafts.Unsure("test")
    return re.sub(r"zorblax", "[NAME]", text, flags=re.I)


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def git(store, *args):
    return subprocess.run(["git", "-C", store, *args], capture_output=True, text=True, check=True).stdout


class Case(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="keep-test-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.store = os.path.join(self.tmp, "shared")
        os.makedirs(os.path.join(self.store, "drafts"))
        subprocess.run(["git", "init", "-q", self.store], check=True)
        with open(os.path.join(self.store, "README.md"), "w") as f:
            f.write("# store\n")
        self.git_env = mock.patch.dict(os.environ, GIT_ENV)
        self.git_env.start()
        self.addCleanup(self.git_env.stop)
        git(self.store, "add", "-A")
        git(self.store, "commit", "-q", "-m", "start")
        patch = mock.patch.object(drafts, "scrub", fake_scrub)
        patch.start()
        self.addCleanup(patch.stop)
        self.draft("lesson-git-rm.md", NOTE)
        self.asked = []   # texts the fake model was given

    def draft(self, name, text):
        path = os.path.join(self.store, "drafts", name)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        return path

    def model(self, text):
        self.asked.append(text)
        return "Use git mv, not git rm, on tracked folders."

    def keep(self, draft="lesson-git-rm.md", to="projects/second-brain/lessons", **kw):
        kw.setdefault("summarize", self.model)
        return memory_keep.keep(draft, to, store=self.store, today="2026-10-27", **kw)

    def tree(self):
        out = {}
        for here, dirs, files in os.walk(self.tmp):
            dirs[:] = [d for d in dirs if d != ".git"]
            for f in files:
                out[os.path.relpath(os.path.join(here, f), self.tmp)] = read(os.path.join(here, f))
        return out


class Keep(Case):
    def test_a_lesson_moves_into_the_project_folder_with_its_front_matter_and_is_committed(self):
        got = self.keep()
        dest = os.path.join(self.store, "projects", "second-brain", "lessons", "lesson-git-rm.md")
        self.assertEqual(got["path"], dest)
        self.assertFalse(os.path.exists(os.path.join(self.store, "drafts", "lesson-git-rm.md")))
        text = read(dest)
        self.assertTrue(text.startswith("---\nproject: second-brain\nkind: lesson\ndate: 2026-10-27\n"), text)
        self.assertIn("summary: Use git mv, not git rm, on tracked folders.\n", text)
        self.assertIn("files: []\npinned: false\n---\n", text)
        self.assertTrue(text.endswith(NOTE))   # the note itself is word for word (it is a local store)
        self.assertEqual(git(self.store, "status", "--porcelain"), "")
        self.assertIn("projects/second-brain/lessons/lesson-git-rm.md", git(self.store, "show", "--stat", "--name-only", "HEAD"))
        self.assertEqual(len(git(self.store, "log", "--oneline").splitlines()), 2)

    def test_a_rule_for_all_projects_gets_project_all_projects(self):
        self.draft("r.md", "Run the tests on the test machine.\n")
        self.keep("r.md", "all-projects/rules")
        text = read(os.path.join(self.store, "all-projects", "rules", "r.md"))
        self.assertIn("project: all-projects\nkind: rule\n", text)

    def test_a_full_file_path_in_to_names_the_new_file(self):
        self.keep(to="projects/second-brain/rules/use-git-mv.md")
        self.assertTrue(os.path.isfile(os.path.join(self.store, "projects", "second-brain", "rules", "use-git-mv.md")))

    def test_files_and_pin_are_written(self):
        self.keep(files=["eval/drafts.py", "bin/brain"], pin=True)
        text = read(os.path.join(self.store, "projects", "second-brain", "lessons", "lesson-git-rm.md"))
        self.assertIn("files:\n  - eval/drafts.py\n  - bin/brain\npinned: true\n---\n", text)

    def test_files_in_the_drafts_own_front_matter_are_used(self):
        self.draft("d.md", "---\nfiles:\n  - a/b.py\npinned: true\n---\nBody.\n")
        self.keep("d.md", "projects/x/rules")
        text = read(os.path.join(self.store, "projects", "x", "rules", "d.md"))
        self.assertIn("files:\n  - a/b.py\npinned: true\n---\nBody.\n", text)
        self.assertEqual(text.count("---\n"), 2)   # the old front matter is replaced, not stacked

    def test_the_summary_is_shown_and_owner_can_change_it(self):
        shown = []

        def confirm(summary):
            shown.append(summary)
            return "<user>'s own line."
        self.keep(confirm=confirm)
        self.assertEqual(shown, ["Use git mv, not git rm, on tracked folders."])
        text = read(os.path.join(self.store, "projects", "second-brain", "lessons", "lesson-git-rm.md"))
        self.assertIn("summary: <user>'s own line.\n", text)

    def test_a_given_summary_skips_the_model(self):
        self.keep(summary="Given line.")
        self.assertEqual(self.asked, [])
        self.assertIn("summary: Given line.\n", read(os.path.join(self.store, "projects", "second-brain", "lessons", "lesson-git-rm.md")))

    def test_a_summary_with_a_colon_stays_valid_and_on_one_line(self):
        self.keep(summary="Note: do this\nnot that")
        text = read(os.path.join(self.store, "projects", "second-brain", "lessons", "lesson-git-rm.md"))
        self.assertIn('summary: "Note: do this not that"\n', text)

    def test_the_model_never_sees_a_private_name(self):
        self.keep()
        self.assertEqual(len(self.asked), 1)
        self.assertNotIn("Zorblax", self.asked[0])
        self.assertIn("[NAME]", self.asked[0])

    def test_a_draft_that_git_tracks_leaves_drafts_in_the_same_commit(self):
        git(self.store, "add", "drafts/lesson-git-rm.md")
        git(self.store, "commit", "-q", "-m", "draft")
        self.keep()
        self.assertEqual(git(self.store, "status", "--porcelain"), "")
        self.assertEqual(git(self.store, "ls-files", "drafts"), "")
        self.assertEqual(len(git(self.store, "log", "--oneline").splitlines()), 3)

    def test_a_second_keep_of_the_same_target_is_refused_and_changes_nothing(self):
        self.keep()
        self.draft("lesson-git-rm.md", "Another.\n")
        before = self.tree()
        with self.assertRaises(memory_keep.KeepError):
            self.keep()
        self.assertEqual(self.tree(), before)

    def test_a_bad_target_is_refused_and_changes_nothing(self):
        before = self.tree()
        for to in ("lessons", "projects/second-brain", "projects/x/notes", "../outside/lessons", "projects/../../x/rules",
                   "history/rules", "/etc/rules", "projects/second-brain/lessons/a.txt"):
            with self.subTest(to=to), self.assertRaises(memory_keep.KeepError):
                self.keep(to=to)
        self.assertEqual(self.tree(), before)

    def test_a_missing_draft_is_refused(self):
        with self.assertRaises(memory_keep.KeepError):
            self.keep("nope.md")

    def test_a_draft_given_as_a_path_outside_the_store_is_moved_in(self):
        other = os.path.join(self.tmp, "elsewhere.md")
        with open(other, "w") as f:
            f.write("Outside.\n")
        self.keep(other)
        self.assertFalse(os.path.exists(other))
        self.assertTrue(os.path.isfile(os.path.join(self.store, "projects", "second-brain", "lessons", "elsewhere.md")))


class Safety(Case):
    def test_a_missing_store_says_so_and_does_not_crash(self):
        gone = os.path.join(self.tmp, "no-such-store")
        with self.assertRaises(memory_keep.KeepError) as ctx:
            memory_keep.keep("x.md", "projects/a/lessons", store=gone, summarize=self.model)
        self.assertIn("store", str(ctx.exception).lower())
        self.assertEqual(self.asked, [])
        self.assertFalse(os.path.exists(gone))

    def test_a_folder_that_is_not_a_git_repo_is_refused_before_anything_moves(self):
        plain = os.path.join(self.tmp, "plain")
        os.makedirs(os.path.join(plain, "drafts"))
        with open(os.path.join(plain, "drafts", "n.md"), "w") as f:
            f.write("x\n")
        with self.assertRaises(memory_keep.KeepError) as ctx:
            memory_keep.keep("n.md", "projects/a/lessons", store=plain, summarize=self.model)
        self.assertIn("git", str(ctx.exception).lower())
        self.assertTrue(os.path.isfile(os.path.join(plain, "drafts", "n.md")))

    def test_when_the_names_filter_is_unsure_no_model_sees_the_text_and_the_note_is_marked_local_only(self):
        self.draft("u.md", "# unsure note\n\nSome text the filter cannot clear.\n")
        got = self.keep("u.md", "projects/second-brain/lessons")
        self.assertEqual(self.asked, [])
        self.assertTrue(got["local_only"])
        text = read(got["path"])
        self.assertIn("local-only: true\n", text)
        self.assertIn("summary: unsure note\n", text)   # no model: the first heading stands in; <user> can edit it
        self.assertEqual(git(self.store, "status", "--porcelain", "--", "projects"), "")

    def test_a_filter_that_is_missing_counts_as_unsure(self):
        def broken(text):
            raise drafts.Unsure("FileNotFoundError")
        with mock.patch.object(drafts, "scrub", broken):
            got = self.keep()
        self.assertEqual(self.asked, [])
        self.assertTrue(got["local_only"])

    def test_a_clean_note_is_not_marked_local_only(self):
        got = self.keep()
        self.assertFalse(got["local_only"])
        self.assertNotIn("local-only", read(got["path"]))

    def test_a_given_summary_is_checked_by_the_filter_too(self):
        got = self.keep(summary="unsure line")
        self.assertTrue(got["local_only"])

    def test_a_model_that_fails_leaves_an_empty_summary_for_owner_and_still_keeps_the_note(self):
        def down(text):
            raise OSError("no model")
        got = self.keep(summarize=down)
        self.assertEqual(got["summary_by"], "fallback")
        self.assertIn("summary: git rm lost the file\n", read(got["path"]))

    def test_a_commit_that_fails_is_reported_and_the_note_goes_back_to_drafts(self):
        with mock.patch.object(memory_keep, "_git", side_effect=memory_keep.KeepError("git failed")):
            with self.assertRaises(memory_keep.KeepError):
                self.keep()
        self.assertTrue(os.path.isfile(os.path.join(self.store, "drafts", "lesson-git-rm.md")))
        self.assertFalse(os.path.exists(os.path.join(self.store, "projects", "second-brain", "lessons", "lesson-git-rm.md")))


class LocalModel(Case):
    """The built-in summary maker talks only to the model on this computer."""

    def fake_urlopen(self, calls):
        def urlopen(req, timeout=None):
            calls.append(req)
            resp = mock.MagicMock()
            resp.__enter__.return_value.read.return_value = b'{"message": {"content": "  A short line.\\nSecond line. "}}'
            return resp
        return urlopen

    def test_it_asks_ollama_on_this_computer_and_returns_one_line(self):
        calls = []
        with mock.patch.dict(os.environ, {"OLLAMA_HOST_URL": "127.0.0.1:11434"}), \
                mock.patch.object(memory_keep.urllib.request, "urlopen", self.fake_urlopen(calls)):
            got = memory_keep.local_summary("Some clean text.")
        self.assertEqual(got, "A short line.")
        self.assertEqual(len(calls), 1)
        self.assertTrue(calls[0].full_url.startswith("http://127.0.0.1:11434/"))

    def test_it_refuses_a_model_host_that_is_not_this_computer(self):
        calls = []
        with mock.patch.dict(os.environ, {"OLLAMA_HOST_URL": "models.example.com:11434"}), \
                mock.patch.object(memory_keep.urllib.request, "urlopen", self.fake_urlopen(calls)):
            with self.assertRaises(OSError):
                memory_keep.local_summary("Some clean text.")
        self.assertEqual(calls, [])

    def test_keep_with_the_built_in_model_sends_only_scrubbed_text_to_it(self):
        calls = []
        with mock.patch.object(memory_keep.urllib.request, "urlopen", self.fake_urlopen(calls)):
            got = memory_keep.keep("lesson-git-rm.md", "projects/second-brain/lessons", store=self.store, today="2026-10-27")
        self.assertEqual(len(calls), 1)
        self.assertNotIn(b"Zorblax", calls[0].data)
        self.assertEqual(got["summary_by"], "model")

    def test_no_network_call_is_made_when_the_filter_is_unsure(self):
        self.draft("u.md", "unsure text\n")
        calls = []
        with mock.patch.object(memory_keep.urllib.request, "urlopen", self.fake_urlopen(calls)):
            memory_keep.keep("u.md", "projects/second-brain/lessons", store=self.store, today="2026-10-27")
        self.assertEqual(calls, [])


class Cli(Case):
    def run_cli(self, argv, stdin_tty=False):
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.dict(os.environ, {"BRAIN_MEMORY_STORE": self.store}), \
                mock.patch.object(memory_keep, "local_summary", self.model), \
                mock.patch.object(sys.stdin, "isatty", return_value=stdin_tty), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = drafts.main(argv)
        return code, out.getvalue(), err.getvalue()

    def test_brain_drafts_keep_with_to_goes_to_the_store_and_shows_the_summary(self):
        code, out, err = self.run_cli(["keep", "lesson-git-rm.md", "--to", "projects/second-brain/lessons", "--files", "bin/brain"])
        self.assertEqual((code, err), (0, ""))
        self.assertIn("Use git mv, not git rm, on tracked folders.", out)
        self.assertIn("projects/second-brain/lessons/lesson-git-rm.md", out)
        self.assertIn("  - bin/brain\n", read(os.path.join(self.store, "projects", "second-brain", "lessons", "lesson-git-rm.md")))

    def test_the_cli_asks_for_a_change_when_there_is_a_terminal(self):
        with mock.patch("builtins.input", return_value="Typed by <user>.") as asked:
            code, out, _ = self.run_cli(["keep", "lesson-git-rm.md", "--to", "projects/second-brain/lessons"], stdin_tty=True)
        self.assertEqual(code, 0)
        self.assertEqual(asked.call_count, 1)
        self.assertIn("summary: Typed by <user>.\n", read(os.path.join(self.store, "projects", "second-brain", "lessons", "lesson-git-rm.md")))

    def test_the_cli_says_so_when_the_store_is_missing(self):
        shutil.rmtree(self.store)
        code, out, err = self.run_cli(["keep", "lesson-git-rm.md", "--to", "projects/second-brain/lessons"])
        self.assertEqual(code, 1)
        self.assertIn("store", err.lower())
        self.assertNotIn("Traceback", err)

    def test_the_old_keep_without_to_still_goes_the_old_way(self):
        code, _, err = self.run_cli(["keep", "d-nothing"])
        self.assertEqual(code, 1)
        self.assertIn("no draft called", err)

    def test_pin_flag(self):
        self.run_cli(["keep", "lesson-git-rm.md", "--to", "projects/second-brain/lessons", "--pin"])
        self.assertIn("pinned: true", read(os.path.join(self.store, "projects", "second-brain", "lessons", "lesson-git-rm.md")))


class IndexBlock(unittest.TestCase):
    """index/index.yml (repo copy): the store is a collection, off by default like the others."""

    def setUp(self):
        text = read(os.path.join(ROOT, "index", "index.yml"))
        # No yaml module in the standard library: read the collection blocks by their indentation.
        self.blocks = {}
        inside = False
        for line in text.splitlines():
            if line.startswith("collections:"):
                inside = True
            elif inside and re.match(r"^\S", line):
                inside = False
            m = re.match(r"^  ([A-Za-z0-9_-]+):\s*$", line)
            if inside and m:
                name = m.group(1)
                self.blocks[name] = []
            elif inside and self.blocks and line.startswith("    "):
                self.blocks[name].append(line)
        self.text = text

    def test_the_store_is_a_collection_off_by_default_with_a_context_line(self):
        self.assertIn("memory", self.blocks)
        block = "\n".join(self.blocks["memory"])
        self.assertIn("includeByDefault: false", block)
        self.assertIn("path: ~/projects/shared", block)
        self.assertRegex(block, r'pattern: "[^"]*\.md"')
        self.assertRegex(block, r'"/": "[^"]{20,}')

    def test_every_collection_is_still_off_by_default(self):
        self.assertGreaterEqual(len(self.blocks), 12)
        for name, lines in self.blocks.items():
            self.assertIn("    includeByDefault: false", lines, name)

    def test_drafts_are_not_searched_and_history_is_marked_old(self):
        block = "\n".join(self.blocks["memory"])
        self.assertIn('- "drafts/**"', block)   # unreviewed notes are never findable
        self.assertIn('"/history"', block)
        self.assertRegex(block, r'"/history": "[^"]*out of date')

    def test_the_file_still_parses_when_a_yaml_reader_is_there(self):
        try:
            import yaml
        except ImportError:
            self.skipTest("no yaml module in this python")
        data = yaml.safe_load(self.text)
        self.assertFalse(data["collections"]["memory"]["includeByDefault"])


if __name__ == "__main__":
    unittest.main()
