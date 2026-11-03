"""brain ask never sends a private name to Haiku (fake Claude, made-up names, no network).

The names filter is decider's (DECIDER_REPO, default ~/projects/decider). Only made-up names are used:
the list is a temp file (DECIDER_PRIVATE_NAMES) and the business folder is empty (DECIDER_BUSINESS_DIR)."""
import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "deciders", "tools"))
import ask  # noqa: E402
try:
    import haiku  # noqa: E402
    import haiku_standby  # noqa: E402
except ImportError:
    raise unittest.SkipTest("needs the optional decider tools (not part of this repo)")

FAKE = {"partner": "Thandoria", "kid": "Plorvik", "words": ["zorblax", "vex", "oszy"]}
ASKED = "When is Zorblax coming? vexfamily said oszyfamily and Thandoria's dog are fine."


class Names(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)
        self.private = os.path.join(self.tmp, "private.json")
        with open(self.private, "w") as f:
            json.dump(FAKE, f)
        os.makedirs(os.path.join(self.tmp, "no-business"))   # empty: a missing one fails closed (decider 4c49c60)
        env = mock.patch.dict(os.environ, {"DECIDER_PRIVATE_NAMES": self.private,
                                           "DECIDER_BUSINESS_DIR": os.path.join(self.tmp, "no-business")})
        env.start()
        self.addCleanup(env.stop)
        self.names = ask._names()

    def lose_the_list(self):
        os.remove(self.private)

    def test_haiku_gets_marks_and_the_answer_gets_the_names_back(self):
        sent, shown = [], []

        def fake(prompt, system, timeout, on_text):
            sent.append((prompt, system))
            on_text("[NAME1] comes")
            return "[NAME1] comes on Sunday with [NAME4]'s dog.", 1, 2
        with mock.patch.object(ask, "_haiku_write", fake):
            text, _, _ = ask.haiku_write(ASKED, on_text=shown.append)
        prompt, system = sent[0]
        self.assertEqual(self.names.find(prompt), 0)
        self.assertIn("[NAME1]", prompt)
        self.assertIn("marks exactly", prompt)
        self.assertEqual(system, ask.SYSTEM)
        self.assertEqual(text, "Zorblax comes on Sunday with Thandoria's dog.")
        self.assertEqual(shown, ["Zorblax comes"])

    def test_a_prompt_without_names_goes_as_it_is(self):
        sent = []
        with mock.patch.object(ask, "_haiku_write", lambda p, s, t, o: sent.append(p) or ("ok", 1, 2)):
            self.assertEqual(ask.haiku_write("how do i restart the bar")[0], "ok")
        self.assertEqual(sent, ["how do i restart the bar"])

    def test_nothing_is_sent_when_the_list_is_missing(self):
        self.lose_the_list()
        sent = []
        with mock.patch.object(ask, "_haiku_write", lambda *a: sent.append(a) or ("ok", 1, 2)):
            with self.assertRaises(RuntimeError) as e:
                ask.haiku_write("how do i restart the bar")
        self.assertEqual(sent, [])
        self.assertIn("not sent", str(e.exception))

    def test_nothing_is_sent_without_the_filter(self):
        sent = []
        with mock.patch.object(ask, "_names", mock.Mock(side_effect=ImportError("no decider"))), \
                mock.patch.object(ask, "_haiku_write", lambda *a: sent.append(a) or ("ok", 1, 2)):
            with self.assertRaises(RuntimeError):
                ask.haiku_write("how do i restart the bar")
        self.assertEqual(sent, [])

    def test_another_system_prompt_is_cleaned_too(self):
        sent = []
        with mock.patch.object(ask, "_haiku_write", lambda p, s, t, o: sent.append(s) or ("ok", 1, 2)):
            ask.haiku_write("hi", system="Answer like Zorblax would.")
        self.assertEqual(self.names.find(sent[0]), 0)

    def test_the_standby_refuses_a_prompt_with_a_name(self):
        self.assertFalse(haiku_standby.names_clear(ASKED))
        self.assertTrue(haiku_standby.names_clear("how do i restart the bar [NAME1]"))
        self.lose_the_list()
        self.assertFalse(haiku_standby.names_clear("how do i restart the bar"))

    def test_the_standby_sends_an_error_and_claude_gets_nothing(self):
        class Conn:
            def __init__(self, line):
                self.f = _File(line)

            def makefile(self, mode):
                return self.f

            def close(self):
                pass
        spare = mock.Mock()
        conn = Conn(json.dumps({"prompt": ASKED}) + "\n")
        haiku_standby.serve(conn, spare)
        proc = spare.take.return_value
        proc.stdin.write.assert_not_called()
        proc.kill.assert_called()
        self.assertIn("not sent", conn.f.out)

    def test_the_example_maker_cleans_or_refuses(self):
        sent = []

        def run(argv, input=None, **k):
            sent.append((input, argv[argv.index("--system-prompt") + 1]))
            return mock.Mock(stdout=json.dumps({"result": "[1]"}))
        with mock.patch.object(haiku.subprocess, "run", run):
            self.assertEqual(haiku.ask_json(ASKED, "about Zorblax"), [1])
            self.assertEqual(self.names.find(json.dumps(sent)), 0)
            self.lose_the_list()
            with self.assertRaises(RuntimeError):
                haiku.ask_json("plain", "plain")
        self.assertEqual(len(sent), 1)


class _File:
    def __init__(self, line):
        self.line, self.out = line, ""

    def readline(self):
        line, self.line = self.line, ""
        return line

    def write(self, s):
        self.out += s

    def flush(self):
        pass


if __name__ == "__main__":
    unittest.main()
