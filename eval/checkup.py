"""brain checkup: the weekly check-up (eval/README.md, docs/checkup.md).

  brain checkup              fair test score (search) + this week's questions, 👍/👎, speed, who wrote
                             (first: is the index keeping up? warns when a collection is 24 h+ behind its folder or the test machine Codex embed failed)
  brain checkup --answers    also asks every fair-test question for real (slow; Haiku may help) and
                             saves the answers for grading by hand in the check-up
  brain checkup --days N     look back N days instead of 7
  brain checkup --no-intent  skip the intent fair test (the local decider, through the decider service, ~15 s)
  brain checkup --no-learn   skip learning from the week's likely misses (Haiku and the second decider label them)
  brain checkup --no-train   find misses, but don't start a training round even with 30+ new examples
  brain checkup --no-drafts  skip the drafts for <user> (test questions and lore stories from the week's signals)
  brain checkup --auto       what the Monday timer runs (eval/remind.sh): everything above with --no-learn --no-train
                             (no online labelling, no training round without <user>), the report saved to
                             ~/.local/state/second-brain/checkups/DATE.txt, the score row added to scores.tsv (note
                             "auto"), the result compared with the last run, and a desktop notice with the flags

Every run also marks answers that were asked again within 10 minutes as 👎 on its own (eval/drafts.py `auto_rate`;
`brain rate <id> up` undoes one).

Scores are written to eval/scores.tsv (one line per run), so each week can be compared with the last.
"""
import contextlib
import io
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
sys.path.insert(0, os.path.join(ROOT, "index"))
import ask  # noqa: E402
import asklog  # noqa: E402
import freshness  # noqa: E402
import drafts  # noqa: E402

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
    """Plain words when deciders/private.json exists but is empty, broken or unreadable (then brain-decide and
    Haiku send nothing online until it is fixed: deciders/private_guard.py); None when it is fine or not there."""
    path = path or os.path.join(DECIDERS, "private.json")
    if DECIDERS not in sys.path:
        sys.path.append(DECIDERS)
    import private_guard
    return private_guard.problem(path)


def freshness_lines(report=None):
    """The index freshness part of the check-up (index/freshness.py): warnings when a collection is more than 24 h
    behind its folder or the test machine Codex embed failed, and the collections to retire. [] when all is well."""
    report = report or freshness.check()
    lines = ["!! " + w for w in report["warnings"]]
    lines += [f"-- to retire (not deleted): {n}: {why}" for n, why in report["retire"]]
    return lines


def drafts_lines(days):
    """The drafts part of the check-up (eval/drafts.py): draft test questions and lore stories from the week's
    signals, for <user> to keep or drop, and up to 3 asks worth rating. Writes only inside the drafts folders."""
    try:
        return drafts.lines(drafts.run(days))
    except Exception as why:   # a draft problem must never lose the score row
        return [f"Drafts for <user>: couldn't make them ({why})"]


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


def _try(problems, what, fn, default=None):
    """Run one part of the check-up; if it breaks, say so in plain words and go on (one broken part must not lose the
    score row). The sentence also goes into `problems`, which the --auto flags show."""
    try:
        return fn()
    except Exception as why:
        problems.append(f"{what} didn't run ({type(why).__name__}: {str(why)[:120]})")
        print("!! " + problems[-1] + "\n")
        return default


def auto_mark(days):
    """Answers asked again within 10 minutes count as 👎 (drafts.auto_rate). Says so only when it marked some."""
    marked = drafts.auto_rate(days)
    if marked:
        print(f"Asked again within 10 minutes, marked 👎 on its own: {len(marked)} "
              f"(press `brain rate <id> up` if the first answer was fine)\n")
    return marked


def run(argv):
    """The check-up. Returns (exit code, summary) where the summary is what --auto needs for its flags."""
    auto = "--auto" in argv
    if auto:   # unattended: nothing goes to an online model and no training round starts without <user>
        argv = list(argv) + ["--no-learn", "--no-train"]
    days = int(argv[argv.index("--days") + 1]) if "--days" in argv else 7
    problems = []
    problem = private_list_problem()
    if problem:
        print("!! " + problem + "\n")
    fresh = _try(problems, "The freshness look", freshness_lines, [])
    if fresh:
        print("Index freshness:\n  " + "\n  ".join(fresh) + "\n")
    rows = load("heldout.jsonl")
    s = search_score(rows)
    _print_search(s)

    it = None if "--no-intent" in argv else _try(problems, "The intent fair test", intent_score)
    if it:
        _print_intent(it)
    _try(problems, "The tuning set", _print_tuning)

    marked = _try(problems, "Marking re-asked answers", lambda: auto_mark(days), [])
    asks, votes = week(days)
    up, down = _print_week(asks, votes, days)

    learned = None if "--no-learn" in argv else learn(days, "--no-train" not in argv)
    if "--no-drafts" not in argv:   # after learning, so this week's new likely misses are in misses.jsonl
        block = drafts_lines(days)
        if block:
            print("\n" + "\n".join(block))
    prev = previous_row()
    if auto and not os.environ.get("CHECKUP_NOTE"):
        os.environ["CHECKUP_NOTE"] = "auto"
    _append_scores(s, it, asks, up, down, learned)

    if "--answers" in argv:
        _save_answers(rows)
    summary = {"s": s, "it": it, "asks": len(asks), "up": len(up), "down": len(down), "marked": len(marked or []),
               "prev": prev, "problem": problem, "fresh": [f for f in fresh if f.startswith("!!")],
               "problems": problems, "days": days}
    return 0, summary


def main(argv):
    return run(argv)[0]


