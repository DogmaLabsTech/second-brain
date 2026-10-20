"""day.py says what it used to swallow: python3 -I day/test_error_paths.py (CRABBOX_LOCAL=1)"""
import contextlib
import io
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "jobs"))
import day  # noqa: E402


@contextlib.contextmanager
def stderr():
    buf = io.StringIO()
    with contextlib.redirect_stderr(buf):
        yield buf


class ReadJsonl(unittest.TestCase):
    def test_a_file_that_is_not_there_yet_is_quiet(self):
        with stderr() as err:
            self.assertEqual(day.read_jsonl("/nonexistent/day.jsonl"), [])
        self.assertEqual(err.getvalue(), "")

    def test_a_file_that_cannot_be_read_is_said(self):
        with tempfile.TemporaryDirectory() as d:   # a folder, not a file
            with stderr() as err:
                self.assertEqual(day.read_jsonl(d), [])
        self.assertIn("could not read", err.getvalue())


class Talking(unittest.TestCase):
    def setUp(self):
        quiet = mock.patch.object(day, "TEST_QUIET", False)
        quiet.start()
        self.addCleanup(quiet.stop)

    def test_say_that_cannot_run_is_said(self):
        fake = mock.Mock()
        fake.island_muted.return_value = False
        with mock.patch.object(day, "remind_list", return_value=fake), \
                mock.patch.object(day.os, "access", return_value=True), \
                mock.patch.object(day.subprocess, "run", side_effect=subprocess.TimeoutExpired("say", 120)), \
                stderr() as err:
            day.say("hello")
        self.assertIn("could not say the line", err.getvalue())

    def test_a_notification_that_cannot_start_is_said(self):
        with mock.patch.object(day.subprocess, "Popen", side_effect=FileNotFoundError("sh")), stderr() as err:
            day.notify_open("t", "b", "/tmp/x")
        self.assertIn("could not show the notification", err.getvalue())


if __name__ == "__main__":
    unittest.main()
