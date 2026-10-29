"""One brain (2026-10-28): every writer and reader of notes points into ~/brain by default.
Each check runs in a fresh python with a fake HOME and no BRAIN_* settings, so nothing real is read or written."""
import json
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def defaults(code, home):
    env = {k: v for k, v in os.environ.items() if not k.startswith(("BRAIN_", "MEMORY_"))}
    env["HOME"] = home
    out = subprocess.run([sys.executable, "-I", "-c", code], cwd=ROOT, env=env, capture_output=True, text=True,
                         timeout=60)
    if out.returncode:
        raise AssertionError(out.stderr[-2000:])
    return json.loads(out.stdout.strip().splitlines()[-1])


class BrainPaths(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.mkdtemp(prefix="brain-paths-")
        self.addCleanup(subprocess.run, ["rm", "-rf", self.home], timeout=30)
        self.brain = os.path.join(self.home, "brain")

    def test_the_agent_store_is_brain_agents_for_every_tool(self):
        got = defaults(
            "import sys, json; sys.path[:0] = ['ask', 'eval'];"
            "import memory, private_tag, memory_keep, memory_drafts, memory_flags;"
            "print(json.dumps([m.store_path() for m in (memory, private_tag, memory_keep, memory_drafts, memory_flags)]))",
            self.home)
        self.assertEqual([os.path.realpath(p) for p in got], [os.path.realpath(os.path.join(self.brain, "agents"))] * 5)

    def test_chat_notes_go_to_brain_chats(self):
        got = defaults("import sys, json; sys.path[:0] = ['chats'];"
                       "import convert, codex; print(json.dumps([convert.OUT, codex.OUT]))", self.home)
        self.assertEqual(got, [os.path.join(self.brain, "chats"), os.path.join(self.brain, "chats", "codex")])

    def test_day_pages_go_to_brain_days_and_the_state_stays(self):
        got = defaults("import sys, json; sys.path[:0] = ['day'];"
                       "import day; print(json.dumps([day.PAGES, day.DATA, day.DONE_FILE]))", self.home)
        self.assertEqual(got, [os.path.join(self.brain, "days"),
                               os.path.join(self.home, ".local/share/second-brain/day"),
                               os.path.join(self.brain, "inbox", "done.md")])

    def test_a_test_run_with_its_own_day_folder_keeps_its_pages_there(self):
        env_code = ("import os, sys, json; os.environ['BRAIN_DAY_DIR'] = '/tmp/x'; sys.path[:0] = ['day'];"
                    "import day; print(json.dumps(day.PAGES))")
        self.assertEqual(defaults(env_code, self.home), "/tmp/x/pages")

    def test_the_remember_list_is_in_brain_inbox(self):
        for script in ("remember", "remind-list"):
            with open(os.path.join(ROOT, "jobs", "bin", script)) as f:
                self.assertIn('"~/brain/inbox/remembered.md"', f.read(), script)

    def test_project_pages_and_open_note_roots_are_in_the_brain(self):
        got = defaults("import sys, json; sys.path[:0] = ['jobs'];"
                       "import jobs; print(json.dumps([jobs.PM_PROJECTS, jobs.NOTE_ROOTS]))", self.home)
        self.assertEqual(got[0], os.path.join(self.brain, "projects"))
        self.assertIn(self.brain, got[1])

    def test_no_old_note_folder_is_named_in_the_code(self):
        old = ("OMARCHY-BRAIN", "projects/shared", "project-manager/projects", ".local/share/second-brain/chats",
               "second-brain/day/pages", "user-labs-business")
        files = ["ask/ask.py", "ask/memory.py", "ask/private_tag.py", "ask/chat_proxy.py", "eval/memory_keep.py",
                 "eval/memory_drafts.py", "eval/memory_flags.py", "eval/drafts.py", "chats/convert.py", "chats/codex.py",
                 "day/day.py", "jobs/jobs.py", "jobs/desktop.py", "jobs/bin/remember", "jobs/bin/remind-list",
                 "deciders/brain_decide.py", "index/index.yml", "index/brain-backup.sh", "index/setup.sh",
                 "index/reindex.sh", "index/codex-testbox.sh", "obsidian/second-brain-ask/main.js"]
        for rel in files:
            with open(os.path.join(ROOT, rel)) as f:
                text = f.read()
            for o in old:
                self.assertNotIn(o, text, f"{rel} still names {o}")


if __name__ == "__main__":
    unittest.main()
