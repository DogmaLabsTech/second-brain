"""The flags file of the agent memory store (agent memory job 6): which notes may be out of date, and when pinned notes
were last confirmed. Read by ask/memory.py (the search marks a flagged note) and written by eval/memory_flags.py.

One file in the store, `flags.jsonl` (not in the notes), one JSON line per event, oldest first, nothing ever deleted:
  {"note": "projects/x/lessons/a.md", "state": "flagged",    "at": "2026-10-28", "kind": "file-gone|file-changed|newer-opposite", "reason": "..."}
  {"note": "...", "state": "confirmed",   "at": "2026-11-02"}   <user>: the note is still right (clears the flag)
  {"note": "...", "state": "still-true",  "at": "2026-11-02"}   <user>: a pinned note is still true (the 90-day check)
  {"note": "...", "state": "retired",     "at": "2026-11-02"}   <user>: the note moved to history/
A note is flagged while its newest flagged/confirmed/retired line says flagged; the flag's age counts from the first
flagged line after its last confirmation. A flag older than LAPSE_DAYS takes the note out of the push (not out of the
store, not out of search). Python standard library only.
"""
import json
import os
import time

FLAGS = "flags.jsonl"
LAPSE_DAYS = 30   # a flag nobody confirmed for this long takes the note out of the push
PIN_DAYS = 90     # a pinned note is asked "still true?" this often


def path(store):
    return os.path.join(store, FLAGS)


def rows(store):
    """Every line of the flags file; an unreadable file or line counts as nothing (a flag must never stop a search)."""
    out = []
    try:
        with open(path(store), encoding="utf-8") as f:
            for line in f:
                try:
                    row = json.loads(line)
                except ValueError:
                    continue
                if isinstance(row, dict) and row.get("note") and row.get("state"):
                    out.append(row)
    except (OSError, UnicodeDecodeError):
        pass
    return out


def append(store, new_rows):
    """Add lines to the flags file (one write, so a half line cannot happen between two of them)."""
    if not new_rows:
        return
    with open(path(store), "a", encoding="utf-8") as f:
        f.write("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in new_rows))


def states(store):
    """{note: {"flagged": since-date or None, "reason": text, "kind": kind, "confirmed": date or None,
    "still_true": date or None, "retired": bool}} for every note that has any line."""
    out = {}
    for r in rows(store):
        s = out.setdefault(r["note"], {"flagged": None, "reason": "", "kind": "", "confirmed": None,
                                       "still_true": None, "retired": False})
        at = str(r.get("at") or "")
        if r["state"] == "flagged":
            if not s["flagged"]:
                s["flagged"], s["reason"], s["kind"] = at, str(r.get("reason") or ""), str(r.get("kind") or "")
        elif r["state"] == "confirmed":
            s.update(flagged=None, reason="", kind="", confirmed=at)
        elif r["state"] == "still-true":
            s["still_true"] = at
        elif r["state"] == "retired":
            s.update(flagged=None, retired=True)
    return out


def flagged(store):
    """{note: since-date} for the notes that are flagged now."""
    return {n: s["flagged"] for n, s in states(store).items() if s["flagged"] and not s["retired"]}


def days_between(since, today=None):
    """Whole days from a YYYY-MM-DD date to today (a date that cannot be read counts as today: 0)."""
    try:
        then = time.mktime(time.strptime(since, "%Y-%m-%d"))
        now = time.mktime(time.strptime(today or time.strftime("%Y-%m-%d"), "%Y-%m-%d"))
    except (ValueError, OverflowError, TypeError):
        return 0
    return max(0, round((now - then) / 86400))


def lapsed(since, today=None):
    """True when a flag raised on `since` has gone unconfirmed for LAPSE_DAYS or more."""
    return bool(since) and days_between(since, today) >= LAPSE_DAYS
