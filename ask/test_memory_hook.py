"""The memory hook (ask/memory_hook.py) run as Claude runs it, on a made-up store, projects folder and search server:
CRABBOX_LOCAL=1 python3 -I ask/test_memory_hook.py"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import memory  # noqa: E402
import memory_hook  # noqa: E402
from test_memory import Base, FakeQmd, free_port, note  # noqa: E402

HOOK = os.path.join(os.path.dirname(HERE), "bin", "brain-memory-hook")


def git(*args, cwd):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, timeout=20)


class Hook(Base):
    """Each test gets a fresh HOME with ~/projects/demo (a git repo) and an empty state folder."""

    def setUp(self):
        super().setUp()
        self.home = tempfile.mkdtemp(prefix="memory-hook-home-")
        self.projects = os.path.join(self.home, "projects", "Projects")
        self.demo = os.path.join(self.projects, "demo")
        os.makedirs(self.demo)
        git("init", "-q", "-b", "main", cwd=self.demo)
        git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "-m", "start", cwd=self.demo)
        self.state = os.path.join(self.home, "state")
        self.env = dict(os.environ, HOME=self.home, BRAIN_MEMORY_STORE=self.store, BRAIN_URL=self.url,
                        BRAIN_HOOK_STATE=self.state, GIT_CONFIG_NOSYSTEM="1")
        for key in ("BRAIN_PROJECTS_DIR", "BRAIN_HOOK_SECONDS", "BRAIN_HOOK_SEARCH_SECONDS"):
            self.env.pop(key, None)

    def tearDown(self):
        super().tearDown()
        shutil.rmtree(self.home, ignore_errors=True)

    def hook(self, stdin=None, cwd=None, prompt="fix the port clash on 8181", session="s1", **env):
        """(stdout, seconds) of one hook run; it must always exit 0 with nothing on stderr."""
        if stdin is None:
            stdin = json.dumps({"session_id": session, "cwd": cwd or self.demo, "prompt": prompt,
                                "hook_event_name": "UserPromptSubmit", "transcript_path": "/nowhere"})
        start = time.monotonic()
        run = subprocess.run([HOOK], input=stdin, capture_output=True, text=True, timeout=30,
                             env=dict(self.env, **env), cwd=self.home)
        took = time.monotonic() - start
        self.assertEqual((run.returncode, run.stderr), (0, ""))
        return run.stdout, took

    def context(self, out):
        return json.loads(out)["hookSpecificOutput"]["additionalContext"]


class Project(Hook):
    def test_the_project_folder_and_a_subfolder(self):
        os.makedirs(os.path.join(self.demo, "src", "deep"))
        self.assertIn("Agent memory for demo", self.context(self.hook()[0]))
        out = self.hook(cwd=os.path.join(self.demo, "src", "deep"), session="s2")[0]
        self.assertIn("Run the tests on the test machine.", self.context(out))

    def test_a_git_worktree_counts_as_its_project(self):
        tree = os.path.join(self.home, "elsewhere", "feature-x")
        git("worktree", "add", "-q", "-b", "feature-x", tree, cwd=self.demo)
        self.assertIn("Agent memory for demo", self.context(self.hook(cwd=tree)[0]))

    def test_a_agent_worktree_folder_without_git(self):
        tree = os.path.join(self.home, ".agent-os", "worktrees", "demo", "some-branch")
        os.makedirs(tree)
        self.assertIn("Agent memory for demo", self.context(self.hook(cwd=tree)[0]))

    def test_folders_that_are_not_projects_get_nothing(self):
        other = os.path.join(self.home, "scratch", "notaproject")
        os.makedirs(other)
        git("init", "-q", cwd=other)
        for cwd in (other, self.home, self.projects, "/", "relative/path", os.path.join(self.home, "missing")):
            self.assertEqual(self.hook(cwd=cwd, session="x" + str(abs(hash(cwd))))[0], "", cwd)

    def test_a_project_with_no_notes_and_an_empty_store(self):
        os.makedirs(os.path.join(self.projects, "lonely"))
        shutil.rmtree(os.path.join(self.store, "all-projects"))
        self.assertEqual(self.hook(cwd=os.path.join(self.projects, "lonely"))[0], "")
        shutil.rmtree(self.store)
        os.makedirs(self.store)
        self.assertEqual(self.hook(session="s2")[0], "")

    def test_the_store_missing_like_on_the_rog(self):
        out, took = self.hook(BRAIN_MEMORY_STORE=os.path.join(self.home, "no-store"))
        self.assertEqual(out, "")
        self.assertLess(took, 2)

    def test_no_projects_folder_at_all(self):
        self.assertEqual(self.hook(BRAIN_PROJECTS_DIR=os.path.join(self.home, "none"))[0], "")


class OncePerSession(Hook):
    def test_only_the_first_prompt_of_a_session(self):
        self.assertNotEqual(self.hook(session="abc")[0], "")
        self.assertEqual(self.hook(session="abc", prompt="now the other port")[0], "")
        self.assertNotEqual(self.hook(session="def")[0], "")

    def test_the_off_switch(self):
        os.makedirs(self.state)
        open(os.path.join(self.state, "memory-hook.off"), "w").close()
        self.assertEqual(self.hook()[0], "")
        os.remove(os.path.join(self.state, "memory-hook.off"))
        self.assertNotEqual(self.hook(session="s2")[0], "")

    def test_a_strange_session_id_gets_nothing(self):
        for sid in ("", "../escape", "a/b", None, 7, "x" * 200):
            self.assertEqual(self.hook(stdin=json.dumps({"session_id": sid, "cwd": self.demo, "prompt": "p q r"}))[0],
                             "")
        self.assertFalse(os.path.exists(os.path.join(self.home, "escape")))

    def test_old_markers_are_pruned(self):
        marks = os.path.join(self.state, "memory-hook")
        os.makedirs(marks)
        for name, age in (("old", 4 * 86400), ("young", 3600)):
            open(os.path.join(marks, name), "w").close()
            os.utime(os.path.join(marks, name), (time.time() - age,) * 2)
        self.hook()
        self.assertEqual(sorted(os.listdir(marks)), ["s1", "young"])


class Prompts(Hook):
    def test_a_prompt_with_no_meaning_pushes_pinned_and_newest_without_a_search(self):
        for i, prompt in enumerate(("continue", "yes", "ok", "Go ahead.", "  ", "y", "keep going!", "do it")):
            text = self.context(self.hook(prompt=prompt, session=f"c{i}")[0])
            self.assertNotIn("Task:", text, prompt)
            self.assertIn("1. Run the tests on the test machine.", text)
        self.assertEqual(FakeQmd.bodies, [])

    def test_task_of(self):
        self.assertIsNone(memory_hook.task_of("Continue, please"))
        self.assertIsNone(memory_hook.task_of("ab"))
        self.assertEqual(memory_hook.task_of("fix  the\nlogin bug"), "fix the login bug")
        self.assertEqual(memory_hook.task_of("fix it"), "fix it")

    def test_a_prompt_that_names_a_brief_searches_with_its_words(self):
        with open(os.path.join(self.demo, "brief.md"), "w") as f:
            f.write("# Builder brief\n\nWorktree /some/where/x. Fix the **port clash** in the go-between.\n")
        self.hook(prompt="Read brief.md and do exactly what it says.")
        vec = [s["query"] for s in FakeQmd.bodies[0]["searches"] if s["type"] == "vec"][0]
        self.assertEqual(vec, "Read brief.md and do exactly what it says. Builder brief Worktree Fix the **port clash** "
                              "in the go-between.")
        self.assertEqual(memory_hook.with_brief("Read /no/such/brief.md now", "/"), "Read /no/such/brief.md now")
        self.assertIsNone(memory_hook.with_brief(None, "/"))

    def test_a_brief_that_is_a_fifo_is_skipped_not_read(self):
        os.mkfifo(os.path.join(self.demo, "pipe.md"))   # an open() on it would block forever
        start = time.monotonic()
        self.assertEqual(memory_hook.with_brief("Read pipe.md now", self.demo), "Read pipe.md now")
        self.assertLess(time.monotonic() - start, 0.5)

    def test_a_real_prompt_is_the_search_task(self):
        FakeQmd.results = [("qmd://memory/projects/demo/lessons/port-clash.md", 0.9)]
        text = self.context(self.hook(prompt="why does port 8181 clash?")[0])
        self.assertIn("Task: why does port 8181 clash?", text)
        self.assertLess(text.index("Port 8181 is the go-between"), text.index("Git worktrees go in"))
        self.assertEqual(len(FakeQmd.bodies), 1)


class Budget(Hook):
    def test_search_down_falls_back_quickly(self):
        out, took = self.hook(BRAIN_URL=f"http://127.0.0.1:{free_port()}")
        self.assertIn("Search was not reachable", self.context(out))
        self.assertLess(took, 2)

    def test_slow_search_holds_the_budget_with_the_fallback(self):
        FakeQmd.delay = 8
        out, took = self.hook()
        print(f"\n  slow search, default budget: {took:.2f}s", file=sys.stderr)
        self.assertIn("slower than 1.5s", self.context(out))
        self.assertLess(took, 3)

    def test_nothing_ready_in_the_total_budget_means_no_output(self):
        FakeQmd.delay = 8
        out, took = self.hook(BRAIN_HOOK_SECONDS="0.6", BRAIN_HOOK_SEARCH_SECONDS="5")
        print(f"  slow search, 0.6s total budget: {took:.2f}s", file=sys.stderr)
        self.assertEqual(out, "")
        self.assertLess(took, 1.5)

    def test_at_most_2000_tokens_whatever_the_store(self):
        for i in range(300):
            note(self.store, f"projects/demo/lessons/long-{i}.md", f"Lesson {i}: " + "word " * 60, date="2026-10-20")
        text = self.context(self.hook()[0])
        self.assertLessEqual(memory.tokens(text), 2000)
        self.assertIn("did not fit in", text)

    def test_the_log_line(self):
        self.hook()
        with open(os.path.join(self.state, "memory-hook.jsonl")) as f:
            line = json.loads(f.read())
        self.assertEqual((line["repo"], line["session"], line["notes"]), ("demo", "s1", 5))
        self.assertLess(line["seconds"], 3)


class Shape(Hook):
    def test_the_exact_output(self):
        out = self.hook(prompt="continue")[0]
        self.assertTrue(out.endswith("}\n") and out.count("\n") == 1)
        data = json.loads(out)
        self.assertEqual(sorted(data), ["hookSpecificOutput", "systemMessage"])
        self.assertEqual(sorted(data["hookSpecificOutput"]), ["additionalContext", "hookEventName"])
        self.assertEqual(data["hookSpecificOutput"]["hookEventName"], "UserPromptSubmit")
        text = data["hookSpecificOutput"]["additionalContext"]
        self.assertTrue(text.startswith("Agent memory for demo: 5 notes from <user>'s memory store"))
        self.assertIn('`memory` tool (brain MCP) or `brain memory demo "task"`', text)
        self.assertEqual(data["systemMessage"], f"Memory: 5 notes pushed ({memory.tokens(text)} tokens) for demo.")

    def test_bad_input_says_nothing(self):
        for stdin in ("", "not json", "[]", "null", '"text"', "{}", '{"cwd": 5, "session_id": "a"}',
                      json.dumps({"session_id": "b", "cwd": self.demo, "prompt": ["a list"]}),
                      "{" * 5000):
            out = self.hook(stdin=stdin)[0]
            self.assertTrue(out == "" or "Agent memory for demo" in self.context(out), stdin[:40])


if __name__ == "__main__":
    unittest.main()
