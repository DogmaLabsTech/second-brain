"""brain memory-flags: which kept notes may be out of date (agent memory job 6, the plan's part 2).

  brain memory-flags [run]        look at every kept note and flag the ones that may be out of date (the weekly check-up
                                  does this by itself); prints what is flagged and what is due
  brain memory-flags list         what is flagged now and which pinned notes are due, no new look
  brain memory-flags confirm <note>   <user>: this note is still right (a flag is cleared; a pinned note's 90 days restart)
  brain memory-flags retire <note> [--why "words"]
                                  <user>: this note is no longer right. It moves to history/ (never deleted) and is
                                  committed in the store. Only this command retires a note, and only <user> runs it.

<note> is the note's path inside the store (projects/<repo>/lessons/<name>.md) or just its file name.

The rule (documented here, tested in eval/test_memory_flags.py). A note is FLAGGED, never changed, when:
  1. file gone: a file in its `files:` list is not in the project's repo any more (~/projects/<project>/,
     BRAIN_PROJECTS_DIR). Notes kept less than GRACE_DAYS ago are not checked for this (the file may sit on a branch
     that is not merged yet);
  2. file changed a lot: git log of that repo since the day after the note's date (or after its last confirmation)
     adds up to at least CHANGED_MIN_LINES changed lines (added + deleted) in that file AND at least CHANGED_RATIO of
     the file's size now;
  3. a newer note says the opposite: a newer note of the same project is proposed by the brain's search (every newer
     note of the project when search is not reachable) and the two summaries share most of their content words
     (OVERLAP_MIN and OVERLAP_SHARED) while only one of them holds a negation (never, not, don't, avoid, stop ...).
     The decider (memory-conflict, ask/memory_decide.py) judges each such pair first: it answers agrees, conflicts or
     unrelated and only "conflicts" flags; when it is not sure, or off (BRAIN_MEMORY_DECIDER=off), the word rule above
     decides. It proposes, <user> decides.
`all-projects` notes have no repo, so only rule 3 applies to them. A note that is already flagged, retired, or
unconfirmed is not flagged twice. The flags live in the store's `flags.jsonl` (ask/memory_flagfile.py), not in the notes.
What a flag does: `brain memory` and the chats' `memory` tool mark the note "(may be out of date, check first)"; a flag
nobody confirms for 30 days takes the note out of the push (not out of the store). Every pinned note is asked "still
true?" every 90 days (its `date`, or the last confirmation). The store path is BRAIN_MEMORY_STORE (default
~/projects/shared); tests use a temp folder. Standard library only; the decider asks the second decider for rule 3 (private text allowed for that task, names removed first).
"""
import os
import re
import subprocess
import sys
import time

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path[:0] = [HERE, os.path.join(ROOT, "ask")]
import memory  # noqa: E402
import memory_decide  # noqa: E402
import memory_flagfile as store_flags  # noqa: E402
import memory_keep  # noqa: E402

GRACE_DAYS = 3
CHANGED_MIN_LINES = 20
CHANGED_RATIO = 0.5
OVERLAP_MIN = 0.5      # of the shorter summary's content words, this share is in the other summary ...
OVERLAP_SHARED = 3     # ... and at least this many words are shared
CANDIDATES = 5
CONFLICT_SHARED = 2    # the decider is asked only about a pair that shares this many content words (else: unrelated)
GIT_SECONDS = 20
STOP = set("the a an and or of to in on for with is are be it this that we you your do does did from at by as when "
           "then than so if use used using must should will can has have had was were its into out all any each "
           "one two more most only just also over".split())
NEGATIONS = {"never", "not", "no", "dont", "don't", "doesnt", "doesn't", "cannot", "cant", "can't", "stop", "avoid",
             "without", "isnt", "isn't", "wont", "won't", "longer", "instead"}


def store_path(store=None):
    return memory_keep.store_path(store)


def projects_dir():
    return os.path.expanduser(os.environ.get("BRAIN_PROJECTS_DIR") or "~/projects")


