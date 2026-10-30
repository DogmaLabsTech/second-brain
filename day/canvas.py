"""canvas: the nodeterm board log as a day page per day (who finished, failed or asked, cards moved, messages lost).

  canvas.py run [--quiet]      copy new board events and agents' "finished" notes into the archive, save the node
                               names nodeterm shows now, rewrite the canvas page of every day that got something new
  canvas.py names --backlog    also find old node names in Claude chat logs (the rename calls); slow, run once
  canvas.py line YYYY-MM-DD    the one line the day page shows ("Canvas: 23 finished, 4 failed, ...")

Sources, read only: each board's .nodeterm/board-log.jsonl and project.json (node titles), and nodeterm's status file
(the inbox keeps agents' "finished" notes and questions for a few hours only, so the hourly reindex runs this).
Archive: ~/.local/share/second-brain/canvas/ (events.jsonl, names.json); events are kept by id, so a re-run never
adds a line twice and a trimmed board log loses nothing. Pages: ~/brain/days/canvas/YYYY-MM-DD.md (collection "days").
A day runs 5:00 to 5:00, as on the day page. No model, nothing leaves this computer.
"""
import collections
import datetime as dt
import fcntl
import glob
import json
import os
import re
import sys

HOME = os.path.expanduser("~")
DATA = os.environ.get("BRAIN_CANVAS_DIR") or os.path.join(HOME, ".local/share/second-brain/canvas")
PAGES = os.environ.get("BRAIN_CANVAS_PAGES") or os.path.join(HOME, "brain/days/canvas")
STATUS = os.environ.get("BRAIN_CANVAS_STATUS") or os.path.join(HOME, ".config/node-terminal/agent-status.json")
# Every board with a .nodeterm folder (agent-os is the main one); BRAIN_CANVAS_BOARDS: folders split by ":".
BOARD_GLOBS = ["agent-os/.nodeterm", "nodeterm/.nodeterm", "projects/.nodeterm", "projects/*/.nodeterm"]
JOB_GLOBS = ["agent-os/jobs/*/*.md", "agent-os/desk/inbox/*.md"]
CHAT_GLOBS = [".config/node-terminal/claude-accounts/*/projects/*/*.jsonl", ".claude/projects/*/*.jsonl"]
DAY_START = 5
TS_MIN, TS_MAX = 946684800000, 4102444800000   # 2000 to 2100, in ms: anything else is a broken line
SAID = 160               # characters of an agent's "finished" note
OK_MESSAGES = {"delivered", "queued", "targetBusy"}   # busy is queued and tried again; the rest never arrived
PROBLEM_WORDS = {"expired": "expired", "notPermitted": "not allowed", "rateLimited": "rate limited",
                 "targetStatusStale": "target status stale", "targetHookScriptStale": "target hook stale",
                 "targetNotIdleUnknown": "target state unknown"}
FAIL_WORDS = {"turn-errored": "stopped with an error", "question-unanswered": "waited on a question nobody answered"}
# Old names in chat logs: a rename call, or a line of `nodeterm.sh list` ("term-… [terminal] OVERSEER @ -144,-2256").
RENAME = re.compile(r'rename[^\n]{0,40}?(term-[a-z0-9]{5,10}-[0-9a-f]{8})[^\n"\\]{0,12}(?:\\"|")([^"\\]{3,80})')
# In agent-os job notes: "fresh core builder: term-…" or "MAIN 3 (`term-…`)"; the last few words before the id.
NOTED = re.compile(r'([A-Za-z][\w·\- ]{1,40}?)(?::\s*|\s*\((?:canvas node\s*)?)`?(term-[a-z0-9]{5,10}-[0-9a-f]{8})`?')
FILLER = {"to", "by", "written", "the", "a", "old", "from", "and", "started", "armed", "opened", "is", "was", "tell",
          "message", "report", "node"}
LISTED = re.compile(r'(term-[a-z0-9]{5,10}-[0-9a-f]{8}) \[terminal\] ([^@\\\n]{2,80}?) @ -?\d')


# ---------- small helpers ----------

def day_of(ms):
    return (dt.datetime.fromtimestamp(ms / 1000) - dt.timedelta(hours=DAY_START)).date()


def clock(ms):
    return dt.datetime.fromtimestamp(ms / 1000).strftime("%H:%M")


def cut(s, n):
    s = " ".join(str(s or "").split())
    return s if len(s) <= n else s[:n - 1].rstrip() + "…"


def read_jsonl(path):
    out = []
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                try:
                    obj = json.loads(line)
                except ValueError:
                    continue
                if isinstance(obj, dict):
                    out.append(obj)
    except FileNotFoundError:
        pass
    return out


