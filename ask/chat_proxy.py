"""The island's search mix for every chat: a thin go-between in front of qmd's search server.

Claude, Codex and Gemini chats reach the brain through the `brain` MCP server at localhost:8181. They used to
get qmd as it is: their own words only. This listens on 8181 instead, hands everything to qmd (now on 8182)
untouched, except a `query` tool call, which gets what `brain ask` does (ask.search, docs/checkup.md):
  - the notes' words for <user>'s words (ask/synonyms.tsv) as one more meaning-search line;
  - a plain `query` (no `searches`) becomes the island's key words + question lines, rerank off, instead of
    qmd's own expansion (40-70 s a question here, 2026-10-18);
  - newer notes win close calls (ask.newer_first): twice the results are asked for, re-sorted, cut back.
It also adds one tool of its own, `memory` (ask/memory.py: the agent memory store's rules and lessons for a
project): `tools/list` gets it added to qmd's list, and its `tools/call` is answered here, never sent to qmd. If
it fails, the chat gets an MCP error result; the other tools are not touched. (A JSON-RPC batch goes as before.)
`status` and /health go straight through. If anything in the rewrite fails, the original call is sent as it was.
Private notes (~/brain/private, index/index.yml `private`) never reach a chat (one brain, 2026-10-29): `get`,
`multi_get`, `resources/read`, `query` and the REST /query and /search answers are read whole here and every
private note is left out (scrub_private); if such an answer can't be read, the caller gets an error, not the answer. Python standard library only; nothing leaves this computer.

It also keeps the search record (ask/searchlog.py, ~/.local/state/second-brain/searches.jsonl): one line per
`query` (what the chat asked, before the mix, and the notes it got back) and per `get` / `multi_get`, with who
asked. The line is written after the reply has gone out; if writing it fails, the search is not touched.

  python3 -I ask/chat_proxy.py [--port 8181] [--upstream http://localhost:8182]
"""
import copy
import http.client
import json
import os
import re
import socket
import sys
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ask  # noqa: E402
import memory  # noqa: E402
import searchlog  # noqa: E402
from expand import expanded_document, extra_words  # noqa: E402

MAX_SEARCHES = 10   # qmd's own limit on sub-queries
HOP = {"connection", "keep-alive", "transfer-encoding", "content-length", "host", "accept-encoding"}
CLIENTS = {}   # process number -> the MCP client's name and version, from its `initialize`
CLIENTS_MAX = 500

MEMORY_TOOL = {
    "name": "memory",
    "title": "Agent memory: rules and lessons for a project",
    "description": (
        "Rules and lessons for working on one of <user>'s code projects, from the agent memory store. Call it when you "
        "start a task in a repo, and before you change something you are unsure about. Give `repo` (the project's "
        "folder name in ~/projects/, case included, e.g. second-brain) and `task` in plain words; name "
        "exact things when you have them (a file name, a port, error text in quotes, a function name). You get the "
        "project's notes (pinned first, then the best matches, then its newest) and the all-projects notes that are "
        "pinned or match your task, each as its summary line word for word, its kind (rule or lesson), project and "
        "path, so you can read the full note with your file tools. "
        "At most 2,000 tokens; it says how many notes did not fit. (local-only) marks a note whose text the names "
        "filter was not sure about."),
    "inputSchema": {
        "type": "object",
        "properties": {
            "repo": {"type": "string", "description": "The project's folder name, e.g. second-brain"},
            "task": {"type": "string", "description": "The task in plain words (optional: without it, only pinned and the project's newest notes)"},
        },
        "required": ["repo"],
    },
}


# ---------- the memory tool (answered here; tested in ask/test_memory_tool.py) ----------

def _params(m):
    """A JSON-RPC message's params when it is an object, else {} (a list or a string there is a bad request that
    qmd answers itself, not a reason to crash this handler)."""
    p = m.get("params")
    return p if isinstance(p, dict) else {}


def is_memory_call(m):
    return (isinstance(m, dict) and m.get("method") == "tools/call"
            and _params(m).get("name") == MEMORY_TOOL["name"])


def is_tools_list(m):
    return isinstance(m, dict) and m.get("method") == "tools/list"