def today_str():
    return time.strftime("%Y-%m-%d")


def next_day(date):
    return time.strftime("%Y-%m-%d", time.localtime(time.mktime(time.strptime(date, "%Y-%m-%d")) + 86400 + 3600))


# ---------- the notes ----------

def all_notes(store):
    """{store-relative path: note} for every kept note (every project and all-projects), with its `files` list."""
    notes = {}
    repos = [d for d in sorted(os.listdir(os.path.join(store, "projects")))
             if os.path.isdir(os.path.join(store, "projects", d))] if os.path.isdir(os.path.join(store, "projects")) else []
    for repo in repos + ["all-projects"]:
        found = memory.scope_notes(store, repo) if repo != "all-projects" else _all_projects(store)
        for rel, note in found.items():
            if note["project"] == repo:
                notes[rel] = note
    for rel, note in notes.items():
        with open(note["path"], encoding="utf-8") as f:
            note["files"] = memory_keep.split_draft(f.read())[0]
    return notes


def _all_projects(store):
    return {r: n for r, n in memory.scope_notes(store, "-none-").items() if n["project"] == "all-projects"}


def find_note(store, ref):
    """The kept note a path or file name means; ValueError (plain words) when there is none or several."""
    notes = all_notes(store)
    ref = (ref or "").strip().lstrip("./")
    hit = [r for r in notes if r == ref] or [r for r in notes if os.path.basename(r) == os.path.basename(ref)]
    if len(hit) != 1:
        raise ValueError("no kept note called %s" % ref if not hit else
                         "%s is more than one note; give the path: %s" % (ref, ", ".join(sorted(hit))))
    return notes[hit[0]]


# ---------- rule 1 and 2: the files ----------

def _git(repo, *args):
    done = subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True, timeout=GIT_SECONDS,
                          stdin=subprocess.DEVNULL)
    return done.stdout if done.returncode == 0 else None


def repo_of(note):
    path = os.path.join(projects_dir(), note["project"])
    return path if note["project"] != "all-projects" and os.path.isdir(os.path.join(path, ".git")) else None


def _safe(file):
    return bool(file) and not os.path.isabs(file) and ".." not in file.replace("\\", "/").split("/")


def changed_lines(repo, file, since):
    """Added + deleted lines of `file` in the repo's commits made after the day `since`, or None when git cannot say."""
    out = _git(repo, "log", "--numstat", "--format=", "--after=" + next_day(since) + " 00:00", "--", file)
    if out is None:
        return None
    total = 0
    for line in out.splitlines():
        a, _, rest = line.partition("\t")
        d = rest.partition("\t")[0]
        total += int(a) + int(d) if a.isdigit() and d.isdigit() else 0
    return total


def file_reasons(note, baseline, today, confirmed=False):
    """[(kind, reason)] for rules 1 and 2. A note <user> confirmed is not flagged again for a file that is gone."""
    repo, out = repo_of(note), []
    if not repo:
        return out
    young = store_flags.days_between(note["date"], today) < GRACE_DAYS
    for file in note.get("files", []):
        if not _safe(file):
            continue
        full = os.path.join(repo, file)
        if not os.path.exists(full):
            if not young and not confirmed:
                out.append(("file-gone", "%s is not in %s any more" % (file, note["project"])))
            continue
        lines = changed_lines(repo, file, baseline)
        size = _line_count(full)
        if lines is not None and lines >= CHANGED_MIN_LINES and lines >= CHANGED_RATIO * size:
            out.append(("file-changed", "%s: %d lines changed since %s (the file has %d now)" % (file, lines, baseline, size)))
    return out


def _line_count(path):
    try:
        with open(path, "rb") as f:
            return sum(1 for _ in f)
    except OSError:
        return 0


# ---------- rule 3: a newer note says the opposite ----------

def content_words(text):
    return {w for w in re.findall(r"[a-z0-9]+", (text or "").lower().replace("'", ""))
            if len(w) >= 3 and w not in STOP and w not in NEGATIONS}


