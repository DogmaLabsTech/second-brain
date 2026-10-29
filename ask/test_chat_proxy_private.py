"""Private notes never reach a chat through the chats' door (ask/chat_proxy.py), one brain 2026-10-29.
A fake qmd on a free port answers like the real one; nothing real is read. python3 -I ask/test_chat_proxy_private.py"""
import http.client
import json
import os
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import chat_proxy as cp  # noqa: E402

SECRET = "the bank pin is 4711"
PRIVATE = {"type": "resource", "resource": {"uri": "qmd://private/finance/bank.md", "name": "private/finance/bank.md",
                                            "text": SECRET}}
PUBLIC = {"type": "resource", "resource": {"uri": "qmd://computer/system/top-bar.md", "name": "computer/system/top-bar.md",
                                           "text": "the bar runs quickshell"}}


def answer(rpc_id, result):
    return {"jsonrpc": "2.0", "id": rpc_id, "result": result}


class FakeQmd(BaseHTTPRequestHandler):
    def log_message(self, *a):
        return None

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
        if self.path == "/query":
            out = {"results": [{"file": "qmd://private/finance/bank.md", "snippet": SECRET},
                               {"file": "qmd://computer/system/top-bar.md", "snippet": "bar"}]}
            data, ctype = json.dumps(out).encode(), "application/json"
        else:
            name = (body.get("params") or {}).get("name")
            if body.get("method") == "resources/read":
                out = answer(body["id"], {"contents": [{"uri": "qmd://private/finance/bank.md", "text": SECRET}]})
            elif name == "get":
                out = answer(body["id"], {"content": [PRIVATE]})
            else:
                out = answer(body["id"], {"content": [
                    {"type": "text", "text": "[SKIPPED: private/owners-notes/big.md - too big. Use 'qmd_get']"},
                    PRIVATE, PUBLIC]})
            # qmd answers MCP as an event stream
            data, ctype = b"event: message\ndata: " + json.dumps(out).encode() + b"\n\n", "text/event-stream"
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def serve(handler):
    srv = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


class Units(unittest.TestCase):
    def test_get_and_multi_get_lose_the_private_note_and_keep_the_rest(self):
        msg = answer(1, {"content": [{"type": "text", "text": "Errors:\nnone"}, PRIVATE, PUBLIC]})
        out = json.dumps(cp.scrub_private(msg))
        self.assertNotIn(SECRET, out)
        self.assertNotIn("private/finance", out)
        self.assertIn("quickshell", out)
        self.assertIn(cp.LEFT_OUT, out)

    def test_names_in_text_lines_go_too(self):
        msg = answer(1, {"content": [{"type": "text", "text": "Did you mean one of these?\n  - private/finance/bank.md\n  - computer/a.md"}]})
        text = cp.scrub_private(msg)["result"]["content"][0]["text"]
        self.assertNotIn("private/", text)
        self.assertIn("computer/a.md", text)

    def test_a_batch_and_resources_read_are_scrubbed(self):
        batch = [answer(1, {"contents": [{"uri": "qmd://private/x.md", "text": SECRET}]}), answer(2, {"content": [PRIVATE]})]
        self.assertNotIn(SECRET, json.dumps(cp.scrub_private(batch)))

    def test_rest_results(self):
        out = cp.scrub_rest({"results": [{"file": "qmd://private/a.md"}, {"file": "qmd://days/b.md"}]})
        self.assertEqual([r["file"] for r in out["results"]], ["qmd://days/b.md"])

    def test_which_requests_are_read_whole(self):
        call = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "get"}}).encode()
        read = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "resources/read", "params": {}}).encode()
        ping = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "ping"}).encode()
        self.assertTrue(cp.needs_guard("POST", "/mcp", call))
        self.assertTrue(cp.needs_guard("POST", "/mcp", read))
        self.assertTrue(cp.needs_guard("POST", "/mcp", b"not json"))
        self.assertTrue(cp.needs_guard("POST", "/query", b"{}"))
        self.assertTrue(cp.needs_guard("POST", "/search?x=1", b"{}"))
        self.assertFalse(cp.needs_guard("POST", "/mcp", ping))
        self.assertFalse(cp.needs_guard("GET", "/health", None))


class ThroughTheDoor(unittest.TestCase):
    def setUp(self):
        self.qmd = serve(FakeQmd)
        self.addCleanup(self.qmd.shutdown)
        handler = type("P", (cp.Proxy,), {"upstream": cp.urllib.parse.urlsplit(f"http://127.0.0.1:{self.qmd.server_port}")})
        self.door = serve(handler)
        self.addCleanup(self.door.shutdown)

    def post(self, path, body, accept="application/json, text/event-stream"):
        conn = http.client.HTTPConnection("127.0.0.1", self.door.server_port, timeout=20)
        conn.request("POST", path, json.dumps(body), {"Content-Type": "application/json", "Accept": accept})
        resp = conn.getresponse()
        data = resp.read().decode()
        conn.close()
        return resp.status, data

    def test_get_of_a_private_note(self):
        status, data = self.post("/mcp", {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                                          "params": {"name": "get", "arguments": {"file": "#abc123"}}})
        self.assertEqual(status, 200)
        self.assertNotIn(SECRET, data)
        self.assertIn("left out", data)

    def test_multi_get_keeps_the_public_note(self):
        status, data = self.post("/mcp", {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                                          "params": {"name": "multi_get", "arguments": {"pattern": "**/*.md"}}},
                                 accept="text/event-stream")
        self.assertEqual(status, 200)
        self.assertTrue(data.startswith("event: message"))
        self.assertNotIn(SECRET, data)
        self.assertNotIn("owners-notes", data)
        self.assertIn("quickshell", data)

    def test_resources_read(self):
        _status, data = self.post("/mcp", {"jsonrpc": "2.0", "id": 3, "method": "resources/read",
                                           "params": {"uri": "qmd://private/finance/bank.md"}})
        self.assertNotIn(SECRET, data)

    def test_rest_query(self):
        status, data = self.post("/query", {"searches": [{"type": "lex", "query": "bank"}]})
        self.assertEqual(status, 200)
        self.assertNotIn(SECRET, data)
        self.assertEqual([r["file"] for r in json.loads(data)["results"]], ["qmd://computer/system/top-bar.md"])


if __name__ == "__main__":
    unittest.main()
