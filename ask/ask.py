"""brain ask: answer a question from <user>'s notes, or turn it into a job.

  python3 -I ask/ask.py "<question>" [--json] [--writer auto|local|local:<model>|haiku] [--how voice|typed]

Steps (docs and timings: README.md, docs/writer-race.md):
  1. intent (brain-decide intent) and the search run at the same time. The decider gets 2.5 s;
     when it is late or `unsure`, the jobs' own simple rules (jobs/*.json `match`) decide, else it's a question.
  2. question: top 5 notes (index/structq.py + ask/synonyms.tsv, the warm qmd server), then
     brain-decide grounded on the top 3. `no` (sure) = "I couldn't find that in your notes".
     Otherwise the writer answers from the top 4 notes, 1-3 plain sentences naming the note, and
     says "I couldn't find that in your notes" itself when they don't answer it.
  3. job:*: the job object (jobs/jobs.py build). chitchat: a short friendly line, no search.
     A decider that chose `unsure` itself (half-heard, two asks at once, no job for it), or the local decider under that
     answer's sure-bar ("reason": "below-bar"), with no job rule fitting: "Sorry, say that again?", no search.
     The agent-os jobs (remember-fix, start-job) win by their tight rule over any decider label; without their
     rule, a decider's agent-os label on a question becomes a question and on two asks "say that again".
     --how (default typed; the island can't tell yet) is how the words came, passed to agent-os.

Writers: local = Ollama (second-brain-ollama.service) qwen2.5 3B by default; haiku = `claude -p`
(Claude Haiku, tools and MCP off); auto (default) = local alone for BRAIN_HAIKU_WAIT (2 s), then Haiku
joins if needed; a good local answer within BRAIN_LOCAL_SECONDS (4 s) still wins. Every answer says who wrote it (`writer`). Private text never goes to the second decider
(brain-decide handles that); Haiku is the documented backup, and it never gets a private name: they are swapped for
[NAME1]... first (decider/names.py) and put back into the answer here, or nothing is sent.

--json prints one object, the island's contract (user.brain-island README):
  {kind, answer, sources[{path,title,snippet}], job, writer, ms} (+ timings in `steps`).
"""
import errno
import http.client
import json
import math
import os
import re
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request

sys.dont_write_bytecode = True

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "jobs"))
from expand import expanded_document  # noqa: E402
import jobs as jobslib  # noqa: E402
import asklog  # noqa: E402

HOME = os.path.expanduser("~")
BRAIN_URL = os.environ.get("BRAIN_URL", "http://localhost:8182")   # qmd itself; chats use the go-between on 8181
OLLAMA = os.environ.get("OLLAMA_HOST_URL", "127.0.0.1:11434")
DECIDE = os.path.join(ROOT, "bin", "brain-decide")
LOCAL_MODEL = os.environ.get("BRAIN_LOCAL_MODEL", "qwen2.5:3b")
LOCAL_SECONDS = float(os.environ.get("BRAIN_LOCAL_SECONDS", "4"))
HAIKU_WAIT = float(os.environ.get("BRAIN_HAIKU_WAIT", "2"))   # Haiku starts only after this, if local isn't done
HAIKU_MODEL = os.environ.get("BRAIN_HAIKU_MODEL", "claude-haiku-5-5")
DECIDER_REPO = os.path.expanduser(os.environ.get("DECIDER_REPO", "~/projects/decider"))
NAMES_NOTE = "\n\n(Some names are hidden as [NAME1], [NAME2] and so on. Write those marks exactly as they are.)"
RERANK = os.environ.get("BRAIN_RERANK", "0") == "1"   # the re-ranker re-reads the top RERANK_POOL notes
RERANK_POOL = int(os.environ.get("BRAIN_RERANK_POOL", "20"))
NEWER_DAYS = float(os.environ.get("BRAIN_NEWER_DAYS", "30"))   # 0 = no newer-first boost
INTENT_SECONDS = float(os.environ.get("BRAIN_INTENT_SECONDS", "2.5"))
NOT_FOUND = "I couldn't find that in your notes."
SAY_AGAIN = "Sorry, say that again?"
COLLECTIONS = {
    # One brain (~/brain, 2026-10-28): one collection per section. Repo guides, the desk, experiments and the
    # content library stay where they are; plans stay in ~/.claude/plans (Claude Code can't write them elsewhere).
    "brain": os.path.join(HOME, "brain"),
    "rules": os.path.join(HOME, "brain", "rules"),
    "memory": os.path.join(HOME, "brain", "agents"),
    "project-notes": os.path.join(HOME, "brain", "projects"),
    "computer": os.path.join(HOME, "brain", "computer"),
    "business": os.path.join(HOME, "brain", "business"),
    "private": os.path.join(HOME, "brain", "private"),
    "chats": os.path.join(HOME, "brain", "chats"),
    "codex": os.path.join(HOME, "brain", "chats", "codex"),
    "days": os.path.join(HOME, "brain", "days"),
    "inbox": os.path.join(HOME, "brain", "inbox"),
    "history": os.path.join(HOME, "brain", "history"),
    "plans": os.path.join(HOME, ".claude", "plans"),
    "projects": os.path.join(HOME, "projects", "Projects"),
    "experiments": os.path.join(HOME, "projects", "experiments"),
    "content": os.path.join(HOME, "projects", "assets", "content-library"),
    "hermes": os.path.join(HOME, ".hermes"),
    "agent-os": os.path.join(HOME, "agent-os"),
    "agent-os-jobs": os.path.join(HOME, "agent-os", "jobs"),
}   # keep in step with index/index.yml
MODEL_SHORT = {"qwen2.5:3b": "qwen2.5", "granite4.2:3b": "granite4.2", "gpt-oss:20b": "gpt-oss"}

