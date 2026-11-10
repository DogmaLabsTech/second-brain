"""details.py says what they used to swallow: python3 -I jobs/test_error_paths.py"""
import contextlib
import io
import os
import sys
import unittest
import urllib.error
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import details  # noqa: E402


@contextlib.contextmanager
def stderr():
    buf = io.StringIO()
    with contextlib.redirect_stderr(buf):
        yield buf


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


class JobsCommandLine(unittest.TestCase):
    def test_build_with_nothing_to_build_says_how_to_use_it(self):
        import subprocess
        out = subprocess.run([sys.executable, "-I", os.path.join(HERE, "jobs.py"), "build"], capture_output=True, text=True, timeout=30)
        self.assertEqual(out.returncode, 2)
        self.assertIn("usage", out.stderr)
        self.assertNotIn("Traceback", out.stderr)


if __name__ == "__main__":
    unittest.main()
