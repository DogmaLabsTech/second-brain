"""day: what moved today, end of day and the morning standup, from scripts (no model, few words).

A day runs 5:00 to 5:00. End of day (`/eod` in the desk, "end of day" or "goodnight" to the island) ends it
early: work after that is "overnight" and goes to the next morning's standup. Plan: ~/brain/projects/second-brain/docs/history/plan-day-journal.md.

  day.py day [today|yesterday|overnight|YYYY-MM-DD] [--say|--json]
                         the day page (about 20 lines, grouped per project); --say: two spoken sentences
                         as {"message", "speak"}; also saves it in pages/ (searchable, collection "days")
  day.py changed <kind> <what>   one line in the change log (moves, renames, setup changes, by hand or script)
  day.py eod             end of day: say the day's summary, clear ticked items, name the jobs that finished (agent-os's
                         in-tray and history files, read only), tick what may run overnight, close the day, run the
                         ticks (no lock). `goodnight` is the same.
  day.py standup [--once]   the morning standup: spoken + a page; --once: only before 11:00, once a day
  day.py nightly         5:00 (timer): save the folder list and the page of the day that just ended

Data: ~/.local/share/second-brain/day/ (changes.jsonl, closeouts.jsonl, overnight.jsonl, snapshots/). Pages: ~/brain/days/.
Safe test run of eod (nothing said, moved or built for real): BRAIN_DAY_DIR=<tmp> BRAIN_REMEMBER_FILE=<tmp list>
BRAIN_DONE_FILE=<tmp> BRAIN_JOBS_DIR=<tmp> AGENT_OS_BIN=<fake> BRAIN_MORNING_BUILD=<fake>
BRAIN_MORNING_BUILD_STATE=<tmp> BRAIN_DAY_QUIET=1 BRAIN_DAY_TEST_PICKS="1. ,Done".
Sources, read only: git history of <user>'s repos (all branches, so worktrees count), the change log, the folders,
agent-os's in-tray (jobs/in-tray.md, made again by `agent-os intray` at end of day) and history files
(jobs/history/YYYY-MM.md). End of day never moves a job folder: agent-os packs finished jobs itself.
"""
import concurrent.futures as cf
import datetime as dt
import glob
import importlib.machinery
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import time

HOME = os.path.expanduser("~")
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.environ.get("BRAIN_DAY_DIR") or os.path.join(HOME, ".local/share/second-brain/day")
CHANGES = os.path.join(DATA, "changes.jsonl")
CLOSEOUTS = os.path.join(DATA, "closeouts.jsonl")
OVERNIGHT = os.path.join(DATA, "overnight.jsonl")
SNAPS = os.path.join(DATA, "snapshots")
# The pages are notes, so they live in the brain (2026-10-28); a test run with its own BRAIN_DAY_DIR keeps them there.
PAGES = os.environ.get("BRAIN_DAY_PAGES") or (os.path.join(DATA, "pages") if os.environ.get("BRAIN_DAY_DIR")
                                               else os.path.join(HOME, "brain/days"))
DAY_START = 5            # 5 am
STANDUP_BEFORE = 11      # --once does nothing from 11:00 (the 12:00 and 18:00 reminders)
MORNING_BUILD = os.environ.get("BRAIN_MORNING_BUILD") or os.path.join(HOME, ".local/bin/morning-build")
MB_STATE = os.environ.get("BRAIN_MORNING_BUILD_STATE") or os.path.join(HOME, ".local/state/morning-build")
MB_HANDLED = os.path.join(MB_STATE, "handled.tsv")
MB_LOCK = os.path.join(MB_STATE, ".lock")
# End of day moves ticked remember-list items here.
DONE_FILE = os.environ.get("BRAIN_DONE_FILE") or os.path.join(HOME, "brain/inbox/done.md")
# agent-os's jobs folder: end of day and the standup read its in-tray.md and history/ (never write or move in it).
JOBS_DIR = os.environ.get("BRAIN_JOBS_DIR") or os.path.join(HOME, "agent-os/jobs")
AGENT_OS = os.environ.get("AGENT_OS_BIN") or shutil.which("agent-os") or os.path.join(HOME, "agent-os/bin/agent-os")
INTRAY_SECONDS = 60
# For a safe test run of eod: no voice, picks made for you ("1. …,Done").
TEST_QUIET = os.environ.get("BRAIN_DAY_QUIET") == "1"
TEST_PICKS = [p for p in os.environ.get("BRAIN_DAY_TEST_PICKS", "").split(",") if p]
PM = os.path.join(HOME, "projects/project-manager/bin/pm")
ISLAND_SAY = os.path.join(HOME, ".config/omarchy/plugins/user.brain-island/bin/say")
# Folders whose children are watched for "appeared / went away without a note".
WATCHED = ["", "projects", "projects", "projects/experiments", "projects/third-party",
           "projects/assets", "brain", "brain/projects", "brain/business/clients", "Downloads", "_inbox"]