SYSTEM = """You answer <user>'s question using only his notes below.
Rules:
- 1 to 3 short sentences. Plain, simple words a 5-year-old could follow. Keep names, commands and numbers exactly as the notes write them.
- Start with the title of the note that answers it, like this: "Your <title> note says ...". Use the real title from the notes; pick the note that really answers the question, not just the first one.
- If the notes don't answer the question, reply exactly: I couldn't find that in your notes.
- Never guess or add facts that are not in the notes. No lists, no markdown, no quotes around the answer."""


# ---------- search ----------

def real_path(qmd_file):
    """qmd://computer/system/x.md -> ~/brain/computer/system/x.md (qmd may lowercase paths)."""
    m = re.match(r"qmd://([^/]+)/(.*)", qmd_file)
    if not m or m.group(1) not in COLLECTIONS:
        return qmd_file
    base, rel = COLLECTIONS[m.group(1)], m.group(2)
    path = os.path.join(base, rel)
    if os.path.exists(path):
        return path
    cur = base   # walk down matching names without caring about case
    for part in rel.split("/"):
        try:
            hit = next((p for p in os.listdir(cur) if p.lower() == part.lower()), None)
        except OSError:
            hit = None
        if not hit:
            return path
        cur = os.path.join(cur, hit)
    return cur


def clean_snippet(s):
    s = re.sub(r"(?m)^\d+: ", "", s or "")
    s = re.sub(r"^@@[^@]*@@ *(\([^)]*\))?", "", s)
    s = re.sub(r"(?m)\*\*|__|`|^\s*(#+|[-*>]|\|)\s*", "", s)   # markdown marks read badly on the card
    return " ".join(s.split())[:240]


def note_date(path):
    """When a note was written: the chat notes' date in the name, else the file's last change."""
    m = re.match(r"(\d{4}-\d{2}-\d{2})-", os.path.basename(path))
    try:
        return time.mktime(time.strptime(m.group(1), "%Y-%m-%d")) if m else os.path.getmtime(path)
    except (OSError, ValueError, OverflowError):
        return 0.0


def newer_first(hits, fresh_days=NEWER_DAYS):
    """Newer notes win close calls: each hit's score is raised by up to 50% when it is new, fading
    over about a month. A clearly better old note still stays on top (qmd's scores are 1, 1/2, 1/3…)."""
    now = time.time()
    for h in hits:
        age = max(0.0, (now - note_date(h["path"])) / 86400) if h["path"].startswith("/") else 365
        h["score"] = float(h.get("score") or 0) * (1 + 0.5 * math.exp(-age / fresh_days))
    return sorted(hits, key=lambda h: -h["score"])


# An online agent (Claude, Codex, ...) that runs `brain ask` or `brain search` in a shell never gets the private
# section: its hits are dropped before anything is written or printed (one brain, 2026-10-29). Set by main() and
# ask/search_cli.py from searchlog.caller(); the island, the Deck and <user>'s own terminal keep them.
ONLINE_AGENTS = ("claude", "codex", "gemini", "opencode", "grok", "copilot", "cursor-agent")
HIDE_PRIVATE = False


def run_by_online_agent(name):
    """True when the program that ran this command (searchlog.caller) is an online agent; never raises."""
    try:
        import searchlog
        return searchlog.caller(name).get("program") in ONLINE_AGENTS
    except Exception:  # noqa: BLE001  can't tell: keep them out
        return True


