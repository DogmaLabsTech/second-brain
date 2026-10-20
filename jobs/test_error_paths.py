"""desktop.py, details.py and sendfiles.py say what they used to swallow: python3 -I jobs/test_error_paths.py"""
import contextlib
import io
import os
import subprocess
import sys
import tempfile
import unittest
import urllib.error
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import desktop  # noqa: E402
import details  # noqa: E402
import sendfiles  # noqa: E402


@contextlib.contextmanager
def stderr():
    buf = io.StringIO()
    with contextlib.redirect_stderr(buf):
        yield buf


class NextTheme(unittest.TestCase):
    def test_a_missing_current_theme_is_said_and_the_first_theme_is_used(self):
        def run(argv, **kw):
            if argv[:3] == ["omarchy", "theme", "list"]:
                return subprocess.CompletedProcess(argv, 0, "Alpha\nBeta\n", "")
            raise subprocess.TimeoutExpired(argv, 5)
        with mock.patch.object(desktop.subprocess, "run", side_effect=run), stderr() as err:
            self.assertEqual(desktop.next_theme(), "alpha")
        self.assertIn("could not read the current theme", err.getvalue())


class Wake(unittest.TestCase):
    def test_a_timeout_is_the_plan_and_stays_quiet(self):
        for why in (TimeoutError("timed out"), urllib.error.URLError(TimeoutError("timed out"))):
            with mock.patch.object(details.urllib.request, "urlopen", side_effect=why), stderr() as err:
                details.wake()
            self.assertEqual(err.getvalue(), "")

    def test_any_other_failure_is_said(self):
        with mock.patch.object(details.urllib.request, "urlopen", side_effect=ConnectionRefusedError("down")), \
                stderr() as err:
            details.wake()
        self.assertIn("could not wake the writer: down", err.getvalue())


class FolderInfo(unittest.TestCase):
    def test_a_file_that_cannot_be_sized_is_said_and_still_counted(self):
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "a.txt"), "w") as f:
                f.write("hello")
            with mock.patch.object(sendfiles.os.path, "getsize", side_effect=OSError("vanished")), stderr() as err:
                count, size = sendfiles._folder_info(d)
        self.assertEqual((count, size), (1, 0))
        self.assertIn("could not size", err.getvalue())
        self.assertIn("vanished", err.getvalue())


if __name__ == "__main__":
    unittest.main()