def memory_result(args, url):
    """The `memory` tool's MCP result; a failure is an error result, never an exception."""
    try:
        args = args if isinstance(args, dict) else {}
        out = memory.find(args.get("repo"), args.get("task"), url=url)
        return {"content": [{"type": "text", "text": out["text"]}],
                "structuredContent": {k: out[k] for k in ("notes", "left_out", "fallback")}}
    except Exception as why:  # noqa: BLE001  a bad call or a broken store: the chat is told, nothing else breaks
        return {"content": [{"type": "text", "text": f"memory: {why}"}], "isError": True}


def add_memory_tool(msg):
    """qmd's tools/list reply with the memory tool added (once)."""
    tools = (msg.get("result") or {}).get("tools")
    if isinstance(tools, list) and not any(t.get("name") == MEMORY_TOOL["name"] for t in tools):
        tools.append(copy.deepcopy(MEMORY_TOOL))
    return msg


# ---------- the rewrite (no network; tested in ask/test_chat_proxy.py) ----------

def _plain_query_to_searches(args):
    """A plain `query` (no `searches`) becomes the island's key words + question lines, rerank off."""
    if args.get("query") and not args.get("searches"):
        q = str(args.pop("query"))
        args["searches"] = [dict(zip(("type", "query"), l.split(": ", 1))) for l in expanded_document(q).splitlines()]
        args.setdefault("rerank", False)


def _notes_words_line(searches):
    """The one more meaning-search line with the notes' words for <user>'s words, or None when none are new."""
    vec = next((s["query"] for s in searches if s.get("type") == "vec"), None)
    said = " ".join(s.get("query", "") for s in searches if s.get("type") in ("lex", "vec"))
    words = [w for w in extra_words(said) if w.lower() not in said.lower()]
    line = f"{vec or said} {' '.join(words)}".strip()
    if words and len(searches) < MAX_SEARCHES and all(s.get("query") != line for s in searches):
        return line
    return None


def rewrite_args(args):
    """A `query` call's arguments -> (new arguments, the limit the caller wanted)."""
    args = dict(args)
    want = int(args.get("limit") or 10)
    _plain_query_to_searches(args)
    searches = [dict(s) for s in args.get("searches") or []]
    line = _notes_words_line(searches)
    if line:
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


def online_ok(r):
    """False for a result from the private section (index/index.yml `private`): chats are online models, so those
    notes never reach them; `brain ask` reads them with the local writer only (ask.local_only)."""
    return str(r.get("file") or "").removeprefix("qmd://").split("/", 1)[0] != "private"


PRIVATE_URI = "qmd://private/"
PRIVATE_NAME = re.compile(r"(?:qmd://)?\bprivate/[^\s'\"]*")
LEFT_OUT = "(A private note was left out: private notes stay on this computer.)"


def _private_item(item):
    """A `resource` item (get, multi_get) or a resources/read entry that holds a private note."""
    res = item.get("resource") if item.get("type") == "resource" else item
    return isinstance(res, dict) and str(res.get("uri") or "").startswith(PRIVATE_URI)


def _scrub_text(text):
    """A text item without the lines that name a private note (multi_get's skip notes, get's "did you mean")."""
    lines = str(text).split("\n")
    kept = [l for l in lines if not PRIVATE_NAME.search(l)]
    return "\n".join(kept) if len(kept) == len(lines) else "\n".join(kept + [LEFT_OUT])


def scrub_private(msg):
    """One JSON-RPC answer (or a batch) with every private note taken out, in place; returns it."""
    for m in msg if isinstance(msg, list) else [msg]:
        res = m.get("result") if isinstance(m, dict) else None
        if not isinstance(res, dict):
            continue
        for key in ("content", "contents"):
            if isinstance(res.get(key), list):
                out = []
                for item in res[key]:
                    if not isinstance(item, dict):
                        out.append(item)
                    elif _private_item(item):
                        out.append({"type": "text", "text": LEFT_OUT} if key == "content" else
                                   {"uri": "qmd://left-out", "text": LEFT_OUT})
                    elif item.get("type") == "text":
                        out.append(dict(item, text=_scrub_text(item.get("text", ""))))
                    else:
                        out.append(item)
                res[key] = out
        sc = res.get("structuredContent")
        if isinstance(sc, dict) and isinstance(sc.get("results"), list):
            sc["results"] = [r for r in sc["results"] if online_ok(r)]
    return msg