def search(q, limit=5):
    doc = expanded_document(q)
    want = limit
    limit = limit * 2 if NEWER_DAYS > 0 else limit   # a wider net, so newer notes can move up
    body = {"limit": limit, "rerank": RERANK, "candidateLimit": RERANK_POOL,
            "searches": [dict(zip(("type", "query"), line.split(": ", 1))) for line in doc.splitlines()]}
    try:
        req = urllib.request.Request(BRAIN_URL + "/query", json.dumps(body).encode(),
                                     {"content-type": "application/json"})
        results = json.load(urllib.request.urlopen(req, timeout=60))["results"]
    except Exception:  # noqa: BLE001  the server is down: qmd itself (loads its models, slower)
        env = dict(os.environ, QMD_LLAMA_GPU=os.environ.get("QMD_LLAMA_GPU", "vulkan"),
                   PATH=os.path.join(HOME, ".local/share/mise/shims") + ":" + os.environ.get("PATH", ""))
        out = subprocess.run(["qmd", "query", doc, "--json", "-n", str(limit), "--no-rerank"],
                             capture_output=True, text=True, env=env, timeout=120)
        results = json.loads(out.stdout or "[]")
    hits = []
    for r in results[:limit]:
        path = real_path(r.get("file", ""))
        if HIDE_PRIVATE and path.startswith(COLLECTIONS["private"] + os.sep):
            continue
        hits.append({"path": path, "title": r.get("title") or os.path.basename(path),
                     "snippet": clean_snippet(r.get("snippet")), "line": int(r.get("line") or 1),
                     "file": r.get("file", ""), "score": r.get("score", 0)})
    if NEWER_DAYS > 0:
        hits = newer_first(hits)
    return hits[:want]


def passage(hit, chars=650):
    """The note text around the hit (more than qmd's 4-line snippet), for the writer."""
    try:
        with open(hit["path"], errors="replace") as f:
            lines = f.read().splitlines()
    except OSError:
        return hit["snippet"]
    start = max(0, hit["line"] - 3)
    text = " ".join(" ".join(lines[start:start + 40]).split())
    return text[:chars] or hit["snippet"]


def local_only(hit):
    """A note that never goes to an online model: every note in the private section (~/brain/private: finance,
    <user>'s own notes), and a memory note with `local-only: true` in its front matter (eval/memory_keep.py: the names
    filter was not sure). A memory note that can't be read counts as local-only."""
    if hit["path"].startswith(COLLECTIONS["private"] + os.sep):
        return True
    if not hit["path"].startswith(COLLECTIONS["memory"] + os.sep):
        return False
    try:
        with open(hit["path"], errors="replace") as f:
            head = f.read(4000)
    except OSError:
        return True
    m = re.match(r"---\n(.*?)\n---", head, re.S)
    return bool(m and re.search(r"^local-only:\s*true\s*$", m.group(1), re.M))


def short_path(p):
    return p.replace(HOME, "~")


def public_sources(hits):
    return [{"path": short_path(h["path"]), "title": h["title"], "snippet": h["snippet"]} for h in hits]


# ---------- deciders ----------

def decide(*args, timeout=INTENT_SECONDS):
    try:
        out = subprocess.run([DECIDE, *args], capture_output=True, text=True, timeout=timeout)
        # brain-decide's own warnings (an unreadable private.json) would be lost here; its other stderr (the
        # decider app's) might hold the question, so only its own lines are passed on
        for line in out.stderr.splitlines():
            if line.startswith("brain-decide:"):
                print(line, file=sys.stderr)
        return json.loads(out.stdout.strip().splitlines()[-1])
    except (OSError, ValueError, IndexError, subprocess.TimeoutExpired) as why:
        # the label stays "timeout" for every failure (the steps and the log show it as before); the real error is
        # said, by type only: a timeout's text holds the whole command, question and private notes included
        detail = f"after {why.timeout:g} s" if isinstance(why, subprocess.TimeoutExpired) else str(why)
        print(f"brain ask: the decider failed ({type(why).__name__} {detail})", file=sys.stderr)
        return {"label": "unsure", "confidence": 0.0, "by": "timeout"}


# ---------- the first sentence, early (--stream) ----------

EMIT = []   # set by main(--stream): prints one JSON line per event


class First:
    """Sends the answer's first sentence as soon as Haiku has written it, so the island can start
    speaking while the rest is still being written. Only once the writer is sure to be used
    (`winner`) and the ask is sure to be a question (`question`); otherwise it waits."""

    def __init__(self):
        self.lock = threading.Lock()
        self.text, self.sent = "", None
        self.winner = self.question = False

    def feed(self, text=None, winner=None, question=None):
        with self.lock:
            if text is not None:
                self.text = text
            if winner is not None:
                self.winner = winner
            if question is not None:
                self.question = question
            if self.sent is not None or not (EMIT and self.winner and self.question):
                return
            m = re.search(r"[.!?](?=\s+\S)", self.text)
            if not m or len(self.text[:m.end()].split()) < 4:
                return
            self.sent = tidy(self.text[:m.end()])
        for f in EMIT:
            f({"event": "first", "text": self.sent})


FIRST = First()


# ---------- writers ----------

_LIVE = []   # writer subprocesses and connections, stopped when their answer isn't needed


def stop_writers():
    for x in list(_LIVE):
        try:
            x.kill() if hasattr(x, "kill") else x.close()
        except Exception as why:  # noqa: BLE001
            print(f"brain ask: could not stop a writer: {why}", file=sys.stderr)

def notes_block(hits, n=4):
    return "\n\n".join(f"[{i}] {h['title']} ({short_path(h['path'])}): {passage(h)}"
                       for i, h in enumerate(hits[:n], 1))


def user_prompt(q, hits):
    return f"Notes:\n{notes_block(hits)}\n\nQuestion: {q}"


