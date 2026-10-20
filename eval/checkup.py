"""brain checkup: the weekly check-up (eval/README.md, docs/checkup.md).

  brain checkup              fair test score (search) + this week's questions, 👍/👎, speed, who wrote
  brain checkup --answers    also asks every fair-test question for real (slow; Haiku may help) and
                             saves the answers for grading by hand in the check-up
  brain checkup --days N     look back N days instead of 7
  brain checkup --no-intent  skip the intent fair test (the local decider, through the decider service, ~15 s)
  brain checkup --no-learn   skip learning from the week's likely misses (Haiku and the second decider label them)
  brain checkup --no-train   find misses, but don't start a training round even with 30+ new examples

Scores are written to eval/scores.tsv (one line per run), so each week can be compared with the last.
"""
import json
import os
import statistics
import subprocess
import sys
import time

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "ask"))
import ask  # noqa: E402
import asklog  # noqa: E402

HOME = os.path.expanduser("~")
DECIDERS = os.path.join(ROOT, "deciders")
DECIDER_APP = os.path.join(HOME, "projects", "Projects", "decider")


def tilde(p):
    return p.replace(HOME, "~")


def load(name):
    with open(os.path.join(HERE, name)) as f:
        return [json.loads(l) for l in f if l.strip()]


def search_score(rows):
    """Top-1 and top-3: is a right note first / in the first three? Newer: does the current note
    come before the outdated one?"""
    out = {"top1": 0, "top3": 0, "n": 0, "newer_ok": 0, "newer_n": 0, "by_use": {}, "misses": []}
    for r in rows:
        if r["use"] == "missing":
            continue
        got = [tilde(h["path"]) for h in ask.search(r["q"])]
        want = set(r["expect_paths"])
        rank = next((i for i, p in enumerate(got) if p in want), None)
        u = out["by_use"].setdefault(r["use"], [0, 0])
        u[1] += 1
        out["n"] += 1
        if rank == 0:
            out["top1"] += 1
        if rank is not None and rank < 3:
            out["top3"] += 1
            u[0] += 1
        else:
            out["misses"].append((r["id"], r["q"], got[:3]))
        if r["use"] == "newer":
            out["newer_n"] += 1
            stale = next((i for i, p in enumerate(got) if p in set(r.get("stale_paths", []))), 99)
            if rank is not None and rank < stale:
                out["newer_ok"] += 1
    return out


def intent_score(test="test.jsonl"):
    """the local decider alone on an intent fair test (deciders/brain-intent/<test>), through the decider service, with each
    answer's sure-bar (deciders/bars.py): how often she is right, and how often she is sure and wrong, meaning
    the brain would act on a wrong answer (router upgrade 2). None when there is no trained the local decider or no test."""
    path = os.path.join(DECIDERS, "brain-intent", test)
    if not os.path.exists(path):
        return None
    sys.path[:0] = [DECIDERS, DECIDER_APP]
    from decider import decide, tasks
    import bars
    t = tasks.load_task("brain-intent")
    if not t.trained:
        return None
    preds = []
    for i, r in enumerate(load_jsonl(path)):
        res = decide("brain-intent", r["text"], backend="local_decider", timeout=60 if i == 0 else 10, caller="checkup")
        a = (res.get("answers") or {}).get("intent") or ((res.get("hint") or {}).get("answers") or {}).get("intent") or {}
        preds.append({"label": r["label"], "pred": a.get("choice"), "conf": float(a.get("confidence") or 0)})
    out = bars.score(preds, bars.load(t.local_decider_checkpoint))
    out["model"] = os.path.basename(t.local_decider_checkpoint)
    out["bars"] = bool(bars.load(t.local_decider_checkpoint))
    return out