def scrub_rest(data):
    """The REST /query or /search answer ({"results": [...]}) without private notes."""
    if isinstance(data, dict) and isinstance(data.get("results"), list):
        data["results"] = [r for r in data["results"] if online_ok(r)]
    return data


def needs_guard(command, path, body):
    """True when this request's answer may hold a note's text and must be read whole (scrub_private / scrub_rest)."""
    if command != "POST":
        return False
    where = path.split("?")[0]
    if where in ("/query", "/search"):
        return True
    if where != "/mcp" or not body:
        return False
    try:
        msg = json.loads(body)
    except ValueError:
        return True   # can't tell what it asks: read the answer whole
    return any(isinstance(m, dict) and m.get("method") in ("tools/call", "resources/read")
               for m in (msg if isinstance(msg, list) else [msg]))


def rewrite_result(msg, want, query):
    res = msg.get("result") or {}
    sc = res.get("structuredContent") or {}
    if "results" not in sc:
        return msg
    sc["results"] = [r for r in sc["results"] if online_ok(r)]
    sc["results"] = newer_first(sc["results"], want) if ask.NEWER_DAYS > 0 else sc["results"][:want]
    res["content"] = [{"type": "text", "text": summary(sc["results"], query)}]
    return msg


def primary(searches):
    return (next((s["query"] for s in searches if s.get("type") == "lex"), None)
            or next((s["query"] for s in searches if s.get("type") == "vec"), None)
            or (searches[0]["query"] if searches else ""))


def is_query_call(m):
    return (isinstance(m, dict) and m.get("method") == "tools/call"
            and _params(m).get("name") == "query")


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


class BadRequest(Exception):
    """The request itself is broken (a Content-Length that is not a number, or absurdly large): answer 400."""


MAX_BODY = 8_000_000   # a search request is a few hundred bytes; this only stops a runaway Content-Length


class CallerGone(Exception):
    """Writing to the caller failed (it closed the stream or cancelled the search): not the search server's fault."""


