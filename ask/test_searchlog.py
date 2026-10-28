"""The search record (ask/searchlog.py) and the chat door that writes it, against a stand-in search server on
this computer: python3 -I ask/test_searchlog.py"""
import http.client
import json
import os
import shutil
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest import mock

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import chat_proxy as cp  # noqa: E402
import search_cli  # noqa: E402
import searchlog  # noqa: E402

# Never the real record, not even for a line written after a test has ended (they are written after the reply).
SAFE_DIR = tempfile.mkdtemp(prefix="searchlog-test-")
searchlog.SEARCHES = os.path.join(SAFE_DIR, "searches.jsonl")
SECRET = "Bearer s3cret-token-do-not-log"

# A recorded exchange, in the shape qmd 2.8 answers (event-stream with keepalives, no session id).
INIT_REPLY = (b'event: message\ndata: {"result":{"protocolVersion":"2025-06-18","capabilities":{"tools":{"listChanged":true}},'
              b'"serverInfo":{"name":"qmd","version":"2.8.3"},"instructions":"QMD is your local search engine."},'
              b'"jsonrpc":"2.0","id":1}\n\n')
LIST_REPLY = (b': keepalive\n\nevent: message\ndata: {"result":{"tools":[{"name":"query","description":"Search \xe2\x80\x94 '
              b'notes"},{"name":"get"}]},"jsonrpc":"2.0","id":2}\n\n')
GET_REPLY = (b'event: message\ndata: {"result":{"content":[{"type":"text","text":"# Bar\\nhow to reload it"}]},'
             b'"jsonrpc":"2.0","id":4}\n\n')
RESULTS = [{"docid": "#a1", "file": "computer/system/top-bar.md", "title": "Top bar", "score": 0.91, "snippet": "reload"},
           {"docid": "#b2", "file": "chats/2020-01-01-bar.md", "title": "Bar chat", "score": 0.5, "snippet": "bar"}]


class Upstream(BaseHTTPRequestHandler):
    """Stands in for qmd on its port: canned answers, and it keeps what it was sent."""
    protocol_version = "HTTP/1.1"
    seen = []

    def log_message(self, *a):
        pass

    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
        Upstream.seen.append((dict(self.headers), body))
        msg = json.loads(body)
        method = msg.get("method")
        if method == "initialize":
            out = INIT_REPLY
        elif method == "tools/list":
            out = LIST_REPLY
        elif method == "tools/call" and msg["params"]["name"] == "query":
            res = {"content": [{"type": "text", "text": "x"}], "structuredContent": {"results": RESULTS}}
            out = b"event: message\ndata: " + json.dumps({"result": res, "jsonrpc": "2.0", "id": msg["id"]}).encode() + b"\n\n"
        else:
            out = GET_REPLY
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache, no-transform")
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)


def start(server):
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def post(port, msg, extra=None):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=20)
    h = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
    h.update(extra or {})
    conn.request("POST", "/mcp", body=json.dumps(msg).encode(), headers=h)
    r = conn.getresponse()
    out = (r.status, r.getheader("Content-Type"), r.getheader("Cache-Control"), r.read())
    conn.close()
    return out


INIT = {"jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "test-chat", "version": "9.1"}}}
LIST = {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}
QUERY = {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "query", "arguments": {
    "searches": [{"type": "lex", "query": "zebra bar"}, {"type": "vec", "query": "where is the zebra bar"}],
    "intent": "the zebra bar", "collections": ["computer"], "rerank": False, "limit": 5}}}
GET = {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "get", "arguments": {"file": "computer/system/top-bar.md"}}}