def learn(days, train=True):
    """Router upgrade 1: mark the week's likely misses (deciders/tools/learn_misses.py), list up to 3 unclear
    ones for <user>, and start a training round on the test machine once 30+ new real examples have built up
    (tools/retrain.py). Returns the number of new real examples added."""
    py = os.path.join(DECIDER_APP, ".venv", "bin", "python")
    tools = os.path.join(DECIDERS, "tools")
    print(f"\nLikely misses, last {days} days (island, bar, Obsidian):")
    try:
        r = subprocess.run([py, "-I", os.path.join(tools, "learn_misses.py"), "--days", str(days)],
                           capture_output=True, text=True, timeout=900)
        lines = r.stdout.strip().splitlines() or ["  (none)"]
        print("\n".join("  " + l for l in lines if l.strip()) + ("\n  error: " + r.stderr.strip()[-300:] if r.returncode else ""))
        added = int(next((l.split("; ")[-1].split()[0] for l in lines if "likely misses" in l), "0"))
        q = json.loads(subprocess.run([py, "-I", os.path.join(tools, "learn_misses.py"), "ask", "3"],
                                      capture_output=True, text=True, timeout=60).stdout or "[]")
        if q:
            print("  For <user> (ask in plain words, then: learn_misses.py answer <id> <label|skip>):")
            for m in q:
                print(f"    {m['id']}: \"{m['q']}\" (it said: {m['answer'][:80]}) - one of {', '.join(m['options'])}?")
        if train:
            t = subprocess.run([py, "-I", os.path.join(tools, "retrain.py")], capture_output=True, text=True, timeout=600)
            print("  Training: " + (t.stdout.strip() or t.stderr.strip()[-300:]))
        return added
    except (OSError, ValueError, subprocess.TimeoutExpired) as why:
        print(f"  couldn't look: {why}")
        return 0


def load_jsonl(path):
    with open(path) as f:
        return [json.loads(l) for l in f if l.strip()]


def week(days):
    since = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(time.time() - days * 86400))
    asks = [a for a in asklog.read(asklog.ASKS) if a.get("at", "") >= since]
    votes = {}
    for r in asklog.read(asklog.RATINGS):
        votes[r["id"]] = r
    return asks, votes


def private_list_problem(path=None):
    """Plain words when deciders/private.json exists but cannot be read (brain-decide then has no family or
    client names to keep private, and its warning is lost in the ask path); None when it is fine or not there."""
    path = path or os.path.join(DECIDERS, "private.json")
    try:
        with open(path) as f:
            data = json.load(f)
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as why:
        return (f"The private names list ({tilde(path)}) can't be read ({why}). Until it is fixed, family and "
                "client names are not kept private: asks that name them can go to the second decider.")
    if not isinstance(data, dict) or not isinstance(data.get("words", []), list) \
            or not all(isinstance(w, str) for w in data.get("words", [])):
        return (f"The private names list ({tilde(path)}) has the wrong shape (it must be an object whose 'words' "
                "is a list of words). Until it is fixed, family and client names are not kept private: asks "
                "that name them can go to the second decider.")
    return None


def _print_search(s):
    print(f"Fair test (search, {s['n']} questions): right note first {s['top1']}/{s['n']}, "
          f"in top 3 {s['top3']}/{s['n']} ({100 * s['top3'] // max(1, s['n'])}%)")
    print("  by use: " + ", ".join(f"{u} {a}/{b}" for u, (a, b) in sorted(s["by_use"].items())))
    print(f"  newer note beats the old one: {s['newer_ok']}/{s['newer_n']}")
    for qid, q, got in s["misses"]:
        print(f"  miss {qid}: {q}\n        got {', '.join(os.path.basename(g) for g in got)}")


def _print_intent(it):
    print(f"Intent fair test (the local decider alone, {it['model']}, {'own sure-bars' if it['bars'] else 'one 0.6 bar'}): "
          f"right {it['right']}/{it['n']}, sure and wrong {it['sure_wrong']}/{it['n']} ({it['sure_wrong_pct']}%)")
    for m in it["mistakes"]:
        print(f"  sure and wrong: {m}")


def _print_tuning():
    seen = load("seen.jsonl") if os.path.exists(os.path.join(HERE, "seen.jsonl")) else []
    if seen:
        t = search_score(seen)
        print(f"Tuning set (past misses, {t['n']}): in top 3 {t['top3']}/{t['n']}")
        for qid, q, got in t["misses"]:
            print(f"  still missing {qid}: {q}")


