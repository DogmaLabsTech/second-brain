"""brain memory / the chats' `memory` tool: the agent memory store's rules and lessons for one project and a task.

find(repo, task) answers "what should I know for this task in this project?" from the store
(BRAIN_MEMORY_STORE, default ~/projects/shared, the same rule as eval/memory_keep.py):
  - scope: `projects/<repo>/` (the name exactly, case included) and `all-projects/`; never `drafts/` or `history/`;
  - search: the brain's search (qmd's warm server, the `memory` collection), meaning-only like `brain ask`
    (expand.expanded_document), plus one word-search line per exact thing in the task (a file name, a port, error
    text in quotes, a function name: exact_things below). Results outside the scope are dropped by path;
  - order: pinned notes first (newest first), then the matches, newer notes winning close calls (ask.newer_first's
    rule, dated by the note's `date`), then the rest of the project's own notes, newest first. All-projects notes come
    only when pinned or when the search ranks them for the task ("only on a match", <user>, 2026-10-28), so a small
    project's push stays small; the header says how many were left out and how to ask. No task: pinned (both scopes),
    then the project's newest notes. Search down, slow, or matching no unpinned note: the same, and the output says so;
  - each note: its stored `summary` line word for word, kind, project, path. `local-only: true` notes are shown like
    any other, marked (local-only) (<user>, 2026-10-28: no hiding). No model rewrites or hides anything;
  - flags (job 6, ask/memory_flagfile.py): a flagged note is marked "(may be out of date, check first)". With
    for_push=True (the memory hook) a note whose flag nobody confirmed for 30 days is left out; every other caller
    still shows it, marked as lapsed. Nothing leaves the store;
  - budget: tokens are counted as characters / 4, rounded up; the list stops before the budget and says how many
    notes did not fit.
Python standard library only; nothing leaves this computer.

  python3 -I ask/memory.py <repo> ["the task in words"]
"""
import json
import math
import os
import re
import sys
import time
import urllib.request

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ask  # noqa: E402
import memory_flagfile  # noqa: E402
from expand import expanded_document  # noqa: E402

BUDGET = 2000
SEARCH_SECONDS = float(os.environ.get("BRAIN_MEMORY_SECONDS", "10"))   # slower than this = fall back to the files
POOL = 50   # results asked for before the path filter (a project with few notes must not look empty)
MAX_EXACT = 3
COLLECTION = "memory"
ALL = "all-projects"
SCOPES = ("projects/{repo}", ALL)
KINDS = {"rules": "rule", "lessons": "lesson"}


def store_path(store=None):
    return os.path.expanduser(store or os.environ.get("BRAIN_MEMORY_STORE") or "~/projects/shared")


