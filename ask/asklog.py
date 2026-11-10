"""The question record: every `brain ask` answer and <user>'s 👍/👎, for the weekly check-up.

  ~/.local/state/second-brain/asks.jsonl     one line per question (what was asked, the answer, who
                                            wrote it, the notes used, timings, from where, and
                                            `client`: the chat or program that ran it, see searchlog.caller)
  ~/.local/state/second-brain/ratings.jsonl  one line per 👍/👎 (`brain rate <id> up|down [why]`)
  ~/.local/state/second-brain/outcomes.jsonl what happened next on the island (`brain outcome <id> <what>
                                            [detail]`): declined (No or Esc on a job card), stopped (Esc while
                                            it was thinking or answering), job-ok, job-failed (+ its message)

Both stay on this computer (folder mode 700). The check-up (eval/checkup.py) reads them.
"""
import json
import os
import sys
import time
import uuid

STATE = os.path.expanduser(os.environ.get("BRAIN_STATE", "~/.local/state/second-brain"))
ASKS = os.path.join(STATE, "asks.jsonl")
RATINGS = os.path.join(STATE, "ratings.jsonl")
OUTCOMES = os.path.join(STATE, "outcomes.jsonl")
OUTCOME_KINDS = ("declined", "stopped", "job-ok", "job-failed")


def _append(path, row):
    os.makedirs(STATE, mode=0o700, exist_ok=True)
    os.chmod(STATE, 0o700)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    with os.fdopen(fd, "a") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def new_id():
    return time.strftime("%m%d-%H%M%S-") + uuid.uuid4().hex[:4]


def _caller():
    """Who ran `brain ask` (the chat, the island, the Deck ...), in the shape of the search record's client."""
    try:
        import searchlog
        return searchlog.caller("brain ask")
    except Exception:  # noqa: BLE001  never break an answer over who asked
        return {"name": "brain ask", "pid": os.getppid(), "program": "terminal", "folder": None}


def log_ask(qid, q, result, source, client=None):
    try:
        _append(ASKS, {"id": qid, "at": time.strftime("%Y-%m-%dT%H:%M:%S"), "from": source,
                       "client": client or _caller(), "q": q,
                       "kind": result.get("kind"), "answer": result.get("answer"),
                       "writer": result.get("writer"), "found": result.get("found", True),
                       "job": (result.get("job") or {}).get("id"),
                       "sources": [s.get("path") for s in result.get("sources", [])],
                       "ms": result.get("ms"), "steps": result.get("steps", {})})
    except OSError as why:   # the record must never break an answer, but a lost line is said
        print(f"asklog: could not record the question: {why}", file=sys.stderr)


def rate(qid, verdict, why=""):
    if verdict not in ("up", "down"):
        raise ValueError("say up or down")
    _append(RATINGS, {"id": qid, "at": time.strftime("%Y-%m-%dT%H:%M:%S"), "verdict": verdict, "why": why})


def outcome(qid, what, detail=""):
    if what not in OUTCOME_KINDS:
        raise ValueError("say one of " + ", ".join(OUTCOME_KINDS))
    _append(OUTCOMES, {"id": qid, "at": time.strftime("%Y-%m-%dT%H:%M:%S"), "what": what, "detail": detail[:200]})


def read(path):
    rows, bad = [], 0
    try:
        with open(path) as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    row = json.loads(line)
                except ValueError:   # one cut or damaged line must not hide the rest of the log
                    bad += 1
                    continue
                if isinstance(row, dict):
                    rows.append(row)
    except FileNotFoundError:   # nothing recorded yet
        return []
    except OSError as why:
        print(f"asklog: could not read {path}: {why}", file=sys.stderr)
        return []
    if bad:
        print(f"asklog: skipped {bad} damaged line{'s' if bad != 1 else ''} in {path}", file=sys.stderr)
    return rows


def _cmd_outcome(argv):
    if len(argv) < 3 or argv[2] not in OUTCOME_KINDS:
        print("brain outcome <id> " + "|".join(OUTCOME_KINDS) + " [detail]", file=sys.stderr)
        return 2
    outcome(argv[1], argv[2], " ".join(argv[3:]))
    return 0


def _cmd_rate(argv):
    if len(argv) < 3:
        print("brain rate <id|last> up|down [why]", file=sys.stderr)
        return 2
    if argv[2] not in ("up", "down"):
        print("brain rate <id|last> up|down [why]   (say up or down)", file=sys.stderr)
        return 2
    qid = argv[1]
    if qid == "last":
        rows = [r for r in read(ASKS) if r.get("id")]
        if not rows:
            print("brain rate: nothing asked yet", file=sys.stderr)
            return 1
        qid = rows[-1]["id"]
    rate(qid, argv[2], " ".join(argv[3:]))
    print(f"noted {argv[2]} for {qid}")
    return 0


def _cmd_log(argv):
    try:
        n = int(argv[1]) if len(argv) > 1 else 10
    except ValueError:
        print("brain log [how many]   (a number, like 20)", file=sys.stderr)
        return 2
    n = max(1, n)
    votes = {r.get("id"): r.get("verdict") for r in read(RATINGS)}
    for r in read(ASKS)[-n:]:
        mark = {"up": "👍", "down": "👎"}.get(votes.get(r.get("id")), "  ")
        print(f"{mark} {str(r.get('at', ''))[5:16]} {r.get('from', '?'):8} {r.get('writer', ''):14} {r.get('ms', 0):>6} ms  {r.get('q', '')}")
        print(f"      → {str(r.get('answer'))[:150]}")
    return 0


def main(argv):
    """brain rate <id|last> up|down [why]   ·   brain outcome <id> <what> [detail]   ·   brain log [n]"""
    if argv and argv[0] == "outcome":
        return _cmd_outcome(argv)
    if argv and argv[0] == "rate":
        return _cmd_rate(argv)
    return _cmd_log(argv)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