def _ollama_body(prompt, model, system, max_tokens):
    body = {"model": model, "stream": True, "keep_alive": "5m",
            "options": {"num_ctx": 4096, "temperature": 0.1, "num_predict": max_tokens},
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}]}
    if model.startswith("granite") or model.startswith("gpt-oss"):
        body["think"] = False if model.startswith("granite") else "low"
    return body


def _read_ollama(resp, t0, deadline):
    """The streamed answer: (text, seconds to the first piece or None)."""
    first, text = None, ""
    while True:
        if deadline and time.monotonic() - t0 > deadline:
            raise TimeoutError("local writer too slow")
        line = resp.readline()
        if not line:
            break
        d = json.loads(line)
        piece = d.get("message", {}).get("content", "")
        if piece and first is None:
            first = time.monotonic() - t0
        text += piece
        if d.get("done"):
            break
    return text, first


def local_write(prompt, model=LOCAL_MODEL, deadline=None, system=SYSTEM, max_tokens=110):
    """Ollama chat, streamed. Returns (text, first_ms, total_ms). Raises TimeoutError past `deadline`
    (seconds from now): the connection is closed, which stops Ollama generating."""
    t0 = time.monotonic()
    body = _ollama_body(prompt, model, system, max_tokens)
    host, _, port = OLLAMA.partition(":")
    conn = http.client.HTTPConnection(host, int(port or 11434), timeout=deadline or 300)
    _LIVE.append(conn)
    try:
        conn.request("POST", "/api/chat", json.dumps(body), {"content-type": "application/json"})
        resp = conn.getresponse()
        if resp.status != 200:
            raise RuntimeError(f"ollama {resp.status}: {resp.read()[:200]!r}")
        text, first = _read_ollama(resp, t0, deadline)
    except OSError as e:   # socket timeout = past the deadline
        if deadline and time.monotonic() - t0 >= deadline - 0.05:
            raise TimeoutError("local writer too slow") from e
        raise
    finally:
        conn.close()
    return text.strip(), int((first or 0) * 1000), int((time.monotonic() - t0) * 1000)


HAIKU_SOCK = os.path.join(os.environ.get("XDG_RUNTIME_DIR", "/tmp"), "brain-haiku.sock")


class _Hangup:
    """Closing the connection stops the pre-started Haiku's answer (stop_writers / the race)."""
    def __init__(self, sock):
        self.sock = sock

    def kill(self):
        try:
            self.sock.shutdown(socket.SHUT_RDWR)
        except OSError as why:
            if why.errno not in (errno.ENOTCONN, errno.EBADF):   # those two just mean it was already closed
                print(f"brain ask: could not hang up on the standby Haiku: {why}", file=sys.stderr)


def haiku_standby_write(prompt, timeout=30, on_text=None):
    """The pre-started Haiku (ask/haiku_standby.py, second-brain-haiku.service). Raises OSError when
    it isn't running, so the caller starts one itself."""
    t0 = time.monotonic()
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    sock.connect(HAIKU_SOCK)
    _LIVE.append(_Hangup(sock))
    first, text = None, ""
    with sock, sock.makefile("rw") as f:
        f.write(json.dumps({"prompt": prompt}) + "\n")
        f.flush()
        for line in f:
            d = json.loads(line)
            if "text" in d:
                text = d["text"]
                if first is None:
                    first = time.monotonic() - t0
                if on_text:
                    on_text(text)
            elif "result" in d:
                text = d["result"] or text
                break
            elif "error" in d:
                raise RuntimeError(f"haiku: {str(d['error'])[:200]}")
    if not text:
        raise RuntimeError("haiku gave no answer")
    return text.strip(), int((first or 0) * 1000), int((time.monotonic() - t0) * 1000)


def _haiku_argv(system):
    return ["claude", "-p", "--model", HAIKU_MODEL, "--tools", "", "--strict-mcp-config", "--setting-sources", "",
            "--no-session-persistence", "--disable-slash-commands", "--system-prompt", system,
            "--output-format", "stream-json", "--verbose", "--include-partial-messages"]


def _delta_text(d):
    """The new words in a stream event, or None when it isn't a text delta."""
    ev = d.get("event") or {}
    if d.get("type") == "stream_event" and ev.get("type") == "content_block_delta":
        return (ev.get("delta") or {}).get("text", "")
    return None


def _read_haiku_stream(proc, t0, on_text):
    """What `claude -p` streamed: (first-piece seconds or None, the text so far, the final result or None)."""
    first, text, final = None, "", None
    for line in proc.stdout:
        try:
            d = json.loads(line)
        except ValueError:
            continue
        piece = _delta_text(d)
        if piece is not None:
            if piece and first is None:
                first = time.monotonic() - t0
            text += piece
            if piece and on_text:
                on_text(text)
        elif d.get("type") == "result":
            final = d.get("result")
            if d.get("is_error"):
                raise RuntimeError(f"haiku: {str(final)[:200]}")
            break
    return first, text, final


