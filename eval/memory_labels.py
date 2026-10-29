"""Label sets for the five memory tasks (agent memory job 9, phase A step 4): rows to train the local decider on later (phase B) and
to measure the second decider and today's word rule against.

  python3 -I eval/memory_labels.py build [--per-task 200]    write eval/labels/<task>.jsonl (+ spot-check-<task>.md)
  python3 -I eval/memory_labels.py ask [--task T]            ask the second decider about every row (REAL calls, decider logs the caller
                                                             memory-labels-<task>) and write the answers into the rows
  python3 -I eval/memory_labels.py report                    accuracy per task: the second decider and the word rule, true-answer rows only

Rows hold private text (<user>'s prompts, notes, job records): eval/labels/ is git-ignored and never leaves this computer
(the second decider sees them only through decider, which removes secrets, emails and names first; this is the ruling of 2026-10-28).
A row: {id, task, state, label, source, rule, second_decider}. `source` says where `label` comes from:
  true-kept-kind     memory-kind: the kept note's own kind (rule | lesson)
  true-draft-pair    memory-same-note "same": a job 7/8 draft and the audited note it became, where the audit reworded it
  true-other-note    memory-same-note "new" and memory-conflict "unrelated": two different kept notes of different projects
                     (conflict) or the same project (same-note), picked at random: different notes, so new / unrelated
  true-same-pair     memory-conflict "agrees": the draft/audited pair above (one idea in two wordings agrees)
  true-proxy         memory-real-task "yes": a first prompt of 8+ words that is not filler (nearly sure, not checked by hand)
  second_decider                no free true answer: the label is the second decider's own answer (not a measure of the second decider: checked by <user>'s spot-check)
`rule` is today's word rule's answer, `second_decider` is the second decider's answer (None = not sure). Seeded, so a rerun gives the same rows.
"""
import json
import os
import random
import re
import sys

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path[:0] = [HERE, os.path.join(ROOT, "ask")]
os.environ.setdefault("BRAIN_MEMORY_DECIDER", "on")
import memory_decide  # noqa: E402
import memory_drafts  # noqa: E402
import memory_flags  # noqa: E402
import memory_hook  # noqa: E402

LABELS = os.path.join(HERE, "labels")
SEED = 20261028
JOBS = os.path.expanduser("~/agent-os/jobs")
TASKS = ["memory-real-task", "memory-same-note", "memory-conflict", "memory-kind", "memory-lesson-worth"]
QUESTION = memory_decide.TASKS


def front_body(path):
    with open(path, encoding="utf-8") as f:
        text = f.read()
    m = re.match(r"---\n(.*?)\n---\n(.*)", text, re.S)
    if not m:
        return {}, text
    fm = {}
    for line in m.group(1).splitlines():
        k, _, v = line.partition(":")
        if v.strip() and not line.startswith(" "):
            fm[k.strip()] = v.strip().strip('"')
    return fm, m.group(2).strip()


def md_files(folder):
    return sorted(os.path.join(d, f) for d, _, fs in os.walk(folder) for f in fs if f.endswith(".md")
                  and f not in ("CONTEXT.md", "README.md"))


def row(task, n, state, label, source, rule):
    return {"id": "%s-%03d" % (task.replace("memory-", ""), n), "task": task, "state": state, "label": label,
            "source": source, "rule": rule, "second_decider": None}


# ---------- the five sets ----------

def kept_notes():
    store = memory_flags.store_path()
    out = []
    for rel, n in memory_flags.all_notes(store).items():
        fm, body = front_body(n["path"])
        out.append({"rel": rel, "project": n["project"], "kind": fm.get("kind", ""), "summary": n["summary"], "body": body})
    return out


def kind_rule(text):
    """A baseline guess for rule vs lesson (the writer guesses today): a standing word means rule, else lesson."""
    return "rule" if re.search(r"\b(never|always|must|only|do not|don't|keep|use|run)\b", text.lower()) else "lesson"