def _print_questions(qs):
    writers = {}
    for a in qs:
        writers[a.get("writer") or "?"] = writers.get(a.get("writer") or "?", 0) + 1
    online = sum(1 for a in qs if (a.get("steps") or {}).get("haiku_started"))
    print("  written by: " + ", ".join(f"{w} {n}" for w, n in sorted(writers.items(), key=lambda x: -x[1])))
    print(f"  notes went to Haiku: {online}/{len(qs)}")
    print(f"  time: middle {statistics.median(a.get('ms') or 0 for a in qs) / 1000:.1f} s, "
          f"slowest {max(a.get('ms') or 0 for a in qs) / 1000:.1f} s")
    print(f"  not found: {sum(1 for a in qs if a.get('found') is False)}")


def _print_week(asks, votes, days):
    """The week's asks: how many, who wrote them, speed, and the 👍/👎. Returns (the 👍 asks, the 👎 asks)."""
    qs = [a for a in asks if a.get("kind") == "answer"]
    print(f"\nLast {days} days: {len(asks)} asks ({len(qs)} questions, {len(asks) - len(qs)} jobs)")
    if qs:
        _print_questions(qs)
    up = [a for a in asks if votes.get(a["id"], {}).get("verdict") == "up"]
    down = [a for a in asks if votes.get(a["id"], {}).get("verdict") == "down"]
    print(f"  👍 {len(up)}   👎 {len(down)}   not rated {len(asks) - len(up) - len(down)}")
    for a in down:
        why = votes[a["id"]].get("why")
        print(f"  👎 {a['id']}: {a['q']}\n      said: {str(a.get('answer'))[:160]}"
              + (f"\n      why: {why}" if why else "") + f"\n      notes: {', '.join(os.path.basename(p) for p in a.get('sources', []))}")
    return up, down


def _append_scores(s, it, asks, up, down, learned):
    line = "\t".join([time.strftime("%Y-%m-%d %H:%M"), f"{s['top1']}/{s['n']}", f"{s['top3']}/{s['n']}",
                      f"{s['newer_ok']}/{s['newer_n']}", str(len(asks)), str(len(up)), str(len(down)),
                      f"{it['right']}/{it['n']}" if it else "-", f"{it['sure_wrong']}/{it['n']}" if it else "-",
                      "-" if learned is None else str(learned),
                      os.environ.get("CHECKUP_NOTE", "")])
    path = os.path.join(HERE, "scores.tsv")
    new = not os.path.exists(path)
    with open(path, "a") as f:
        if new:
            f.write("when\ttop1\ttop3\tnewer\tasks\tup\tdown\tintent\tsure_wrong\tlearned\tnote\n")
        f.write(line + "\n")


def _save_answers(rows):
    """Ask every fair-test question for real and save the answers for grading by hand."""
    out = os.path.join(asklog.STATE, "checkup-answers-" + time.strftime("%Y-%m-%d") + ".jsonl")
    os.environ["BRAIN_FROM"] = "checkup"
    with open(out, "w") as f:
        for r in rows:
            res = ask.ask(r["q"])
            f.write(json.dumps({"id": r["id"], "use": r["use"], "q": r["q"], "expect": r["expect_answer"],
                                "answer": res["answer"], "writer": res["writer"], "ms": res["ms"]}) + "\n")
            print(f"  {r['id']} {res['writer']:14} {res['ms']:>6} ms  {res['answer'][:90]}")
    print(f"\nAnswers saved for grading: {tilde(out)}")


def main(argv):
    days = int(argv[argv.index("--days") + 1]) if "--days" in argv else 7
    problem = private_list_problem()
    if problem:
        print("!! " + problem + "\n")
    rows = load("heldout.jsonl")
    s = search_score(rows)
    _print_search(s)

    it = None if "--no-intent" in argv else intent_score()
    if it:
        _print_intent(it)
    _print_tuning()

    asks, votes = week(days)
    up, down = _print_week(asks, votes, days)

    learned = None if "--no-learn" in argv else learn(days, "--no-train" not in argv)
    _append_scores(s, it, asks, up, down, learned)

    if "--answers" in argv:
        _save_answers(rows)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