def _names():
    if DECIDER_REPO not in sys.path:
        sys.path.append(DECIDER_REPO)
    from decider import names
    return names


class ListProblem(RuntimeError):
    """The private names list is there but empty, broken or unreadable: its message is plain words for <user>."""


_GUARD = []


def private_list_problem(names):
    """Plain words when the private names list the filter reads (names.private_file()) is there but empty, broken or
    unreadable (deciders/private_guard.py, the one guard brain-decide uses too); None when it is fine or not there
    (the filter itself then refuses). Loaded by path, so deciders/ does not join the module search path."""
    if not _GUARD:
        import importlib.util
        spec = importlib.util.spec_from_file_location("private_guard",
                                                      os.path.join(ROOT, "deciders", "private_guard.py"))
        _GUARD.append(importlib.util.module_from_spec(spec))
        spec.loader.exec_module(_GUARD[0])
    return _GUARD[0].problem(names.private_file())


def private_names_out(prompt, system):
    """(prompt, system, back): the text for an online model with every private name (decider/names.py, the same list
    brain-decide uses) swapped for [NAME1], [NAME2]..., and the map that puts them back into the answer here.
    Raises RuntimeError, and nothing may be sent, when the names can't be removed for sure or the filter is missing
    (ListProblem, a RuntimeError, when the list itself is empty, broken or unreadable)."""
    try:
        names = _names()
        why = private_list_problem(names)
        if why:
            raise ListProblem(f"haiku: not sent. {why}")
        clean, back = names.scrub_keyed(prompt)
        if system != SYSTEM:
            system = names.scrub(system)
    except ListProblem:
        raise
    except Exception as why:  # noqa: BLE001 - names.Unsafe, or no filter: never send
        raise RuntimeError(f"haiku: not sent, private names could not be removed ({type(why).__name__})") from None
    return (clean + NAMES_NOTE if back else clean), system, back


def haiku_write(prompt, system=SYSTEM, timeout=30, on_text=None):
    """Claude Haiku: the pre-started one when it's running (and the rules are the usual ones), else
    `claude -p` started now: no tools, no MCP, no settings, no saved session.
    Private names never go out: they are swapped for marks first and put back into the answer here
    (private_names_out); when that can't be done for sure, nothing is sent and it raises RuntimeError.
    Returns (text, first_ms, total_ms)."""
    prompt, system, back = private_names_out(prompt, system)
    if back:
        restore, shown = _names().restore, on_text
        on_text = shown and (lambda t: shown(restore(t, back)))
        text, first_ms, total_ms = _haiku_write(prompt, system, timeout, on_text)
        return restore(text, back), first_ms, total_ms
    return _haiku_write(prompt, system, timeout, on_text)


def _haiku_write(prompt, system, timeout, on_text):
    if system == SYSTEM and os.path.exists(HAIKU_SOCK):
        try:
            return haiku_standby_write(prompt, timeout, on_text)
        except (OSError, ConnectionError) as why:   # not running: start one here
            print(f"brain ask: the standby Haiku did not answer ({why}); starting Haiku here", file=sys.stderr)
    t0 = time.monotonic()
    proc = subprocess.Popen(_haiku_argv(system), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.DEVNULL, text=True, cwd=tempfile.gettempdir())
    _LIVE.append(proc)
    proc.stdin.write(prompt)
    proc.stdin.close()
    timer = threading.Timer(timeout, proc.kill)
    timer.start()
    try:
        first, text, final = _read_haiku_stream(proc, t0, on_text)
    finally:
        timer.cancel()
        try:
            proc.kill()
        except OSError as why:
            print(f"brain ask: could not stop Haiku: {why}", file=sys.stderr)
    if final is None and not text:
        raise RuntimeError("haiku gave no answer")
    return (final or text).strip(), int((first or 0) * 1000), int((time.monotonic() - t0) * 1000)


def local_loaded(model=LOCAL_MODEL):
    """Is the local writer already in memory? A cold load takes 15-30 s here, far past its 4 s."""
    try:
        with urllib.request.urlopen(f"http://{OLLAMA}/api/ps", timeout=0.5) as r:
            return any(m.get("name") == model or m.get("model") == model for m in json.load(r).get("models", []))
    except Exception:  # noqa: BLE001
        return False


def local_ok(text):
    """A light check on a local answer before it is used: in the race the 3B models said "not found"
    for notes that did answer, gave bare fragments, or echoed paths. Haiku is already running, so
    those go to Haiku instead."""
    t = tidy(text)
    if t == NOT_FOUND or len(t.split()) < 5:
        return False
    if re.search(r"qmd://|search/|\.md\b|^[\w ]+:\s", t):
        return False
    return True


def warm_local(model=LOCAL_MODEL):
    """Load the local writer in the background (no answer), so the next question finds it ready."""
    def go():
        try:
            req = urllib.request.Request(f"http://{OLLAMA}/api/generate",
                                         json.dumps({"model": model, "keep_alive": "5m"}).encode(),
                                         {"content-type": "application/json"})
            urllib.request.urlopen(req, timeout=120).read()
        except Exception as why:  # noqa: BLE001
            print(f"brain ask: could not warm the local writer: {why}", file=sys.stderr)
    threading.Thread(target=go, daemon=True).start()


