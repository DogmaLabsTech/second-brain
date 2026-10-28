"""The agent memory score: how well `brain memory` (ask/memory.py find) puts the right note high for a task.

Two sets of questions (README.md in this folder, "The agent test set"):
  memory-tuning.jsonl   written for the kept notes, in an agent's words: the set to tune on
  memory-heldout.jsonl  real first prompts quoted from run specs: measure only, never tune on it
Each row: {"id", "repo", "task", "want": ["<store path, relative>", ...], "source"}. A row is a hit when any wanted
note is in the top 3 of what `find` returns.

For every row it runs find() against the live search (read only, localhost), twice: with the exact-thing word-search
rule (today's behaviour) and without it (BRAIN_MEMORY_EXACT=0). Two ranks per row, of the first wanted note:
  all       among all returned notes (pinned first, as an agent sees them): the rank the pilot bar uses
  unpinned  among the unpinned notes only: how well the search itself ranks (pinned notes take the top places by design)
A note the push does not list (the 2,000-token budget cut it) counts as one past the last listed note, so a miss
costs something. The mean rank is over all rows with that rule; "missed" counts the rows with no wanted note listed.

  python3 -I eval/memory_score.py [--set tuning|heldout|both] [--rule on|off|both] [--floor] [--detail] [--log "note"]

--floor also scores "no search" (the task is left out, so find returns pinned then newest first): the project's scope
alone. A search is worth only what it adds over this line.

--log adds one row per set and rule to memory-scores.tsv (newest last). The exit code is 0 when it ran.
"""
import argparse
import json
import os
import sys
import time

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "ask"))
import memory  # noqa: E402

LOG = os.path.join(HERE, "memory-scores.tsv")
SHARE = os.path.expanduser("~/.local/share/second-brain/memory-heldout.jsonl")
HEADER = "when\tset\trule\trows\ttop3_all\ttop3_unpinned\tmean_rank_all\tmean_rank_unpinned\tmissed\tnote"
TOP = 3


def set_files():
    """{set name: (file, is_example)}. The real held-out set stays on this computer (it is git-ignored)."""
    held = [(os.path.join(HERE, "memory-heldout.jsonl"), False), (SHARE, False),
            (os.path.join(HERE, "memory-heldout.example.jsonl"), True)]
    held = next(((p, ex) for p, ex in held if os.path.exists(p)), held[-1])
    return {"tuning": (os.path.join(HERE, "memory-tuning.jsonl"), False), "heldout": held}


def load(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def rank_of(listed, want):
    """1-based place of the first wanted note in `listed` (a list of store-relative paths), or None."""
    for i, rel in enumerate(listed, 1):
        if rel in want:
            return i
    return None


def score_row(row, find, store):
    """{"all": rank or None, "unpinned": rank or None, "listed": n} for one question."""
    out = find(row["repo"], row["task"])
    notes = [(os.path.relpath(n["path"], store), bool(n["pinned"])) for n in out["notes"]]
    want = set(row["want"])
    return {"all": rank_of([r for r, _ in notes], want),
            "unpinned": rank_of([r for r, p in notes if not p], want),
            "listed": len(notes), "unpinned_listed": sum(1 for _, p in notes if not p)}


def summarize(results):
    """top-3 hits and mean rank for both rank kinds. A miss counts as one past the last listed note."""
    n = len(results)
    out = {"rows": n, "missed": sum(1 for r in results if r["all"] is None)}
    for kind, listed in (("all", "listed"), ("unpinned", "unpinned_listed")):
        ranks = [r[kind] if r[kind] is not None else r[listed] + 1 for r in results]
        out["top3_" + kind] = sum(1 for r in results if r[kind] is not None and r[kind] <= TOP)
        out["mean_rank_" + kind] = round(sum(ranks) / n, 2) if n else 0.0
    return out


def run_set(rows, find, store, rule_on):
    """Score every row with the exact-thing rule on or off. Returns (per-row results, summary)."""
    old = os.environ.get("BRAIN_MEMORY_EXACT")
    os.environ["BRAIN_MEMORY_EXACT"] = "1" if rule_on else "0"
    try:
        results = [score_row(r, find, store) for r in rows]
    finally:
        if old is None:
            os.environ.pop("BRAIN_MEMORY_EXACT", None)
        else:
            os.environ["BRAIN_MEMORY_EXACT"] = old
    return results, summarize(results)


def no_search(find):
    """find with the task left out: pinned, then the scope's newest notes (the floor a search must beat)."""
    return lambda repo, task: find(repo, None)


def log_row(name, rule_on, s, note, when=None):
    rule = "none" if rule_on is None else "on" if rule_on else "off"
    return "\t".join([when or time.strftime("%Y-%m-%d %H:%M"), name, rule, str(s["rows"]),
                      f"{s['top3_all']}/{s['rows']}", f"{s['top3_unpinned']}/{s['rows']}",
                      str(s["mean_rank_all"]), str(s["mean_rank_unpinned"]), str(s["missed"]), note])


def append_log(lines, path=None):
    path = path or LOG
    new = not os.path.exists(path) or os.path.getsize(path) == 0
    with open(path, "a", encoding="utf-8") as f:
        if new:
            f.write(HEADER + "\n")
        f.write("".join(l + "\n" for l in lines))


def main(argv, find=None):
    ap = argparse.ArgumentParser(prog="memory_score.py", description="Score the agent memory search.")
    ap.add_argument("--set", choices=("tuning", "heldout", "both"), default="both")
    ap.add_argument("--rule", choices=("on", "off", "both"), default="both", help="the exact-thing word-search rule")
    ap.add_argument("--floor", action="store_true", help="also score no search (the scope's newest notes)")
    ap.add_argument("--detail", action="store_true", help="one line per question")
    ap.add_argument("--log", metavar="NOTE", help="add the rows to memory-scores.tsv with this note")
    args = ap.parse_args(argv)
    find = find or memory.find
    store = memory.store_path()
    files = set_files()
    names = ("tuning", "heldout") if args.set == "both" else (args.set,)
    rules = {"on": (True,), "off": (False,), "both": (True, False)}[args.rule] + ((None,) if args.floor else ())
    lines = []
    for name in names:
        path, example = files[name]
        rows = load(path)
        if example:
            print(f"NOTE: the real held-out set is not on this computer; scoring the {len(rows)}-row example file.")
        for rule_on in rules:
            results, s = run_set(rows, find if rule_on is not None else no_search(find), store, bool(rule_on))
            print(f"{name:8} rule {'none' if rule_on is None else 'on ' if rule_on else 'off'}  rows {s['rows']:2}  "
                  f"top 3: {s['top3_all']}/{s['rows']} (all) {s['top3_unpinned']}/{s['rows']} (unpinned)  "
                  f"mean rank: {s['mean_rank_all']} (all) {s['mean_rank_unpinned']} (unpinned)  missed {s['missed']}")
            if args.detail:
                for row, r in zip(rows, results):
                    print(f"   {row['id']:46} all {r['all'] or '-':>2}  unpinned {r['unpinned'] or '-':>2}")
            lines.append(log_row(name + ("-example" if example else ""), rule_on, s, args.log or ""))
    if args.log is not None:
        append_log(lines)
        print(f"Added {len(lines)} row(s) to {os.path.relpath(LOG)}.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
