"""The search record: one private line for every search an agent makes against the brain, for the Deck.

  ~/.local/state/second-brain/searches.jsonl   one line per search (file mode 600, folder 700)

Chats' `query` calls through the chat door (ask/chat_proxy.py, localhost:8181) are "from": "mcp", "kind": "search";
their `get` / `multi_get` calls are a lighter "kind": "read" line (what was opened, no reply parsed). `brain search`
writes "from": "cli". A line:

  {"at", "from", "kind", "client", "q", "searches": [{"type", "query"}], "intent", "collections",
   "results": [{"path", "collection", "score"}], "ms"}

`client` says who searched: the MCP client's name and version (from its `initialize`), the program's process
number, name and folder (looked up from the connection, since qmd has no session ids). Nothing else from the
request is kept: no headers, so no auth. The file keeps the last KEEP_LINES lines and KEEP_DAYS days. Recording
never breaks a search: any failure is one line on stderr. Python standard library only.
"""
import fcntl
import json
import os
import sys
import threading
import time

STATE = os.path.expanduser(os.environ.get("BRAIN_STATE", "~/.local/state/second-brain"))
SEARCHES = os.path.join(STATE, "searches.jsonl")
KEEP_LINES = 5000
KEEP_DAYS = 30
TRIM_BYTES = 10 * 1024 * 1024   # 5,000 lines of ten results is about 6 MB; past this the file is trimmed
SEARCH_TOOLS = ("query",)
READ_TOOLS = ("get", "multi_get")
HOME = os.path.expanduser("~")
RECENT = []   # the programs found lately, looked at first (a chat calls many times; a full look takes ~30 ms)


# ---------- the lines (no I/O; tested in ask/test_searchlog.py) ----------

def _now():
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def _collection(file):
    """qmd://computer/system/x.md or computer/system/x.md -> computer"""
    return file.removeprefix("qmd://").split("/", 1)[0] if file else None


def first_query(args):
    """What was asked, in one line: the intent, else the first meaning search, else the first word search."""
    searches = args.get("searches") or []
    return (args.get("intent")
            or next((s.get("query") for s in searches if s.get("type") == "vec"), None)
            or next((s.get("query") for s in searches if s.get("type") == "lex"), None)
            or (searches[0].get("query") if searches else None)
            or args.get("query") or "")


def searches_of(args):
    if args.get("searches"):
        return [{"type": s.get("type"), "query": s.get("query")} for s in args["searches"] if isinstance(s, dict)]
    return [{"type": "plain", "query": args["query"]}] if args.get("query") else []


def results_of(reply, real_path=lambda f: f):
    """Paths and scores out of a `query` tool reply (a JSON-RPC message)."""
    sc = ((reply or {}).get("result") or {}).get("structuredContent") or {}
    return [{"path": real_path("qmd://" + r["file"]) if r.get("file") else None, "collection": _collection(r.get("file")),
             "score": round(float(r.get("score") or 0), 3)} for r in sc.get("results") or []]


def search_line(args, reply, client, ms, real_path=lambda f: f):
    """A chat's `query` call (its own arguments, before the chat door adds anything) and the reply it got."""
    return {"at": _now(), "from": "mcp", "kind": "search", "client": client, "q": first_query(args),
            "searches": searches_of(args), "intent": args.get("intent"), "collections": args.get("collections") or [],
            "results": results_of(reply, real_path), "ms": ms}


def read_line(tool, args, client, ms):
    """A chat's `get` / `multi_get` call: what it opened (the arguments only, the reply is not read)."""
    what = args.get("file") or args.get("pattern") or ""
    return {"at": _now(), "from": "mcp", "kind": "read", "client": client, "q": f"{tool} {what}".strip(),
            "searches": [], "intent": None, "collections": [], "results": [{"path": what, "collection": _collection(what),
                                                                            "score": None}] if what else [], "ms": ms}


def cli_line(q, searches, hits, ms):
    """`brain search`: the question, the search lines it sent and the notes it printed."""
    return {"at": _now(), "from": "cli", "kind": "search", "client": {"name": "brain search", "pid": os.getppid()},
            "q": q, "searches": searches, "intent": None, "collections": [],
            "results": [{"path": h.get("path"), "collection": _collection(h.get("file")),
                         "score": round(float(h.get("score") or 0), 3)} for h in hits], "ms": ms}


def calls(msg):
    """(tool name, arguments, id) for each search or read tool call in a JSON-RPC message or batch."""
    out = []
    for m in msg if isinstance(msg, list) else [msg]:
        if isinstance(m, dict) and m.get("method") == "tools/call":
            p = m.get("params") or {}
            if p.get("name") in SEARCH_TOOLS + READ_TOOLS:
                out.append((p["name"], dict(p.get("arguments") or {}), m.get("id")))
    return out