class Door(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.up = start(ThreadingHTTPServer(("127.0.0.1", 0), Upstream))
        cp.Proxy.upstream = cp.urllib.parse.urlsplit(f"http://127.0.0.1:{cls.up.server_address[1]}")
        cls.door = start(ThreadingHTTPServer(("127.0.0.1", 0), cp.Proxy))
        cls.port = cls.door.server_address[1]

    @classmethod
    def tearDownClass(cls):
        cls.door.shutdown()
        cls.up.shutdown()

    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.log = os.path.join(self.dir, "state", "searches.jsonl")
        self.p = mock.patch.object(searchlog, "SEARCHES", self.log)
        self.p.start()
        Upstream.seen.clear()

    def tearDown(self):
        time.sleep(0.1)   # a line is written just after the reply: let the last one land in this test's folder
        self.p.stop()
        shutil.rmtree(self.dir, ignore_errors=True)

    def lines(self, want=0):
        """The record's lines, waiting up to 3 s for `want` of them (they are written just after the reply)."""
        end = time.monotonic() + 3
        while True:
            rows = self._read()
            if len(rows) >= want or time.monotonic() > end:
                return rows
            time.sleep(0.02)

    def _read(self):
        try:
            with open(self.log) as f:
                return [json.loads(l) for l in f]
        except FileNotFoundError:
            return []

    def test_pass_through_is_byte_for_byte(self):
        for msg, want in ((INIT, INIT_REPLY), (GET, GET_REPLY)):
            status, ctype, cache, body = post(self.port, msg)
            self.assertEqual((status, ctype, cache, body), (200, "text/event-stream", "no-cache, no-transform", want))
            self.assertEqual(json.loads(Upstream.seen[-1][1]), msg)   # the request reached qmd unchanged too

    def test_tools_list_is_qmds_plus_memory_in_qmds_format(self):
        # The one reply the door changes (2026-10-28): the memory tool is added (ask/test_memory_tool.py).
        status, ctype, cache, body = post(self.port, LIST)
        self.assertEqual((status, ctype, cache), (200, "text/event-stream", "no-cache, no-transform"))
        self.assertEqual(json.loads(Upstream.seen[-1][1]), LIST)
        want = cp.sse_messages(LIST_REPLY)
        want["result"]["tools"].append(cp.MEMORY_TOOL)
        self.assertEqual(cp.sse_messages(body), want)

    def test_a_search_writes_one_correct_line(self):
        post(self.port, INIT)
        status, _, _, body = post(self.port, QUERY)
        self.assertEqual(status, 200)
        self.assertIn(b"top-bar.md", body)
        rows = [r for r in self.lines(1) if r["kind"] == "search"]
        self.assertEqual(len(rows), 1)
        r = rows[0]
        self.assertEqual(set(r), {"at", "from", "kind", "client", "q", "searches", "intent", "collections", "results", "ms"})
        self.assertEqual((r["from"], r["q"], r["intent"], r["collections"]), ("mcp", "the zebra bar", "the zebra bar", ["computer"]))
        self.assertEqual(r["searches"], QUERY["params"]["arguments"]["searches"])   # the chat's own words, before the mix
        self.assertEqual([x["collection"] for x in r["results"]], ["computer", "chats"])
        self.assertTrue(r["results"][0]["path"].endswith("system/top-bar.md"))
        self.assertEqual(r["results"][0]["score"], 0.91)
        self.assertEqual((r["client"]["name"], r["client"]["version"], r["client"]["pid"]), ("test-chat", "9.1", os.getpid()))
        self.assertIn("folder", r["client"])
        self.assertIsInstance(r["ms"], int)
        self.assertEqual(oct(os.stat(self.log).st_mode & 0o777), "0o600")
        self.assertEqual(oct(os.stat(os.path.dirname(self.log)).st_mode & 0o777), "0o700")

    def test_a_read_writes_a_light_line(self):
        post(self.port, GET)
        r = self.lines(1)[-1]
        self.assertEqual(r["client"]["pid"], os.getpid())   # found even though a read is quick
        self.assertEqual((r["kind"], r["q"], r["results"][0]["path"]), ("read", "get computer/system/top-bar.md",
                                                                         "computer/system/top-bar.md"))

    def test_other_calls_write_nothing(self):
        post(self.port, INIT)
        post(self.port, LIST)
        post(self.port, GET)   # the one line, written after the others were answered
        self.assertEqual([r["kind"] for r in self.lines(1)], ["read"])
        self.assertEqual(self.lines(1)[0]["client"]["name"], "test-chat")   # the name from `initialize`

    def test_a_broken_record_does_not_break_the_search(self):
        blocker = os.path.join(self.dir, "not-a-folder")
        open(blocker, "w").close()
        with mock.patch.object(searchlog, "SEARCHES", os.path.join(blocker, "searches.jsonl")), \
                mock.patch("sys.stderr"):
            status, _, _, body = post(self.port, QUERY)
            self.assertEqual((status, b"top-bar.md" in body), (200, True))
            self.assertEqual(post(self.port, GET)[3], GET_REPLY)

    def test_no_headers_or_auth_are_kept(self):
        post(self.port, INIT, {"Authorization": SECRET, "Cookie": "sid=" + SECRET})
        post(self.port, QUERY, {"Authorization": SECRET, "Cookie": "sid=" + SECRET})
        post(self.port, GET, {"Authorization": SECRET})
        self.lines(2)
        with open(self.log) as f:
            text = f.read()
        self.assertEqual(len(text.splitlines()), 2)
        self.assertNotIn("s3cret", text)
        self.assertNotIn("Authorization", text)


class File(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.log = os.path.join(self.dir, "searches.jsonl")

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def write(self, rows):
        with open(self.log, "w") as f:
            f.writelines(json.dumps(r) + "\n" for r in rows)

    def test_trim_keeps_the_last_lines(self):
        self.write([{"at": time.strftime("%Y-%m-%dT%H:%M:%S"), "n": i} for i in range(30)])
        searchlog.trim(self.log, keep_lines=10)
        with open(self.log) as f:
            self.assertEqual([json.loads(l)["n"] for l in f], list(range(20, 30)))
        self.assertEqual(oct(os.stat(self.log).st_mode & 0o777), "0o600")

    def test_trim_drops_old_days(self):
        self.write([{"at": "2020-01-01T00:00:00", "n": 0}, {"at": time.strftime("%Y-%m-%dT%H:%M:%S"), "n": 1}])
        searchlog.trim(self.log)
        with open(self.log) as f:
            self.assertEqual([json.loads(l)["n"] for l in f], [1])

    def test_record_trims_when_the_first_line_is_too_old(self):
        self.write([{"at": "2020-01-01T00:00:00", "n": 0}])
        searchlog.record({"at": time.strftime("%Y-%m-%dT%H:%M:%S"), "n": 1}, self.log)
        with open(self.log) as f:
            self.assertEqual([json.loads(l)["n"] for l in f], [1])

    def test_record_trims_a_big_file(self):
        now = time.strftime("%Y-%m-%dT%H:%M:%S")
        self.write([{"at": now, "n": i} for i in range(50)])
        with mock.patch.object(searchlog, "TRIM_BYTES", 100), mock.patch.object(searchlog, "KEEP_LINES", 5):
            searchlog.record({"at": now, "n": 50}, self.log)
        with open(self.log) as f:
            self.assertEqual([json.loads(l)["n"] for l in f], [46, 47, 48, 49, 50])

    def test_cli_search_writes_a_cli_line(self):
        hits = [{"path": "/home/x/OMARCHY-BRAIN/system/top-bar.md", "file": "qmd://computer/system/top-bar.md",
                 "score": 1.2345, "snippet": "s"}]
        with mock.patch.object(searchlog, "SEARCHES", self.log), mock.patch.object(search_cli.ask, "search", return_value=hits):
            self.assertEqual(search_cli.search("how do I reload the bar"), hits)
        with open(self.log) as f:
            r = json.loads(f.read())
        self.assertEqual((r["from"], r["kind"], r["q"]), ("cli", "search", "how do I reload the bar"))
        self.assertEqual(r["results"], [{"path": hits[0]["path"], "collection": "computer", "score": 1.234}])
        self.assertTrue(r["searches"] and all(s["type"] in ("lex", "vec") for s in r["searches"]))

    def test_cli_search_survives_a_broken_record(self):
        with mock.patch.object(searchlog, "SEARCHES", "/proc/no/such/searches.jsonl"), \
                mock.patch.object(search_cli.ask, "search", return_value=[]), mock.patch("sys.stderr"):
            self.assertEqual(search_cli.search("x"), [])


if __name__ == "__main__":
    try:
        unittest.main()
    finally:
        shutil.rmtree(SAFE_DIR, ignore_errors=True)
