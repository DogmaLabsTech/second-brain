"""The question record: every `brain ask` answer and <user>'s 👍/👎, for the weekly check-up.

  ~/.local/state/second-brain/asks.jsonl     one line per question (what was asked, the answer, who
                                            wrote it, the notes used, timings, from where)
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


def log_ask(qid, q, result, source):
    try:
        _append(ASKS, {"id": qid, "at": time.strftime("%Y-%m-%dT%H:%M:%S"), "from": source, "q": q,
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
    try:
        with open(path) as f:
            return [json.loads(l) for l in f if l.strip()]
    except (OSError, ValueError):
        return []


def main(argv):
    """brain rate <id|last> up|down [why]   ·   brain outcome <id> <what> [detail]   ·   brain log [n]"""
    if argv and argv[0] == "outcome":
        if len(argv) < 3 or argv[2] not in OUTCOME_KINDS:
            print("brain outcome <id> " + "|".join(OUTCOME_KINDS) + " [detail]", file=sys.stderr)
            return 2
        outcome(argv[1], argv[2], " ".join(argv[3:]))
        return 0
    if argv and argv[0] == "rate":
        if len(argv) < 3:
            print("brain rate <id|last> up|down [why]", file=sys.stderr)
            return 2
        qid = argv[1]
        if qid == "last":
            rows = read(ASKS)
            if not rows:
                print("brain rate: nothing asked yet", file=sys.stderr)
                return 1
            qid = rows[-1]["id"]
        rate(qid, argv[2], " ".join(argv[3:]))
        print(f"noted {argv[2]} for {qid}")
        return 0
    n = int(argv[1]) if len(argv) > 1 else 10
    votes = {r["id"]: r["verdict"] for r in read(RATINGS)}
    for r in read(ASKS)[-n:]:
        mark = {"up": "👍", "down": "👎"}.get(votes.get(r["id"]), "  ")
        print(f"{mark} {r['at'][5:16]} {r.get('from', '?'):8} {r.get('writer', ''):14} {r.get('ms', 0):>6} ms  {r['q']}")
        print(f"      → {str(r.get('answer'))[:150]}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