def _run_into(res, key, fn):
    """Run a writer and keep its answer (or the first 120 characters of why it failed) in `res`."""
    try:
        res[key] = fn()
    except Exception as why:  # noqa: BLE001
        res[key + "_error"] = str(why)[:120]


def _local_good(res):
    return "local" in res and local_ok(res["local"][0])


def _local_won(res, extra):
    for x in list(_LIVE):   # stop Haiku, if it started
        if hasattr(x, "kill"):
            x.kill()
    text, first, total = res["local"]
    return text, first, total, "local:" + MODEL_SHORT.get(LOCAL_MODEL, LOCAL_MODEL), extra


def _wait_for_local(res, tl, extra, t0):
    """Haiku has started and local is still writing. Whichever is first: a good local answer wins; a finished
    Haiku isn't kept waiting. The winning local answer, or None."""
    while time.monotonic() - t0 < LOCAL_SECONDS + 0.2:
        if _local_good(res):
            return _local_won(res, extra)
        if "haiku" in res or "haiku_error" in res or not tl.is_alive():
            break
        time.sleep(0.05)
    return _local_won(res, extra) if _local_good(res) else None


def _why_local_gave_up(res):
    return ("weak answer: " + res["local"][0][:60]) if "local" in res else res.get("local_error", "too slow")


def auto_write(prompt):
    """Local first; Haiku only when the local one is too slow or weak (docs/writer-race.md).
    The local writer starts alone. Haiku (which needs the notes) starts only if there is no good local
    answer after BRAIN_HAIKU_WAIT (2 s, <user>'s pick 2026-10-15: notes leave the computer less). The local
    one keeps going until BRAIN_LOCAL_SECONDS (4 s); a good local answer by then still wins and stops Haiku,
    unless Haiku has already finished (the pre-started Haiku takes about 2 s).
    The local writer is skipped (and loaded for next time) when its model isn't loaded, or when
    BRAIN_LOCAL_SECONDS is 0."""
    t0 = time.monotonic()
    res = {}
    use_local = LOCAL_SECONDS > 0 and local_loaded()
    extra = {"haiku_started": False}
    th = threading.Thread(target=_run_into, args=(res, "haiku", lambda: haiku_write(prompt, on_text=lambda t: FIRST.feed(text=t))),
                          daemon=True)
    if use_local:
        tl = threading.Thread(target=_run_into, args=(res, "local", lambda: local_write(prompt, LOCAL_MODEL, deadline=LOCAL_SECONDS)),
                              daemon=True)
        tl.start()
        tl.join(min(HAIKU_WAIT, LOCAL_SECONDS))
        if _local_good(res):
            return _local_won(res, extra)
        if not ("local" in res and not _local_good(res)):   # still writing: Haiku starts, local keeps going
            extra["haiku_started"] = True
            th.start()
            won = _wait_for_local(res, tl, extra, t0)
            if won:
                return won
        extra["local_gave_up"] = _why_local_gave_up(res)
        FIRST.feed(winner=True)
    else:
        extra["local_gave_up"] = "not loaded" if LOCAL_SECONDS > 0 else "off"
        if LOCAL_SECONDS > 0:
            warm_local()
        FIRST.feed(winner=True)
    if not extra["haiku_started"]:
        extra["haiku_started"] = True
        th.start()
    th.join(40)
    if "haiku" not in res:
        raise RuntimeError(res.get("haiku_error", "haiku timed out"))
    text, first, _ = res["haiku"]
    return text, first, int((time.monotonic() - t0) * 1000), "haiku", extra


def write(q, hits, writer="auto"):
    """Returns (answer, writer_name, info)."""
    prompt = user_prompt(q, hits)
    info = {}
    if any(local_only(h) for h in hits[:4]):   # the notes user_prompt sends: local writer only, Haiku gets nothing
        info["local_only_note"] = True
        if writer == "haiku":
            raise RuntimeError("haiku: not sent, a note is marked local-only")
        if not writer.startswith("local"):
            writer = "local"
    if writer.startswith("local"):
        model = writer.split(":", 1)[1] if ":" in writer else LOCAL_MODEL
        model = {"qwen2.5": "qwen2.5:3b", "granite4.2": "granite4.2:3b", "gpt-oss": "gpt-oss:20b"}.get(model, model)
        text, first, total = local_write(prompt, model)
        name = "local:" + MODEL_SHORT.get(model, model)
    elif writer == "haiku":
        FIRST.feed(winner=True)
        text, first, total = haiku_write(prompt, on_text=lambda t: FIRST.feed(text=t))
        name = "haiku"
    else:  # auto: see auto_write()
        text, first, total, name, extra = auto_write(prompt)
        info.update(extra)
    info.update(first_ms=first, write_ms=total)
    return tidy(text), name, info


