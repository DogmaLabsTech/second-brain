"""When the private names list exists but is empty, broken or unreadable, nothing goes to Haiku (fake Claude, made-up
names, no network): python3 -I ask/test_private_fail_closed.py. A missing list refuses as before (names.py)."""
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

BAD = {"empty file": "", "blank file": " \n", "empty object": "{}", "no words": '{"words": []}',
       "typo": '{"words": ["zorblax"],}', "wrong shape": '["zorblax"]', "words not a list": '{"words": "zorblax"}',
       "dash only": '{"words": ["-"]}', "one letter": '{"words": ["a"]}', "partner mark": '{"partner": "?"}'}


class FailClosed(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)
        self.private = os.path.join(self.tmp, "private.json")
        os.makedirs(os.path.join(self.tmp, "no-business"))   # empty: a missing one fails closed (decider 4c49c60)
        env = mock.patch.dict(os.environ, {"DECIDER_PRIVATE_NAMES": self.private,
                                           "DECIDER_BUSINESS_DIR": os.path.join(self.tmp, "no-business")})
        env.start()
        self.addCleanup(env.stop)

    def write(self, text):
        with open(self.private, "w") as f:
            f.write(text)

    def test_ask_sends_nothing_and_says_why(self):
        for name, text in BAD.items():
            with self.subTest(name):
                self.write(text)
                sent = []
                with mock.patch.object(ask, "_haiku_write", lambda *a: sent.append(a) or ("ok", 1, 2)):
                    with self.assertRaises(RuntimeError) as e:
                        ask.haiku_write("how do i restart the bar")
                self.assertEqual(sent, [])
                self.assertIsInstance(e.exception, ask.ListProblem)
                self.assertIn("not sent", str(e.exception))
                self.assertIn("Nothing is sent to any online model", str(e.exception))
                self.assertIn(os.path.basename(self.private) + ")", str(e.exception))

    def test_an_unreadable_file_sends_nothing(self):
        if os.geteuid() == 0:
            self.skipTest("root can read anything")
        self.write('{"words": ["zorblax"]}')
        os.chmod(self.private, 0)
        sent = []
        with mock.patch.object(ask, "_haiku_write", lambda *a: sent.append(a) or ("ok", 1, 2)):
            with self.assertRaises(RuntimeError) as e:
                ask.haiku_write("how do i restart the bar")
        self.assertEqual(sent, [])
        self.assertIn("can't be read", str(e.exception))

    def test_the_message_never_holds_what_is_in_the_file(self):
        self.write('{"words": ["zorblax"],}')
        with self.assertRaises(RuntimeError) as e:
            ask.haiku_write("how do i restart the bar")
        self.assertNotIn("zorblax", str(e.exception).lower())

    def test_a_good_list_still_sends(self):
        self.write('{"words": ["zorblax"]}')
        with mock.patch.object(ask, "_haiku_write", lambda p, s, t, o: ("ok", 1, 2)):
            self.assertEqual(ask.haiku_write("how do i restart the bar")[0], "ok")

    def test_a_missing_list_still_refuses_as_before(self):
        with mock.patch.object(ask, "_haiku_write", lambda *a: self.fail("sent")):
            with self.assertRaises(RuntimeError) as e:
                ask.haiku_write("how do i restart the bar")
        self.assertIn("not sent", str(e.exception))

    def test_the_standby_is_not_clear_with_a_bad_list(self):
        self.write('{"words": ["zorblax"]}')
        self.assertTrue(haiku_standby.names_clear("how do i restart the bar"))
        for name, text in BAD.items():
            with self.subTest(name):
                self.write(text)
                self.assertFalse(haiku_standby.names_clear("how do i restart the bar"))

    def test_the_example_maker_sends_nothing_with_a_bad_list(self):
        for name, text in BAD.items():
            with self.subTest(name):
                self.write(text)
                with mock.patch.object(haiku.subprocess, "run", lambda *a, **k: self.fail("sent")):
                    with self.assertRaises(RuntimeError) as e:
                        haiku.ask_json("plain", "plain")
                self.assertIn("Nothing is sent to any online model", str(e.exception))

    def test_the_example_maker_still_sends_with_a_good_list(self):
        self.write('{"words": ["zorblax"]}')
        run = lambda argv, input=None, **k: mock.Mock(stdout=json.dumps({"result": "[1]"}))  # noqa: E731
        with mock.patch.object(haiku.subprocess, "run", run):
            self.assertEqual(haiku.ask_json("plain", "plain"), [1])


if __name__ == "__main__":
    unittest.main()
