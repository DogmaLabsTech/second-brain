"""Who ran `brain search` / `brain ask` (searchlog.caller), against made-up process trees in a fake /proc:
python3 -I ask/test_caller.py"""
import json
import os
import shutil
import sys
import tempfile
import time
import unittest
from unittest import mock

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import asklog  # noqa: E402
import search_cli  # noqa: E402
import searchlog  # noqa: E402

SAFE_DIR = tempfile.mkdtemp(prefix="caller-test-")   # never the real records
searchlog.SEARCHES = os.path.join(SAFE_DIR, "searches.jsonl")
asklog.ASKS = os.path.join(SAFE_DIR, "asks.jsonl")
TOKEN = "nt-s3cret-hook-token"


class FakeProc:
    """A fake /proc: add(pid, comm, argv, ppid, cwd)."""

    def __init__(self):
        self.root = tempfile.mkdtemp(dir=SAFE_DIR)

    def add(self, pid, comm, argv, ppid, cwd=None):
        d = os.path.join(self.root, str(pid))
        os.makedirs(d)
        with open(os.path.join(d, "stat"), "w") as f:
            f.write(f"{pid} ({comm}) S {ppid} {pid} {pid} 0 -1 4194560 100 0 0 0\n")
        with open(os.path.join(d, "cmdline"), "wb") as f:
            f.write(b"".join(a.encode() + b"\0" for a in argv))
        if cwd:
            os.symlink(cwd, os.path.join(d, "cwd"))
        return self

    def caller(self, start, env=None):
        return searchlog.caller("brain search", start=start, proc=self.root, env=env or {})


HOME = searchlog.HOME


