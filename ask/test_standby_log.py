"""The standby Haiku never writes what it was given into a log line: python3 -I ask/test_standby_log.py"""
import contextlib
import io
import os
import sys
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import haiku_standby  # noqa: E402


class FakeFile:
    def readline(self):
        raise UnicodeDecodeError("utf-8", b"my secret question", 3, 4, "invalid start byte")

    def write(self, text):
        pass

    def flush(self):
        pass


class Log(unittest.TestCase):
    def test_a_decode_error_logs_its_type_not_the_bytes(self):
        conn = mock.Mock()
        conn.makefile.return_value = FakeFile()
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            haiku_standby.serve(conn, mock.Mock())
        self.assertIn("dropped a request: UnicodeDecodeError", err.getvalue())
        self.assertNotIn("secret", err.getvalue())


if __name__ == "__main__":
    unittest.main()
