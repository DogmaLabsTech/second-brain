"""Small tests for the chat search mix (ask/chat_proxy.py), no network: python3 -I ask/test_chat_proxy.py"""
import os
import sys
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ask  # noqa: E402
import chat_proxy as cp  # noqa: E402


class Rewrite(unittest.TestCase):
    def test_plain_query_becomes_the_island_mix(self):
        args, want = cp.rewrite_args({"query": "how do I reload the bar", "limit": 4, "intent": "the top bar"})
        self.assertNotIn("query", args)
        self.assertEqual(want, 4)
        types = [s["type"] for s in args["searches"]]
        self.assertEqual(types, ["vec", "vec"])   # no word-search line since 2026-10-27 (ask/expand.py)
        self.assertIn({"type": "vec", "query": "how do I reload the bar"}, args["searches"])
        self.assertTrue(any("restart" in s["query"] for s in args["searches"] if s["type"] == "vec"))
        self.assertFalse(args["rerank"])
        self.assertEqual(args["intent"], "the top bar")

    def test_plain_query_keeps_a_rerank_the_caller_asked_for(self):
        args, _ = cp.rewrite_args({"query": "how do I reload the bar", "rerank": True})
        self.assertTrue(args["rerank"])

    def test_chat_searches_get_the_notes_words_once(self):
        mine = [{"type": "lex", "query": "reload bar"}, {"type": "vec", "query": "how do I reload the bar"}]
        args, _ = cp.rewrite_args({"searches": mine, "rerank": False})
        self.assertEqual(args["searches"][:2], mine)
        self.assertEqual(len(args["searches"]), 3)
        self.assertTrue(args["searches"][2]["query"].startswith("how do I reload the bar "))
        again, _ = cp.rewrite_args(args)
        self.assertEqual(len(again["searches"]), 3)

    def test_nothing_added_when_no_word_matches(self):
        mine = [{"type": "lex", "query": "zebra"}, {"type": "vec", "query": "where is the zebra"}]
        self.assertEqual(cp.rewrite_args({"searches": mine})[0]["searches"], mine)

    def test_never_more_than_qmd_allows(self):
        mine = [{"type": "lex", "query": f"reload {i}"} for i in range(cp.MAX_SEARCHES)]
        self.assertEqual(len(cp.rewrite_args({"searches": mine})[0]["searches"]), cp.MAX_SEARCHES)

    def test_wider_net_for_newer_first(self):
        old = ask.NEWER_DAYS
        try:
            ask.NEWER_DAYS = 30
            self.assertEqual(cp.rewrite_args({"searches": [{"type": "lex", "query": "x"}]})[0]["limit"], 20)
            self.assertEqual(cp.rewrite_args({"searches": [{"type": "lex", "query": "x"}], "limit": 3}), (
                {"searches": [{"type": "lex", "query": "x"}], "limit": 6}, 3))
        finally:
            ask.NEWER_DAYS = old


class Result(unittest.TestCase):
    def test_newer_note_wins_a_close_call_and_the_list_is_cut_back(self):
        today = time.strftime("%Y-%m-%d")
        rows = [{"docid": "#a", "file": "chats/2020-01-01-old.md", "title": "Old", "score": 1.0},
                {"docid": "#b", "file": f"chats/{today}-new.md", "title": "New", "score": 0.9},
                {"docid": "#c", "file": "chats/2020-01-02-other.md", "title": "Other", "score": 0.3}]
        msg = {"jsonrpc": "2.0", "id": 7, "result": {"content": [], "structuredContent": {"results": rows}}}
        old = ask.NEWER_DAYS
        try:
            ask.NEWER_DAYS = 30
            out = cp.rewrite_result(msg, 2, "bar")
        finally:
            ask.NEWER_DAYS = old
        got = out["result"]["structuredContent"]["results"]
        self.assertEqual([r["docid"] for r in got], ["#b", "#a"])
        self.assertEqual(got[0]["score"], 0.9)   # the shown score stays qmd's
        self.assertEqual(out["result"]["content"][0]["text"],
                         'Found 2 results for "bar":\n\n'
                         f"#b 90% chats/{today}-new.md - New\n#a 100% chats/2020-01-01-old.md - Old")

    def test_private_notes_never_reach_a_chat(self):
        rows = [{"docid": "#p", "file": "private/finance/bill.md", "title": "Bill", "score": 1.0},
                {"docid": "#q", "file": "qmd://private/owners-notes/x.md", "title": "X", "score": 0.95},
                {"docid": "#c", "file": "computer/system/top-bar.md", "title": "Bar", "score": 0.5}]
        msg = {"jsonrpc": "2.0", "id": 3, "result": {"content": [], "structuredContent": {"results": rows}}}
        out = cp.rewrite_result(msg, 5, "bill")
        self.assertEqual([r["docid"] for r in out["result"]["structuredContent"]["results"]], ["#c"])
        self.assertNotIn("private", out["result"]["content"][0]["text"])

    def test_errors_pass_through(self):
        msg = {"jsonrpc": "2.0", "id": 1, "error": {"code": -1, "message": "no"}}
        self.assertEqual(cp.rewrite_result(dict(msg), 5, "x"), msg)


class Stream(unittest.TestCase):
    def test_event_stream_with_keepalives(self):
        raw = b': keepalive\n\n: keepalive\n\nevent: message\ndata: {"id": 1, "result": {}}\n\n'
        self.assertEqual(cp.sse_messages(raw), {"id": 1, "result": {}})

    def test_plain_json(self):
        self.assertEqual(cp.sse_messages(b'{"id": 2}'), {"id": 2})

    def test_only_query_calls_are_touched(self):
        self.assertTrue(cp.is_query_call({"method": "tools/call", "params": {"name": "query"}}))
        self.assertFalse(cp.is_query_call({"method": "tools/call", "params": {"name": "get"}}))
        self.assertFalse(cp.is_query_call({"method": "tools/list"}))


class BadShapes(unittest.TestCase):
    """Malformed requests get a plain answer instead of a traceback in the log."""

    def test_params_that_are_not_an_object_are_not_ours(self):
        for params in ([1, 2], "text", 7, None):
            m = {"method": "tools/call", "params": params}
            self.assertFalse(cp.is_memory_call(m), params)
            self.assertFalse(cp.is_query_call(m), params)

    def test_a_bad_content_length_gets_a_400(self):
        import socket
        import threading
        from http.server import ThreadingHTTPServer
        srv = ThreadingHTTPServer(("127.0.0.1", 0), cp.Proxy)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.server_close)
        self.addCleanup(srv.shutdown)
        for length in ("abc", "-5", "99999999999"):
            with socket.create_connection(srv.server_address, timeout=10) as c:
                c.sendall(("POST /mcp HTTP/1.1\r\nHost: x\r\nContent-Length: %s\r\n\r\n" % length).encode())
                head = c.recv(4096).decode()
            self.assertTrue(head.startswith("HTTP/1.1 400"), (length, head[:60]))


if __name__ == "__main__":
    unittest.main()
