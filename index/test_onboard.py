"""brain onboard (index/onboard.py): everything runs in a temporary HOME with made-up chats and notes.
Run: python3 -I index/test_onboard.py   (no network, no qmd needed)"""
import contextlib
import glob
import io
import json
import os
import stat
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import onboard  # noqa: E402

FAKE_KEY = "sk-ant-api03-ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789abcdefg"


def session_lines(session_id, text):
    lines = []
    for i in range(4):
        lines.append({"type": "user", "timestamp": "2026-10-20T10:0%d:00.000Z" % (i * 2), "cwd": "/tmp/demo", "sessionId": session_id,
                      "message": {"role": "user", "content": "%s (question %d)" % (text, i)}})
        lines.append({"type": "assistant", "timestamp": "2026-10-20T10:0%d:30.000Z" % (i * 2), "sessionId": session_id,
                      "message": {"role": "assistant", "content": [{"type": "text", "text": "Here is a careful answer number %d with several words in it." % i}]}})
    return "\n".join(json.dumps(x) for x in lines) + "\n"


class OnboardCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = self.tmp.name
        self.brain = os.path.join(self.home, "brain")
        self.env = mock.patch.dict(os.environ, {"HOME": self.home, "XDG_CONFIG_HOME": os.path.join(self.home, ".config"),
                                                "PATH": os.path.dirname(sys.executable) + os.pathsep + "/usr/bin" + os.pathsep + "/bin"})
        self.env.start()
        os.environ.pop("BRAIN_HOME", None)
        self.addCleanup(self.env.stop)
        self.addCleanup(self.tmp.cleanup)

    def write(self, rel, text):
        path = os.path.join(self.home, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        return path

    def run_main(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = onboard.main(list(argv))
        return code, out.getvalue(), err.getvalue()

    def fake_chats(self):
        self.write(".claude/projects/-tmp-demo/s1.jsonl", session_lines("s1", "How do I deploy? my key is " + FAKE_KEY))
        self.write(".claude/projects/-tmp-skipme/s2.jsonl", session_lines("s2", "A private side project question"))
        self.write(".codex/sessions/2026/11/02/rollout-1.jsonl", "{}\n")

    def notes(self):
        self.write("notes/garden.md", "# Garden\nPlant tomatoes in May.\n")
        self.write("notes/.env", "TOKEN=nope\n")
        return os.path.join(self.home, "notes")


class PlanTests(OnboardCase):
    def test_an_empty_home_finds_nothing_and_writes_nothing(self):
        code, out, _ = self.run_main("--plan", "--json")
        found = json.loads(out)
        self.assertEqual(code, 0)
        self.assertEqual((found["notes"], found["sessions"]), ([], []))
        self.assertFalse(os.path.exists(self.brain))
        self.assertFalse(os.path.exists(os.path.join(self.home, ".config", "second-brain")))

    def test_it_counts_chats_without_reading_them(self):
        self.fake_chats()
        found = json.loads(self.run_main("--plan", "--json")[1])
        by_id = {s["id"]: s for s in found["sessions"]}
        self.assertEqual((by_id["claude"]["count"], by_id["codex"]["count"]), (2, 1))
        self.assertEqual(by_id["claude"]["default"], "skip")

    def test_a_listed_notes_folder_flags_secret_like_files(self):
        self.notes()
        found = json.loads(self.run_main("--plan", "--json")[1])
        self.assertEqual([n["count"] for n in found["notes"]], [1])
        self.assertTrue(found["notes"][0]["flags"])


class DecisionTests(OnboardCase):
    def test_without_a_terminal_and_without_yes_it_asks_for_a_decision(self):
        self.fake_chats()
        code, out, _ = self.run_main()
        self.assertEqual(code, onboard.UNDECIDED)
        self.assertIn("needs a decision", out)
        self.assertFalse(os.path.exists(self.brain))

    def test_yes_with_no_choice_is_refused(self):
        self.assertEqual(self.run_main("--yes")[0], onboard.BAD_ARGS)

    def test_bad_arguments_are_refused(self):
        self.assertEqual(self.run_main("--yes", "--notes", "/no/such/folder")[0], onboard.BAD_ARGS)
        self.assertEqual(self.run_main("--yes", "--sessions", "chatgpt")[0], onboard.BAD_ARGS)
        self.assertEqual(self.run_main("--yes", "--notes", self.brain)[0], onboard.BAD_ARGS)


class IngestTests(OnboardCase):
    def chat_files(self):
        return [p for p in glob.glob(os.path.join(self.brain, "chats", "**", "*.md"), recursive=True)]

    def test_notes_only_makes_the_skeleton_and_ingests_no_chats(self):
        self.fake_chats()
        folder = self.notes()
        code, out, _ = self.run_main("--yes", "--notes", folder, "--sessions", "none", "--no-index")
        self.assertEqual(code, 0, out)
        self.assertEqual(self.chat_files(), [])
        self.assertEqual(stat.S_IMODE(os.stat(self.brain).st_mode), 0o700)
        receipt = json.load(open(os.path.join(self.home, ".config", "second-brain", "onboard.json")))
        self.assertEqual((receipt["notes"], receipt["sessions"]), ([folder], []))

    def test_claude_chats_become_notes_with_secrets_removed(self):
        self.fake_chats()
        code, out, _ = self.run_main("--yes", "--sessions", "claude", "--no-index")
        self.assertEqual(code, 0, out)
        files = self.chat_files()
        self.assertTrue(files, out)
        text = "".join(open(p, encoding="utf-8").read() for p in files)
        self.assertNotIn(FAKE_KEY, text)
        self.assertFalse(os.path.exists(os.path.join(self.brain, "chats", "codex")))

    def test_excluded_projects_are_left_out(self):
        self.fake_chats()
        self.run_main("--yes", "--sessions", "claude", "--exclude-project", "*skipme*", "--no-index")
        text = "".join(open(p, encoding="utf-8").read() for p in self.chat_files())
        self.assertIn("deploy", text)
        self.assertNotIn("private side project", text)

    def test_a_dry_run_writes_nothing(self):
        self.fake_chats()
        code, out, _ = self.run_main("--yes", "--sessions", "claude", "--dry-run")
        self.assertEqual(code, 0, out)
        self.assertFalse(os.path.exists(self.brain))
        self.assertFalse(os.path.exists(os.path.join(self.home, ".config")))

    def test_a_second_run_changes_nothing_new(self):
        self.fake_chats()
        self.run_main("--yes", "--sessions", "claude", "--no-index")
        first = sorted(self.chat_files())
        self.assertEqual(self.run_main("--yes", "--sessions", "claude", "--no-index")[0], 0)
        self.assertEqual(sorted(self.chat_files()), first)


class SearchConfigTests(OnboardCase):
    def test_each_notes_folder_becomes_its_own_collection_and_a_missing_qmd_is_not_an_error(self):
        folder = self.notes()
        code, out, _ = self.run_main("--yes", "--notes", folder, "--sessions", "none")
        self.assertEqual(code, 0, out)
        conf = open(os.path.join(self.home, ".config", "qmd", "index.yml"), encoding="utf-8").read()
        self.assertIn("notes-notes:", conf)
        self.assertIn(folder, conf)
        self.assertIn("qmd is not installed", out)

    def conf_text(self):
        with open(os.path.join(self.home, ".config", "qmd", "index.yml"), encoding="utf-8") as f:
            return f.read()

    def test_a_second_run_with_another_folder_of_the_same_name_gets_its_own_collection(self):
        a, b = os.path.join(self.home, "a", "notes"), os.path.join(self.home, "b", "notes")
        os.makedirs(a)
        os.makedirs(b)
        self.assertEqual(onboard.write_qmd_config([a], self.brain, self.home, False)[1], ["notes-notes"])
        _, added = onboard.write_qmd_config([b], self.brain, self.home, False)
        self.assertEqual(added, ["notes-notes-2"])
        conf = self.conf_text()
        self.assertIn(a, conf)
        self.assertIn(b, conf)

    def test_the_same_folder_twice_adds_nothing_and_says_so(self):
        a = os.path.join(self.home, "a", "notes")
        os.makedirs(a)
        onboard.write_qmd_config([a], self.brain, self.home, False)
        before = self.conf_text()
        _, added = onboard.write_qmd_config([a], self.brain, self.home, False)
        self.assertEqual(added, [])
        self.assertEqual(self.conf_text(), before)
        self.assertEqual(self.conf_text().count("notes-notes:"), 1)

    def test_a_folder_with_a_quote_or_backslash_in_its_name_still_gives_valid_yaml(self):
        import yaml
        odd = os.path.join(self.home, 'my "best" notes\\v2')
        os.makedirs(odd)
        onboard.write_qmd_config([odd], self.brain, self.home, False)
        data = yaml.safe_load(self.conf_text())
        paths = [c.get("path") for c in data["collections"].values()]
        self.assertIn(odd, paths)

    def test_an_existing_config_with_the_folder_written_in_quotes_is_recognised(self):
        a = os.path.join(self.home, "a", "notes")
        os.makedirs(a)
        self.write(".config/qmd/index.yml", 'collections:\n  mine:\n    path: "%s"\n' % a)
        _, added = onboard.write_qmd_config([a], self.brain, self.home, False)
        self.assertEqual(added, [])

    def test_qmd_is_run_when_it_exists_and_an_old_config_is_kept_as_a_backup(self):
        fake = self.write("bin/qmd", "#!/bin/sh\necho \"$@\" >> \"%s/qmd.calls\"\n" % self.home)
        os.chmod(fake, 0o755)
        os.environ["PATH"] = os.path.dirname(fake) + os.pathsep + os.environ["PATH"]
        self.write(".config/qmd/index.yml", "collections: {}\n")
        folder = self.notes()
        self.assertEqual(self.run_main("--yes", "--notes", folder, "--sessions", "none")[0], 0)
        self.assertIn("update", open(os.path.join(self.home, "qmd.calls")).read())
        self.assertTrue(glob.glob(os.path.join(self.home, ".config", "qmd", "index.yml.bak-*")))

    def test_an_existing_search_config_is_extended_never_replaced(self):
        mine = "global_context: mine\ncollections:\n  my-own:\n    path: /data/stuff\n    pattern: \"**/*.md\"\n  brain:\n    path: /custom/brain\n"
        conf = self.write(".config/qmd/index.yml", mine)
        folder = self.notes()
        self.assertEqual(self.run_main("--yes", "--notes", folder, "--sessions", "none")[0], 0)
        text = open(conf, encoding="utf-8").read()
        self.assertTrue(text.startswith(mine))                      # what you had is untouched, in place
        self.assertEqual(text.count("\n  brain:"), 1)                # your own "brain" is kept, not duplicated
        self.assertIn("/custom/brain", text)
        self.assertIn("\n  notes-notes:", text)                     # the chosen folder was added
        self.assertIn("\n  rules:", text)                           # a shipped section you lacked was added
        backups = glob.glob(os.path.join(self.home, ".config", "qmd", "index.yml.bak-*"))
        self.assertEqual(open(backups[0], encoding="utf-8").read(), mine)

    def test_a_config_qmd_has_added_models_to_still_gets_the_new_folder(self):
        # qmd adds a `models:` section after `collections:` the first time it runs
        mine = "collections:\n  my-own:\n    path: /data/stuff\n    pattern: \"**/*.md\"\nmodels:\n  embed: some-model\n"
        conf = self.write(".config/qmd/index.yml", mine)
        folder = self.notes()
        code, out, _ = self.run_main("--yes", "--notes", folder, "--sessions", "none")
        self.assertEqual(code, 0)
        text = open(conf, encoding="utf-8").read()
        self.assertTrue(text.endswith("models:\n  embed: some-model\n"))   # the models section stays last and untouched
        self.assertLess(text.index("\n  notes-notes:"), text.index("\nmodels:"))
        self.assertIn("+1 notes collections", out)

    def test_the_search_config_has_full_paths_because_qmd_does_not_expand_a_tilde(self):
        self.run_main("--yes", "--sessions", "none")
        text = open(os.path.join(self.home, ".config", "qmd", "index.yml"), encoding="utf-8").read()
        self.assertNotRegex(text, r"path:\s*~")
        self.assertIn("path: %s\n" % os.path.join(self.home, "brain", "chats"), text)

    def test_a_second_run_leaves_the_search_config_alone(self):
        folder = self.notes()
        self.run_main("--yes", "--notes", folder, "--sessions", "none")
        conf = os.path.join(self.home, ".config", "qmd", "index.yml")
        first = open(conf, encoding="utf-8").read()
        self.run_main("--yes", "--notes", folder, "--sessions", "none")
        self.assertEqual(open(conf, encoding="utf-8").read(), first)
        self.assertEqual(glob.glob(os.path.join(self.home, ".config", "qmd", "index.yml.bak-*")), [])


if __name__ == "__main__":
    unittest.main()