def read_json(path, default):
    """The file's JSON when it has the same shape as default (a dict or a list), else default."""
    try:
        with open(path, encoding="utf-8") as f:
            got = json.load(f)
    except (OSError, ValueError):
        return default
    return got if isinstance(got, type(default)) else default


def good_ts(v):
    """A board time in ms, or None for a missing, odd or impossible one (NaN, 1e100, a string)."""
    if isinstance(v, bool) or not isinstance(v, (int, float)) or v != v or not TS_MIN <= v <= TS_MAX:
        return None
    return int(v)


def text(v):
    return v if isinstance(v, str) else ""


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)


def boards():
    env = os.environ.get("BRAIN_CANVAS_BOARDS")
    dirs = env.split(":") if env else [d for g in BOARD_GLOBS for d in sorted(glob.glob(os.path.join(HOME, g)))]
    return [d for d in dirs if os.path.isdir(d)]


def board_name(folder):
    return os.path.basename(os.path.dirname(os.path.abspath(folder)))


# ---------- names ----------

def load_names():
    return read_json(os.path.join(DATA, "names.json"), {})


def save_names(names):
    write(os.path.join(DATA, "names.json"), json.dumps(dict(sorted(names.items())), indent=1, ensure_ascii=False) + "\n")


def current_names(folders):
    """The titles nodeterm shows now, for every board."""
    out = {}
    for folder in folders:
        nodes = read_json(os.path.join(folder, "project.json"), {}).get("nodes")
        for n in nodes if isinstance(nodes, list) else []:
            if isinstance(n, dict) and isinstance(n.get("id"), str) and isinstance(n.get("title"), str) \
                    and n.get("kind") != "group":
                out[n["id"]] = n["title"]
    return out


