"""`brain private <note> on|off` and `brain private list` (ask/private_tag.py): tag a memory note local-only by hand.
Everything runs on temp stores with made-up notes; the real store and the real backups folder are never touched.
Run: python3 -I ask/test_private_tag.py   (no network, no model)"""
import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
os.environ["BRAIN_STATE"] = tempfile.mkdtemp(prefix="private-test-state-")
import ask  # noqa: E402
import private_tag  # noqa: E402

GIT_ENV = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.invalid"}
ZORB = ('---\nproject: demo\nkind: lesson\ndate: 2026-10-20\nsummary: "Zorbel: use git mv"\nfiles:\n  - a.py\n'
        'pinned: true\n---\n# Zorbel moved the folder\n\nUse git mv.  \nTrailing spaces stay.\n')
PLAIN = "---\nproject: demo\nkind: rule\ndate: 2026-10-21\nsummary: Plain rule\nfiles: []\npinned: false\n---\n# Restart the chat door\n\nBody.\n"


def read(path):
    with open(path, encoding="utf-8", newline="") as f:
        return f.read()


class Case(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="private-test-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.store = os.path.join(self.tmp, "shared")
        self.backups = os.path.join(self.tmp, "backups")
        self.note("projects/demo/lessons/zorbel-git-mv.md", ZORB)
        self.note("projects/demo/rules/restart-chat-door.md", PLAIN)
        self.note("all-projects/lessons/restart-before-you-test.md", PLAIN.replace("chat door", "shell first"))
        self.note("drafts/a-draft.md", PLAIN)
        self.note("README.md", "# store\n")
        env = mock.patch.dict(os.environ, dict(GIT_ENV, BRAIN_MEMORY_STORE=self.store, BRAIN_BACKUP_DIR=self.backups))
        env.start()
        self.addCleanup(env.stop)

    def note(self, rel, text):
        path = os.path.join(self.store, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write(text)
        return path

    def run_cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = private_tag.main(list(argv))
        return code, out.getvalue(), err.getvalue()


class TagUntag(Case):
    def test_on_changes_only_the_tag_lines_and_keeps_a_backup(self):
        path = os.path.join(self.store, "projects/demo/lessons/zorbel-git-mv.md")
        got = private_tag.set_private("zorbel", True, today="2026-10-28")
        self.assertTrue(got["changed"])
        self.assertEqual(read(path), ZORB.replace("pinned: true\n---", "pinned: true\nlocal-only: true\n"
                                                  "local-only-by: owner\nlocal-only-at: 2026-10-28\n---"))
        self.assertEqual(read(got["backup"]), ZORB)
        self.assertTrue(got["backup"].startswith(self.backups + os.sep))

    def test_off_after_the_filter_tagged_it_replaces_its_lines_in_place(self):
        auto = ZORB.replace("pinned: true\n", "local-only: true\nlocal-only-by: filter\nlocal-only-at: 2026-10-20\npinned: true\n")
        path = self.note("projects/demo/lessons/zorbel-git-mv.md", auto)
        got = private_tag.set_private("zorbel", False, today="2026-10-28")
        self.assertFalse(got["local_only"])
        self.assertEqual(got["by"], "owner")
        self.assertEqual(read(path), auto.replace("local-only: true\nlocal-only-by: filter\nlocal-only-at: 2026-10-20",
                                                  "local-only: false\nlocal-only-by: owner\nlocal-only-at: 2026-10-28"))

    def test_an_old_tag_without_by_counts_as_the_filter_and_on_again_makes_it_a_hand_choice(self):
        self.note("projects/demo/lessons/zorbel-git-mv.md", ZORB.replace("pinned: true\n", "pinned: true\nlocal-only: true\n"))
        self.assertEqual([n["by"] for n in private_tag.list_private()], ["filter"])
        self.assertTrue(private_tag.set_private("zorbel", True)["changed"])
        self.assertEqual([n["by"] for n in private_tag.list_private()], ["owner"])

    def test_the_same_choice_twice_changes_nothing(self):
        private_tag.set_private("zorbel", True)
        before = read(os.path.join(self.store, "projects/demo/lessons/zorbel-git-mv.md"))
        got = private_tag.set_private("zorbel", True)
        self.assertFalse(got["changed"])
        self.assertIsNone(got["backup"])
        self.assertEqual(read(got["path"]), before)
        self.assertEqual(len(os.listdir(self.backups)), 1)

    def test_crlf_and_no_front_matter(self):
        crlf = self.note("projects/demo/lessons/windows-note.md", "---\r\nproject: demo\r\n---\r\n# Win\r\nbody\r\n")
        private_tag.set_private("windows-note", True, today="2026-10-28")
        self.assertEqual(read(crlf), "---\r\nproject: demo\r\nlocal-only: true\r\nlocal-only-by: owner\r\n"
                                     "local-only-at: 2026-10-28\r\n---\r\n# Win\r\nbody\r\n")
        bare = self.note("projects/demo/lessons/bare-note.md", "# Bare\nbody\n")
        private_tag.set_private("bare-note", True, today="2026-10-28")
        self.assertEqual(read(bare), "---\nlocal-only: true\nlocal-only-by: owner\nlocal-only-at: 2026-10-28\n---\n# Bare\nbody\n")

    def test_unclosed_front_matter_is_refused(self):
        path = self.note("projects/demo/lessons/broken-note.md", "---\nproject: demo\n# no end\n")
        with self.assertRaises(private_tag.TagError):
            private_tag.set_private("broken-note", True)
        self.assertEqual(read(path), "---\nproject: demo\n# no end\n")

    def test_permissions_are_kept(self):
        path = os.path.join(self.store, "projects/demo/lessons/zorbel-git-mv.md")
        os.chmod(path, 0o640)
        private_tag.set_private("zorbel", True)
        self.assertEqual(os.stat(path).st_mode & 0o777, 0o640)

    def test_a_git_store_gets_one_commit_with_only_that_note(self):
        subprocess.run(["git", "init", "-q", self.store], check=True)
        subprocess.run(["git", "-C", self.store, "add", "-A"], check=True)
        subprocess.run(["git", "-C", self.store, "commit", "-q", "-m", "start"], check=True)
        self.note("projects/demo/rules/restart-chat-door.md", PLAIN + "unrelated edit\n")
        got = private_tag.set_private("zorbel", True)
        self.assertIsNone(got["commit_problem"])
        files = subprocess.run(["git", "-C", self.store, "show", "--name-only", "--format=%s", "HEAD"],
                               capture_output=True, text=True, check=True).stdout.split()
        self.assertEqual(files[-1], "projects/demo/lessons/zorbel-git-mv.md")
        self.assertIn("private: on", subprocess.run(["git", "-C", self.store, "log", "-1", "--format=%s"],
                                                    capture_output=True, text=True).stdout)
        self.assertIn("restart-chat-door.md", subprocess.run(["git", "-C", self.store, "status", "--short"],
                                                             capture_output=True, text=True).stdout)


class WhichNote(Case):
    def test_path_part_of_name_and_title_words(self):
        rel = "projects/demo/lessons/zorbel-git-mv.md"
        for name in (rel, os.path.join(self.store, rel), "zorbel-git", "ZORBEL", "moved folder"):
            self.assertEqual(private_tag.find(name, private_tag.store_path()), rel, name)

    def test_several_matches_are_listed_and_nothing_changes(self):
        before = {r: read(os.path.join(self.store, r)) for r in private_tag.notes(self.store)}
        code, out, err = self.run_cli("restart", "on")
        self.assertEqual(code, 1)
        self.assertIn("2 memory notes match", err)
        self.assertIn("projects/demo/rules/restart-chat-door.md", err)
        self.assertIn("all-projects/lessons/restart-before-you-test.md", err)
        self.assertEqual({r: read(os.path.join(self.store, r)) for r in private_tag.notes(self.store)}, before)
        self.assertFalse(os.path.exists(self.backups))
        code, out, _ = self.run_cli("restart", "on", "--json")
        self.assertEqual(json.loads(out)["matches"], ["all-projects/lessons/restart-before-you-test.md",
                                                      "projects/demo/rules/restart-chat-door.md"])

    def test_non_memory_notes_are_refused(self):
        outside = os.path.join(self.tmp, "other-note.md")
        with open(outside, "w") as f:
            f.write("# elsewhere\n")
        for name in (outside, "drafts/a-draft.md", os.path.join(self.store, "README.md")):
            with self.assertRaises(private_tag.TagError) as cm:
                private_tag.set_private(name, True)
            self.assertIn("only memory notes can be tagged", str(cm.exception), name)
        self.assertEqual(read(outside), "# elsewhere\n")
        self.assertEqual(read(os.path.join(self.store, "drafts/a-draft.md")), PLAIN)

    def test_a_symlink_out_of_the_store_is_refused(self):
        outside = os.path.join(self.tmp, "secret.md")
        with open(outside, "w") as f:
            f.write("# secret\n")
        os.symlink(outside, os.path.join(self.store, "projects/demo/lessons/link.md"))
        with self.assertRaises(private_tag.TagError):
            private_tag.set_private(os.path.join(self.store, "projects/demo/lessons/link.md"), True)
        self.assertNotIn("projects/demo/lessons/link.md", private_tag.notes(self.store))
        self.assertEqual(read(outside), "# secret\n")

    def test_no_match(self):
        code, _, err = self.run_cli("nothing-like-this", "on")
        self.assertEqual(code, 1)
        self.assertIn("no memory note matches", err)


class Listing(Case):
    def test_list_shows_title_path_who_and_when(self):
        private_tag.set_private("zorbel", True, today="2026-10-28")
        code, out, _ = self.run_cli("list")
        self.assertEqual(code, 0)
        self.assertIn("- Zorbel moved the folder", out)
        self.assertIn("projects/demo/lessons/zorbel-git-mv.md", out)
        self.assertIn("marked by you, by hand, on 2026-10-28", out)
        self.assertNotIn("restart", out)

    def test_json_modes_for_the_deck(self):
        code, out, _ = self.run_cli("zorbel", "on", "--json")
        got = json.loads(out)
        self.assertEqual((code, got["ok"], got["local_only"], got["by"], got["changed"]), (0, True, True, "owner", True))
        code, out, _ = self.run_cli("list", "--json")
        notes = json.loads(out)["notes"]
        self.assertEqual([(n["rel"], n["title"], n["by"]) for n in notes],
                         [("projects/demo/lessons/zorbel-git-mv.md", "Zorbel moved the folder", "owner")])
        self.assertEqual(json.loads(self.run_cli("zorbel", "off", "--json")[1])["local_only"], False)
        self.assertEqual(json.loads(self.run_cli("list", "--json")[1])["notes"], [])
        code, out, _ = self.run_cli("list", "nope", "--json")
        self.assertEqual((code, json.loads(out)["ok"]), (1, False))

    def test_brain_help_names_it(self):
        out = subprocess.run([os.path.join(ROOT, "bin", "brain"), "--help"], capture_output=True, text=True).stdout
        self.assertIn("brain private <note> on|off | list", out)


class AskBlocksHaiku(Case):
    """A note <user> tagged by hand is local-only for `brain ask`: the local writer answers, Haiku gets nothing."""
    def test_hand_tagged_note_never_reaches_haiku(self):
        sent = []
        for name in ("haiku_write", "local_write"):
            p = mock.patch.object(ask, name, lambda prompt, *a, who=name, **k: sent.append(who) or ("ok", 1, 2))
            p.start()
            self.addCleanup(p.stop)
        p = mock.patch.dict(ask.COLLECTIONS, {"memory": self.store})
        p.start()
        self.addCleanup(p.stop)
        hit = {"path": os.path.join(self.store, "projects/demo/lessons/zorbel-git-mv.md"), "title": "t",
               "snippet": "s", "line": 1}
        self.assertFalse(ask.local_only(hit))
        private_tag.set_private("zorbel", True)
        self.assertTrue(ask.local_only(hit))
        self.assertTrue(ask.write("q", [hit], "auto")[1].startswith("local:"))
        with self.assertRaises(RuntimeError):
            ask.write("q", [hit], "haiku")
        self.assertEqual(sent, ["local_write"])
        private_tag.set_private("zorbel", False)
        self.assertFalse(ask.local_only(hit))
        ask.write("q", [hit], "haiku")
        self.assertEqual(sent, ["local_write", "haiku_write"])


if __name__ == "__main__":
    unittest.main()
