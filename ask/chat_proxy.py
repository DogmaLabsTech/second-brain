"""The island's search mix for every chat: a thin go-between in front of qmd's search server.

Claude, Codex and Gemini chats reach the brain through the `brain` MCP server at localhost:8181. They used to
get qmd as it is: their own words only. This listens on 8181 instead, hands everything to qmd (now on 8182)
untouched, except a `query` tool call, which gets what `brain ask` does (ask.search, docs/checkup.md):
  - the notes' words for <user>'s words (ask/synonyms.tsv) as one more meaning-search line;
  - a plain `query` (no `searches`) becomes the island's key words + question lines, rerank off, instead of
    qmd's own expansion (40-70 s a question here, 2026-10-18);
  - newer notes win close calls (ask.newer_first): twice the results are asked for, re-sorted, cut back.
`get`, `multi_get`, `status`, the REST /query and /health go straight through. If anything in the rewrite
fails, the original call is sent as it was. Python standard library only; nothing leaves this computer.

  python3 -I ask/chat_proxy.py [--port 8181] [--upstream http://localhost:8182]
"""
import http.client
import json
import os
import socket
import sys
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ask  # noqa: E402
from expand import expanded_document, extra_words  # noqa: E402

MAX_SEARCHES = 10   # qmd's own limit on sub-queries
HOP = {"connection", "keep-alive", "transfer-encoding", "content-length", "host", "accept-encoding"}


# ---------- the rewrite (no network; tested in ask/test_chat_proxy.py) ----------

def rewrite_args(args):
    """A `query` call's arguments -> (new arguments, the limit the caller wanted)."""
    args = dict(args)
    want = int(args.get("limit") or 10)
    if args.get("query") and not args.get("searches"):
        q = str(args.pop("query"))
        args["searches"] = [dict(zip(("type", "query"), l.split(": ", 1))) for l in expanded_document(q).splitlines()]
        args.setdefault("rerank", False)
    searches = [dict(s) for s in args.get("searches") or []]
    vec = next((s["query"] for s in searches if s.get("type") == "vec"), None)
    said = " ".join(s.get("query", "") for s in searches if s.get("type") in ("lex", "vec"))
    words = [w for w in extra_words(said) if w.lower() not in said.lower()]
    base = vec or said
    line = f"{base} {' '.join(words)}".strip()
    if words and len(searches) < MAX_SEARCHES and all(s.get("query") != line for s in searches):
        searches.append({"type": "vec", "query": line})
    args["searches"] = searches
    if ask.NEWER_DAYS > 0:
        args["limit"] = want * 2
    return args, want


def summary(results, query):
    """qmd's text summary (formatSearchSummary), for the re-sorted list."""
    if not results:
        return f'No results found for "{query}"'
    lines = [f'Found {len(results)} result{"" if len(results) == 1 else "s"} for "{query}":\n']
    lines += [f"{r['docid']} {round(r['score'] * 100)}% {r['file']} - {r['title']}" for r in results]
    return "\n".join(lines)


def newer_first(results, want):
    """Re-sort qmd's results the island's way (ask.newer_first) and keep `want`. Scores shown stay qmd's."""
    hits = [{"path": ask.real_path("qmd://" + r["file"]), "score": r.get("score", 0), "r": r} for r in results]
    return [h["r"] for h in ask.newer_first(hits)][:want]


def rewrite_result(msg, want, query):
    res = msg.get("result") or {}
    sc = res.get("structuredContent") or {}
    if "results" not in sc:
        return msg
    sc["results"] = newer_first(sc["results"], want) if ask.NEWER_DAYS > 0 else sc["results"][:want]
    res["content"] = [{"type": "text", "text": summary(sc["results"], query)}]
    return msg


def primary(searches):
    return (next((s["query"] for s in searches if s.get("type") == "lex"), None)
            or next((s["query"] for s in searches if s.get("type") == "vec"), None)
            or (searches[0]["query"] if searches else ""))


def is_query_call(m):
    return (isinstance(m, dict) and m.get("method") == "tools/call"
            and (m.get("params") or {}).get("name") == "query")


# ---------- the server ----------

def sse_messages(raw):
    """JSON-RPC messages out of a JSON or an event-stream body."""
    text = raw.decode()
    if text.lstrip().startswith("{") or text.lstrip().startswith("["):
        return json.loads(text)
    out, data = [], []
    for line in text.splitlines() + [""]:
        if line.startswith("data:"):
            data.append(line[5:].lstrip())
        elif not line and data:
            out.append(json.loads("\n".join(data)))
            data = []
    return out[0] if len(out) == 1 else out