def tidy(text):
    text = text.strip().strip('"').strip()
    text = re.sub(r"\*\*|__|`", "", text)
    text = re.sub(r"\s*\[\d+(,\s*\d+)*\]", "", text)   # "[1]" markers read badly out loud
    text = re.sub(r"\b(notes? says?):?\s*(\.\.\.|…)\s*(\w)", lambda m: f"{m.group(1)} {m.group(3).lower()}", text)
    if "couldn't find that in your notes" in text.lower() or "could not find that in your notes" in text.lower():
        return NOT_FOUND
    sentences = re.split(r"(?<=[.!?])\s+", " ".join(text.split()))
    return " ".join(sentences[:3])


# ---------- chitchat ----------

def chitchat(text):
    t = text.lower()
    if re.search(r"\b(thanks|thank you|cheers|ta)\b", t):
        return "You're welcome!"
    if re.search(r"\b(bye|good ?night|see you|later)\b", t):
        return "Bye for now. Say Hey Claude when you need me."
    if re.search(r"\bhow are you\b", t):
        return "I'm good, and ready to look in your notes."
    if re.search(r"\b(who|what) are you\b", t):
        return "I'm your second brain. Ask me about your notes, or ask me to do a small job."
    return "Hi <user>! Ask me anything about your notes, or ask me to do a small job."


# ---------- the whole thing ----------

def answer_question(q, hits, writer, steps):
    """Grounded check, then the writer. Returns (answer, writer_name)."""
    if not hits:
        return NOT_FOUND, "none"
    snippets = "\n".join(f"[{i}] {os.path.basename(h['path'])}: {passage(h, 420)}" for i, h in enumerate(hits[:3], 1))
    t = time.monotonic()
    g = decide("grounded", q, snippets, timeout=3)
    steps["grounded_ms"] = int((time.monotonic() - t) * 1000)
    steps["grounded"] = f"{g.get('label')} ({g.get('by')})"
    if g.get("label") == "no" and g.get("by") == "local_decider" and float(g.get("confidence") or 0) >= 0.8:
        return NOT_FOUND, "local_decider"
    try:
        answer, name, info = write(q, hits, writer)
        steps.update(info)
        return answer or NOT_FOUND, name
    except Exception as why:  # noqa: BLE001
        steps["writer_error"] = str(why)[:200]
        return f"I couldn't write an answer just now, but your note {hits[0]['title']} looks like the best match.", "none"


def _run_intent(q, rule, box, steps):
    t = time.monotonic()
    box["intent"] = decide("intent", q, timeout=1.5 if rule else INTENT_SECONDS)
    steps["intent_ms"] = int((time.monotonic() - t) * 1000)


def _run_search(q, writer, box, steps, then_answer):
    t = time.monotonic()
    try:
        box["hits"] = search(q)
    except Exception as why:  # noqa: BLE001
        box["hits"], steps["search_error"] = [], str(why)[:200]
    steps["search_ms"] = int((time.monotonic() - t) * 1000)
    if then_answer:
        box["answer"] = answer_question(q, box["hits"], writer, steps)


def _word_rule_fix(q, rule, label, by, again):
    """The first correction the word rules make to the decider's answer: (label, by, again)."""
    if label == "unsure" or not label:
        if not again:
            label, by = (f"job:{rule}", "rule") if rule else ("question", by)
    elif rule in jobslib.AGENT_JOBS and label != f"job:{rule}":   # tight rules, new to the decider: the rule wins
        label, by = f"job:{rule}", "rule"
    elif label[4:] in jobslib.AGENT_JOBS and rule != label[4:] and jobslib.two_asks(q, label[4:]):
        label, again = "unsure", True   # two asks in one line never hand off to agent-os: say it again
    elif rule in jobslib.DESKTOP_JOBS + jobslib.DAY_JOBS and label in ("question", "chitchat", "job:open-note"):
        label, by = f"job:{rule}", "rule"
    elif jobslib.route_label(rule, label, q) != label:   # "send it to the laptop" is not an open-file
        label, by = jobslib.route_label(rule, label, q), "rule"
    return label, by, again


def _question_not_job(q, rule, label):
    if label[4:] in jobslib.DESKTOP_JOBS and jobslib.is_how_question(q):
        return "question"
    if label[4:] in jobslib.AGENT_JOBS and rule != label[4:] and jobslib.is_how_question(q):
        return "question"   # "what should I fix on my remember list?" is a question, whatever the decider says
    return label


def _route(q, rule, intent):
    """What the decider said, corrected by the word rules: (label, by, again). `again` = say it again."""
    label, by = intent.get("label", "unsure"), intent.get("by", "?")
    # A decider's own "unsure" (or the local decider under its bar) means it didn't catch what <user> wants. A timeout or a
    # fallback with no answer keeps the old way: the word rules, else a question.
    again = label == "unsure" and not rule and (by in ("local_decider", "second_decider") or intent.get("reason") == "below-bar")
    label, by, again = _word_rule_fix(q, rule, label, by, again)
    return _question_not_job(q, rule, label), by, again


