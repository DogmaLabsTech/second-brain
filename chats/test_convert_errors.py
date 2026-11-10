"""convert.py says when it cannot read a session file (it used to skip it silently): python3 -I chats/test_convert_errors.py"""
import contextlib
import datetime
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


def _session(session_id="s1"):
    """A made-up Claude Code chat long enough to be a real note; the id is the one thing a test changes."""
    rows = []
    for i in range(4):
        rows.append({"type": "user", "timestamp": "2026-10-20T10:0%d:00.000Z" % (i * 2), "cwd": "/tmp/demo",
                     "sessionId": session_id, "message": {"role": "user", "content": "question number %d about the garden" % i}})
        rows.append({"type": "assistant", "timestamp": "2026-10-20T10:0%d:30.000Z" % (i * 2), "sessionId": session_id,
                     "message": {"role": "assistant", "content": [{"type": "text", "text": "a careful answer number %d with words" % i}]}})
    return "\n".join(json.dumps(r) for r in rows) + "\n"


class HostileChats(unittest.TestCase):
    """Damaged or odd chat files must not write outside the notes folder, add front matter lines or stop the run."""

    def convert(self, *texts, extra=None):
        d = tempfile.mkdtemp()
        self.addCleanup(lambda: __import__("shutil").rmtree(d, ignore_errors=True))
        root, out = os.path.join(d, "projects"), os.path.join(d, "inner", "chats")
        os.makedirs(os.path.join(root, "-tmp-demo"))
        os.makedirs(out)
        for i, text in enumerate(texts):
            with open(os.path.join(root, "-tmp-demo", "s%d.jsonl" % i), "w") as f:
                f.write(text)
        if extra:
            extra(root)
        out_io, err_io = io.StringIO(), io.StringIO()
        with mock.patch.object(convert, "sources", lambda: [root]), contextlib.redirect_stdout(out_io), \
                contextlib.redirect_stderr(err_io):
            code = convert.main(["--out", out, "--quiet"])
        return d, root, out, code, out_io.getvalue(), err_io.getvalue()

    def notes(self, out):
        found = []
        for base, _, files in os.walk(out):
            found += [os.path.join(base, n) for n in files if n.endswith(".md")]
        return found

    def test_a_session_id_with_slashes_stays_inside_the_notes_folder(self):
        d, root, out, code, _, _ = self.convert(_session("/../../."))
        self.assertEqual(code, 0)
        for base, _, files in os.walk(d):
            for n in files:
                inside = os.path.join(base, n)
                self.assertTrue(inside.startswith((out + os.sep, root + os.sep)), inside)
        self.assertTrue(self.notes(out))

    def test_a_session_id_with_a_newline_adds_no_front_matter_line(self):
        d, root, out, code, _, _ = self.convert(_session("abc\nevil: yes"))
        self.assertEqual(code, 0)
        text = open(self.notes(out)[0]).read()
        self.assertEqual([l for l in text.splitlines() if l.startswith("evil")], [])
        self.assertEqual(len([l for l in text.splitlines() if l.startswith("session:")]), 1)

    def test_odd_shapes_in_one_line_do_not_stop_the_chat_or_the_run(self):
        odd = [
            {"type": "user", "timestamp": 1700000000, "message": {"role": "user", "content": "number as a time"}},
            {"type": "user", "timestamp": "2026-10-20T10:00:00", "message": {"role": "user", "content": "a time with no zone"}},
            {"type": "user", "timestamp": "2026-10-20T10:01:00Z", "message": "a message that is a string"},
            {"type": "custom-title", "customTitle": 5},
            {"type": "summary", "summary": ["not", "text"]},
        ]
        text = _session("s-odd") + "\n".join(json.dumps(r) for r in odd) + "\n"
        d, root, out, code, said, err = self.convert(text, _session("s-fine"))
        self.assertEqual(code, 0, err)
        self.assertIn(" 0 errors", said)
        self.assertEqual(len(self.notes(out)), 2)

    def test_a_project_folder_that_cannot_be_read_is_skipped_not_fatal(self):
        def lock(root):
            os.makedirs(os.path.join(root, "-tmp-locked"))
            os.chmod(os.path.join(root, "-tmp-locked"), 0)
            self.addCleanup(lambda: os.chmod(os.path.join(root, "-tmp-locked"), 0o700))
        d, root, out, code, said, err = self.convert(_session("s-ok"), extra=lock)
        if os.access(os.path.join(root, "-tmp-locked"), os.R_OK):
            self.skipTest("running as a user that can read a mode-000 folder")
        self.assertEqual(code, 0, err)
        self.assertEqual(len(self.notes(out)), 1)
        self.assertIn("could not read", err)

    def test_sample_needs_a_number_of_one_or_more(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err), mock.patch.object(convert, "find_sessions", lambda: []):
            self.assertEqual(convert.main(["--sample", "0"]), 2)
        self.assertIn("--sample needs", err.getvalue())

    def test_parse_ts_gives_an_aware_time_or_nothing(self):
        self.assertIsNone(convert.parse_ts(1700000000))
        self.assertIsNone(convert.parse_ts(["x"]))
        naive, aware = convert.parse_ts("2026-10-20T10:00:00"), convert.parse_ts("2026-10-20T10:00:00Z")
        self.assertEqual(naive - aware, datetime.timedelta(0))   # comparable: no "naive and aware" TypeError


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
