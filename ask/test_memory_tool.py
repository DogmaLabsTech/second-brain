"""The chats' `memory` tool through the go-between (ask/chat_proxy.py) on a test port, with a fake search server
and a made-up store: python3 -I ask/test_memory_tool.py"""
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import chat_proxy as cp  # noqa: E402
from test_memory import make_store  # noqa: E402

QMD_TOOLS = [{"name": n, "inputSchema": {"type": "object"}} for n in ("query", "get", "multi_get", "status")]


class Upstream(BaseHTTPRequestHandler):
    """qmd as the go-between sees it: /mcp (tools/list, tools/call, batches) and the REST /query."""
    got, sse, query_status = [], False, 200
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def send(self, obj, status=200):
        data = json.dumps(obj).encode()
        ctype = "application/json"
        if Upstream.sse and self.path == "/mcp":
            data, ctype = b"event: message\ndata: " + data + b"\n\n", "text/event-stream"
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        Upstream.got.append((self.path, body))
        if self.path == "/query":
            files = ["projects/demo/lessons/port-clash.md", "projects/other/rules/secret.md"]
            return self.send({"results": [{"file": "qmd://memory/" + f, "score": 1 / (i + 1)}
                                          for i, f in enumerate(files)]}, Upstream.query_status)
        self.send([self.one(m) for m in body] if isinstance(body, list) else self.one(body))

    @staticmethod
    def one(m):
        if m.get("method") == "tools/list":
            return {"jsonrpc": "2.0", "id": m["id"], "result": {"tools": json.loads(json.dumps(QMD_TOOLS))}}
        if m["params"]["name"] == "query":
            sc = {"results": [{"docid": "#a", "score": 1, "file": "computer/x.md", "title": "x"}]}
            return {"jsonrpc": "2.0", "id": m["id"], "result": {"content": [], "structuredContent": sc}}
        return {"jsonrpc": "2.0", "id": m["id"], "result": {"content": [{"type": "text", "text": "from qmd"}]}}


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def wait_for(port, seconds=10):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.2).close()
            return
        except OSError:
            time.sleep(0.05)
    raise RuntimeError("the go-between did not start")