class Proxy(BaseHTTPRequestHandler):
    upstream = urllib.parse.urlsplit("http://localhost:8182")
    protocol_version = "HTTP/1.1"
    timeout = 120   # a caller that stops sending mid-request frees its handler thread (upstream waits are not limited by this)

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
            self._to_caller(self.end_headers)
            while chunk := resp.read1(65536):
                self._to_caller(self._write_chunk, chunk)
            self._know_caller()
            self._to_caller(self.wfile.write, b"0\r\n\r\n")
        finally:
            conn.close()
        self.close_connection = True

    def _guarded(self, body):
        """Like _relay, but the answer is read whole first. With no private note in it, it goes back byte for byte
        with qmd's own headers; otherwise every private note is taken out (scrub_private / scrub_rest)."""
        mcp = self.path.split("?")[0] == "/mcp"
        conn, resp = self._send_upstream(body)
        try:
            raw, status, headers = resp.read(), resp.status, resp.getheaders()
        finally:
            conn.close()
        self._know_caller()
        if b"private/" not in raw:
            return self._reply_raw(status, resp.reason, headers, raw)
        if status != 200:
            return self._reply(502, "application/json", json.dumps({"error": "left out: it named a private note"}).encode())
        try:
            msgs = sse_messages(raw) if mcp else json.loads(raw)
            out = json.dumps(scrub_private(msgs) if mcp else scrub_rest(msgs)).encode()
        except (ValueError, TypeError, AttributeError) as why:
            print(f"private filter could not read the answer, not sent: {type(why).__name__}", file=sys.stderr)
            return self._reply(502, "application/json", json.dumps({"error": "search server answer not readable"}).encode())
        ctype = dict((k.lower(), v) for k, v in headers).get("content-type", "application/json")
        if mcp and "text/event-stream" in ctype:
            self._reply(200, "text/event-stream", b"event: message\ndata: " + out + b"\n\n")
        else:
            self._reply(200, "application/json", out)

    def _reply_raw(self, status, reason, headers, data):
        self.send_response(status, reason)
        for k, v in headers:
            if k.lower() not in HOP and k.lower() != "content-length":
                self.send_header(k, v)
        self.send_header("Content-Length", str(len(data)))
        self._to_caller(self.end_headers)
        self._to_caller(self.wfile.write, data)

    def _write_chunk(self, chunk):
        self.wfile.write(b"%x\r\n%s\r\n" % (len(chunk), chunk))
        self.wfile.flush()

    @staticmethod
    def _to_caller(write, *args):
        """Run a write to the caller; a failure there is CallerGone, so it is not taken for an upstream failure."""
        try:
            write(*args)
        except OSError as why:
            raise CallerGone(why) from why

    def _query(self, msg):
        """A query call (or a batch holding one): rewrite, ask qmd, re-sort, answer as JSON or event-stream."""
        batch = msg if isinstance(msg, list) else [msg]
        plan, asked = {}, {}
        for m in batch:
            if is_query_call(m):
                asked[json.dumps(m.get("id"))] = copy.deepcopy(m["params"].get("arguments") or {})
                new, want = rewrite_args(m["params"].get("arguments") or {})
                m["params"]["arguments"] = new
                plan[json.dumps(m.get("id"))] = (want, primary(new["searches"]))
        body = json.dumps(msg).encode()
        conn, resp = self._send_upstream(body, {"Accept": "application/json, text/event-stream"})
        try:
            raw, status, ctype = resp.read(), resp.status, resp.getheader("Content-Type", "")
        finally:
            conn.close()
        self._know_caller()
        if status != 200:
            self._reply(status, ctype, raw)
            return self._record_searches(asked, {})
        out = sse_messages(raw)
        replies = {}
        for m in out if isinstance(out, list) else [out]:
            key = json.dumps(m.get("id"))
            if key in plan:
                rewrite_result(m, *plan[key])
                replies[key] = m
        scrub_private(out)   # a batch may hold a get or multi_get next to the query
        data = json.dumps(out).encode()
        if "application/json" in (self.headers.get("Accept") or "application/json"):
            self._reply(200, "application/json", data)
        else:
            self._reply(200, "text/event-stream", b"event: message\ndata: " + data + b"\n\n")
        self._record_searches(asked, replies)

    def _answer(self, out):
        """A JSON-RPC reply, as JSON or as an event-stream (what the caller accepts)."""
        data = json.dumps(out).encode()
        if "application/json" in (self.headers.get("Accept") or "application/json"):
            self._reply(200, "application/json", data)
        else:
            self._reply(200, "text/event-stream", b"event: message\ndata: " + data + b"\n\n")

    def _memory(self, msg):
        url = f"{self.upstream.scheme}://{self.upstream.netloc}"
        self._answer({"jsonrpc": "2.0", "id": msg.get("id"),
                      "result": memory_result((msg.get("params") or {}).get("arguments"), url)})

    def _tools_list(self, body):
        """qmd's tool list with the memory tool added, in qmd's own format and headers; anything unexpected goes
        back as qmd sent it."""
        conn, resp = self._send_upstream(body)
        try:
            raw, status, headers = resp.read(), resp.status, resp.getheaders()
        finally:
            conn.close()
        try:
            out = sse_messages(raw) if status == 200 else None
        except ValueError:
            out = None
        if isinstance(out, dict):
            data = json.dumps(add_memory_tool(out)).encode()
            stream = "text/event-stream" in dict((k.lower(), v) for k, v in headers).get("content-type", "")
            raw = b"event: message\ndata: " + data + b"\n\n" if stream else data
        self.send_response(status)
        for k, v in headers:
            if k.lower() not in HOP:
                self.send_header(k, v)
        self.send_header("Content-Length", str(len(raw)))
        self._to_caller(self.end_headers)
        self._to_caller(self.wfile.write, raw)

    def _own_post(self, body):
        """The parsed /mcp message when this POST is one memory call or one tools/list, else None."""
        if self.command == "POST" and self.path.split("?")[0] == "/mcp" and body:
            msg = json.loads(body)
            if is_memory_call(msg) or is_tools_list(msg):
                return msg
        return None

    # ---------- the search record (never breaks a search) ----------

    def _start_record(self, body):
        """Note the search / read calls and an `initialize` in this request; start finding who sent it."""
        self._rec = None
        try:
            if self.command != "POST" or not body or self.path.split("?")[0] != "/mcp":
                return
            msg = json.loads(body)
            found, init = searchlog.calls(msg), searchlog.client_info(msg)
            if found or init:
                caller = searchlog.Caller(self.client_address[1], self.server.server_address[1])
                self._rec = {"calls": found, "init": init, "caller": caller, "t0": time.monotonic()}
        except Exception:  # noqa: BLE001  not JSON, or no socket (tests): nothing to record
            self._rec = None

    def _know_caller(self):
        """Let the look-up of who is calling finish (at most 0.2 s, mostly 0) before the caller can hang up."""
        if getattr(self, "_rec", None):
            self._rec["caller"].result(0.2)

    def _client(self):
        rec = self._rec
        found = rec["caller"].result()
        if rec["init"] and found.get("pid"):
            if len(CLIENTS) >= CLIENTS_MAX:
                CLIENTS.clear()
            CLIENTS[found["pid"]] = rec["init"]
        info = rec["init"] or CLIENTS.get(found.get("pid")) or {"name": None, "version": None}
        return {**info, **found}

    def _ms(self):
        return round((time.monotonic() - self._rec["t0"]) * 1000)

    def _record_searches(self, asked, replies):
        try:
            if not getattr(self, "_rec", None):
                return
            client, ms = self._client(), self._ms()
            for key, args in asked.items():
                searchlog.record(searchlog.search_line(args, replies.get(key), client, ms, ask.real_path))
        except Exception as why:  # noqa: BLE001
            print(f"searchlog: {why}", file=sys.stderr)

    def _record_relayed(self):
        """After a straight-through call: remember an `initialize`, write a line per read (and per query call
        the mix could not rewrite: its notes are not known then)."""
        try:
            if not getattr(self, "_rec", None):
                return
            client, ms = self._client(), self._ms()
            for tool, args, _ in self._rec["calls"]:
                line = (searchlog.search_line(args, None, client, ms) if tool in searchlog.SEARCH_TOOLS
                        else searchlog.read_line(tool, args, client, ms))
                searchlog.record(line)
        except Exception as why:  # noqa: BLE001
            print(f"searchlog: {why}", file=sys.stderr)

    def _reply(self, status, ctype, data):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self._to_caller(self.end_headers)
        self._to_caller(self.wfile.write, data)

    def _read_body(self):
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            raise BadRequest("Content-Length is not a number") from None
        if n < 0 or n > MAX_BODY:
            raise BadRequest("Content-Length is out of range")
        return self.rfile.read(n) if n else (None if self.command in ("GET", "HEAD", "DELETE") else b"")

    def _is_query_post(self, body):
        """The parsed /mcp message when this POST holds a `query` tool call, else None."""
        if self.command == "POST" and self.path.split("?")[0] == "/mcp" and body:
            msg = json.loads(body)
            if any(is_query_call(m) for m in (msg if isinstance(msg, list) else [msg])):
                return msg
        return None

    def _handle(self):
        try:
            body = self._read_body()
        except BadRequest as why:
            self.close_connection = True
            try:
                self._reply(400, "application/json", json.dumps({"error": str(why)}).encode())
            except CallerGone:
                pass
            return
        self._start_record(body)
        try:
            own = self._own_post(body)
            if own is not None:
                return self._memory(own) if is_memory_call(own) else self._tools_list(body)
            if self._is_query_post(body) is not None:
                try:
                    return self._query(json.loads(body))
                except (ValueError, KeyError, TypeError, AttributeError) as why:
                    print(f"query rewrite failed, sent as it was: {why}", file=sys.stderr)
            self._guarded(body) if needs_guard(self.command, self.path, body) else self._relay(body)
            return self._record_relayed()
        except ValueError:
            self._guarded(body) if needs_guard(self.command, self.path, body) else self._relay(body)
            return self._record_relayed()
        except CallerGone:
            # The caller closed the stream or cancelled the search: nothing to answer, nothing wrong upstream, so
            # no log line (it would be a false "search server failed" each time).
            self.close_connection = True
        except (ConnectionError, OSError, http.client.HTTPException) as why:
            print(f"search server failed, answering 502: {why}", file=sys.stderr)
            try:
                self._reply(502, "application/json", json.dumps({"error": f"search server: {why}"}).encode())
            except CallerGone:
                self.close_connection = True   # the caller left before the 502 could reach it

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