def client_info(msg):
    """name/version from an `initialize` message (or a batch holding one), else None."""
    for m in msg if isinstance(msg, list) else [msg]:
        if isinstance(m, dict) and m.get("method") == "initialize":
            ci = (m.get("params") or {}).get("clientInfo") or {}
            return {"name": str(ci.get("name") or "")[:80] or None, "version": str(ci.get("version") or "")[:40] or None}
    return None


# ---------- the file ----------

def _too_old(line, cutoff):
    try:
        return json.loads(line).get("at", "") < cutoff
    except ValueError:
        return True


def trim(path=None, keep_lines=None, keep_days=None):
    """Keep the last `keep_lines` lines no older than `keep_days`. Call it holding the lock."""
    path, keep_lines, keep_days = path or SEARCHES, keep_lines or KEEP_LINES, keep_days or KEEP_DAYS
    cutoff = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(time.time() - keep_days * 86400))
    with open(path, encoding="utf-8", errors="replace") as f:
        lines = f.readlines()
    keep = [l for l in lines[-keep_lines:] if l.strip() and not _too_old(l, cutoff)]
    if len(keep) == len(lines):
        return
    tmp = path + ".trim"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.writelines(keep)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _needs_trim(path):
    if os.path.getsize(path) > TRIM_BYTES:
        return True
    with open(path, encoding="utf-8", errors="replace") as f:
        first = f.readline()
    cutoff = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(time.time() - KEEP_DAYS * 86400))
    return bool(first.strip()) and _too_old(first, cutoff)


def record(line, path=None):
    """Append one line (and trim when the file is too big or its first line too old). Never raises."""
    path = path or SEARCHES
    try:
        folder = os.path.dirname(path)
        os.makedirs(folder, mode=0o700, exist_ok=True)
        os.chmod(folder, 0o700)
        lock = os.open(path + ".lock", os.O_WRONLY | os.O_CREAT, 0o600)   # a lock file, so a trim's swap loses no line
        try:
            fcntl.flock(lock, fcntl.LOCK_EX)
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
            with os.fdopen(fd, "a", encoding="utf-8") as f:
                f.write(json.dumps(line, ensure_ascii=False) + "\n")
            if _needs_trim(path):
                trim(path)
        finally:
            os.close(lock)
    except Exception as why:  # noqa: BLE001  a lost line is said, the search goes on
        print(f"searchlog: could not record the search: {why}", file=sys.stderr)


# ---------- who is calling (the program at the other end of a loopback connection) ----------

def _socket_inode(peer_port, our_port):
    """The inode of the caller's end of a loopback connection, from /proc/net/tcp and tcp6."""
    for table in ("/proc/net/tcp", "/proc/net/tcp6"):
        try:
            with open(table) as f:
                next(f)
                for row in f:
                    cols = row.split()
                    if (int(cols[1].rsplit(":", 1)[1], 16) == peer_port
                            and int(cols[2].rsplit(":", 1)[1], 16) == our_port):
                        return cols[9]
        except (OSError, IndexError, ValueError, StopIteration):
            continue
    return None


def _holds(pid, target):
    try:
        fds = f"/proc/{pid}/fd"
        return any(os.readlink(f"{fds}/{fd}") == target for fd in os.listdir(fds))
    except OSError:
        return False


def _pid_of(inode):
    target = f"socket:[{inode}]"
    uid = os.getuid()
    for pid in list(RECENT):
        if _holds(pid, target):
            return int(pid)
    for pid in os.listdir("/proc"):
        try:
            if pid.isdigit() and pid not in RECENT and os.stat(f"/proc/{pid}").st_uid == uid and _holds(pid, target):
                RECENT.insert(0, pid)
                del RECENT[20:]
                return int(pid)
        except OSError:
            continue
    return None


def _program(pid):
    out = {"pid": pid}
    try:
        with open(f"/proc/{pid}/comm") as f:
            out["program"] = f.read().strip()
        cwd = os.readlink(f"/proc/{pid}/cwd")
        out["folder"] = "~" + cwd[len(HOME):] if cwd == HOME or cwd.startswith(HOME + "/") else cwd
    except OSError:
        pass
    return out


def who(peer_port, our_port):
    """{"pid", "program", "folder"} of the program that opened this connection, or {} when it can't be told."""
    try:
        inode = _socket_inode(peer_port, our_port)
        pid = _pid_of(inode) if inode and inode != "0" else None
        return _program(pid) if pid else {}
    except Exception:  # noqa: BLE001  best effort only
        return {}


class Caller:
    """Looks up who is calling in the background while the search runs (the connection must still be open)."""

    def __init__(self, peer_port, our_port):
        self.found = {}
        self._t = threading.Thread(target=self._run, args=(peer_port, our_port), daemon=True)
        self._t.start()

    def _run(self, peer_port, our_port):
        self.found = who(peer_port, our_port)

    def result(self, wait=1.0):
        self._t.join(wait)
        return dict(self.found)
