"""brain memory (ask/memory.py) on a made-up store and a fake search server: python3 -I ask/test_memory.py"""
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import memory  # noqa: E402

OLD = time.mktime((2024, 1, 1, 0, 0, 0, 0, 0, -1))   # no newer-first boost left at this age


def note(store, rel, summary, pinned=False, local_only=False, date="2026-10-20", mtime=OLD):
    path = os.path.join(store, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fm = ["---", "project: x", "kind: rule", f"date: {date}", f"summary: {summary}", "files: []",
          f"pinned: {'true' if pinned else 'false'}"] + (["local-only: true"] if local_only else []) + ["---", ""]
    with open(path, "w") as f:
        f.write("\n".join(fm) + "The note body.\n")
    os.utime(path, (mtime, mtime))
    return path


def make_store(root):
    note(root, "projects/demo/rules/tests-on-testbox.md", "Run the tests on the test machine.", pinned=True, date="2026-10-01")
    note(root, "projects/demo/rules/old-pin.md", "An older pinned rule.", pinned=True, date="2026-09-01")
    note(root, "projects/demo/lessons/port-clash.md", "Port 8181 is the go-between; qmd moved to 8182.", date="2026-10-25")
    note(root, "projects/demo/lessons/names.md", 'Summary: with a "colon" and quotes', local_only=True, date="2026-10-10")
    note(root, "all-projects/rules/worktrees.md", "Git worktrees go in ~/.agent-os/worktrees/<repo>/.", date="2026-10-15")
    note(root, "projects/other/rules/secret.md", "Another project's rule.", date="2026-10-27")
    note(root, "projects/Demo/rules/case.md", "Same name, other case.", date="2026-10-27")
    note(root, "projects/demo/history/retired.md", "A retired note in the project.", date="2026-10-27")
    note(root, "history/projects/demo/rules/retired.md", "A retired note.", date="2026-10-27")
    note(root, "drafts/demo-draft.md", "A draft, never pushed.", date="2026-10-27")
    note(root, "projects/demo/drafts/inner.md", "A draft inside the project.", date="2026-10-27")


class FakeQmd(BaseHTTPRequestHandler):
    """POST /query: answers the files in `results` (a list of (file, score)) and keeps the bodies it got."""
    results, bodies, delay, status = [], [], 0, 200

    def log_message(self, *a):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        FakeQmd.bodies.append(body)
        time.sleep(FakeQmd.delay)
        data = json.dumps({"results": [{"file": f, "score": s, "title": "t", "snippet": ""}
                                       for f, s in FakeQmd.results]}).encode()
        try:
            self.send_response(FakeQmd.status)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        except OSError:
            pass   # the slow-search test hung up first


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), FakeQmd)
        cls.url = f"http://127.0.0.1:{cls.server.server_address[1]}"
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        self.store = tempfile.mkdtemp(prefix="memory-test-")
        make_store(self.store)
        FakeQmd.results, FakeQmd.bodies, FakeQmd.delay, FakeQmd.status = [], [], 0, 200

    def tearDown(self):
        shutil.rmtree(self.store, ignore_errors=True)

    def find(self, task=None, repo="demo", **kw):
        kw.setdefault("url", self.url)
        return memory.find(repo, task, store=self.store, **kw)

    def summaries(self, out):
        return [n["summary"] for n in out["notes"]]


class Scope(Base):
    def test_only_the_project_and_all_projects_never_drafts_or_history(self):
        got = self.summaries(self.find())
        self.assertEqual(sorted(got), sorted(["Run the tests on the test machine.", "An older pinned rule.",
                                              "Port 8181 is the go-between; qmd moved to 8182.",
                                              'Summary: with a "colon" and quotes',
                                              "Git worktrees go in ~/.agent-os/worktrees/<repo>/."]))

    def test_search_results_outside_the_scope_are_dropped(self):
        FakeQmd.results = [("qmd://memory/projects/other/rules/secret.md", 1.0), ("qmd://memory/drafts/demo-draft.md", 0.9),
                           ("qmd://memory/history/projects/demo/rules/retired.md", 0.8),
                           ("qmd://memory/projects/demo/history/retired.md", 0.75),
                           ("qmd://memory/projects/Demo/rules/case.md", 0.7),
                           ("qmd://memory/projects/demo/lessons/port-clash.md", 0.5)]
        got = self.summaries(self.find("what about ports"))
        self.assertEqual(got[2:], ["Port 8181 is the go-between; qmd moved to 8182."])

    def test_the_repo_name_is_exact(self):
        self.assertEqual(self.summaries(self.find(repo="Demo"))[0], "Same name, other case.")
        self.assertNotIn("Same name, other case.", self.summaries(self.find()))

    def test_qmd_lowercased_paths_still_match(self):
        note(self.store, "projects/demo/lessons/CamelNote.md", "Camel case file.")
        FakeQmd.results = [("qmd://memory/projects/demo/lessons/camelnote.md", 1.0)]
        self.assertIn("Camel case file.", self.summaries(self.find("camel")))

    def test_a_bad_repo_name_is_refused(self):
        for bad in ("", "../shared", "a/b", None, ".hidden"):
            with self.assertRaises(ValueError):
                self.find(repo=bad)


