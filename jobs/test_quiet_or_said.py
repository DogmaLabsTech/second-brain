"""Files that may be missing stay quiet; files that are broken or unreadable are said (details.py,
asklog.py, convert.py): python3 -I jobs/test_quiet_or_said.py"""
import contextlib
import io
import os
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
for d in (HERE, os.path.join(ROOT, "deciders"), os.path.join(ROOT, "ask"), os.path.join(ROOT, "chats")):
    sys.path.insert(0, d)
import asklog  # noqa: E402
import convert  # noqa: E402
import details  # noqa: E402


@contextlib.contextmanager
def stderr():
    buf = io.StringIO()
    with contextlib.redirect_stderr(buf):
        yield buf


class Files(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = os.path.join(self.tmp.name, "file.json")

    def put(self, text):
        with open(self.path, "w") as f:
            f.write(text)

    def check(self, call, bad_text, empty, good=None):
        """Missing: the default, no line. Broken JSON: the default and a line. Good file (if given): its value."""
        with stderr() as err:
            self.assertEqual(call(), empty)
        self.assertEqual(err.getvalue(), "")
        self.put(bad_text)
        with stderr() as err:
            self.assertEqual(call(), empty)
        self.assertIn(self.path, err.getvalue())
        if good:
            self.put(good[0])
            with stderr() as err:
                self.assertEqual(call(), good[1])
            self.assertEqual(err.getvalue(), "")

    def test_details_on(self):
        with mock.patch.object(details, "CONFIG", self.path), mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("BRAIN_DETAILS", None)
            self.check(details.on, "{oops", False, ('{"on": true}', True))

    def test_asklog_read(self):
        self.check(lambda: asklog.read(self.path), "{oops\n", [], ('{"id": "1"}\n', [{"id": "1"}]))

    def test_convert_load_state(self):
        self.check(lambda: convert.load_state(self.path), "{oops", {}, ('{"a": 1}', {"a": 1}))

    @unittest.skipIf(os.geteuid() == 0, "root can read anything")
    def test_a_file_without_permission_is_said_too(self):
        self.put("{}")
        os.chmod(self.path, 0)
        with stderr() as err:
            self.assertEqual(convert.load_state(self.path), {})
        self.assertIn("could not read the state file", err.getvalue())


class Fill(unittest.TestCase):
    def fill(self, error):
        with mock.patch.object(details, "schema", return_value={"type": "object"}), \
                mock.patch.object(details, "loaded", return_value=True), \
                mock.patch.object(details.http.client, "HTTPConnection", side_effect=error), stderr() as err:
            return details.fill("start-claude", "start a claude on example"), err.getvalue()

    def test_a_writer_that_is_down_is_said(self):
        got, out = self.fill(ConnectionRefusedError("down"))
        self.assertIsNone(got)
        self.assertIn("the writer failed (ConnectionRefusedError: down)", out)

    def test_a_writer_that_is_too_slow_is_quiet(self):
        got, out = self.fill(TimeoutError("timed out"))
        self.assertEqual((got, out), (None, ""))


if __name__ == "__main__":
    unittest.main()
