"""The agent memory part of the weekly check-up (agent memory job 6, the plan's part 3): one list for <user> and two numbers.

  python3 -I eval/memory_week.py [--days N]      print it (`brain checkup` prints the same block and adds the numbers to its row)

The list, in plain words, each with the command that answers it:
  new drafts      the lesson drafts that wait in the store's drafts/ (keep or drop)
  flags           notes that may be out of date: keep (still right), edit (change the note, then keep) or retire
  pinned notes    pinned notes whose 90-day "still true?" is due
The two numbers (the last N days, default 7; `brain checkup` puts them in scores.tsv):
  repeat count    drafts written in the window with already-known yes and was-pushed yes: a lesson the store already
                  held and the hook pushed, and the agent still hit it again (a repeat got through)
  second-round    desk jobs finished in the window whose check records show `fix: 2` or higher / all desk jobs finished in
  rate            the window. A desk job is a folder in the jobs home (AGENT_OS_HOME, default ~/agent-os/jobs, and its
                  done/ folder); it is finished when one of its check-*.md / review-*.md records says
                  `result: pass` (or a "## Result" heading followed by a pass), counted at that record's time.
Running it also moves old drafts to history/expired-drafts/ (eval/memory_drafts.py expire) and looks for new flags
(eval/memory_flags.py). Tests use a temp store (BRAIN_MEMORY_STORE) and a temp jobs folder. Standard library only.
"""
import os
import re
import sys
import time

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path[:0] = [HERE, os.path.join(ROOT, "ask")]
import memory_drafts  # noqa: E402
import memory_flagfile  # noqa: E402
import memory_flags  # noqa: E402

CHECK = re.compile(r"^(?:check|review)(?:-[0-9a-f]{7,40})?\.md$")
FIX = re.compile(r"^\s*(?:[-*]\s+)?(?:\*\*)?fix(?:\*\*)?\s*:\s*(?:\*\*)?\s*(\d+)", re.I | re.M)
RESULT = re.compile(r"^\s*(?:[-*]\s+)?(?:\*\*)?result(?:\*\*)?\s*:\s*(?:\*\*)?\s*([A-Za-z]+)", re.I | re.M)
RESULT_HEADING = re.compile(r"^#+\s*result\s*\n+\s*(?:[-*]\s+)?(?:\*\*)?([A-Za-z]+)", re.I | re.M)


def jobs_home():
    return os.path.expanduser(os.environ.get("AGENT_OS_HOME") or "~/agent-os/jobs")


# ---------- the numbers ----------

def repeat_count(store, days=7, today=None):
    """Drafts written in the last `days` days that were already known and had been pushed."""
    since = _day_back(today, days)
    return sum(1 for r in memory_drafts.log_rows(store)
               if str(r.get("date", "")) > since and r.get("already_known") == "yes" and r.get("was_pushed") == "yes")


def _day_back(today, days):
    now = time.mktime(time.strptime(today, "%Y-%m-%d")) if today else time.time()
    return time.strftime("%Y-%m-%d", time.localtime(now - days * 86400))


def job_folders(home):
    out = []
    for base in (home, os.path.join(home, "done")):
        try:
            names = sorted(os.listdir(base))
        except OSError:
            continue
        out += [os.path.join(base, n) for n in names if n != "done" and os.path.isdir(os.path.join(base, n))]
    return out


def check_records(folder):
    """[(mtime, fix round or 0, passed)] for the folder's check records."""
    out = []
    try:
        names = sorted(os.listdir(folder))
    except OSError:
        return out
    for name in names:
        if not CHECK.match(name):
            continue
        path = os.path.join(folder, name)
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                text = f.read(20000)
            when = os.path.getmtime(path)
        except OSError:
            continue
        m = RESULT.search(text) or RESULT_HEADING.search(text)
        fix = FIX.search(text)
        out.append((when, int(fix.group(1)) if fix else 0, bool(m and m.group(1).lower().startswith("pass"))))
    return out


def second_round_rate(days=7, today=None, home=None):
    """(jobs finished in the window with fix >= 2, all jobs finished in the window)."""
    now = time.mktime(time.strptime(today, "%Y-%m-%d")) + 86400 if today else time.time()
    since = now - days * 86400
    again = done = 0
    for folder in job_folders(home or jobs_home()):
        records = check_records(folder)
        passed = [r for r in records if r[2] and since <= r[0] < now]
        if passed:
            done += 1
            again += 1 if any(r[1] >= 2 for r in records) else 0
    return again, done


# ---------- the list ----------

def draft_lines(store):
    out = []
    for d in memory_drafts.waiting(store):
        out.append("  new draft %s (%s): %s" % (d["name"], d["date"], d["summary"]))
        out.append("      already known: %s%s, was pushed: %s. Keep: brain drafts keep %s --to <where>. Drop: "
                   "brain memory-drafts drop %s" % (d["already_known"], (" (" + d["same_as"] + ")") if d["same_as"] else "",
                                                    d["was_pushed"], d["name"], d["name"]))
    return out


def flag_lines(result, today=None):
    out = []
    why = {n: s for n, s in memory_flagfile.states(result["store"]).items()}
    for rel, since in sorted(result["flagged"].items()):
        age = memory_flagfile.days_between(since, today)
        out.append("  flag %s (%d days%s): %s" % (rel, age, ", out of the push" if memory_flagfile.lapsed(since, today) else "",
                                                 why.get(rel, {}).get("reason") or "may be out of date"))
        out.append("      Keep: brain memory-flags confirm %s. Edit: change the note, then confirm. Retire: "
                   "brain memory-flags retire %s" % (os.path.basename(rel), os.path.basename(rel)))
    for rel, days in result["pins_due"]:
        out.append("  pinned, still true? last checked %d days ago: %s. Yes: brain memory-flags confirm %s" % (
            days, rel, os.path.basename(rel)))
    return out


def report(days=7, today=None, store=None, home=None):
    """{"lines": [...], "repeats": int, "second_round": (again, done)}; moves old drafts and looks for new flags first."""
    store = memory_drafts.store_path(store)
    if not os.path.isdir(store):
        return {"lines": ["Agent memory: no store at %s" % store], "repeats": None, "second_round": None}
    expired = memory_drafts.expire(store, today)
    found = memory_flags.look(store, today)
    found["store"] = store
    again, done = second_round_rate(days, today, home)
    repeats = repeat_count(store, days, today)
    lines = ["Agent memory for <user>:"] + (draft_lines(store) + flag_lines(found, today) or ["  nothing waits"])
    if expired:
        lines.append("  moved to history/expired-drafts/ (30 days, no keep): " + ", ".join(expired))
    lines.append("  repeats that got through (already known and pushed): %d" % repeats)
    lines.append("  second-round rate (desk jobs finished with fix 2 or more): %d/%d" % (again, done))
    return {"lines": lines, "repeats": repeats, "second_round": (again, done)}


def parse_days(argv, default=7):
    """The number after --days; the default when it is missing or not a number (so a typo never gives a traceback)."""
    if "--days" not in argv:
        return default
    i = argv.index("--days") + 1
    try:
        return max(1, int(argv[i]))
    except (IndexError, ValueError):
        print(f"--days needs a number of days; using {default}", file=sys.stderr)
        return default


def main(argv):
    days = parse_days(argv)
    print("\n".join(report(days)["lines"]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
