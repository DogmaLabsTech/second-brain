"""Tests for the errors the ask helpers used to swallow: each now says something on stderr, no network,
no models: python3 -I ask/test_error_paths.py (CRABBOX_LOCAL=1)"""
import contextlib
import errno
import http.client
import io
import json
import os
import socket
import sys
import tempfile
import threading
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import fake_names  # noqa: E402,F401  (made-up names for the names filter)
import ask  # noqa: E402
import asklog  # noqa: E402
import chat_proxy as cp  # noqa: E402
import haiku_standby  # noqa: E402


@contextlib.contextmanager
def stderr():
    buf = io.StringIO()
    with contextlib.redirect_stderr(buf):
        yield buf


class Boom:
    def __init__(self, exc):
        self.exc = exc
        self.tried = False

    def kill(self):
        self.tried = True
        raise self.exc


class StopWriters(unittest.TestCase):
    def test_a_writer_that_will_not_stop_is_said_and_the_rest_are_still_stopped(self):
        first, second = Boom(RuntimeError("stuck")), Boom(OSError("gone"))
        with mock.patch.object(ask, "_LIVE", [first, second]), stderr() as err:
            ask.stop_writers()
        self.assertTrue(first.tried and second.tried)
        self.assertIn("could not stop a writer: stuck", err.getvalue())
        self.assertIn("could not stop a writer: gone", err.getvalue())

    def test_hangup_on_a_closed_standby_socket_is_quiet(self):
        a, b = socket.socketpair()
        b.close()
        a.close()   # shutdown on a closed socket: the answer was already finished
        with stderr() as err:
            ask._Hangup(a).kill()
        self.assertEqual(err.getvalue(), "")

    def test_hangup_that_fails_for_another_reason_is_said(self):
        sock = mock.Mock()
        sock.shutdown.side_effect = OSError(errno.EIO, "disk on fire")
        with stderr() as err:
            ask._Hangup(sock).kill()
        self.assertIn("could not hang up on the standby Haiku", err.getvalue())


class HaikuWrite(unittest.TestCase):
    def test_a_standby_that_does_not_answer_is_said_before_haiku_starts_here(self):
        with mock.patch.object(ask.os.path, "exists", return_value=True), \
                mock.patch.object(ask, "haiku_standby_write", side_effect=ConnectionRefusedError("stale socket")), \
                mock.patch.object(ask.subprocess, "Popen", side_effect=RuntimeError("started here")), \
                stderr() as err:
            with self.assertRaisesRegex(RuntimeError, "started here"):
                ask.haiku_write("hi")
        self.assertIn("standby Haiku did not answer (stale socket)", err.getvalue())

    def test_a_haiku_that_cannot_be_stopped_is_said_but_the_answer_still_comes(self):
        proc = mock.Mock()
        proc.stdout = [json.dumps({"type": "result", "result": "Two words here."}) + "\n"]
        proc.kill.side_effect = PermissionError("not yours")
        with mock.patch.object(ask.os.path, "exists", return_value=False), \
                mock.patch.object(ask.subprocess, "Popen", return_value=proc), \
                mock.patch.object(ask, "_LIVE", []), stderr() as err:
            text, _, _ = ask.haiku_write("hi", timeout=30)
        self.assertEqual(text, "Two words here.")
        self.assertIn("could not stop Haiku: not yours", err.getvalue())

    def test_warming_the_local_writer_says_when_it_fails(self):
        class Now:   # a thread that runs at once
            def __init__(self, target, daemon=None):
                self.target = target

            def start(self):
                self.target()
        with mock.patch.object(ask.threading, "Thread", Now), \
                mock.patch.object(ask.urllib.request, "urlopen", side_effect=OSError("ollama is down")), \
                stderr() as err:
            ask.warm_local()
        self.assertIn("could not warm the local writer: ollama is down", err.getvalue())


class AskLog(unittest.TestCase):
    def test_a_lost_record_is_said_and_never_breaks_the_answer(self):
        with tempfile.NamedTemporaryFile() as not_a_folder, \
                mock.patch.object(asklog, "STATE", not_a_folder.name), stderr() as err:
            asklog.log_ask("id1", "what?", {"kind": "question"}, "typed")   # must not raise
        self.assertIn("could not record the question", err.getvalue())


class ChatProxy(unittest.TestCase):
    def test_requests_are_not_logged_one_by_one(self):
        with stderr() as err:
            cp.Proxy.log_request(mock.Mock(), 200, 10)
        self.assertEqual(err.getvalue(), "")

    def test_a_search_server_that_is_down_is_logged_and_answered_with_502(self):
        down = socket.socket()
        down.bind(("127.0.0.1", 0))
        port_down = down.getsockname()[1]
        down.close()   # nothing listens here now
        with mock.patch.object(cp.Proxy, "upstream", cp.urllib.parse.urlsplit(f"http://127.0.0.1:{port_down}")):
            srv = cp.ThreadingHTTPServer(("127.0.0.1", 0), cp.Proxy)
            threading.Thread(target=srv.serve_forever, daemon=True).start()
            try:
                with stderr() as err:
                    c = http.client.HTTPConnection("127.0.0.1", srv.server_address[1], timeout=10)
                    c.request("GET", "/health")
                    r = c.getresponse()
                    body = r.read()
                    c.close()
            finally:
                srv.shutdown()
                srv.server_close()
        self.assertEqual(r.status, 502)
        self.assertIn("search server", json.loads(body)["error"])
        self.assertIn("search server failed, answering 502", err.getvalue())

    def test_no_ipv6_listener_is_said(self):
        server = mock.Mock()
        with mock.patch.object(cp, "ThreadingHTTPServer", return_value=server), \
                mock.patch.object(cp, "V6", side_effect=OSError("no ::1 here")), stderr() as err:
            cp.serve(0, "http://localhost:1")
        server.serve_forever.assert_called_once()
        self.assertIn("no listener on ::1 (IPv4 only): no ::1 here", err.getvalue())


class FakeFile:
    def __init__(self, first_line, write_error=None):
        self.first_line, self.write_error = first_line, write_error

    def readline(self):
        return self.first_line

    def write(self, text):
        if self.write_error:
            raise self.write_error

    def flush(self):
        pass


class HaikuStandby(unittest.TestCase):
    def serve(self, f, close_error=None):
        conn = mock.Mock()
        conn.makefile.return_value = f
        if close_error:
            conn.close.side_effect = close_error
        proc = mock.Mock()
        proc.stdin.write.side_effect = f.write_error
        proc.stdout = iter(())
        spare = mock.Mock()
        spare.take.return_value = proc
        with stderr() as err:
            haiku_standby.serve(conn, spare)
        return err.getvalue(), proc

    def test_nonsense_from_the_asker_is_said(self):
        out, _ = self.serve(FakeFile("this is not json\n"))
        self.assertIn("dropped a request", out)

    def test_an_asker_that_hung_up_is_quiet_and_haiku_is_still_stopped(self):
        out, proc = self.serve(FakeFile('{"prompt": "hi"}\n', write_error=BrokenPipeError()))
        self.assertEqual(out, "")
        proc.kill.assert_called_once()

    def test_a_connection_that_will_not_close_is_said(self):
        out, _ = self.serve(FakeFile('{"prompt": "hi"}\n', write_error=BrokenPipeError()), close_error=OSError("stuck"))
        self.assertIn("could not close the connection: stuck", out)


if __name__ == "__main__":
    unittest.main()