def negated(text):
    return any(w in NEGATIONS for w in re.findall(r"[a-z']+", (text or "").lower().replace("’", "'")))


def opposite(a, b):
    """True when two summaries are about the same thing and only one of them holds a negation."""
    wa, wb = content_words(a), content_words(b)
    shared = wa & wb
    short = min(len(wa), len(wb))
    return bool(short) and len(shared) >= OVERLAP_SHARED and len(shared) / short >= OVERLAP_MIN \
        and negated(a) != negated(b)


def qmd_candidates(notes):
    """A function summary -> rels of the notes the brain's search proposes (None for a failed search)."""
    down = []

    def search(summary):
        if down:
            return None   # one failed search is enough: no waiting on a dead or slow server for every note
        try:
            hits = memory.search(summary)
        except Exception:  # noqa: BLE001  search down: the caller falls back to all newer notes of the project
            down.append(True)
            return None
        rels = [memory.in_scope(h.get("file", ""), notes) for h in hits]
        return [n["rel"] for n in rels if n][:CANDIDATES]
    return search


def says_opposite(note, other):
    """True when the newer note `other` says the opposite of `note`. The decider (memory-conflict) answers first when it
    is sure ("conflicts" is true, "agrees" and "unrelated" are false); the word rule `opposite` is the fallback."""
    if len(content_words(note["summary"]) & content_words(other["summary"])) >= CONFLICT_SHARED:
        got = memory_decide.relation(other["summary"], note["summary"])
        if got is not None:
            return got == "conflicts"
    return opposite(note["summary"], other["summary"])


def opposite_reasons(note, notes, search, baseline=""):
    """[(kind, reason)] when a newer note (newer than the baseline too) of the same project says the opposite."""
    proposed = search(note["summary"]) if search else None
    if proposed is None:
        proposed = list(notes)
    for rel in proposed:
        other = notes.get(rel)
        if other and other["rel"] != note["rel"] and other["project"] == note["project"] \
                and other["date"] > max(note["date"], baseline) and says_opposite(note, other):
            return [("newer-opposite", "a newer note (%s) may say the opposite: \"%s\"" % (other["rel"], other["summary"]))]
    return []


# ---------- the pass ----------

def baseline_of(note, state):
    return max(note["date"], (state or {}).get("confirmed") or "")


def look(store, today=None, search="qmd"):
    """Flag what may be out of date. Returns {"new": [(rel, kind, reason)], "flagged": {...}, "pins_due": [...]}.
    `search` is a function summary -> rels (or None), "qmd" for the brain's search, None for no search."""
    today = today or today_str()
    notes, states = all_notes(store), store_flags.states(store)
    search = qmd_candidates(notes) if search == "qmd" else search
    new = []
    for rel, note in sorted(notes.items()):
        st = states.get(rel) or {}
        if st.get("flagged") or st.get("retired"):
            continue
        base = baseline_of(note, st)
        found = file_reasons(note, base, today, bool(st.get("confirmed"))) + opposite_reasons(note, notes, search, base)
        if found:
            new.append((rel, found[0][0], "; ".join(r for _, r in found)))
    store_flags.append(store, [{"note": rel, "state": "flagged", "at": today, "kind": kind, "reason": why}
                               for rel, kind, why in new])
    if new:
        _commit(store, "flags: %d note%s may be out of date" % (len(new), "" if len(new) == 1 else "s"))
    return {"new": new, "flagged": store_flags.flagged(store), "pins_due": pins_due(store, today)}


def pins_due(store, today=None):
    """[(rel, days since the last "still true?")] for pinned notes older than the 90-day check."""
    today, states = today or today_str(), store_flags.states(store)
    due = []
    for rel, note in sorted(all_notes(store).items()):
        st = states.get(rel) or {}
        if note["pinned"] and not st.get("retired"):
            days = store_flags.days_between(st.get("still_true") or note["date"], today)
            if days >= store_flags.PIN_DAYS:
                due.append((rel, days))
    return due