def build_kind(rng, per):
    notes = [n for n in kept_notes() if n["kind"] in ("rule", "lesson")]
    lessons = [n for n in notes if n["kind"] == "lesson"]
    rules = [n for n in notes if n["kind"] == "rule"]
    rng.shuffle(rules)
    picked = lessons[:per // 2] + rules[:per - len(lessons[:per // 2])]
    rng.shuffle(picked)
    return [row("memory-kind", i, (n["summary"] + "\n" + n["body"])[:1500], n["kind"], "true-kept-kind",
                kind_rule(n["summary"] + " " + n["body"])) for i, n in enumerate(picked, 1)]


def audited_pairs():
    """[(draft title+body, audited note's summary, project)] where the audit changed the wording."""
    out = []
    for job in sorted(os.listdir(JOBS)):
        base = os.path.join(JOBS, job)
        for sub in ([""] if os.path.isdir(os.path.join(base, "drafts-audited")) else []) + \
                   [b for b in sorted(os.listdir(base)) if b.startswith("batch")] if os.path.isdir(base) else []:
            drafts_dir, audited = os.path.join(base, sub, "drafts"), os.path.join(base, sub, "drafts-audited")
            if not (os.path.isdir(drafts_dir) and os.path.isdir(audited)):
                continue
            for name in sorted(os.listdir(audited)):
                a, d = os.path.join(audited, name), os.path.join(drafts_dir, name)
                if not (name.endswith(".md") and os.path.isfile(d)):
                    continue
                (fa, _), (fd, bd) = front_body(a), front_body(d)
                if fa.get("summary") and fd.get("summary") and fa["summary"] != fd["summary"]:
                    out.append((fd["summary"], bd[:700], fa["summary"], fa.get("to", "").split("/")[1] if "/" in fa.get("to", "") else ""))
    return out


def build_same(rng, per):
    """Each reworded draft gives a "same" row (against the note it became), a "new" row (against another note of its
    project) and a hard row (against the other note that shares the most words: the second decider's answer only)."""
    pairs, notes, rows = audited_pairs(), kept_notes(), []
    rng.shuffle(pairs)
    by_project = {}
    for n in notes:
        by_project.setdefault(n["project"], []).append(n)
    hard = []
    for title, body, summary, project in pairs:
        rows.append(("same", memory_decide.same_state(title, body, summary), "true-draft-pair",
                     memory_drafts.says_the_same(title, body, {"summary": summary})))
        others = [n for n in by_project.get(project, []) if n["summary"] != summary]
        if others:
            o = rng.choice(others)
            rows.append(("new", memory_decide.same_state(title, body, o["summary"]), "true-other-note",
                         memory_drafts.says_the_same(title, body, {"summary": o["summary"]})))
            want = memory_flags.content_words(title + " " + body)
            best = max(others, key=lambda n: len(want & memory_flags.content_words(n["summary"])))
            hard.append((None, memory_decide.same_state(title, body, best["summary"]), "second_decider",
                         memory_drafts.says_the_same(title, body, {"summary": best["summary"]})))
    rows = (rows + hard)[:per]
    return [dict(row("memory-same-note", i, st, lab, src, None), rule="same" if rule else "new")
            for i, (lab, st, src, rule) in enumerate(rows, 1)]


def build_conflict(rng, per):
    notes, pairs, rows = kept_notes(), audited_pairs(), []
    rng.shuffle(pairs)
    for title, _, summary, _ in pairs[:per // 4]:
        rows.append(("agrees", memory_decide.relation_state(summary, title), "true-same-pair", memory_flags.opposite(summary, title)))
    for _ in range(per // 4):
        a, b = rng.sample(notes, 2)
        if a["project"] != b["project"]:
            rows.append(("unrelated", memory_decide.relation_state(a["summary"], b["summary"]), "true-other-note",
                         memory_flags.opposite(a["summary"], b["summary"])))
    # same project pairs that share words (what the flags look at): no free answer
    cand = []
    for a in notes:
        for b in notes:
            if a["project"] == b["project"] and a["rel"] < b["rel"]:
                shared = memory_flags.content_words(a["summary"]) & memory_flags.content_words(b["summary"])
                if len(shared) >= memory_flags.CONFLICT_SHARED:
                    cand.append((len(shared), a, b))
    cand.sort(key=lambda c: -c[0])
    rng.shuffle(cand[:per * 2])
    for _, a, b in cand[:per * 2]:
        if len(rows) >= per:
            break
        rows.append((None, memory_decide.relation_state(b["summary"], a["summary"]), "second_decider", memory_flags.opposite(a["summary"], b["summary"])))
    return [dict(row("memory-conflict", i, st, lab, src, None), rule="conflicts" if rule else "not-conflict")
            for i, (lab, st, src, rule) in enumerate(rows, 1)]


def first_prompts():
    """The first typed message of Claude Code sessions (private text; stays here)."""
    out, base = [], os.path.expanduser("~/.claude/projects")
    for proj in sorted(os.listdir(base)):
        folder = os.path.join(base, proj)
        for name in sorted(os.listdir(folder)) if os.path.isdir(folder) else []:
            if not name.endswith(".jsonl"):
                continue
            try:
                with open(os.path.join(folder, name), encoding="utf-8") as f:
                    for line in f:
                        ev = json.loads(line)
                        msg = ev.get("message") or {}
                        if ev.get("type") == "user" and not ev.get("isMeta") and msg.get("role") == "user" \
                                and isinstance(msg.get("content"), str):
                            text = " ".join(msg["content"].split())
                            if text and not text.startswith(("<", "Caveat", "[Request interrupted")):
                                out.append(text[:1000])
                            break
            except (OSError, ValueError):
                continue
    return out


def build_real(rng, per):
    texts = sorted(set(first_prompts()))
    rng.shuffle(texts)
    long_ = [t for t in texts if len(t.split()) >= 8][:per * 3 // 5]
    short = [t for t in texts if len(t.split()) < 8]
    fillers = [t for t in short if memory_hook.task_of(t) is None]
    rest = [t for t in short if memory_hook.task_of(t) is not None]
    short = (fillers[:per // 4] + rest)[:per - len(long_)]
    rows = [(t, "yes", "true-proxy") for t in long_] + [(t, None, "second_decider") for t in short]
    rng.shuffle(rows)
    return [row("memory-real-task", i, t, lab, src, "yes" if memory_hook.task_of(t) else "no") for i, (t, lab, src) in enumerate(rows, 1)]


def build_worth(rng, per):
    sys.path.insert(0, os.path.expanduser("~/agent-os"))
    from engine import checking, config, librarian   # read only
    home, rows = config.jobs_home(), []
    folders = [os.path.join(home, "done", d) for d in sorted(os.listdir(os.path.join(home, "done")))] + \
              [os.path.join(home, d) for d in sorted(os.listdir(home)) if d[:2] == "20" and os.path.isdir(os.path.join(home, d))]
    for folder in folders:
        try:
            got, main, worker = checking.folders(folder)
            signals, quote, quoted = librarian.job_signals(got, main, worker)
        except Exception:  # noqa: BLE001  a folder that is not a job
            continue
        if not signals:
            continue
        variants = [signals] + ([[s] for s in signals] if len(signals) > 1 else [])
        for sig in variants:
            title, body = librarian.compose(got.job, sig, quote, quoted)
            rows.append(memory_decide.worth_state(title, body))
    rng.shuffle(rows)
    return [row("memory-lesson-worth", i, st, None, "second_decider", "yes") for i, st in enumerate(rows[:per], 1)]


BUILDERS = {"memory-real-task": build_real, "memory-same-note": build_same, "memory-conflict": build_conflict,
            "memory-kind": build_kind, "memory-lesson-worth": build_worth}


# ---------- files ----------

def path(task):
    return os.path.join(LABELS, task + ".jsonl")


def load(task):
    with open(path(task), encoding="utf-8") as f:
        return [json.loads(line) for line in f]


def save(task, rows):
    os.makedirs(LABELS, exist_ok=True)
    with open(path(task), "w", encoding="utf-8") as f:
        f.write("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
    os.chmod(path(task), 0o600)


def cmd_build(per):
    for task in TASKS:
        rows = BUILDERS[task](random.Random(SEED), per)
        save(task, rows)
        by = {}
        for r in rows:
            by[r["source"]] = by.get(r["source"], 0) + 1
        print("%-20s %3d rows  %s" % (task, len(rows), by))


def cmd_ask(only):
    from concurrent.futures import ThreadPoolExecutor
    for task in [only] if only else TASKS:
        rows = load(task)
        decide = memory_decide._decide()

        def one(r):
            res = decide(task, r["state"], backend="second_decider", timeout=15, caller="memory-labels-" + task.replace("memory-", ""))
            ans = (res.get("answers") or {}).get(QUESTION[task]) if res.get("sure") else None
            r["second_decider"] = ans.get("choice") if isinstance(ans, dict) else None
            return r
        with ThreadPoolExecutor(4) as pool:
            rows = list(pool.map(one, rows))
        for r in rows:
            if r["source"] == "second_decider":
                r["label"] = r["second_decider"]
        save(task, rows)
        print("%-20s asked %d, the second decider not sure on %d" % (task, len(rows), sum(1 for r in rows if r["second_decider"] is None)))


def spot_check(task, rows, n=10):
    rng = random.Random(SEED + 1)
    pool = [r for r in rows if r["source"] == "second_decider"] or rows
    picked = rng.sample(pool, min(n, len(pool)))
    lines = ["# Spot-check: %s (private text, git-ignored)" % task, "",
             "Write your own answer next to each row. Options: %s" % ", ".join(
                 {"memory-real-task": ["yes", "no"], "memory-lesson-worth": ["yes", "no"], "memory-same-note": ["same", "new"],
                  "memory-conflict": ["agrees", "conflicts", "unrelated"], "memory-kind": ["rule", "lesson"]}[task]), ""]
    for r in picked:
        lines += ["## %s  (the second decider: %s, word rule: %s, label from: %s)" % (r["id"], r["second_decider"], r["rule"], r["source"]), "",
                  "```", r["state"][:900], "```", "", "Your answer: ", ""]
    with open(os.path.join(LABELS, "spot-check-%s.md" % task), "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def cmd_report():
    print("%-20s %6s %6s %9s %9s %s" % ("task", "rows", "true", "the second decider right", "rule right", "the second decider not sure"))
    for task in TASKS:
        rows = load(task)
        true = [r for r in rows if r["source"] != "second_decider"]
        sure = [r for r in true if r["second_decider"] is not None]
        second_decider_ok = sum(1 for r in sure if r["second_decider"] == r["label"])

        def rule_ok(r):
            if task == "memory-conflict":     # the word rule only says conflict or not
                return (r["rule"] == "conflicts") == (r["label"] == "conflicts")
            return r["rule"] == r["label"]
        print("%-20s %6d %6d %9s %9s %d" % (task, len(rows), len(true),
              "%d/%d" % (second_decider_ok, len(sure)) if sure else "n/a",
              "%d/%d" % (sum(1 for r in true if rule_ok(r)), len(true)) if true else "n/a",
              sum(1 for r in rows if r["second_decider"] is None)))
        labels = {}
        for r in rows:
            labels[r["label"]] = labels.get(r["label"], 0) + 1
        print("    labels:", dict(sorted(labels.items(), key=lambda kv: str(kv[0]))))


def main(argv):
    cmd = argv[0] if argv else ""
    per = int(argv[argv.index("--per-task") + 1]) if "--per-task" in argv else 200
    if cmd == "build":
        cmd_build(per)
        for t in TASKS:
            spot_check(t, load(t))
    elif cmd == "ask":
        cmd_ask(argv[argv.index("--task") + 1] if "--task" in argv else None)
        for t in TASKS:
            spot_check(t, load(t))
    elif cmd == "report":
        cmd_report()
    else:
        print(__doc__.split("\n\n")[0], file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