class Order(Base):
    def test_no_task_pinned_then_newest(self):
        self.assertEqual(self.summaries(self.find()), [
            "Run the tests on the test machine.", "An older pinned rule.", "Port 8181 is the go-between; qmd moved to 8182.",
            "Git worktrees go in ~/.agent-os/worktrees/<repo>/.", 'Summary: with a "colon" and quotes'])
        self.assertEqual(FakeQmd.bodies, [])   # no task, no search

    def test_with_a_task_pinned_first_then_best_match(self):
        FakeQmd.results = [("qmd://memory/all-projects/rules/worktrees.md", 1.0),
                           ("qmd://memory/projects/demo/rules/tests-on-testbox.md", 0.9),
                           ("qmd://memory/projects/demo/lessons/names.md", 0.5)]
        out = self.find("where do worktrees go")
        self.assertEqual(self.summaries(out), ["Run the tests on the test machine.", "An older pinned rule.",
                                               "Git worktrees go in ~/.agent-os/worktrees/<repo>/.",
                                               'Summary: with a "colon" and quotes'])
        body = FakeQmd.bodies[0]
        self.assertEqual(body["collections"], ["memory"])
        self.assertFalse(body["rerank"])

    def test_newer_wins_a_close_call_but_not_a_clear_one(self):
        note(self.store, "projects/demo/lessons/fresh.md", "A fresh lesson.", mtime=time.time())
        FakeQmd.results = [("qmd://memory/projects/demo/lessons/port-clash.md", 1.0),
                           ("qmd://memory/projects/demo/lessons/fresh.md", 0.9)]
        self.assertEqual(self.summaries(self.find("ports"))[2:], ["A fresh lesson.", "Port 8181 is the go-between; qmd moved to 8182."])
        FakeQmd.results = [("qmd://memory/projects/demo/lessons/port-clash.md", 1.0),
                           ("qmd://memory/projects/demo/lessons/fresh.md", 0.3)]
        self.assertEqual(self.summaries(self.find("ports"))[2:], ["Port 8181 is the go-between; qmd moved to 8182.", "A fresh lesson."])


class Output(Base):
    def test_summary_word_for_word_kind_project_path(self):
        out = self.find()
        text = out["text"]
        self.assertIn("1. Run the tests on the test machine.\n   rule, demo (pinned): " +
                      os.path.join(self.store, "projects/demo/rules/tests-on-testbox.md"), text)
        self.assertIn("lesson, demo", text)
        self.assertIn("rule, all-projects: " + os.path.join(self.store, "all-projects/rules/worktrees.md"), text)

    def test_local_only_is_shown_and_marked(self):
        out = self.find()
        n = next(n for n in out["notes"] if n["local_only"])
        self.assertEqual(n["summary"], 'Summary: with a "colon" and quotes')
        self.assertIn('Summary: with a "colon" and quotes\n   lesson, demo (local-only): ', out["text"])

    def test_a_json_quoted_summary_is_read_as_stored(self):
        path = note(self.store, "projects/demo/rules/q.md", "x")
        with open(path) as f:
            text = f.read().replace("summary: x", "summary: " + json.dumps('Use "brain ask": not #1'))
        with open(path, "w") as f:
            f.write(text)
        self.assertIn('Use "brain ask": not #1', self.summaries(self.find()))


class ExactThings(Base):
    def test_the_rule(self):
        cases = {
            "the bar restarts too often": [],
            "fix chat_proxy.py on port 8181": ["chat_proxy.py", "8181"],
            'why "connection refused" in the island': ["connection refused"],
            "call newer_first() from search": ["newer_first"],
            "keep_draft raises ValueError": ["keep_draft", "ValueError"],
            "the `brain memory` command": ["brain memory"],
            "what runs on :8080 and in index/setup.sh": ["index/setup.sh", "8080"],
            "rename loadNotes in the plugin": ["loadNotes"],
        }
        for task, want in cases.items():
            self.assertEqual(memory.exact_things(task), want, task)

    def test_meaning_only_unless_an_exact_thing(self):
        self.find("how do I run the tests")
        self.assertEqual({s["type"] for s in FakeQmd.bodies[-1]["searches"]}, {"vec"})
        self.find("the tests for chat_proxy.py fail")
        lex = [s["query"] for s in FakeQmd.bodies[-1]["searches"] if s["type"] == "lex"]
        self.assertEqual(lex, ["chat_proxy.py"])

    def test_at_most_three_exact_things(self):
        self.assertEqual(len(memory.exact_things("a.py b.py c.py d.py e_f g_h")), 3)