def _commit(store, message):
    """Commit the flags file in the store when the store is a git repo; quietly nothing otherwise."""
    if not os.path.exists(os.path.join(store, ".git")):
        return
    try:
        memory_keep._git(store, "add", "--", store_flags.FLAGS)
        memory_keep._git(store, "commit", "-q", "-m", message, "--", store_flags.FLAGS)
    except memory_keep.KeepError:
        pass   # nothing to commit or git trouble: the flags file is still written


# ---------- <user>'s answers ----------

def confirm(store, ref, today=None):
    """<user>: still right. Clears a flag; restarts a pinned note's 90 days. Returns what was done."""
    note, today = find_note(store, ref), today or today_str()
    state = store_flags.states(store).get(note["rel"]) or {}
    rows = []
    if state.get("flagged"):
        rows.append({"note": note["rel"], "state": "confirmed", "at": today})
    if note["pinned"]:
        rows.append({"note": note["rel"], "state": "still-true", "at": today})
    if not rows:
        raise ValueError("%s is not flagged and not pinned, so there is nothing to confirm" % note["rel"])
    store_flags.append(store, rows)
    _commit(store, "flags: confirmed %s" % note["rel"])
    return [r["state"] for r in rows]


def retire(store, ref, why=None, today=None):
    """<user>: no longer right. The note moves to history/<same path> and the move is committed. Returns the new path."""
    note, today = find_note(store, ref), today or today_str()
    dest = os.path.join(store, "history", note["rel"])
    if os.path.lexists(dest):
        raise ValueError("history/%s is already there; rename one of them first" % note["rel"])
    git = os.path.exists(os.path.join(store, ".git"))
    # A hand-made note that was never committed has no old path for git to stage: leave it out, or the add fails
    # after the move (half done).
    tracked = git and bool(memory_keep._git(store, "ls-files", "--", note["rel"]).strip())
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    os.replace(note["path"], dest)
    store_flags.append(store, [{"note": note["rel"], "state": "retired", "at": today, "reason": why or ""}])
    if git:
        paths = ([note["rel"]] if tracked else []) + [os.path.join("history", note["rel"]), store_flags.FLAGS]
        memory_keep._git(store, "add", "-A", "--", *paths)
        memory_keep._git(store, "commit", "-q", "-m", "retire: %s%s" % (note["rel"], (": " + why) if why else ""), "--", *paths)
    return dest


# ---------- command line ----------

def lines(result, today=None):
    """Plain words for what the pass found."""
    out = []
    for rel, _, why in result["new"]:
        out.append("new flag: %s: %s" % (rel, why))
    for rel, since in sorted(result["flagged"].items()):
        out.append("flagged since %s (%d days): %s" % (since, store_flags.days_between(since, today), rel))
    for rel, days in result["pins_due"]:
        out.append("pinned, still true? last checked %d days ago: %s" % (days, rel))
    return out or ["nothing flagged, no pinned note due"]


def main(argv):
    cmd, rest = (argv[0], list(argv[1:])) if argv else ("run", [])
    store = store_path()
    try:
        if cmd in ("run", "list"):
            result = look(store) if cmd == "run" else {"new": [], "flagged": store_flags.flagged(store),
                                                       "pins_due": pins_due(store)}
            print("\n".join(lines(result)))
        elif cmd == "confirm" and len(rest) == 1:
            print("confirmed %s (%s)" % (rest[0], ", ".join(confirm(store, rest[0]))))
        elif cmd == "retire" and rest and rest[0] != "--why":
            why = rest[rest.index("--why") + 1] if "--why" in rest[1:] and rest.index("--why") + 1 < len(rest) else None
            print("retired: moved to %s" % retire(store, rest[0], why).replace(os.path.expanduser("~"), "~", 1))
        else:
            print(__doc__.split("\n\n")[0], file=sys.stderr)
            return 2
    except (ValueError, OSError, memory_keep.KeepError) as why:
        print("brain memory-flags: %s" % why, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