class Caller(unittest.TestCase):
    def test_finds_the_chat_through_its_shells(self):
        p = (FakeProc().add(900, "claude", ["/x/claude/latest/claude", "do the brief"], 800, HOME + "/projects/x")
             .add(901, "bash", ["/usr/bin/bash", "-c", "brain search hi"], 900, HOME + "/elsewhere")
             .add(902, "bash", ["bash", "/x/bin/brain", "search", "hi"], 901, HOME + "/elsewhere"))
        self.assertEqual(p.caller(902), {"name": "brain search", "pid": 900, "program": "claude",
                                         "folder": "~/projects/x"})

    def test_an_agent_run_by_node_is_named_by_its_script(self):
        p = (FakeProc().add(50, "node", ["/usr/bin/node", "/usr/lib/node_modules/codex/bin/codex.js"], 1, HOME)
             .add(51, "sh", ["sh"], 50, HOME))
        self.assertEqual((p.caller(51)["program"], p.caller(51)["pid"], p.caller(51)["folder"]), ("codex", 50, "~"))

    def test_each_known_program(self):
        for comm, argv, want in [("gemini", ["gemini"], "gemini"), ("opencode", ["opencode"], "opencode"),
                                 ("grok", ["grok"], "grok"), ("copilot", ["copilot"], "copilot"),
                                 ("cursor-agent", ["cursor-agent"], "cursor-agent"),
                                 ("quickshell", ["quickshell", "-p", "x"], "island"), ("qs", ["qs"], "island"),
                                 ("obsidian", ["/opt/obsidian/obsidian"], "obsidian"),
                                 ("python3", ["python3", "/home/x/Downloads/agent-notes/brain-prototypes/server.py"], "deck"),
                                 ("tmux: server", ["tmux", "-L", "node-terminal", "new"], "node-terminal")]:
            with self.subTest(comm=comm):
                p = FakeProc().add(10, comm, argv, 1, "/tmp").add(11, "bash", ["bash"], 10, "/tmp")
                self.assertEqual(p.caller(11)["program"], want)

    def test_the_deck_run_from_the_repo_is_named_by_its_folder(self):
        # the Deck starts as `python3 -I server/server.py` from the repo's deck/ folder: only the folder says it is the Deck
        for cwd in (HOME + "/projects/second-brain/deck", HOME + "/Downloads/agent-notes/brain-prototypes"):
            with self.subTest(cwd=cwd):
                p = FakeProc().add(10, "python3", ["python3", "-I", "server/server.py"], 1, cwd).add(11, "bash", ["bash"], 10, cwd)
                self.assertEqual(p.caller(11)["program"], "deck")
        p = FakeProc().add(10, "python3", ["python3", "-I", "server/server.py"], 1, "/tmp/other").add(11, "bash", ["bash"], 10, "/tmp")
        self.assertEqual(p.caller(11)["program"], "terminal")

    def test_a_comm_with_spaces_and_brackets_still_finds_the_parent(self):
        p = (FakeProc().add(7, "claude", ["claude"], 1, HOME)
             .add(8, "weird ) (name", ["weird"], 7, HOME).add(9, "bash", ["bash"], 8, HOME))
        self.assertEqual(p.caller(9)["pid"], 7)

    def test_no_agent_is_terminal_with_the_parent(self):
        p = FakeProc().add(20, "alacritty", ["alacritty"], 1, HOME).add(21, "bash", ["bash"], 20, HOME + "/notes")
        self.assertEqual(p.caller(21), {"name": "brain search", "pid": 21, "program": "terminal", "folder": "~/notes"})

    def test_proc_read_errors_never_raise(self):
        p = FakeProc().add(31, "bash", ["bash"], 30, "/tmp")   # its parent 30 is gone
        self.assertEqual(p.caller(31)["program"], "terminal")
        self.assertEqual(p.caller(999)["folder"], None)        # the start itself is gone
        os.makedirs(os.path.join(p.root, "40"))
        with open(os.path.join(p.root, "40", "stat"), "w") as f:
            f.write("garbage")
        self.assertEqual(p.caller(40)["program"], "terminal")
        p.add(41, "bash", ["bash"], 40)
        os.chmod(os.path.join(p.root, "41", "cmdline"), 0)
        self.assertEqual(p.caller(41)["program"], "terminal")
        with mock.patch.object(searchlog, "_proc", side_effect=RuntimeError("boom")):
            self.assertEqual(p.caller(41)["program"], "terminal")

    def test_a_loop_or_a_deep_tree_stops(self):
        p = FakeProc().add(60, "bash", ["bash"], 61).add(61, "bash", ["bash"], 60)
        self.assertEqual(p.caller(60)["program"], "terminal")
        deep = FakeProc()
        for pid in range(100, 300):
            deep.add(pid, "sh", ["sh"], pid - 1 if pid > 100 else 1)
        deep.add(99, "claude", ["claude"], 1)
        t0 = time.monotonic()
        self.assertEqual(deep.caller(299)["program"], "terminal")   # claude is past MAX_HOPS
        self.assertLess(time.monotonic() - t0, 0.2)

    def test_the_node_title_and_nothing_secret(self):
        data = tempfile.mkdtemp(dir=SAFE_DIR)
        with open(os.path.join(data, "agent-status.json"), "w") as f:
            json.dump({"nodes": {"term-1": {"name": "  Caller\nnames  brief ", "sessionId": "sess-123",
                                            "account": {"configDir": "/home/x/.claude", "accountId": "acct-9"}}}}, f)
        env = {"NODETERM_NODE_ID": "term-1", "NODETERM_DATA_DIR": data, "NODETERM_HOOK_TOKEN": TOKEN,
               "CLAUDE_CODE_MESSAGING_TOKEN": TOKEN, "NODETERM_HOOK_ENDPOINT": "http://127.0.0.1:1/" + TOKEN}
        p = FakeProc().add(5, "claude", ["claude", "--token", TOKEN], 1, HOME).add(6, "bash", ["bash"], 5, HOME)
        out = p.caller(6, env)
        self.assertEqual(out["title"], "Caller names brief")
        text = json.dumps(out)
        for secret in (TOKEN, "sess-123", "acct-9", "configDir", "--token"):
            self.assertNotIn(secret, text)
        self.assertEqual(set(out), {"name", "pid", "program", "folder", "title"})

    def test_no_title_when_nodeterm_has_none(self):
        data = tempfile.mkdtemp(dir=SAFE_DIR)
        p = FakeProc().add(5, "claude", ["claude"], 1, HOME)
        self.assertNotIn("title", p.caller(5, {"NODETERM_NODE_ID": "term-1", "NODETERM_DATA_DIR": data}))   # no file
        with open(os.path.join(data, "agent-status.json"), "w") as f:
            f.write("{broken")
        self.assertNotIn("title", p.caller(5, {"NODETERM_NODE_ID": "term-1", "NODETERM_DATA_DIR": data}))
        with open(os.path.join(data, "agent-status.json"), "w") as f:
            json.dump({"nodes": {"term-1": {"name": None}, "term-2": {"name": 7}}}, f)
        for node in ("term-1", "term-2", "term-3"):
            self.assertNotIn("title", p.caller(5, {"NODETERM_NODE_ID": node, "NODETERM_DATA_DIR": data}))

    def test_the_real_lookup_is_quick(self):
        t0 = time.monotonic()
        for _ in range(20):
            out = searchlog.caller("brain search")
        self.assertLess((time.monotonic() - t0) / 20, searchlog.MAX_MS / 1000)
        self.assertEqual(out["name"], "brain search")
        self.assertTrue(out["program"])


