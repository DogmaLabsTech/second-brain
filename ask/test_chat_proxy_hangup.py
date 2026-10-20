"""The chat proxy keeps a caller that hung up apart from a search server that failed: python3 -I ask/test_chat_proxy_hangup.py"""
import contextlib
import io
import os
import sys
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import chat_proxy as cp  # noqa: E402


class Wfile:
    """Takes `ok` writes, then the caller is gone."""
    def __init__(self, ok):
        self.ok = ok

    def write(self, data):
        if self.ok <= 0:
            raise ConnectionResetError(104, "Connection reset by peer")
        self.ok -= 1

    def flush(self):
        pass


def proxy(wfile, upstream):
    h = cp.Proxy.__new__(cp.Proxy)
    h.command, h.path, h.headers = "GET", "/stream", {}
    h.rfile, h.wfile = io.BytesIO(), wfile
    h.request_version, h.requestline, h.client_address, h.close_connection = "HTTP/1.1", "GET /stream", ("x", 1), False
    h._send_upstream = upstream
    return h


def good_upstream(body, headers=None):
    resp = mock.Mock(status=200, reason="OK")
    resp.getheaders.return_value = []
    resp.read1.side_effect = [b"one", b"two", b""]
    return mock.Mock(), resp


class Hangup(unittest.TestCase):
    def run_handle(self, h):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            h._handle()
        return err.getvalue()

    def test_a_caller_that_left_before_the_headers_is_not_a_search_server_failure(self):
        h = proxy(Wfile(0), good_upstream)
        self.assertEqual(self.run_handle(h), "")
        self.assertTrue(h.close_connection)

    def test_a_caller_that_left_mid_stream_is_not_a_search_server_failure(self):
        h = proxy(Wfile(2), good_upstream)   # the headers and the first chunk get through
        self.assertEqual(self.run_handle(h), "")
        self.assertTrue(h.close_connection)

    def test_a_search_server_that_fails_is_still_said(self):
        def down(body, headers=None):
            raise ConnectionRefusedError(111, "Connection refused")
        h = proxy(Wfile(10), down)
        self.assertIn("search server failed, answering 502", self.run_handle(h))

    def test_a_search_server_failure_the_caller_never_hears_about_is_said_once_and_quietly_dropped(self):
        def down(body, headers=None):
            raise ConnectionRefusedError(111, "Connection refused")
        out = self.run_handle(proxy(Wfile(0), down))
        self.assertEqual(out.count("search server failed"), 1)
        self.assertNotIn("hung up", out)


if __name__ == "__main__":
    unittest.main()
