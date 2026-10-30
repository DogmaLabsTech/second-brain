"""tests_week: one page per week of test failures and flaky tests, from agent-os's failure log (no model).

  tests_week.py [YYYY-Www] [--print]   write the page of that week (default: this week); --print also shows it

Sources, read only: ~/agent-os/desk/failures/<repo>.jsonl (one row per failing test per run, a run being one job, commit
and time: when, job, test, sig,
where, outcome new|old|flaky) and ~/agent-os/desk/flaky/<repo>.json (the tests known to fail at random).
Page: ~/brain/days/tests/YYYY-Www.md (collection "days"). The 5:00 `day nightly` run rewrites the week that day
belongs to; a page is always rewritten whole, so a re-run never adds a line twice.
"""
import collections
import datetime as dt
import glob
import json
import os
import sys

HOME = os.path.expanduser("~")
FAILURES = os.environ.get("BRAIN_TESTS_FAILURES") or os.path.join(HOME, "agent-os/desk/failures")
FLAKY = os.environ.get("BRAIN_TESTS_FLAKY") or os.path.join(HOME, "agent-os/desk/flaky")
PAGES = os.environ.get("BRAIN_TESTS_PAGES") or os.path.join(HOME, "brain/days/tests")
TOP = 8                  # tests listed per kind per project
SIG = 100                # characters of a failure's first line


def cut(s, n):
    s = " ".join(str(s or "").split())
    return s if len(s) <= n else s[:n - 1].rstrip() + "…"


def week_of(d):
    y, w, _ = d.isocalendar()
    return f"{y}-W{w:02d}"


def week_days(week):
    monday = dt.datetime.strptime(week + "-1", "%G-W%V-%u").date()
    return monday, monday + dt.timedelta(days=6)


def when(row):
    try:
        return dt.datetime.fromisoformat(row["when"]).date()
    except (KeyError, TypeError, ValueError):
        return None


def failures(week):
    """{repo: [rows of that week]}."""
    out = {}
    for path in sorted(glob.glob(os.path.join(FAILURES, "*.jsonl"))):
        rows = []
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                try:
                    r = json.loads(line)
                except ValueError:
                    continue
                if isinstance(r, dict) and isinstance(r.get("test"), str) and r["test"] and when(r) \
                        and week_of(when(r)) == week:
                    # Only text fields are used; anything else (a list, a dict) counts as missing.
                    rows.append({k: v for k, v in r.items() if isinstance(v, str)})
        if rows:
            out[os.path.basename(path)[:-6]] = rows
    return out


def listed(repo):
    try:
        with open(os.path.join(FLAKY, repo + ".json"), encoding="utf-8") as f:
            tests = json.load(f).get("tests")
    except (OSError, ValueError, AttributeError):
        return []
    if not isinstance(tests, dict):   # a hand-edited list or anything else: no flaky list rather than no page
        return []
    return sorted(t for t, v in tests.items() if isinstance(v, dict) and v.get("listed"))


def page(week, data):
    first, last = week_days(week)
    out = [f"# Tests: week {week} ({first:%-d %b} to {last:%-d %b %Y})", ""]
    if not data:
        return "\n".join(out + ["No test failed this week (agent-os failure log)."]) + "\n"
    total = sum(len(r) for r in data.values())
    runs = {(repo, r.get("job"), r.get("commit"), r.get("when")) for repo, rows in data.items() for r in rows}
    out.append(f"{total} failing test{'s' if total != 1 else ''} in {len(runs)} test run{'s' if len(runs) != 1 else ''}"
               f" across {len(data)} project{'s' if len(data) != 1 else ''} (from agent-os's failure log).")
    for repo, rows in sorted(data.items()):
        by = collections.defaultdict(list)
        for r in rows:
            by[r.get("outcome") or "old"].append(r)
        jobs = sorted({r.get("job") for r in rows if r.get("job")})
        out += ["", f"## {repo}", "", f"- runs with a failure: {len({(r.get('job'), r.get('commit'), r.get('when')) for r in rows})}"
                + (f" (jobs: {', '.join(jobs[:6])}{' …' if len(jobs) > 6 else ''})" if jobs else "")]
        for kind, words in (("new", "new failures"), ("old", "failed again"), ("flaky", "flaky (passed on rerun)")):
            tests = collections.Counter(r["test"] for r in by.get(kind, []))
            if not tests:
                continue
            out.append(f"- {words}:")
            for t, n in tests.most_common(TOP):
                sig = next((r.get("sig") for r in by[kind] if r["test"] == t and r.get("sig")), "")
                where = sorted({r.get("where") for r in by[kind] if r["test"] == t and r.get("where")})
                out.append(f"  - {cut(t, 140)}{f' x{n}' if n > 1 else ''}"
                           + (f" [{', '.join(where)}]" if where else "") + (f": {cut(sig, SIG)}" if sig else ""))
            if len(tests) > TOP:
                out.append(f"  - and {len(tests) - TOP} more")
        known = listed(repo)
        if known:
            out.append(f"- on the flaky list ({len(known)}): " + "; ".join(cut(t, 80) for t in known[:TOP]))
    return "\n".join(out).rstrip() + "\n"


def write_week(week, show=False):
    text = page(week, failures(week))
    path = os.path.join(PAGES, week + ".md")
    os.makedirs(PAGES, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)
    if show:
        print(text, end="")
    return path


def main(argv):
    if argv and argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    week = next((a for a in argv if not a.startswith("--")), week_of(dt.date.today()))
    try:
        week_days(week)
    except ValueError:
        print(f"tests_week: say a week like 2026-W44, not {week!r}", file=sys.stderr)
        return 2
    path = write_week(week, "--print" in argv)
    if "--print" not in argv:
        print(f"tests_week: wrote {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