class Budget(Base):
    def test_stops_before_the_budget_and_says_how_many_did_not_fit(self):
        for i in range(60):
            note(self.store, f"projects/demo/lessons/n{i:02d}.md", f"Lesson number {i} " + "word " * 20)
        out = self.find()
        self.assertLessEqual(memory.tokens(out["text"]), 2000)
        self.assertGreater(out["left_out"], 0)
        self.assertEqual(len(out["notes"]) + out["left_out"], 65)
        self.assertIn(f"{out['left_out']} more notes did not fit in 2000 tokens", out["text"])

    def test_a_small_budget(self):
        out = self.find(budget=60)
        self.assertLessEqual(memory.tokens(out["text"]), 60)
        self.assertEqual(len(out["notes"]) + out["left_out"], 5)

    def test_everything_fits_no_line_about_it(self):
        self.assertNotIn("did not fit", self.find()["text"])


class Missing(Base):
    def test_no_store(self):
        out = memory.find("demo", "x", store=os.path.join(self.store, "nope"), url=self.url)
        self.assertIn("No memory store at", out["text"])
        self.assertEqual(out["notes"], [])

    def test_empty_store(self):
        empty = tempfile.mkdtemp(prefix="memory-empty-")
        try:
            out = memory.find("demo", "x", store=empty, url=self.url)
            self.assertIn("No notes for demo", out["text"])
        finally:
            os.rmdir(empty)

    def test_no_notes_for_the_repo_still_gets_all_projects(self):
        self.assertEqual(self.summaries(self.find(repo="newrepo")), ["Git worktrees go in ~/.agent-os/worktrees/<repo>/."])

    def test_a_broken_note_is_skipped_not_a_crash(self):
        with open(os.path.join(self.store, "projects/demo/rules/bin.md"), "wb") as f:
            f.write(b"\xff\xfe\x00 not text")
        self.assertEqual(len(self.find()["notes"]), 5)


class Fallback(Base):
    def check_fallback(self, out):
        self.assertIn("Search was not reachable", out["text"])
        self.assertIn("showing pinned and newest notes instead", out["fallback"])
        self.assertEqual(self.summaries(out)[:3], ["Run the tests on the test machine.", "An older pinned rule.",
                                                   "Port 8181 is the go-between; qmd moved to 8182."])

    def test_search_down(self):
        self.check_fallback(self.find("ports", url=f"http://127.0.0.1:{free_port()}"))

    def test_search_slow(self):
        FakeQmd.delay, old = 0.5, memory.SEARCH_SECONDS
        memory.SEARCH_SECONDS = 0.1
        try:
            out = self.find("ports")
        finally:
            memory.SEARCH_SECONDS = old
        self.check_fallback(out)
        self.assertIn("slower than 0.1s", out["text"])

    def test_search_error_reply(self):
        FakeQmd.status = 500
        self.check_fallback(self.find("ports"))


class Cli(Base):
    def run_cli(self, *args, url=None):
        env = dict(os.environ, BRAIN_MEMORY_STORE=self.store, BRAIN_URL=url or self.url)
        return subprocess.run([sys.executable, "-I", os.path.join(HERE, "memory.py"), *args],
                              capture_output=True, text=True, env=env, timeout=30)

    def test_results_exit_0(self):
        FakeQmd.results = [("qmd://memory/projects/demo/lessons/port-clash.md", 1.0)]
        out = self.run_cli("demo", "which", "port")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("Task: which port", out.stdout)
        self.assertIn("3. Port 8181 is the go-between; qmd moved to 8182.", out.stdout)
        self.assertEqual(FakeQmd.bodies[-1]["searches"][0], {"type": "vec", "query": "which port"})

    def test_plain_message_exit_0(self):
        env_store, self.store = self.store, os.path.join(self.store, "missing")
        try:
            out = self.run_cli("demo")
        finally:
            self.store = env_store
        self.assertEqual(out.returncode, 0)
        self.assertIn("No memory store at", out.stdout)

    def test_bad_call_exit_1(self):
        self.assertEqual(self.run_cli().returncode, 1)
        out = self.run_cli("../etc")
        self.assertEqual(out.returncode, 1)
        self.assertIn("not a project name", out.stderr)

    def test_the_brain_command(self):
        env = dict(os.environ, BRAIN_MEMORY_STORE=self.store, BRAIN_URL=f"http://127.0.0.1:{free_port()}")
        out = subprocess.run([os.path.join(os.path.dirname(HERE), "bin", "brain"), "memory", "demo", "ports"],
                             capture_output=True, text=True, env=env, timeout=30)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("Search was not reachable", out.stdout)


if __name__ == "__main__":
    unittest.main()