def _job_answer(q, how, label, by, steps, out):
    stop_writers()

    def note_search(topic):
        return public_sources(search(topic))
    built = jobslib.build_with_details(label[4:], q, search=note_search, how=how,
                                       local_writer=lambda p: local_write(p, LOCAL_MODEL, deadline=8, system="Answer with one name only.",
                                                                          max_tokens=12)[0])
    steps["details"] = built.pop("details", "rules")   # router upgrade 3: "local" = the writer's form made the job
    if "details_ms" in built:
        steps["details_ms"] = built.pop("details_ms")
    built.pop("form", None)
    out.update(built)
    out["writer"] = by if by in ("second_decider", "local_decider") else "rule"


def _question_answer(q, writer, ts, box, steps, out):
    ts.join()
    hits = box["hits"]
    answer, name = box["answer"] if "answer" in box else answer_question(q, hits, writer, steps)
    out.update(answer=answer, writer=name, sources=public_sources(hits[:3]))
    if answer == NOT_FOUND:
        out["found"] = False


def ask(q, writer="auto", how="typed"):
    """Intent and search start together. Unless a job rule fits the words, the answer is written
    straight after the search, without waiting for the decider (it takes 0.2-3 s); if the decider then
    says job or chitchat, that answer is thrown away (and the writer stopped)."""
    t0 = time.monotonic()
    q = jobslib.clean_text(q) or q
    steps = {}
    box = {}
    rule = jobslib.match_rule(q)
    ti = threading.Thread(target=_run_intent, args=(q, rule, box, steps), daemon=True)
    ts = threading.Thread(target=_run_search, args=(q, writer, box, steps, rule is None), daemon=True)
    ti.start()
    ts.start()
    ti.join()
    label, by, again = _route(q, rule, box["intent"])
    steps["intent"] = f"{label} ({by})"
    if not label.startswith("job:") and label != "chitchat" and not again:
        FIRST.feed(question=True)
    out = {"kind": "answer", "answer": "", "sources": [], "job": None, "writer": "", "ms": 0}

    if label.startswith("job:"):
        _job_answer(q, how, label, by, steps, out)
    elif label == "chitchat":
        stop_writers()
        out.update(answer=chitchat(q), writer="rule")
    elif again:
        stop_writers()
        out.update(answer=SAY_AGAIN, writer="rule", found=False, again=True)
    else:
        _question_answer(q, writer, ts, box, steps, out)
    out["ms"] = int((time.monotonic() - t0) * 1000)
    out["steps"] = steps
    return out


def _parse_argv(argv):
    """(words, as_json, writer, source, stream, how) from the command line."""
    writer = "auto"
    source = os.environ.get("BRAIN_FROM", "cli")
    stream = False
    how = "typed"   # the island can't tell speech from typing yet; `--how voice` once it can
    words = []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--json":
            pass
        elif a == "--writer" and i + 1 < len(argv):
            writer = argv[i + 1]
            i += 1
        elif a.startswith("--writer="):
            writer = a.split("=", 1)[1]
        elif a == "--from" and i + 1 < len(argv):
            source = argv[i + 1]
            i += 1
        elif a == "--stream":
            stream = True
        elif a == "--how" and i + 1 < len(argv):
            how = argv[i + 1] if argv[i + 1] in ("voice", "typed") else "typed"
            i += 1
        else:
            words.append(a)
        i += 1
    return words, "--json" in argv, writer, source, stream, how


def _print_stream_done(result):
    first = FIRST.sent
    if first and result["answer"].startswith(first):
        result["rest"] = result["answer"][len(first):].strip()
    elif first:
        result["rest"] = ""   # already spoke a different start; don't repeat
    print(json.dumps(dict(result, event="done", first=first)), flush=True)


def _print_plain(result):
    print(result["answer"])
    if result.get("job"):
        j = result["job"]
        print(f"\nJob: {j['label']}{' (asks first)' if j['needs_confirm'] else ''}\n  run: brain job run {j['id']} --args-json '{json.dumps(j)}'")
    for s in result["sources"]:
        print(f"  - {s['title']}: {s['path']}")
    print(f"({result['writer']}, {result['ms']} ms)  rate it: brain rate {result['id']} up|down")


def main(argv):
    words, as_json, writer, source, stream, how = _parse_argv(argv)
    q = " ".join(words).strip()
    if not q:
        print("brain ask: say what to ask", file=sys.stderr)
        return 2
    if stream:
        EMIT.append(lambda ev: print(json.dumps(ev), flush=True))
    global HIDE_PRIVATE
    HIDE_PRIVATE = run_by_online_agent("brain ask")
    result = ask(q, writer, how)
    result["id"] = asklog.new_id()
    asklog.log_ask(result["id"], q, result, source)
    if stream:
        _print_stream_done(result)
    elif as_json:
        print(json.dumps(result))
    else:
        _print_plain(result)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
