"""convert.py says when it cannot read a session file (it used to skip it silently): python3 -I chats/test_convert_errors.py"""
import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import convert  # noqa: E402


class Signature(unittest.TestCase):
    def test_a_file_that_vanished_is_said_and_left_out_of_the_signature(self):
        with tempfile.TemporaryDirectory() as d:
            here = os.path.join(d, "a.jsonl")
            with open(here, "w") as f:
                f.write("{}\n")
            gone = os.path.join(d, "gone.jsonl")
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                sig = convert.Session("k", here, [gone], d).signature()
            self.assertEqual([s[0] for s in sig], ["a.jsonl"])
            self.assertIn(f"could not stat {gone}", err.getvalue())


class MissingSource(unittest.TestCase):
    def run_main(self, roots, out):
        err = io.StringIO()
        with mock.patch.object(convert, "sources", lambda: roots), contextlib.redirect_stderr(err), \
                contextlib.redirect_stdout(io.StringIO()):
            code = convert.main(["--out", out, "--quiet"])
        return code, err.getvalue()

    def seed(self, out):
        with open(os.path.join(out, "kept.md"), "w") as f:
            f.write("a note from an earlier run\n")
        with open(os.path.join(out, convert.STATE_NAME), "w") as f:
            json.dump({"version": 1, "sources": {"gone-session": {"note": "kept.md", "sig": []}}}, f)

    def test_a_missing_source_folder_keeps_the_notes(self):
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "out")
            os.makedirs(out)
            self.seed(out)
            code, err = self.run_main([os.path.join(d, "not-mounted")], out)
            self.assertEqual(code, 0)
            self.assertTrue(os.path.exists(os.path.join(out, "kept.md")))
            self.assertIn("is not there; keeping the 1 notes", err)

    def test_a_source_folder_that_is_there_but_has_lost_the_chat_still_removes_its_note(self):
        with tempfile.TemporaryDirectory() as d:
            out, root = os.path.join(d, "out"), os.path.join(d, "projects")
            os.makedirs(out)
            os.makedirs(root)
            self.seed(out)
            self.run_main([root], out)
            self.assertFalse(os.path.exists(os.path.join(out, "kept.md")))   # the documented mirror behaviour


class NodetermAccounts(unittest.TestCase):
    def test_canvas_agents_chats_are_found_next_to_claudes_own(self):
        """nodeterm's canvas agents keep their chats in their own Claude folders (2026-10-30)."""
        with tempfile.TemporaryDirectory() as home:
            own = os.path.join(home, ".claude", "projects", "-home-x")
            node = os.path.join(home, ".config", "node-terminal", "claude-accounts", "acc1", "projects", "-home-y")
            for d, sid in ((own, "s-own"), (node, "s-node")):
                os.makedirs(d)
                with open(os.path.join(d, sid + ".jsonl"), "w") as f:
                    f.write("{}\n")
            sub = os.path.join(node, "s-own", "subagents")   # a subagent folder whose main chat is in ~/.claude
            os.makedirs(sub)
            with open(os.path.join(sub, "agent-1.jsonl"), "w") as f:
                f.write("{}\n")
            with mock.patch.object(convert, "HOME", home), \
                    mock.patch.object(convert, "SRC", os.path.join(home, ".claude", "projects")):
                found = sorted(os.path.basename(s.main) for s in convert.find_sessions() if s.main)
                self.assertEqual(found, ["s-node.jsonl", "s-own.jsonl"])
                self.assertEqual(len(convert.sources()), 2)


if __name__ == "__main__":
    unittest.main()