PER_PROJECT = 3          # commit subjects shown per project
SUBJECT = 70             # characters per subject
MAX_PROJECTS = 8         # projects with their own line; the rest share one


# ---------- time ----------

def day_of(ts):
    """The day (a date) a moment belongs to: 5:00 to 5:00."""
    return (dt.datetime.fromtimestamp(ts) - dt.timedelta(hours=DAY_START)).date()


def day_start(d):
    return dt.datetime.combine(d, dt.time(DAY_START)).timestamp()


def closeout(d, path=None):
    """The last goodnight that ended day d, or None."""
    last = None
    for c in read_jsonl(path or CLOSEOUTS):
        if c.get("day") == d.isoformat():
            last = c
    return last


def last_goodnight(now, hours=24, path=None):
    """The newest goodnight in the `hours` before now (bed after 5 am still counts for this morning)."""
    got = [c for c in read_jsonl(path or CLOSEOUTS) if now - hours * 3600 <= c.get("t", 0) <= now]
    return got[-1] if got else None


def window(d, now=None):
    """(start, end, closed) of day d: 5:00 to the next 5:00, or to goodnight, never past now."""
    now = now or time.time()
    c = closeout(d)
    end = c["t"] if c else day_start(d + dt.timedelta(days=1))
    return day_start(d), min(end, now), bool(c)


def clock(ts):
    return dt.datetime.fromtimestamp(ts).strftime("%-I:%M %p").lower().replace(":00 ", " ")


def day_name(d):
    return dt.datetime.combine(d, dt.time()).strftime("%A %b %-d")


# ---------- files ----------

def read_jsonl(path):
    out = []
    try:
        with open(path) as f:
            for line in f:
                try:
                    obj = json.loads(line)
                except ValueError:
                    continue
                if isinstance(obj, dict):
                    out.append(obj)
    except OSError as why:
        if not isinstance(why, FileNotFoundError):   # no file yet just means nothing was written
            print(f"day: could not read {path}: {why}", file=sys.stderr)
    return out