def tokens(text):
    """The budget's count: characters / 4, rounded up (simple and stable; real tokenizers differ a little)."""
    return -(-len(text) // 4)


# ---------- the exact-thing rule (when a word-search line is added) ----------

EXACT = [
    r"`([^`\n]{2,80})`",                                         # anything in backticks
    r"\"([^\"\n]{3,80})\"",                                      # quoted text (error messages)
    r"(?<![\w/.-])((?:[\w.-]+/)*[\w-]+\.(?:py|sh|md|json|jsonl|ya?ml|toml|qml|js|mjs|ts|tsx|rs|go|service|timer|conf|tsv))\b",
    r"(?:\bport\s?|:)(\d{2,5})\b",                               # a port: "port 8181", ":8181"
    r"\b([A-Za-z_][\w.]*)\(\)",                                  # a call: name()
    r"\b([a-z]+(?:_[a-z0-9]+)+)\b",                              # snake_case names
    r"\b([a-z]+(?:[A-Z][a-z0-9]+)+)\b",                          # camelCase names
    r"\b([A-Z]\w*(?:Error|Exception))\b",                        # ValueError, CallerGone-like error types
]


def exact_things(task):
    """The exact things in a task (file name, port, quoted error text, function name), at most MAX_EXACT."""
    out = []
    for pat in EXACT:
        for m in re.finditer(pat, task or ""):
            thing = m.group(1).strip()
            if thing and not any(thing in o or o in thing for o in out):
                out.append(thing)
    return out[:MAX_EXACT]


def exact_rule_on():
    """BRAIN_MEMORY_EXACT=0 turns the exact-thing word-search line off (the score test compares with and without)."""
    return os.environ.get("BRAIN_MEMORY_EXACT", "1") != "0"


def searches(task):
    """The search lines: brain ask's meaning lines, plus one word-search line per exact thing."""
    lines = [dict(zip(("type", "query"), l.split(": ", 1))) for l in expanded_document(task).splitlines()]
    exact = exact_things(task) if exact_rule_on() else []
    return [s for s in lines if s["type"] == "vec"] + [{"type": "lex", "query": t} for t in exact]


# ---------- the notes ----------

def front(text):
    """The note's front matter as a dict of plain values (quoted values decoded, `files` left out)."""
    m = re.match(r"---\n(.*?)\n---\n", text, re.S)
    out = {}
    for line in (m.group(1).splitlines() if m else []):
        if line[:1].isspace() or ":" not in line:
            continue
        key, _, value = line.partition(":")
        value = value.strip()
        if value.startswith('"'):
            try:
                value = json.loads(value)
            except ValueError:
                pass
        out[key.strip()] = value
    return out


def read_note(store, rel):
    """One note: summary (as stored), kind and project from the path, pinned, local-only, date, path."""
    path = os.path.join(store, rel)
    try:
        with open(path, encoding="utf-8") as f:
            fm = front(f.read())
    except (OSError, UnicodeDecodeError):
        return None
    parts = rel.split("/")
    project = parts[1] if parts[0] == "projects" else "all-projects"
    kind = next((KINDS[p] for p in parts if p in KINDS), fm.get("kind") or "note")
    return {"path": path, "rel": rel, "summary": fm.get("summary") or "(no summary line)", "kind": kind,
            "project": project, "pinned": str(fm.get("pinned")).lower() == "true",
            "local_only": str(fm.get("local-only")).lower() == "true",
            "date": str(fm.get("date") or ""), "mtime": _mtime(path)}


def _mtime(path):
    try:
        return os.path.getmtime(path)
    except OSError:
        return 0.0


def scope_notes(store, repo):
    """Every note in the scope: {store-relative path: note}. drafts/ and history/ are never walked."""
    notes = {}
    for top in (s.format(repo=repo) for s in SCOPES):
        root = os.path.join(store, top)
        if not os.path.isdir(root) or (top.startswith("projects/") and repo not in os.listdir(os.path.join(store, "projects"))):
            continue   # the second check keeps the name exact on a case-blind disk
        for dirpath, dirs, files in os.walk(root):
            dirs[:] = sorted(d for d in dirs if d not in ("drafts", "history") and not d.startswith("."))
            for name in sorted(files):
                if name.endswith(".md") and name not in ("README.md", "CONTEXT.md"):
                    rel = os.path.relpath(os.path.join(dirpath, name), store)
                    note = read_note(store, rel)
                    if note:
                        notes[rel] = note
    since = memory_flagfile.flagged(store)
    for rel, note in notes.items():
        note["flagged"] = since.get(rel)
    return notes


def newest(notes):
    return sorted(notes, key=lambda n: (n["date"], n["mtime"], n["rel"]), reverse=True)


# ---------- the search ----------

def search(task, url=None, timeout=None):
    """qmd's results for the task in the `memory` collection (the warm server's REST /query, rerank off)."""
    body = {"searches": searches(task), "collections": [COLLECTION], "limit": POOL, "rerank": False}
    req = urllib.request.Request((url or ask.BRAIN_URL) + "/query", json.dumps(body).encode(),
                                 {"content-type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout or SEARCH_SECONDS) as resp:
        return json.load(resp)["results"]


def in_scope(file, notes):
    """The scope's note for a result's file (qmd://memory/<rel>, maybe lowercased by qmd), else None."""
    rel = re.sub(r"^(qmd://)?" + COLLECTION + "/", "", file or "")
    if rel in notes:
        return notes[rel]
    same = [n for r, n in notes.items() if r.lower() == rel.lower()]
    return same[0] if len(same) == 1 else None


def matches(task, notes, url=None):
    """(the unpinned notes in order, a fallback message or None). Best match first, newer wins close calls.
    All-projects notes come only when the search ranks them (or pinned): unranked, only the project's own notes follow
    (<user>, 2026-10-28: "only on a match"), so a small project's push stays small. find() counts the ones left out."""
    loose = [n for n in notes.values() if not n["pinned"] and n["project"] != ALL]
    if not task:
        return newest(loose), None
    try:
        results = search(task, url)
    except Exception as why:  # noqa: BLE001  down, slow, or no memory collection: the files still answer
        why = "slower than %gs" % SEARCH_SECONDS if "timed out" in str(why) else str(why)[:120]
        return newest(loose), f"Search was not reachable ({why}); showing pinned and this project's newest notes instead."
    hits, seen = [], set()
    for r in results:
        n = in_scope(r.get("file", ""), notes)
        if n and not n["pinned"] and n["rel"] not in seen:
            seen.add(n["rel"])
            hits.append({"score": r.get("score", 0), "note": n})
    hits = newer_first(hits)
    # None of the project's own notes is hidden: those search did not rank follow, newest first; the budget cuts the bottom.
    rest = newest([n for n in loose if n["rel"] not in seen])
    note = None if hits else "Search ranked no unpinned note for this task; showing pinned and this project's newest notes instead."
    return [h["note"] for h in hits] + rest, note


def note_age_days(n, now):
    """Days since the note's `date` (front matter), else since its file last changed."""
    try:
        when = time.mktime(time.strptime(n["date"], "%Y-%m-%d"))
    except (ValueError, OverflowError):
        when = n["mtime"]
    return max(0.0, (now - when) / 86400)


def newer_first(hits):
    """ask.newer_first's rule (newer wins close calls, a clearly better old note stays on top), dated by the note."""
    if ask.NEWER_DAYS <= 0:
        return hits
    now = time.time()
    for h in hits:
        h["score"] = float(h["score"] or 0) * (1 + 0.5 * math.exp(-note_age_days(h["note"], now) / ask.NEWER_DAYS))
    return sorted(hits, key=lambda h: -h["score"])


# ---------- the answer ----------

def check_repo(repo):
    if not isinstance(repo, str) or not re.fullmatch(r"[A-Za-z0-9][\w.-]*", repo) or ".." in repo:
        raise ValueError(f"not a project name: {repo!r} (the folder name in ~/projects/)")


def entry(i, n):
    marks = (" (pinned)" if n["pinned"] else "") + (" (local-only)" if n["local_only"] else "")
    if n.get("flagged"):
        marks += " (may be out of date, check first" + ("; flag over 30 days old, not pushed" if lapsed(n) else "") + ")"
    return f"{i}. {n['summary']}\n   {n['kind']}, {n['project']}{marks}: {n['path']}\n"


def lapsed(n):
    return memory_flagfile.lapsed(n.get("flagged"))


def render(repo, task, ordered, budget, note=None, skipped=0):
    """The text an agent gets: header, as many notes as fit in the budget, and how many did not.
    `skipped`: all-projects notes left out for not matching (one header line says so)."""
    head = f"Memory for {repo}: pinned, then matches, then its own newest notes.\n"
    if task:
        head += f"Task: {' '.join(task.split())[:200]}\n"
    if note:
        head += note + "\n"
    if skipped:
        head += (f"{skipped} all-projects note{'' if skipped == 1 else 's'} left out (no match): "
                 f"ask `memory` with a task to find them.\n")
    text, shown = head, []
    reserve = tokens("\n%d more notes did not fit in %d tokens (characters / 4).\n" % (len(ordered), budget))
    for n in ordered:
        e = entry(len(shown) + 1, n)
        if tokens(text + e) + reserve > budget:
            break
        text += e
        shown.append(n)
    left = len(ordered) - len(shown)
    if left:
        text += f"\n{left} more note{'' if left == 1 else 's'} did not fit in {budget} tokens (characters / 4).\n"
    return text, shown, left


def find(repo, task=None, store=None, budget=BUDGET, url=None, for_push=False):
    """{"text", "notes", "left_out", "fallback"} for one project and an optional task (see the top of this file).
    for_push: the memory hook's call; notes with a lapsed flag are left out."""
    check_repo(repo)
    task = (task or "").strip() or None
    root = store_path(store)
    if not os.path.isdir(root):
        return plain(f"No memory store at {root} (set BRAIN_MEMORY_STORE if it lives somewhere else).")
    notes = scope_notes(root, repo)
    if not notes:
        return plain(f"No notes for {repo} in the memory store yet, and none for all projects.")
    if for_push:
        notes = {r: n for r, n in notes.items() if not lapsed(n)}
        if not notes:
            return plain(f"No notes to push for {repo}.")
    pinned = newest([n for n in notes.values() if n["pinned"]])
    rest, fallback = matches(task, notes, url)
    shown_rels = {n["rel"] for n in pinned + rest}
    skipped = sum(1 for n in notes.values() if n["rel"] not in shown_rels)   # only unpinned all-projects notes can be
    text, shown, left = render(repo, task, pinned + rest, budget, fallback, skipped)
    keys = ("summary", "kind", "project", "path", "pinned", "local_only", "flagged")
    return {"text": text, "notes": [{k: n[k] for k in keys} for n in shown], "left_out": left, "fallback": fallback}


def plain(message):
    return {"text": message + "\n", "notes": [], "left_out": 0, "fallback": None}


def main(argv):
    if not argv or argv[0] in ("-h", "--help"):
        print('usage: brain memory <repo> ["the task in words"]', file=sys.stderr)
        return 1
    try:
        out = find(argv[0], " ".join(argv[1:]))
    except ValueError as why:
        print(f"brain memory: {why}", file=sys.stderr)
        return 1
    sys.stdout.write(out["text"])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
