"""A pre-started Haiku, so `brain ask` doesn't wait for Claude Code to start (about 1.5-2 s).

second-brain-haiku.service runs this. It keeps one `claude -p` (Haiku, no tools, no MCP, no settings,
no saved session, the answer rules as its system prompt) started and waiting. `brain ask` connects to
$XDG_RUNTIME_DIR/brain-haiku.sock, sends {"prompt": "..."} on one line and gets JSON lines back:
{"text": "<answer so far>"} while it writes, then {"result": "...", "ms_api": n} (or {"error": "..."}).
Each waiting Claude answers one question, then is stopped and a fresh one is started, so questions
never share a conversation. A waiting one is replaced every 20 minutes. Closing the connection
early stops the answer (the writer race uses that).

Nothing is sent anywhere until a question arrives.
"""
import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

SOCK = os.path.join(os.environ.get("XDG_RUNTIME_DIR", "/tmp"), "brain-haiku.sock")
FRESH_SECONDS = 20 * 60


def argv():
    import ask   # the same model and answer rules as a cold Haiku
    return ["claude", "-p", "--model", ask.HAIKU_MODEL, "--tools", "", "--strict-mcp-config", "--setting-sources", "",
            "--no-session-persistence", "--disable-slash-commands", "--system-prompt", ask.SYSTEM,
            "--input-format", "stream-json", "--output-format", "stream-json", "--verbose", "--include-partial-messages"]


class Spare:
    def __init__(self):
        self.lock = threading.Lock()
        self.proc, self.born = None, 0.0
        self.cmd = argv()

    def start(self):
        p = subprocess.Popen(self.cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                             text=True, cwd=tempfile.gettempdir())
        with self.lock:
            old, self.proc, self.born = self.proc, p, time.monotonic()
        if old:
            old.kill()

    def take(self):
        """The waiting Claude (or a new one if it died or is stale); a replacement starts at once."""
        with self.lock:
            p, born, self.proc = self.proc, self.born, None
        if not p or p.poll() is not None or time.monotonic() - born > FRESH_SECONDS:
            if p:
                p.kill()
            p = subprocess.Popen(self.cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                 text=True, cwd=tempfile.gettempdir())
        threading.Thread(target=self.start, daemon=True).start()
        return p

    def keep_fresh(self):
        while True:
            time.sleep(60)
            with self.lock:
                stale = self.proc is None or self.proc.poll() is not None or time.monotonic() - self.born > FRESH_SECONDS
            if stale:
                self.start()


def names_clear(prompt):
    """True only when the shared names filter (decider/names.py) finds no private name. `brain ask` removes them
    before it sends; this is the second check, so no other caller can push a name out through the standby."""
    try:
        import ask
        names = ask._names()
        return ask.private_list_problem(names) is None and names.find(prompt) == 0
    except Exception:  # noqa: BLE001 - names.Unsafe, or no filter: not sure, so not clear
        return False


def _send(f, obj):
    f.write(json.dumps(obj) + "\n")
    f.flush()


def _stream_answer(proc, f):
    """Pass Claude's streamed answer on to the asker: the text so far, then the result (or an error)."""
    text = ""
    for line in proc.stdout:
        try:
            d = json.loads(line)
        except ValueError:
            continue
        ev = d.get("event") or {}
        if d.get("type") == "stream_event" and ev.get("type") == "content_block_delta":
            piece = (ev.get("delta") or {}).get("text", "")
            if piece:
                text += piece
                _send(f, {"text": text})
        elif d.get("type") == "result":
            key = "error" if d.get("is_error") else "result"
            _send(f, {key: d.get("result") or text, "ms_api": d.get("duration_api_ms")})
            return
    _send(f, {"error": "haiku stopped without an answer"})


def serve(conn, spare):
    f = conn.makefile("rw")
    proc = None
    try:
        req = json.loads(f.readline() or "{}")
        proc = spare.take()
        if not names_clear(req["prompt"]):   # the waiting Claude is stopped below, it never sees the prompt
            _send(f, {"error": "not sent: a private name is in the prompt, or the names filter is not sure"})
            return
        proc.stdin.write(json.dumps({"type": "user", "message": {"role": "user", "content": req["prompt"]}}) + "\n")
        proc.stdin.flush()
        _stream_answer(proc, f)
    except (OSError, ValueError, KeyError) as why:
        if not isinstance(why, (BrokenPipeError, ConnectionResetError)):   # those two: the asker hung up, its answer wasn't needed
            print(f"haiku standby: dropped a request: {type(why).__name__}", file=sys.stderr)
    finally:
        if proc:
            proc.kill()
        try:
            conn.close()
        except OSError as why:
            print(f"haiku standby: could not close the connection: {why}", file=sys.stderr)


def main():
    spare = Spare()
    spare.start()
    threading.Thread(target=spare.keep_fresh, daemon=True).start()
    if os.path.exists(SOCK):
        os.unlink(SOCK)
    srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    srv.bind(SOCK)
    os.chmod(SOCK, 0o600)
    srv.listen(4)
    while True:
        conn, _ = srv.accept()
        threading.Thread(target=serve, args=(conn, spare), daemon=True).start()


if __name__ == "__main__":
    main()