def append_jsonl(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a") as f:
        f.write(json.dumps(obj) + "\n")


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        f.write(text)
    os.replace(tmp, path)


# ---------- sources ----------

def repos():
    """<user>'s git repos: every project and experiment, and the brain."""
    dev = os.path.join(HOME, "projects")
    found = glob.glob(os.path.join(dev, "Projects/*/.git")) + glob.glob(os.path.join(dev, "experiments/*/.git"))
    found += [os.path.join(HOME, "brain/.git")]
    return sorted(os.path.dirname(g) for g in found if os.path.exists(g))


def git_commits(repo, start, end):
    """[(time, subject)] of commits made in [start, end) on any branch of repo, local and remote (worktrees share them; not stashes or backup refs)."""
    fmt = "%Y-%m-%d %H:%M:%S"
    argv = ["git", "-C", repo, "log", "--branches", "--remotes", "--no-merges", "--format=%H%x09%ct%x09%s",
            "--since=" + dt.datetime.fromtimestamp(start).strftime(fmt),
            "--until=" + dt.datetime.fromtimestamp(end).strftime(fmt)]
    try:
        out = subprocess.run(argv, capture_output=True, text=True, timeout=20).stdout
    except (OSError, subprocess.TimeoutExpired):
        return []
    seen, rows = set(), []
    for line in out.splitlines():
        parts = line.split("\t", 2)
        if len(parts) == 3 and parts[0] not in seen and parts[1].isdigit():
            seen.add(parts[0])
            t = int(parts[1])
            if start <= t < end:
                rows.append((t, parts[2].strip()))
    return sorted(rows)


def all_commits(start, end):
    """{repo name: [(time, subject)]}, busiest first."""
    with cf.ThreadPoolExecutor(8) as pool:
        got = dict(zip(repos(), pool.map(lambda r: git_commits(r, start, end), repos())))
    out = {os.path.basename(r): c for r, c in got.items() if c}
    return dict(sorted(out.items(), key=lambda kv: -len(kv[1])))


def logged(start, end):
    return [c for c in read_jsonl(CHANGES) if start <= c.get("t", 0) < end]


def snapshot():
    """The watched folders' children, as sorted 'folder/child' lines (symlinks marked with ' ->')."""
    lines = []
    for rel in WATCHED:
        base = os.path.join(HOME, rel)
        try:
            names = os.listdir(base)
        except OSError:
            continue
        for n in names:
            if n.startswith("."):
                continue
            p = os.path.join(base, n)
            lines.append(os.path.join(rel, n) + (" ->" if os.path.islink(p) else ""))
    return sorted(set(lines))


def save_snapshot(d, overwrite=True):
    path = os.path.join(SNAPS, d.isoformat() + ".txt")
    if overwrite or not os.path.exists(path):
        write(path, "\n".join(snapshot()) + "\n")


def load_snapshot(d):
    try:
        with open(os.path.join(SNAPS, d.isoformat() + ".txt")) as f:
            return [l.rstrip("\n") for l in f if l.strip()]
    except OSError:
        return None


def folder_changes(d, notes, live=False):
    """(appeared, gone) folders on day d with no line in the change log naming them. Compares the list
    kept at the end of the day before with the end of day d (or now, while d is still going)."""
    before = load_snapshot(d - dt.timedelta(days=1))
    after = snapshot() if live else load_snapshot(d)
    if before is None or after is None:
        return [], []
    words = " ".join(str(n.get("what", "")) for n in notes)

    def unnoted(paths):
        return [p for p in paths if os.path.basename(p.removesuffix(" ->")) not in words]
    return unnoted(sorted(set(after) - set(before))), unnoted(sorted(set(before) - set(after)))


# ---------- the day page ----------

def cut(s, n=SUBJECT):
    s = " ".join(s.split())
    return s if len(s) <= n else s[:n - 1].rstrip() + "…"


def gather(start, end, d=None, live=False):
    notes = logged(start, end)
    appeared, gone = folder_changes(d, notes, live) if d else ([], [])
    return {"commits": all_commits(start, end), "notes": notes, "appeared": appeared, "gone": gone}


def _commit_lines(commits):
    n = sum(len(c) for c in commits.values())
    if not n:
        return ["Saved changes: none"]
    lines = [f"Saved changes: {n} in {len(commits)} project{'s' if len(commits) != 1 else ''}"]
    items = list(commits.items())
    for repo, rows in items[:MAX_PROJECTS]:
        newest = [cut(s) for _, s in reversed(rows)][:PER_PROJECT]
        more = f" (+{len(rows) - len(newest)} more)" if len(rows) > len(newest) else ""
        lines.append(f"- {repo} ({len(rows)}): " + "; ".join(newest) + more)
    if len(items) > MAX_PROJECTS:
        lines.append("- also: " + ", ".join(f"{r} ({len(c)})" for r, c in items[MAX_PROJECTS:]))
    return lines


def page(title, g, extra=()):
    lines = [f"# {title}", ""] + _commit_lines(g["commits"])
    if g["notes"]:
        lines += ["", f"Logged changes ({len(g['notes'])}):"]
        lines += [f"- {clock(c['t'])} {c.get('kind', 'change')}: {cut(str(c.get('what', '')), 120)}" for c in g["notes"]]
    if g["appeared"] or g["gone"]:
        lines += ["", "Folders changed without a note:"]
        lines += [f"- new: ~/{p}" for p in g["appeared"]] + [f"- gone: ~/{p}" for p in g["gone"]]
    lines += list(extra)
    return "\n".join(lines).rstrip() + "\n"


def spoken_name(repo):
    return re.sub(r"[-_]+", " ", repo)


def _commit_sentence(when, commits):
    n = sum(len(c) for c in commits.values())
    if not n:
        return f"{when.capitalize()}: no saved changes."
    names = list(commits)
    top = f"most in {spoken_name(names[0])} ({len(commits[names[0]])})" if len(names) > 1 else \
        f"all in {spoken_name(names[0])}"
    rest = ", ".join(spoken_name(r) for r in names[1:4])
    return (f"{when.capitalize()}: {n} saved change{'s' if n != 1 else ''} in {len(names)} "
            f"project{'s' if len(names) != 1 else ''}, {top}" + (f", then {rest}" if rest else "") + ".")


def say_line(when, g):
    commits = g["commits"]
    n = sum(len(c) for c in commits.values())
    if not n and not g["notes"] and not g["appeared"] and not g["gone"]:
        return f"Nothing moved {when}."
    parts = [_commit_sentence(when, commits)]
    if g["notes"]:
        k = len(g["notes"])
        parts.append(f"{k} logged change{'s' if k != 1 else ''}, the last: {cut(str(g['notes'][-1].get('what', '')), 80)}.")
    k = len(g["appeared"]) + len(g["gone"])
    if k:
        parts.append(f"{k} folder{'s' if k != 1 else ''} changed without a note.")
    return " ".join(parts)


def resolve(when, now=None):
    """'today' / 'yesterday' / 'overnight' / a date -> (day or None, start, end, title, spoken name, live)."""
    now = now or time.time()
    today = day_of(now)
    if when == "overnight":
        c = last_goodnight(now)
        start = c["t"] if c else day_start(today)
        return None, start, now, f"Overnight since {clock(start)}", "overnight", False
    if when == "yesterday":
        d = today - dt.timedelta(days=1)
    elif when in ("today", "", None):
        d = today
    else:
        d = dt.date.fromisoformat(when)
    start, end, closed = window(d, now)
    title = f"{day_name(d)} ({clock(start)} to {clock(end)}{', closed out' if closed else ''})"
    spoken = "today" if d == today else "yesterday" if d == today - dt.timedelta(days=1) else day_name(d)
    return d, start, end, title, spoken, d == today


def cmd_day(args):
    when = next((a for a in args if not a.startswith("--")), "today")
    try:
        d, start, end, title, spoken, live = resolve(when)
    except ValueError:
        print(f"day: say today, yesterday, overnight or a date like 2026-10-15, not {when!r}", file=sys.stderr)
        return 2
    g = gather(start, end, d, live)
    text = page(title, g)
    if d:
        write(os.path.join(PAGES, d.isoformat() + ".md"), text)
    if "--say" in args:
        print(json.dumps({"message": say_line(spoken, g), "speak": True}))
    elif "--json" in args:
        print(json.dumps({"title": title, "start": start, "end": end, **g}))
    else:
        print(text, end="")
    return 0


def cmd_changed(args):
    if len(args) < 2 or not " ".join(args[1:]).strip():
        print('usage: brain changed <kind> "<what changed>"   e.g. brain changed move "~/x -> /mnt/backup/home/x"',
              file=sys.stderr)
        return 2
    kind = re.sub(r"[^a-z0-9-]", "", args[0].lower())[:20] or "change"
    what = " ".join(" ".join(args[1:]).split())[:500]
    append_jsonl(CHANGES, {"t": int(time.time()), "kind": kind, "what": what,
                           "by": os.environ.get("BRAIN_CHANGED_BY") or os.path.basename(os.environ.get("_", "")) or "?"})
    return 0


# ---------- talking to <user> ----------

def remind_list():
    return _script_module("remind-list")


def say(text, wait=True):
    """The island speaks (unless muted). wait: until it has finished, so the next voice doesn't talk over it."""
    if TEST_QUIET:
        return
    try:
        muted = remind_list().island_muted()
    except Exception:  # noqa: BLE001
        muted = True
    if muted or not os.access(ISLAND_SAY, os.X_OK):
        return
    argv = [ISLAND_SAY, text]
    if wait:
        try:
            subprocess.run(argv, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=120)
        except (OSError, subprocess.TimeoutExpired) as why:
            print(f"day: could not say the line: {why}", file=sys.stderr)
    else:
        subprocess.Popen(argv, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)


def notify_open(title, body, path):
    """A notification that opens path when clicked (in the background; this returns at once)."""
    script = ('a=$(notify-send -a "Second brain" -i brain -t 3600000 --wait -A default=Open "$1" "$2"); '
              '[ "$a" = default ] && xdg-open "$3"')
    try:
        subprocess.Popen(["sh", "-c", script, "sh", title, body, path], stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, start_new_session=True)
    except OSError as why:
        print(f"day: could not show the notification: {why}", file=sys.stderr)


def _script_module(name):
    """jobs/bin/<name> as a module (those scripts have no .py name)."""
    path = os.path.join(ROOT, "jobs/bin", name)
    sys.path.insert(0, os.path.join(ROOT, "jobs"))
    loader = importlib.machinery.SourceFileLoader(name.replace("-", "_"), path)
    mod = importlib.util.module_from_spec(importlib.util.spec_from_loader(loader.name, loader))
    loader.exec_module(mod)
    return mod


def busy():
    """Names of the Claudes and agent helpers working right now (as the bar and whats-waiting count them)."""
    try:
        return [x["name"] for x in _script_module("whats-waiting").agents() if x["group"] == "working"]
    except Exception:  # noqa: BLE001
        return []


def waiting_line():
    """whats-waiting's own sentence: who needs <user> (Claudes, helpers, PM runs) and who still works."""
    try:
        out = subprocess.run([os.path.join(ROOT, "jobs/bin/whats-waiting")], capture_output=True, text=True, timeout=30)
        return json.loads(out.stdout.strip().splitlines()[-1])["message"]
    except (OSError, ValueError, KeyError, IndexError, subprocess.TimeoutExpired):
        return ""


# ---------- end of day ----------

def pick_overnight(mod, menu=None):
    """<user> ticks remember-list items that may run tonight, one at a time. Returns [(line, date, text)]."""
    if menu is None and TEST_PICKS:
        answers = iter(TEST_PICKS)

        def menu(prompt, options):
            want = next(answers, None)
            return next((o for o in options if want and o.startswith(want)), None)
    menu = menu or mod.menu
    left, picked = list(mod.items())[:12], []
    while left:
        done = f"Done ({len(picked)} picked)" if picked else "Nothing tonight"
        labels = [f"{k + 1}. {mod.short(t, 70)}" for k, (_, _, t) in enumerate(left)]
        got = menu("Run tonight?", [done] + labels)
        if got is None or got == done:
            break
        picked.append(left.pop(labels.index(got)))
    return picked


def mark_overnight(line_no, path):
    """'→ started with Claude overnight <date>' at the end of the line, so the reminder skips it."""
    with open(path) as f:
        lines = f.read().splitlines()
    lines[line_no] += " → started with Claude overnight " + time.strftime("%Y-%m-%d")
    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")


TICKED = re.compile(r"^- \[[xX]\] (?:\d{4}-\d{2}-\d{2}(?: \d{2}:\d{2})?: )?(.+)$")


def clear_ticked(path, done_path, d):
    """Ticked remember-list lines (`- [x] …`) leave the list for the done list. Returns their texts."""
    try:
        lines = open(path).read().splitlines()
    except OSError:
        return []
    keep, done = [], []
    for l in lines:
        m = TICKED.match(l)
        (done if m else keep).append(m.group(1).strip() if m else l)
    if done:
        if not os.path.exists(done_path):
            write(done_path, "# Done\n\nRemember-list items <user> ticked, moved here at end of day (brain eod).\n\n")
        with open(done_path, "a") as f:
            f.writelines(f"- [x] {d.isoformat()}: {t}\n" for t in done)
        write(path, "\n".join(keep) + "\n")
    return done


def refresh_intray():
    """`agent-os intray` makes jobs/in-tray.md again. Quiet: when it fails, the tray as it was is read."""
    env = dict(os.environ, AGENT_OS_HOME=JOBS_DIR)
    try:
        subprocess.run([AGENT_OS, "intray"], capture_output=True, text=True, timeout=INTRAY_SECONDS,
                       stdin=subprocess.DEVNULL, env=env)
    except (OSError, subprocess.SubprocessError):
        pass


DATE_CELL = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _table_rows(path, width):
    """The cells of each table row with `width` cells and a date where agent-os puts one."""
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read()
    except OSError:
        return []
    rows = []
    for raw in text.splitlines():
        if not raw.strip().startswith("|"):
            continue
        cells = [c.strip() for c in raw.strip().strip("|").split("|")]
        if len(cells) == width and DATE_CELL.match(cells[width - 6]):
            rows.append(cells)
    return rows


def _tray(jobs_dir):
    """In-tray rows (state, date, job, ask, result, cost, report) as agent-os writes them (engine/intray.py)."""
    return [r for r in _table_rows(os.path.join(jobs_dir, "in-tray.md"), 7) if r[0] in ("new", "read", "old")]


def _history(jobs_dir):
    """History rows (date, job, ask, result, cost, report) from every jobs/history/YYYY-MM.md."""
    folder = os.path.join(jobs_dir, "history")
    try:
        names = sorted(n for n in os.listdir(folder) if re.match(r"^\d{4}-\d{2}\.md$", n))
    except OSError:
        return []
    return [r for n in names for r in _table_rows(os.path.join(folder, n), 6)]


def finished_jobs(jobs_dir, d, today=None):
    """[(job, result)] that finished on day d, from the in-tray and the history files, each job once. A job that
    finished after midnight (dated up to `today`, the calendar day of the goodnight) counts for d too."""
    last = max(d, today or d).isoformat()
    seen, out = set(), []
    for date, job, result in [(r[1], r[2], r[4]) for r in _tray(jobs_dir)] + \
            [(r[0], r[1], r[3]) for r in _history(jobs_dir)]:
        if d.isoformat() <= date <= last and job not in seen:
            seen.add(job)
            out.append((job, result))
    return out


def new_reports(jobs_dir):
    """How many finished reports in the in-tray <user> has not read yet."""
    return sum(1 for r in _tray(jobs_dir) if r[0] == "new")


def handled_since(text, since):
    """morning-build's verdict on this text, handled at or after `since` (epoch): (verdict, where) or None."""
    try:
        with open(MB_HANDLED) as f:
            rows = [l.rstrip("\n").split("\t") for l in f if l.strip() and not l.startswith("#")]
    except OSError:
        return None
    for r in reversed(rows):
        if len(r) >= 5 and r[4].strip() == text.strip():
            try:
                at = dt.datetime.strptime(r[2], "%Y-%m-%d %H:%M").timestamp()
            except ValueError:
                continue
            if at >= since - 60:
                return r[1], r[3]
    return None


def lock_free():
    import fcntl
    try:
        with open(MB_LOCK, "a") as f:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
            fcntl.flock(f, fcntl.LOCK_UN)
        return True
    except BlockingIOError:
        return False
    except OSError:
        return True


def run_one(text, day):
    """One ticked item through morning-build (Claude in its sandbox; never pushes). Waits while the 6:00 morning
    build holds the lock, and tries again if it was turned away."""
    for _ in range(3):
        waited = 0
        while not lock_free() and waited < 3 * 3600:
            time.sleep(60)
            waited += 60
        t0 = time.time()
        try:
            subprocess.run([MORNING_BUILD, "--note", text, "--limit", "1"], stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, timeout=2 * 3600)
        except (OSError, subprocess.TimeoutExpired) as why:
            got = ("error", str(why)[:200])
        else:
            got = handled_since(text, t0)
        if got:
            break
    got = got or ("not run", "the morning build was busy or failed")
    append_jsonl(OVERNIGHT, {"t": int(time.time()), "day": day, "text": text, "result": got[0], "where": got[1]})


def _start_detached():
    """The island's job runner gives a job 60 s, and the menu waits on <user>: go on in our own unit."""
    argv = [sys.executable, "-I", os.path.abspath(__file__), "eod", "--run"]
    unit = ["systemd-run", "--user", "--collect", "--quiet", f"--unit=second-brain-eod-{int(time.time())}"]
    unit += [f"--setenv={k}" for k in sorted(os.environ) if k.startswith("BRAIN_")]   # the unit starts clean
    try:
        subprocess.run(unit + argv, check=True, timeout=15, capture_output=True)
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        subprocess.Popen(argv, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    print(json.dumps({"message": "Closing out the day. Pick what may run tonight."}))
    return 0


def _tidy_phrase(cleared, finished):
    tidy = []
    if cleared:
        tidy.append(f"{len(cleared)} ticked item{'s' if len(cleared) != 1 else ''} cleared")
    if finished:
        tidy.append(f"{len(finished)} job{'s' if len(finished) != 1 else ''} finished, in your in-tray")
    return " " + " and ".join(tidy) + "." if tidy else ""


def _eod_page_extra(cleared, finished):
    return ([""] if cleared or finished else []) + ([f"- Cleared from the remember list: {', '.join(cut(t, 60) for t in cleared)}"] if cleared else []) + \
        ([f"- Jobs finished today: {', '.join(f'{j} ({cut(r, 60)})' if r else j for j, r in finished)}"] if finished else [])


def _run_overnight(d, running):
    """Keep the computer from sleeping while the ticks run; with helpers already busy, until 7:00 at least."""
    hold_until = dt.datetime.combine(d + dt.timedelta(days=1), dt.time(7)).timestamp() if running else 0
    argv = ["systemd-inhibit", "--what=sleep:idle", "--who=Second brain", "--why=Overnight work",
            sys.executable, "-I", os.path.abspath(__file__), "overnight-run", d.isoformat(), str(int(hold_until))]
    try:
        return subprocess.run(argv).returncode
    except OSError:
        return cmd_overnight_run([d.isoformat(), str(int(hold_until))])


def _flag_value(args, name):
    """The text after `name=` in the arguments, or None."""
    for a in args:
        if a.startswith(name + "="):
            return a.split("=", 1)[1]
    return None


def picks_from_flag(mod, value):
    """--picks=3,7: the open items on those line numbers (the Fire's tick list); an empty value is nothing tonight."""
    want = {int(n) for n in value.split(",") if n.strip().isdigit()}
    return [item for item in mod.items() if item[0] in want]


def cmd_eod(args):
    if "--run" not in args:
        return _start_detached()
    speak = (lambda text, wait=True: None) if "--silent" in args else say   # --silent: no voice (the Fire's button)
    now = time.time()
    d = day_of(now)
    save_snapshot(d)
    start, _, _ = window(d, now)
    g = gather(start, now, d, live=True)
    summary = say_line("today", g)
    mod = remind_list()
    cleared = clear_ticked(mod.PATH, DONE_FILE, d)
    refresh_intray()
    finished = finished_jobs(JOBS_DIR, d, dt.date.fromtimestamp(now))
    speak(summary + _tidy_phrase(cleared, finished), wait=True)
    value = _flag_value(args, "--picks")   # given: the ticks come with the call, no menu to answer
    picked = pick_overnight(mod) if value is None else picks_from_flag(mod, value)
    for line_no, _, _ in picked:
        mark_overnight(line_no, mod.PATH)
    running = busy()
    append_jsonl(CLOSEOUTS, {"t": int(now), "day": d.isoformat(), "picked": [t for _, _, t in picked],
                             "running": running, "cleared": cleared, "finished": [j for j, _ in finished]})
    write(os.path.join(PAGES, d.isoformat() + ".md"),
          page(f"{day_name(d)} ({clock(start)} to {clock(now)}, closed out)", g, _eod_page_extra(cleared, finished)))
    n = len(picked)
    speak("The day is closed. " + (f"{n} thing{'s' if n != 1 else ''} will run tonight. " if n else
                                   "Nothing new runs tonight. ") + "I'll tell you how it went at the standup.", wait=True)
    if not picked and not running:
        return 0
    return _run_overnight(d, running)


cmd_goodnight = cmd_eod   # "goodnight" is the same command


def cmd_overnight_run(args):
    day = args[0]
    c = closeout(dt.date.fromisoformat(day))
    for text in (c or {}).get("picked", []):
        run_one(text, day)
    hold_until = int(args[1]) if len(args) > 1 else 0
    while time.time() < hold_until:
        time.sleep(300)
    return 0


# ---------- standup ----------

RESULTS = {"built:done": "built", "not_idea": "skipped, not something to build", "vague": "skipped, too vague",
           "error": "didn't run (error)", "not run": "didn't run"}


def result_words(r):
    r = str(r)
    return RESULTS.get(r) or ("build failed" if r.startswith("built:") else r)


def _overnight_lines(c, ran):
    """The overnight section: what was ticked and how each came out."""
    if not c:
        return ["- No goodnight last night, so nothing was queued."]
    lines = []
    for t in c.get("picked", []):
        r = next((x for x in ran if x.get("text") == t), None)
        lines.append(f"- {cut(t, 90)}: " + (f"{result_words(r['result'])} ({cut(str(r.get('where', '')), 120)})"
                                             if r else "still running"))
    if c.get("running"):
        lines.append("- Helpers that were busy at bedtime: " + ", ".join(c["running"]))
    if not c.get("picked") and not c.get("running"):
        lines.append("- Nothing was ticked to run.")
    return lines


def _open_item_count():
    try:
        return len(remind_list().items())
    except Exception:  # noqa: BLE001
        return 0


def _standup_spoken(g, c, ran, night, waiting, fresh=0):
    spoken = ["Good morning. " + say_line("yesterday", g)]
    if c and c.get("picked"):
        ok = sum(1 for r in ran if str(r.get("result", "")).startswith("built:done"))
        spoken.append(f"Overnight, {len(c['picked'])} ticked thing{'s' if len(c['picked']) != 1 else ''} ran, "
                      f"{ok} built.")
    n_night = sum(len(x) for x in night["commits"].values())
    if n_night:
        spoken.append(f"Since bedtime: {n_night} saved change{'s' if n_night != 1 else ''}.")
    if waiting:
        spoken.append(waiting)
    if fresh:
        spoken.append(f"{fresh} new report{'s' if fresh != 1 else ''} in your in-tray.")
    return " ".join(spoken)


def standup(now=None):
    """(page text, spoken text) for this morning."""
    now = now or time.time()
    today = day_of(now)
    y = today - dt.timedelta(days=1)
    start, end, closed = window(y, now)
    g = gather(start, end, y)
    write(os.path.join(PAGES, y.isoformat() + ".md"),
          page(f"{day_name(y)} ({clock(start)} to {clock(end)}{', closed out' if closed else ''})", g))
    c = last_goodnight(now)
    night_start = c["t"] if c else day_start(today)
    night = gather(night_start, now)
    ran = [r for r in read_jsonl(OVERNIGHT) if c and r.get("day") == c.get("day")]
    waiting = waiting_line()
    open_items = _open_item_count()
    fresh = new_reports(JOBS_DIR)

    lines = [f"# Standup, {day_name(today)}", ""]
    lines += ["## Yesterday", ""] + page(f"{day_name(y)}", g).splitlines()[2:]
    lines += ["", f"## Overnight (since {clock(night_start)})", ""] + _overnight_lines(c, ran)
    lines += ["", "Since bedtime:"] + page("x", night).splitlines()[2:]
    lines += ["", "## Waiting on you", ""]
    lines.append(f"- {waiting or 'Could not check.'}")
    lines.append(f"- Remember list: {open_items} open item{'s' if open_items != 1 else ''}.")
    lines.append(f"- In-tray: {fresh} new finished report{'s' if fresh != 1 else ''}.")
    return "\n".join(lines) + "\n", _standup_spoken(g, c, ran, night, waiting, fresh)


def cmd_standup(args):
    now = time.time()
    flag = os.path.join(DATA, "standup-done-" + dt.date.today().isoformat())
    if "--once" in args and (os.path.exists(flag) or dt.datetime.now().hour >= STANDUP_BEFORE):
        return 0
    text, spoken = standup(now)
    path = os.path.join(PAGES, "standup-" + dt.date.today().isoformat() + ".md")
    write(path, text)
    write(flag, "")
    if "--print" in args:
        print(text, end="")
        print("\nspoken:", spoken)
        return 0
    say(spoken, wait=True)
    if not TEST_QUIET:
        notify_open("Morning standup", spoken[:300] + "\nClick to read it.", path)
    return 0


def cmd_nightly(args):
    ended = day_of(time.time()) - dt.timedelta(days=1)
    save_snapshot(ended, overwrite=False)     # a goodnight's list stays; else this is the end of the day
    start, end, closed = window(ended)
    write(os.path.join(PAGES, ended.isoformat() + ".md"),
          page(f"{day_name(ended)} ({clock(start)} to {clock(end)}{', closed out' if closed else ''})",
               gather(start, end, ended)))
    return 0


def main(argv):
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    cmds = {"day": cmd_day, "changed": cmd_changed, "eod": cmd_eod, "goodnight": cmd_eod, "standup": cmd_standup,
            "nightly": cmd_nightly, "overnight-run": cmd_overnight_run}
    if argv[0] not in cmds:
        print(f"day: unknown command {argv[0]!r}", file=sys.stderr)
        return 2
    return cmds[argv[0]](argv[1:])


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