class PrivateOk(unittest.TestCase):
    """May this caller read private notes? Only this copy's Deck or Obsidian, positively found, with no online agent
    anywhere in the chain; a terminal (yours, or a pane an agent types into) never."""
    REAL_DECK = ["python3", "-I", searchlog.DECK_SERVER]
    OBSIDIAN = ["/usr/lib/electron43/electron", "/usr/lib/obsidian/app.asar"]

    def ok(self, p, start, **kw):
        return searchlog.private_ok(start=start, proc=p.root, **kw)

    def test_the_real_deck(self):
        p = FakeProc().add(9, "deck", ["bash", "app/deck"], 1).add(10, "python3", self.REAL_DECK, 9, os.path.dirname(searchlog.DECK_SERVER))
        self.assertTrue(self.ok(p, 10))
        by_hand = FakeProc().add(10, "python3", ["python3", "-I", "server/server.py"], 1,
                                 os.path.dirname(os.path.dirname(searchlog.DECK_SERVER)))
        self.assertTrue(self.ok(by_hand, 10))

    def test_obsidian_as_electron_runs_it(self):
        # main process, then the zygote and the renderer whose title holds its whole command line in one string
        p = (FakeProc().add(20, "electron", self.OBSIDIAN, 1)
             .add(21, "electron", ["/usr/lib/electron43/electron --type=zygote"], 20)
             .add(22, "electron", ["/usr/lib/electron43/electron --type=renderer --app-path=/usr/lib/obsidian/app.asar"], 21))
        self.assertTrue(self.ok(p, 22))
        self.assertTrue(self.ok(FakeProc().add(30, "obsidian", ["/opt/obsidian/obsidian"], 1), 30))
        flags_first = ["/usr/lib/electron43/electron", "--ozone-platform=wayland", "--enable-wayland-ime", "/usr/lib/obsidian/app.asar"]
        self.assertTrue(self.ok(FakeProc().add(31, "electron", flags_first, 1), 31))

    def test_everyone_else_stays_out(self):
        other_copy = "/tmp/elsewhere/second-brain/deck/server/server.py"
        for name, comm, argv, cwd in [
                ("your own or an agent's shell", "bash", ["bash"], "/tmp"),
                ("a terminal window", "alacritty", ["alacritty"], "/tmp"),
                ("the island", "quickshell", ["quickshell", "-p", "x"], "/tmp"),
                ("another copy's Deck", "python3", ["python3", "-I", other_copy], "/tmp"),
                ("the old prototype", "python3", ["python3", "/x/brain-prototypes/server.py"], "/tmp"),
                ("another server.py", "python3", ["python3", "server.py"], "/tmp/second-brain/deck"),
                ("another electron app", "electron", ["/usr/lib/electron43/electron", "/opt/other/app.asar"], "/tmp")]:
            with self.subTest(name):
                self.assertFalse(self.ok(FakeProc().add(40, comm, argv, 1, cwd), 40))

    def test_an_online_agent_anywhere_in_the_chain_stays_out(self):
        for agent in ("claude", "codex", "gemini", "opencode", "grok", "copilot", "cursor-agent"):
            with self.subTest(agent):
                below = FakeProc().add(50, "python3", self.REAL_DECK, 1, "/tmp").add(51, agent, [agent], 50).add(52, "bash", ["bash"], 51)
                self.assertFalse(self.ok(below, 52))
                above = FakeProc().add(60, agent, [agent], 1).add(61, "python3", self.REAL_DECK, 60, "/tmp")
                self.assertFalse(self.ok(above, 61))

    def test_anything_unreadable_hides(self):
        gap = FakeProc().add(70, "python3", self.REAL_DECK, 69, "/tmp")   # its parent is gone: the chain is not whole
        self.assertFalse(self.ok(gap, 70))
        self.assertFalse(self.ok(FakeProc(), 999))
        loop = FakeProc().add(71, "python3", self.REAL_DECK, 72, "/tmp").add(72, "bash", ["bash"], 71)
        self.assertFalse(self.ok(loop, 71))
        with mock.patch.object(searchlog, "_proc", side_effect=RuntimeError("boom")):
            self.assertFalse(self.ok(FakeProc(), 70))

    def test_the_time_limit_hides_and_is_longer_than_the_log_lines(self):
        p = FakeProc().add(80, "python3", self.REAL_DECK, 1, "/tmp")
        self.assertTrue(self.ok(p, 80))
        self.assertFalse(self.ok(p, 80, max_ms=0))
        self.assertGreater(searchlog.TRUST_MS, searchlog.MAX_MS)

    def test_the_logged_program_does_not_change(self):
        p = FakeProc().add(90, "electron", self.OBSIDIAN, 1)
        self.assertEqual(p.caller(90), {"name": "brain search", "pid": 90, "program": "terminal", "folder": None})