class Proxy(BaseHTTPRequestHandler):
    upstream = urllib.parse.urlsplit("http://localhost:8182")
    protocol_version = "HTTP/1.1"

    def log_request(self, *a):
        """No line per request (journald gets only errors): the default log_message still says every error."""
        return None

    def _send_upstream(self, body, headers=None):
        conn = http.client.HTTPConnection(self.upstream.hostname, self.upstream.port, timeout=600)
        h = {k: v for k, v in self.headers.items() if k.lower() not in HOP}
        h["Host"] = self.headers.get("Host") or f"localhost:{self.upstream.port}"   # qmd checks it is local
        h.update(headers or {})
        if body is not None:
            h["Content-Length"] = str(len(body))
        conn.request(self.command, self.path, body=body, headers=h)
        return conn, conn.getresponse()

    def _relay(self, body):
        """Straight through, streamed (event-stream keepalives arrive as they come)."""
        conn, resp = self._send_upstream(body)
        try:
            self.send_response(resp.status, resp.reason)
            for k, v in resp.getheaders():
                if k.lower() not in HOP:
                    self.send_header(k, v)
            self.send_header("Transfer-Encoding", "chunked")
            self.send_header("Connection", "close")
            self.end_headers()
            while chunk := resp.read1(65536):
                self.wfile.write(b"%x\r\n%s\r\n" % (len(chunk), chunk))
                self.wfile.flush()
            self.wfile.write(b"0\r\n\r\n")
        finally:
            conn.close()
        self.close_connection = True

    def _query(self, msg):
        """A query call (or a batch holding one): rewrite, ask qmd, re-sort, answer as JSON or event-stream."""
        batch = msg if isinstance(msg, list) else [msg]
        plan = {}
        for m in batch:
            if is_query_call(m):
                new, want = rewrite_args(m["params"].get("arguments") or {})
                m["params"]["arguments"] = new
                plan[json.dumps(m.get("id"))] = (want, primary(new["searches"]))
        body = json.dumps(msg).encode()
        conn, resp = self._send_upstream(body, {"Accept": "application/json, text/event-stream"})
        try:
            raw, status, ctype = resp.read(), resp.status, resp.getheader("Content-Type", "")
        finally:
            conn.close()
        if status != 200:
            return self._reply(status, ctype, raw)
        out = sse_messages(raw)
        for m in out if isinstance(out, list) else [out]:
            key = json.dumps(m.get("id"))
            if key in plan:
                rewrite_result(m, *plan[key])
        data = json.dumps(out).encode()
        if "application/json" in (self.headers.get("Accept") or "application/json"):
            return self._reply(200, "application/json", data)
        return self._reply(200, "text/event-stream", b"event: message\ndata: " + data + b"\n\n")

    def _reply(self, status, ctype, data):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _handle(self):
        n = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(n) if n else (None if self.command in ("GET", "HEAD", "DELETE") else b"")
        try:
            if self.command == "POST" and self.path.split("?")[0] == "/mcp" and body:
                msg = json.loads(body)
                if any(is_query_call(m) for m in (msg if isinstance(msg, list) else [msg])):
                    try:
                        return self._query(json.loads(body))
                    except (ValueError, KeyError, TypeError, AttributeError) as why:
                        print(f"query rewrite failed, sent as it was: {why}", file=sys.stderr)
            return self._relay(body)
        except ValueError:
            return self._relay(body)
        except (ConnectionError, OSError, http.client.HTTPException) as why:
            print(f"search server failed, answering 502: {why}", file=sys.stderr)
            try:
                self._reply(502, "application/json", json.dumps({"error": f"search server: {why}"}).encode())
            except OSError as gone:
                print(f"could not send the 502 (the caller hung up): {gone}", file=sys.stderr)

    do_GET = do_POST = do_DELETE = do_HEAD = do_OPTIONS = do_PUT = _handle


class V6(ThreadingHTTPServer):
    address_family = socket.AF_INET6


def serve(port, upstream):
    Proxy.upstream = urllib.parse.urlsplit(upstream)
    servers = [ThreadingHTTPServer(("127.0.0.1", port), Proxy)]
    try:   # "localhost" may be ::1 first (Claude's MCP client); this computer only either way
        servers.append(V6(("::1", port), Proxy))
    except OSError as why:
        print(f"no listener on ::1 (IPv4 only): {why}", file=sys.stderr)
    for s in servers[1:]:
        threading.Thread(target=s.serve_forever, daemon=True).start()
    print(f"chat search mix on :{port} -> {upstream}", file=sys.stderr)
    servers[0].serve_forever()


if __name__ == "__main__":
    a = sys.argv[1:]
    serve(int(a[a.index("--port") + 1]) if "--port" in a else 8181,
          a[a.index("--upstream") + 1] if "--upstream" in a else "http://localhost:8182")