def backlog_names():
    """Old names from Claude chat logs: the last `nodeterm.sh rename --node <id> --title "..."` seen per node."""
    files = [f for g in CHAT_GLOBS for f in glob.glob(os.path.join(HOME, g))]
    files.sort(key=lambda f: os.path.getmtime(f))
    out = {}
    for f in files:
        try:
            with open(f, encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    if "term-" not in line:
                        continue
                    for pat in (LISTED, RENAME) if "rename" in line else (LISTED,):
                        for m in pat.finditer(line):
                            out[m.group(1)] = m.group(2).strip()
        except OSError:
            continue
    return out


def job_names():
    """Names agent-os job notes give node ids, with the job's short name: "core builder (one-brain)"."""
    out = {}
    files = sorted(f for g in JOB_GLOBS for f in glob.glob(os.path.join(HOME, g)))
    for f in files:
        job = re.sub(r"^\d{8}(-\d{4})?-", "", os.path.basename(os.path.dirname(f)))
        try:
            with open(f, encoding="utf-8", errors="replace") as fh:
                text = fh.read()
        except OSError:
            continue
        for m in NOTED.finditer(text):
            words = m.group(1).split()[-4:]
            while words and words[0].lower() in FILLER:
                words = words[1:]
            while words and words[-1].lower() in FILLER:
                words = words[:-1]
            if words and m.group(2) not in out:
                label = " ".join(words)
                out[m.group(2)] = label if job == "inbox" else f"{label} ({job})"
    return out


def name(names, node):
    """The node's title, else "agent <short id>"."""
    if not node:
        return "someone"
    return names.get(node) or "agent " + short_id(node)


def short_id(node):
    parts = node.split("-")
    return parts[1] if node.startswith("term-") and len(parts) >= 3 else node


# ---------- archive ----------

def board_events(folder):
    b = board_name(folder)
    for r in read_jsonl(os.path.join(folder, "board-log.jsonl")):
        e, ts = r.get("event"), good_ts(r.get("ts"))
        if isinstance(r.get("id"), str) and ts and isinstance(e, dict) and isinstance(e.get("type"), str):
            node = r.get("nodeId") if isinstance(r.get("nodeId"), str) else None
            yield {"id": r["id"], "ts": ts, "board": b, "node": node,
                   "event": {k: v for k, v in e.items() if isinstance(v, str)}}   # only text fields are used


def status_notes(path=None):
    """Agents' "finished" notes and questions from nodeterm's status file (kept there for a few hours)."""
    inbox = read_json(path or STATUS, {}).get("inbox")
    events = inbox.get("events") if isinstance(inbox, dict) else None
    for r in events if isinstance(events, list) else []:
        if not isinstance(r, dict) or not isinstance(r.get("id"), (str, int)) or not good_ts(r.get("ts")):
            continue
        kind = {"done": "agent-done", "question": "agent-asked"}.get(r.get("kind"))
        if kind:
            yield {"id": "status-" + str(r["id"]), "ts": good_ts(r["ts"]), "board": "nodeterm",
                   "node": r.get("nodeId") if isinstance(r.get("nodeId"), str) else None,
                   "event": {"type": kind, "title": text(r.get("title")), "detail": text(r.get("detail"))}}


def archive_path():
    return os.path.join(DATA, "events.jsonl")


def read_archive():
    """The archive, each event once (by id), broken lines left out."""
    out, seen = [], set()
    for r in read_jsonl(archive_path()):
        ts = good_ts(r.get("ts"))
        if r.get("id") in seen or not ts or not isinstance(r.get("event"), dict):
            continue
        seen.add(r["id"])
        out.append(r)
    return out


def add_to_archive(new):
    """Append events not seen before (the caller holds the lock); returns the days that got something."""
    path = archive_path()
    seen = {r.get("id") for r in read_archive()}
    days = set()
    fresh = []
    for r in new:
        if r["id"] in seen:
            continue
        seen.add(r["id"])
        fresh.append(r)
        days.add(day_of(r["ts"]))
    if fresh:
        os.makedirs(DATA, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            for r in sorted(fresh, key=lambda r: r["ts"]):
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return days, len(fresh)


def events_of(d, archive=None):
    rows = archive if archive is not None else read_archive()
    return sorted((r for r in rows if day_of(r["ts"]) == d), key=lambda r: (r["ts"], r["id"]))


# ---------- the page ----------

def tally(rows):
    t = collections.Counter()
    for r in rows:
        e = r["event"]
        typ, to = e.get("type"), e.get("to")
        if typ == "station-reported":
            t["finished" if to == "succeeded" else "failed"] += 1
        elif typ == "station-failed":
            t["failed"] += 1
        elif typ == "agent-asked":
            t["asked"] += 1
        elif typ == "agent-message":
            t["arrived" if e.get("title") in OK_MESSAGES else "lost"] += 1
        elif typ == "card-moved":
            t["moved"] += 1
    return t


def line(d, archive=None):
    """The day page's one line, or "" when the canvas was quiet."""
    t = tally(events_of(d, archive))
    if not t:
        return ""
    bits = [f"{t['finished']} finished", f"{t['failed']} failed"]
    if t["asked"]:
        bits.append(f"{t['asked']} asked you")
    bits.append(f"{t['lost']} message{'s' if t['lost'] != 1 else ''} lost")
    return f"Canvas: {', '.join(bits)} (days/canvas/{d.isoformat()}.md)"


def timeline_line(r, names):
    e, who = r["event"], name(names, r["node"])
    typ, to = e.get("type"), e.get("to")
    at = clock(r["ts"])
    if typ == "station-reported":
        return f"- {at} {name(names, e.get('from') or r['node'])}: " + ("finished" if to == "succeeded" else f"reported {to}")
    if typ == "station-failed":
        return f"- {at} {name(names, e.get('from') or r['node'])}: {FAIL_WORDS.get(to, to)}"
    if typ == "agent-done":
        return f"- {at} {who} said when done: \"{cut(e.get('detail') or e.get('title'), SAID)}\""
    if typ == "agent-asked":
        return f"- {at} {who} asked you: \"{cut(e.get('title'), SAID)}\""
    if typ == "card-moved":
        return f"- {at} card {who} moved {e.get('from', '?')} -> {to}"
    if typ == "card-created":
        return f"- {at} card {cut(e.get('title'), 60)} added to {to}"
    if typ == "priority-set":
        return f"- {at} card {who} set to {to}"
    if typ in ("column-added", "column-deleted"):
        return f"- {at} column {cut(e.get('title'), 40)} {typ.split('-')[1]}"
    if typ == "column-renamed":
        return f"- {at} column {cut(e.get('from'), 40)} renamed to {cut(to, 40)}"
    return None   # messages are summed below, not listed


def page(d, rows, names):
    t = tally(rows)
    title = dt.datetime.combine(d, dt.time()).strftime("%A %-d %B %Y")
    per_board = collections.Counter(r["board"] for r in rows)
    out = [f"# Canvas: {title}", "",
           f"Agents on the nodeterm canvas, 5:00 to 5:00. Finished {t['finished']} · failed {t['failed']} · "
           f"asked you {t['asked']} · cards moved {t['moved']} · messages {t['arrived']} arrived, {t['lost']} lost",
           "Boards: " + ", ".join(f"{b} ({n})" for b, n in per_board.most_common()), "", "## Timeline", ""]
    lines = [x for x in (timeline_line(r, names) for r in rows) if x]
    out += lines or ["- nothing but messages"]
    lost = collections.defaultdict(list)
    for r in rows:
        e = r["event"]
        if e.get("type") == "agent-message" and e.get("title") not in OK_MESSAGES:
            lost[(e.get("from"), e.get("to") or r["node"])].append(r)
    if lost:
        out += ["", "## Messages that never arrived", ""]
        for (a, b), rs in sorted(lost.items(), key=lambda kv: kv[1][0]["ts"]):
            why = collections.Counter(PROBLEM_WORDS.get(r["event"].get("title"), r["event"].get("title") or "unknown")
                                      for r in rs)
            first, last = clock(rs[0]["ts"]), clock(rs[-1]["ts"])
            span = first if first == last else f"{first}-{last}"
            out.append(f"- {span} {name(names, a)} -> {name(names, b)}: "
                       + ", ".join(f"{w} x{n}" if n > 1 else w for w, n in why.most_common()))
    # Who did what, with the short id, so a search for an id or a name finds the day.
    seen = collections.defaultdict(collections.Counter)
    for r in rows:
        e = r["event"]
        typ = e.get("type")
        if typ in ("station-reported", "station-failed"):
            ok = typ == "station-reported" and e.get("to") == "succeeded"
            seen[e.get("from") or r["node"]]["finished" if ok else "failed"] += 1
        elif typ == "agent-message":
            seen[e.get("from")]["sent"] += 1
            seen[e.get("to") or r["node"]]["got"] += 1
        elif typ in ("agent-done", "agent-asked"):
            seen[r["node"]]["asked" if typ == "agent-asked" else "said done"] += 1
    seen.pop(None, None)
    if seen:
        out += ["", "## Agents this day", ""]
        for node, c in sorted(seen.items(), key=lambda kv: name(names, kv[0]).lower()):
            out.append(f"- {name(names, node)} [{short_id(node)}]: " + ", ".join(f"{k} {v}" for k, v in c.items()))
    return "\n".join(out).rstrip() + "\n"


# ---------- commands ----------

def run(quiet=False, backlog=False):
    """One import at a time: the hourly reindex and the day page may call it together."""
    os.makedirs(DATA, exist_ok=True)
    with open(os.path.join(DATA, ".lock"), "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        return _run(quiet, backlog)


def _run(quiet, backlog):
    folders = boards()
    names = load_names()
    if backlog:
        # A name seen on the canvas wins over one from a chat log, which wins over one from a job note.
        for k, v in {**job_names(), **backlog_names()}.items():
            names.setdefault(k, v)
    names.update(current_names(folders))
    save_names(names)
    new = [r for f in folders for r in board_events(f)] + list(status_notes())
    _, n = add_to_archive(new)
    archive = read_archive()
    # A day's page is rewritten when its event count differs from the last page written (pages.json), so a page
    # that failed once is made again next run; with --backlog every day (the names changed).
    counts = collections.Counter(day_of(r["ts"]) for r in archive)
    done_path = os.path.join(DATA, "pages.json")
    done = read_json(done_path, {})
    days = [d for d in sorted(counts) if backlog or done.get(d.isoformat()) != counts[d]
            or not os.path.exists(os.path.join(PAGES, d.isoformat() + ".md"))]
    for d in days:
        try:
            write(os.path.join(PAGES, d.isoformat() + ".md"), page(d, events_of(d, archive), names))
            done[d.isoformat()] = counts[d]
        except Exception as why:   # noqa: BLE001 - one bad day must not stop the others; it is tried again next run
            print(f"canvas: page {d} skipped: {why!r}", file=sys.stderr)
    write(done_path, json.dumps(done, indent=1, sort_keys=True) + "\n")
    if not quiet:
        print(f"canvas: {n} new event{'s' if n != 1 else ''}, {len(days)} day page{'s' if len(days) != 1 else ''} "
              f"written, {len(names)} names known")
    return 0


def main(argv):
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    if argv[0] == "run":
        return run(quiet="--quiet" in argv)
    if argv[0] == "names":
        return run(quiet="--quiet" in argv, backlog="--backlog" in argv)
    if argv[0] == "line" and len(argv) > 1:
        try:
            d = dt.date.fromisoformat(argv[1])
        except ValueError:
            print("canvas: say a date like 2026-10-29", file=sys.stderr)
            return 2
        print(line(d))
        return 0
    print(f"canvas: unknown command {argv[0]!r}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