class Door(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="memory-tool-test-")
        cls.store = os.path.join(cls.tmp, "store")
        make_store(cls.store)
        cls.up = ThreadingHTTPServer(("127.0.0.1", 0), Upstream)
        threading.Thread(target=cls.up.serve_forever, daemon=True).start()
        cls.port = free_port()
        env = dict(os.environ, BRAIN_MEMORY_STORE=cls.store, BRAIN_STATE=os.path.join(cls.tmp, "state"))
        cls.proc = subprocess.Popen([sys.executable, "-I", os.path.join(HERE, "chat_proxy.py"), "--port", str(cls.port),
                                     "--upstream", f"http://127.0.0.1:{cls.up.server_address[1]}"],
                                    env=env, stderr=subprocess.DEVNULL)
        wait_for(cls.port)

    @classmethod
    def tearDownClass(cls):
        cls.proc.terminate()
        cls.proc.wait(timeout=10)
        cls.up.shutdown()
        cls.up.server_close()
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def setUp(self):
        Upstream.got, Upstream.sse, Upstream.query_status = [], False, 200

    def post(self, msg, accept="application/json, text/event-stream"):
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}/mcp", json.dumps(msg).encode(),
                                     {"Content-Type": "application/json", "Accept": accept})
        with urllib.request.urlopen(req, timeout=30) as resp:
            return cp.sse_messages(resp.read()), resp.headers.get("Content-Type")

    def call(self, args, id_=7):
        out, _ = self.post({"jsonrpc": "2.0", "id": id_, "method": "tools/call",
                            "params": {"name": "memory", "arguments": args}})
        self.assertEqual(out["id"], id_)
        return out["result"]

    def test_tools_list_has_qmds_tools_and_memory(self):
        out, ctype = self.post({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        names = [t["name"] for t in out["result"]["tools"]]
        self.assertEqual(names, ["query", "get", "multi_get", "status", "memory"])
        tool = out["result"]["tools"][-1]
        self.assertEqual(tool["inputSchema"]["required"], ["repo"])
        self.assertIn("task", tool["inputSchema"]["properties"])
        self.assertIn("rules and lessons", tool["description"].lower())
        self.assertEqual(ctype, "application/json")

    def test_tools_list_from_an_event_stream_and_to_one(self):
        Upstream.sse = True
        out, ctype = self.post({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}, accept="text/event-stream")
        self.assertEqual(out["result"]["tools"][-1]["name"], "memory")
        self.assertEqual(ctype, "text/event-stream")
        out, ctype = self.post({"jsonrpc": "2.0", "id": 3, "method": "tools/list"})   # qmd's format is kept
        self.assertEqual((out["result"]["tools"][-1]["name"], ctype), ("memory", "text/event-stream"))

    def test_memory_call_answered_here_with_find(self):
        res = self.call({"repo": "demo", "task": "which port"})
        self.assertNotIn("isError", res)
        text = res["content"][0]["text"]
        self.assertIn("1. Run the tests on the test machine.", text)
        self.assertIn("3. Port 8181 is the go-between; qmd moved to 8182.", text)
        self.assertNotIn("Another project's rule.", text)
        self.assertEqual(res["structuredContent"]["left_out"], 0)
        self.assertEqual([p for p, _ in Upstream.got], ["/query"])   # the call itself never reached qmd
        self.assertEqual(Upstream.got[0][1]["collections"], ["memory"])

    def test_memory_call_without_a_task(self):
        res = self.call({"repo": "demo"})
        self.assertEqual(len(res["structuredContent"]["notes"]), 4)   # no unpinned all-projects note without a task
        self.assertEqual(Upstream.got, [])

    def test_local_only_reaches_the_chat_marked(self):
        text = self.call({"repo": "demo"})["content"][0]["text"]
        self.assertIn('Summary: with a "colon" and quotes\n   lesson, demo (local-only):', text)

    def test_search_down_falls_back(self):
        Upstream.query_status = 500
        res = self.call({"repo": "demo", "task": "which port"})
        self.assertNotIn("isError", res)
        self.assertIn("Search was not reachable", res["content"][0]["text"])

    def test_a_bad_call_is_an_error_result(self):
        for args in ({}, {"repo": "../etc"}, {"repo": 5}, None):
            res = self.call(args)
            self.assertTrue(res["isError"], args)
            self.assertTrue(res["content"][0]["text"].startswith("memory: "))

    def test_the_other_tools_still_go_to_qmd(self):
        out, _ = self.post({"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                            "params": {"name": "get", "arguments": {"file": "x.md"}}})
        self.assertEqual(out["result"]["content"][0]["text"], "from qmd")
        out, _ = self.post({"jsonrpc": "2.0", "id": 4, "method": "tools/call",
                            "params": {"name": "query", "arguments": {"query": "where is the bar"}}})
        self.assertEqual(out["result"]["structuredContent"]["results"][0]["file"], "computer/x.md")
        sent = Upstream.got[-1][1]["params"]["arguments"]
        self.assertIn("searches", sent)   # still rewritten the island's way

    def test_a_batch_goes_as_before(self):
        out, _ = self.post([{"jsonrpc": "2.0", "id": 5, "method": "tools/call", "params": {"name": "memory", "arguments": {}}},
                            {"jsonrpc": "2.0", "id": 6, "method": "tools/call", "params": {"name": "get", "arguments": {}}}])
        self.assertEqual([m["id"] for m in out], [5, 6])
        self.assertEqual(Upstream.got[-1][0], "/mcp")


class Unit(unittest.TestCase):
    def test_a_failing_find_is_an_error_result(self):
        with mock.patch.object(cp.memory, "find", side_effect=RuntimeError("store broke")):
            res = cp.memory_result({"repo": "demo"}, "http://127.0.0.1:1")
        self.assertEqual(res, {"content": [{"type": "text", "text": "memory: store broke"}], "isError": True})

    def test_memory_is_added_once(self):
        msg = {"result": {"tools": [{"name": "memory"}]}}
        self.assertEqual(len(cp.add_memory_tool(msg)["result"]["tools"]), 1)
        self.assertEqual(cp.add_memory_tool({"error": {"code": 1}}), {"error": {"code": 1}})


if __name__ == "__main__":
    unittest.main()