# ---------- the unattended run (the Monday timer) ----------

def ratio(text):
    """'7/34' -> (7, 34); None for '-' or anything else."""
    try:
        a, b = str(text).split("/")
        return int(a), int(b)
    except ValueError:
        return None


def previous_row(path=None):
    """The last row of scores.tsv (the one before this run's) as a dict, or None."""
    path = path or os.path.join(HERE, "scores.tsv")
    try:
        with open(path) as f:
            lines = [l.rstrip("\n").split("\t") for l in f if l.strip()]
    except OSError:
        return None
    if len(lines) < 2:
        return None
    head = lines[0]
    return dict(zip(head, lines[-1]))


def flags(sm, prev_misses=None):
    """Plain-word flags for the notice: a lower fair-test score than the last row, newly missed questions, 👎 (and
    how many were marked on their own), 'sure and wrong' router answers, warnings, parts that broke, a week with no
    asks. [] when all is well."""
    s, out = sm["s"], []
    prev = sm.get("prev") or {}
    now_scores = {"top3": (s["top3"], s["n"]), "top1": (s["top1"], s["n"]), "newer": (s["newer_ok"], s["newer_n"])}
    for key, label in (("top3", "right note in the top 3"), ("top1", "right note first"), ("newer", "newer note wins")):
        was, now = ratio(prev.get(key)), now_scores[key]
        if was and was[1] == now[1] and now[0] < was[0]:
            out.append(f"{label} fell from {was[0]}/{was[1]} to {now[0]}/{now[1]}")
    if prev_misses is not None:
        new = sorted({m[0] for m in s["misses"]} - set(prev_misses))
        if new:
            out.append(f"newly missed in the fair test: {', '.join(new)}")
    it = sm.get("it")
    if it and it.get("sure_wrong"):
        out.append(f"the router was sure and wrong {it['sure_wrong']}/{it['n']} times")
    if sm["down"]:
        out.append(f"{sm['down']} 👎 in {sm['days']} days" + (f" ({sm['marked']} marked on their own because they were asked again)" if sm["marked"] else ""))
    if sm.get("problem"):
        out.append("the private names list has a problem (nothing goes online until it is fixed)")
    out += [w.lstrip("! ") for w in sm.get("fresh", [])]
    out += sm.get("problems", [])
    if not sm["asks"]:
        out.append(f"no asks in {sm['days']} days (nothing to learn from; is anything logging them?)")
    return out


def checkups_dir():
    d = os.path.join(asklog.STATE, "checkups")
    os.makedirs(d, mode=0o700, exist_ok=True)
    return d


def _last_miss_ids(today):
    """The fair-test miss ids saved by the previous --auto run (today's file is only overwritten after this read), or None."""
    d = checkups_dir()
    olds = sorted(f for f in os.listdir(d) if f.endswith(".json") and f[:-5] <= today)
    if not olds:
        return None
    try:
        with open(os.path.join(d, olds[-1])) as f:
            return json.load(f).get("miss_ids")
    except (OSError, ValueError):
        return None


def notify(title, body):
    try:
        subprocess.run(["notify-send", "-a", "Second brain", "-i", "brain", title, body], timeout=10, check=False)
    except (OSError, subprocess.TimeoutExpired):
        pass   # no desktop (or no notify-send): the saved report still has everything


def auto_main(argv):
    """`brain checkup --auto`: run the check-up, save the report and the miss ids, tell <user> the result."""
    today = time.strftime("%Y-%m-%d")
    buf = io.StringIO()
    real = sys.stdout

    class Tee:
        def write(self, text):
            real.write(text)
            buf.write(text)

        def flush(self):
            real.flush()

    try:
        with contextlib.redirect_stdout(Tee()):
            code, sm = run(argv)
    except Exception as why:   # no score row was made: say so, so the gap is never silent again
        msg = f"The Monday check-up did not run: {type(why).__name__}: {str(why)[:160]}"
        print("!! " + msg, file=sys.stderr)
        with open(os.path.join(checkups_dir(), today + ".txt"), "a") as f:
            f.write(buf.getvalue() + "\n!! " + msg + "\n")
        notify("Brain check-up failed", msg)
        return 3   # remind.sh: already told <user>
    flagged = flags(sm, _last_miss_ids(today))
    report = os.path.join(checkups_dir(), today + ".txt")
    s = sm["s"]
    summary = (f"Fair test: right note first {s['top1']}/{s['n']}, in top 3 {s['top3']}/{s['n']}, newer wins "
               f"{s['newer_ok']}/{s['newer_n']}. Week: {sm['asks']} asks, 👎 {sm['down']}.")
    tail = ["", "Flags:"] + ["  - " + f for f in flagged] if flagged else ["", "Flags: none"]
    with open(report, "w") as f:
        f.write(buf.getvalue() + "\n" + summary + "\n" + "\n".join(tail) + "\n")
    os.chmod(report, 0o600)
    with open(os.path.join(checkups_dir(), today + ".json"), "w") as f:
        json.dump({"top1": s["top1"], "top3": s["top3"], "n": s["n"], "miss_ids": [m[0] for m in s["misses"]]}, f)
    print("\n" + summary + "\n" + "\n".join(tail))
    notify("Brain check-up done" + (" - look at this" if flagged else ""),
           summary + ("\nFlags: " + "; ".join(flagged) if flagged else "\nAll quiet.") +
           "\nReport: " + tilde(report) + ". Type /brain-checkup in Claude to fix what it found.")
    return code


if __name__ == "__main__":
    argv = sys.argv[1:]
    sys.exit(auto_main(argv) if "--auto" in argv else main(argv))