class Lines(unittest.TestCase):
    def setUp(self):
        for f in (searchlog.SEARCHES, asklog.ASKS):
            if os.path.exists(f):
                os.unlink(f)

    def test_brain_search_line_names_the_caller(self):
        who = {"name": "brain search", "pid": 4, "program": "claude", "folder": "~/x", "title": "t"}
        with mock.patch.object(search_cli.ask, "search", return_value=[]), \
                mock.patch.object(searchlog, "caller", return_value=who):
            search_cli.search("hi")
        with open(searchlog.SEARCHES) as f:
            r = json.loads(f.read())
        self.assertEqual((r["from"], r["kind"], r["client"]), ("cli", "search", who))

    def test_brain_ask_line_names_the_caller_and_keeps_its_fields(self):
        who = {"name": "brain ask", "pid": 4, "program": "codex", "folder": "~/x"}
        with mock.patch.object(searchlog, "caller", return_value=who):
            asklog.log_ask("q1", "what?", {"kind": "answer", "answer": "a.", "writer": "local"}, "island")
        r = asklog.read(asklog.ASKS)[-1]
        self.assertEqual((r["id"], r["from"], r["q"], r["client"]), ("q1", "island", "what?", who))
        self.assertTrue({"kind", "answer", "writer", "found", "job", "sources", "ms", "steps"} <= set(r))

    def test_a_broken_lookup_still_writes_the_ask(self):
        with mock.patch.object(searchlog, "caller", side_effect=RuntimeError("boom")):
            asklog.log_ask("q2", "what?", {"kind": "answer"}, "cli")
        self.assertEqual(asklog.read(asklog.ASKS)[-1]["client"]["program"], "terminal")


if __name__ == "__main__":
    try:
        unittest.main()
    finally:
        shutil.rmtree(SAFE_DIR, ignore_errors=True)
