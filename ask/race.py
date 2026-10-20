"""Writer race: the same notes, several writers, scored on hand-written facts (race-questions.tsv).

  CRABBOX_LOCAL=1 python3 -I ask/race.py [writer ...]     (default: local:qwen2.5 local:granite4.2 haiku)

Each question is searched once; every writer gets the same top notes and prompt (ask.py write()).
A local model gets one unscored warm-up first, so its load time isn't counted.
Prints a markdown table and writes ask/race-results.jsonl (answers kept for checking by hand).
"""
import json
import os
import re
import sys
import time

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ask  # noqa: E402


def load():
    rows = []
    for line in open(os.path.join(HERE, "race-questions.tsv")):
        if line.startswith("#") or not line.strip():
            continue
        q, facts, where = line.rstrip("\n").split("\t")
        rows.append((q, facts, where))
    return rows


def score(answer, facts):
    nf = answer.strip() == ask.NOT_FOUND
    if facts == "NOTFOUND":
        return "honest" if nf else "made up"
    if nf:
        return "not found"
    ok = all(re.search(f.strip(), answer, re.I) for f in facts.split(" && "))
    return "right" if ok else "wrong"


def _warm_up(w, rows, hits):
    """A local model gets one unscored warm-up first, so its load time isn't counted."""
    if w.startswith("local"):
        try:
            ask.write("warm up", hits[rows[0][0]][:1], w)
        except Exception as e:  # noqa: BLE001
            print(f"{w}: warm-up failed: {e}", file=sys.stderr)


def _race_one(w, q, facts, where, hits):
    """One writer on one question: the record that goes in race-results.jsonl."""
    t = time.monotonic()
    try:
        answer, name, info = ask.write(q, hits[q], w)
    except Exception as e:  # noqa: BLE001
        answer, name, info = f"ERROR {e}", w, {"first_ms": 0, "write_ms": int((time.monotonic() - t) * 1000)}
    s = score(answer, facts)
    in_top4 = where == "-" or any(where in h["file"] for h in hits[q][:4])
    rec = {"writer": w, "q": q, "score": s, "answer": answer, "first_ms": info.get("first_ms"),
           "total_ms": info.get("write_ms"), "note_in_top4": in_top4}
    print(f"{w:18} {s:9} {info.get('first_ms', 0):>6} {info.get('write_ms', 0):>6}  {q} -> {answer[:140]}",
          file=sys.stderr)
    return rec


def _print_table(summary):
    print("| Writer | Right (of 18) | Honest when not found (of 3) | Made up / wrong | First words, median | Whole answer, median | Whole answer, slowest |")
    print("|---|---|---|---|---|---|---|")
    for w, res in summary.items():
        right = sum(r["score"] == "right" for r in res)
        honest = sum(r["score"] == "honest" for r in res)
        bad = sum(r["score"] in ("wrong", "made up") for r in res)
        fm = sorted(r["first_ms"] or 0 for r in res)
        tm = sorted(r["total_ms"] or 0 for r in res)
        print(f"| {w} | {right} | {honest} | {bad} | {fm[len(fm) // 2] / 1000:.1f} s | {tm[len(tm) // 2] / 1000:.1f} s | {tm[-1] / 1000:.1f} s |")


def main():
    writers = sys.argv[1:] or ["local:qwen2.5", "local:granite4.2", "haiku"]
    rows = load()
    hits = {}
    for q, _, _ in rows:
        hits[q] = ask.search(q)
    out = open(os.path.join(HERE, "race-results.jsonl"), "w")
    summary = {}
    for w in writers:
        _warm_up(w, rows, hits)
        res = []
        for q, facts, where in rows:
            rec = _race_one(w, q, facts, where, hits)
            out.write(json.dumps(rec) + "\n")
            out.flush()
            res.append(rec)
        summary[w] = res
    _print_table(summary)


main()
