"""brain memory-drafts: lesson drafts for the agent memory store (agent memory job 6, the plan's part 1).

  brain memory-drafts add --to projects/<repo>/lessons --job <job id> --title "one line" --source "where it came from"
                          [--files a.py,b.py] [--window START,END | --sessions id,id] [--name slug]   (body on stdin)
  brain memory-drafts expire        move drafts nobody kept for 30 days to history/expired-drafts/ (never deleted)
  brain memory-drafts list          the drafts that wait for <user>'s keep or drop
  brain memory-drafts drop <draft>  <user>'s drop: the draft moves to history/dropped-drafts/ (never deleted)

`add` is what the desk's librarian step calls after a job (agent-os `librarian lesson`, which reads the job's own files).
It writes ONE draft into the store's `drafts/` folder in the note format (`keep` in eval/memory_keep.py turns it into a
note): front matter `to:` (where it would go), `summary:`, `files:`, `pinned: false`, and two fields about repeats:
  already-known  yes | no   a kept note of the project (or of all-projects) says the same: the notes' summaries are
                            searched (the brain's search, else every note of the scope); "the same" means at least
                            SAME_SHARE of the note's summary words are in the draft's title and body, at least
                            SAME_SHARED words are shared and negation agrees (never/not/avoid ...). `same-as:` names the note.
  was-pushed     yes | no | unknown   that note was in the memory hook's push for the job's sessions (ask/memory_hook.py
                            logs the pushed paths in memory-hook.jsonl). Sessions come from --sessions, else the push
                            lines of the project inside --window (START,END as ISO times). No line, or lines from before
                            the log held paths: unknown. No matching note: no.
  "yes and pushed" means a repeat got through; the weekly list counts those (eval/memory_week.py).
The body is the job's own text with a `Source:` line. The text goes through the names filter first (decider/names.py,
through drafts.scrub).

Who writes the summary and the body (<user>, 2026-10-28; `BRAIN_DRAFT_WRITER=haiku|fixed`, default haiku): Claude Haiku
5.5, through the one call `brain ask` uses (ask.haiku_write: `claude -p`, no tools, no MCP, no settings), gets ONLY the
scrubbed records and writes a one-line summary (at most 25 words, what to do) and a short body (at most 120 words: what
happened, what to do instead, where the fix lives). Its answer is scrubbed again before it is written. The front matter
says `written-by: haiku` or `written-by: fixed-rule` (the librarian's own title and records, as before), and a
`fixed-rule-why:` line when Haiku was wanted but not used (switch off, slow over 30 s, failed, empty, answer not in the
form or too long, answer not safe). When the names guard or filter is not sure, Haiku is not called and the fixed-rule
draft is written as it came, marked `local-only: true` (with `local-only-by: filter`), so it is never sent online.

Two choices are asked of the decider first (ask/memory_decide.py; BRAIN_MEMORY_DECIDER=off turns that off), the word rules
above are the fallback whenever it is not sure: "already-known" asks memory-same-note about the first SAME_ASKED
candidate notes, and a "no" from memory-lesson-worth (is this finished job worth a lesson?) skips the draft after the
fixed signals fired (NotWorth, logged as `skipped` in memory-decider.jsonl; nothing counts against the weekly limit).

Limits: at most MAX_PER_WEEK drafts per ISO week, counted by the draft's date in the store's `draft-log.jsonl` (one
line per draft written; it also keeps the two fields, so keeping or dropping a draft does not free a place); a sixth is
refused in plain words. One draft per job. Drafts older than 30 days that nobody kept move to
history/expired-drafts/ (`expire`, which the weekly check-up runs): they are never deleted and never pushed.
Drafts are not committed in the store (the inbox); a keep commits the note. The store is BRAIN_MEMORY_STORE
(default ~/projects/shared); tests use a temp folder. Standard library only; Haiku is called only by `add`, once per draft, after the cap check
(and after the lesson-worth gate); the decider (the second decider) is asked the two choices above.
"""
import json
import os
import re
import sys
import time

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path[:0] = [HERE, os.path.join(ROOT, "ask")]
import drafts  # noqa: E402
import memory  # noqa: E402
import memory_decide  # noqa: E402
import memory_flagfile  # noqa: E402
import memory_flags  # noqa: E402
import memory_hook  # noqa: E402
import memory_keep  # noqa: E402

MAX_PER_WEEK = 5
SAME_ASKED = 3         # the decider (memory-same-note) looks at this many candidate notes; the word rule at the rest
EXPIRE_DAYS = 30
SAME_SHARE = 0.6
SAME_SHARED = 3
HAIKU_SECONDS = 30
SUMMARY_WORDS = 25
BODY_WORDS = 120
SUMMARY_CHARS = 240   # the same cap as keep's summary (eval/memory_keep.py)
HAIKU_SYSTEM = (
    "You write one lesson for an agent memory store from the records of a finished job. Use only what the records say; "
    "do not invent files, causes or fixes. Marks like [NAME] are hidden names: leave them as they are. Reply in exactly "
    "this form and nothing else:\n"
    "SUMMARY: one line of at most %d words, an instruction an agent can act on, starting with what to do\n"
    "BODY: at most %d words of plain text: what happened, what to do instead, where the fix lives"
    % (SUMMARY_WORDS, BODY_WORDS))
LOG = "draft-log.jsonl"
EXPIRED = os.path.join("history", "expired-drafts")


class DraftError(ValueError):
    """The draft cannot be written; the message is plain words. Nothing was written."""


class NotWorth(DraftError):
    """The decider (memory-lesson-worth) said the job is not worth a lesson. Nothing was written; the skip is logged."""


def store_path(store=None):
    return memory_keep.store_path(store)


def iso_week(date):
    """'2026-W44' for a YYYY-MM-DD date."""
    return time.strftime("%G-W%V", time.strptime(date, "%Y-%m-%d"))


def _read_jsonl(path):
    out = []
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                try:
                    row = json.loads(line)
                except ValueError:
                    continue
                if isinstance(row, dict):
                    out.append(row)
    except (OSError, UnicodeDecodeError):
        pass
    return out


def log_rows(store):
    return _read_jsonl(os.path.join(store, LOG))


# ---------- already-known ----------

def says_the_same(title, body, note):
    """True when the kept note's summary is (nearly) in the draft's words and does not turn it round."""
    summary = memory_flags.content_words(note["summary"])
    if len(summary) < SAME_SHARED:
        return False
    shared = summary & memory_flags.content_words(title + " " + body)
    return len(shared) >= SAME_SHARED and len(shared) / len(summary) >= SAME_SHARE \
        and memory_flags.negated(title) == memory_flags.negated(note["summary"])


def already_known(store, project, title, body, search="qmd", decide=True):
    """The kept note (a note dict) of the scope that says the same, or None. The decider (memory-same-note) judges the
    first SAME_ASKED candidates (not at all when `decide` is False: text the names filter could not clean stays local); a note it is not sure about (or every note, when it is off) goes through the word rule."""
    notes = memory.scope_notes(store, project)
    rels = None
    if search == "qmd":
        try:
            hits = memory.search(title)
            rels = [n["rel"] for n in (memory.in_scope(h.get("file", ""), notes) for h in hits) if n]
        except Exception:  # noqa: BLE001  search down: look at every note of the scope
            rels = None
    elif search:
        rels = search(title)
    if rels is None:     # search down: the likeliest notes first, by shared words, so the decider sees the best few
        want = memory_flags.content_words(title + " " + body)
        rels = sorted(notes, key=lambda r: (-len(want & memory_flags.content_words(notes[r]["summary"])), r))
    asked = 0
    for rel in rels:
        if rel not in notes:
            continue
        verdict = None
        if decide and asked < SAME_ASKED:
            asked += 1
            verdict = memory_decide.same_note(title, body, notes[rel]["summary"])
        if verdict if verdict is not None else says_the_same(title, body, notes[rel]):
            return notes[rel]
    return None


# ---------- was-pushed ----------

def hook_log_rows():
    return _read_jsonl(os.path.join(memory_hook.state_dir(), "memory-hook.jsonl"))


def was_pushed(note, project, window=None, sessions=None, rows=None):
    """'yes' | 'no' | 'unknown' (see the top of this file)."""
    if not note:
        return "no"
    rows = hook_log_rows() if rows is None else rows
    if sessions:
        mine = [r for r in rows if r.get("session") in sessions]
    else:
        lo, hi = window or ("", "")
        mine = [r for r in rows if r.get("repo") == project and lo <= str(r.get("when", "")) <= (hi or "9")] \
            if window else []
    if not mine or not any("paths" in r for r in mine):
        return "unknown"
    real = os.path.realpath(note["path"])
    return "yes" if any(os.path.realpath(p) == real for r in mine for p in r.get("paths") or []) else "no"


# ---------- writing a draft ----------

def slug(text, words=6):
    return "-".join(re.findall(r"[a-z0-9]+", text.lower())[:words]) or "lesson"


def front(to, summary, files, known, pushed, same_as, today, job, written_by="fixed-rule", why="", local_only=False):
    out = ["---", "to: " + to, "summary: " + memory_keep._yaml(summary)]
    out += ["files:"] + ["  - " + f for f in files] if files else ["files: []"]
    out += ["pinned: false", "already-known: " + known, "was-pushed: " + pushed]
    if same_as:
        out.append("same-as: " + same_as)
    out += ["date: " + today, "job: " + job, "written-by: " + written_by]
    if why:
        out.append("fixed-rule-why: " + memory_keep._yaml(why))
    if local_only:
        out += ["local-only: true", "local-only-by: filter", "local-only-at: " + today]
    return "\n".join(out + ["---", ""])


# ---------- Haiku writes the lesson ----------

def writer_mode():
    """'haiku' (default) or 'fixed' (BRAIN_DRAFT_WRITER)."""
    return "fixed" if (os.environ.get("BRAIN_DRAFT_WRITER") or "").strip().lower() == "fixed" else "haiku"


def ask_haiku(prompt, system, timeout=HAIKU_SECONDS):
    """The answer text of Haiku: the one call `brain ask` makes (ask/ask.py haiku_write). Raises on any trouble."""
    import ask   # loaded only here: it imports the search and jobs helpers
    return ask.haiku_write(prompt, system=system, timeout=timeout)[0]


def parse_lesson(answer):
    """(summary, body) from Haiku's `SUMMARY: ...` / `BODY: ...` answer. ValueError (plain words) when it is not in
    that form, empty or longer than the limits."""
    text = re.sub(r"\*\*|`{3}\w*", "", answer or "")
    m = re.search(r"^\s*SUMMARY:\s*(.+?)\s*^\s*BODY:\s*(.+?)\s*\Z", text, re.S | re.M | re.I)
    if not m:
        raise ValueError("the answer was empty or not in the SUMMARY / BODY form")
    summary, body = " ".join(m.group(1).split()), "\n".join(l.rstrip() for l in m.group(2).strip().splitlines())
    if not summary or not body.strip():
        raise ValueError("the answer had an empty summary or body")
    if len(summary.split()) > SUMMARY_WORDS or len(body.split()) > BODY_WORDS:
        raise ValueError("the answer was longer than %d / %d words" % (SUMMARY_WORDS, BODY_WORDS))
    return summary, body


def haiku_lesson(title, body):
    """(summary, body, '') from Haiku, written from the scrubbed records only and scrubbed again; or (None, None, why)
    in plain words when the fixed-rule draft has to stand in. Never raises."""
    try:
        answer = ask_haiku("Records of the job (names hidden):\n\n%s\n\n%s" % (title, body), HAIKU_SYSTEM)
    except TimeoutError:
        return None, None, "Haiku was too slow (over %d s)" % HAIKU_SECONDS
    except Exception as why:  # noqa: BLE001  not sent, not running, failing: the fixed-rule draft stands in
        return None, None, "Haiku could not answer (%s)" % type(why).__name__
    try:
        summary, text = parse_lesson(answer)
    except ValueError as why:
        return None, None, str(why)
    try:
        return drafts.scrub(summary), drafts.scrub(text), ""
    except drafts.Unsure:
        return None, None, "Haiku's answer could not be made safe by the names filter"


def check_limits(store, job, today):
    rows = log_rows(store)
    if any(r.get("job") == job for r in rows):
        raise DraftError("a draft was already written for job %s (one draft per job)" % job)
    week = iso_week(today)
    if sum(1 for r in rows if r.get("week") == week) >= MAX_PER_WEEK:
        raise DraftError("%d drafts were already written in week %s (the most there can be). <user> looks at them "
                         "first (brain checkup); the next one can be written next week." % (MAX_PER_WEEK, week))


def _file_name(store, project, title):
    base = "%s-lesson-%s" % (project, slug(title))
    name, n = base + ".md", 2
    while os.path.lexists(os.path.join(store, "drafts", name)) or os.path.lexists(os.path.join(store, EXPIRED, name)):
        name, n = "%s-%d.md" % (base, n), n + 1
    return name


def add(to, job, title, source, body, store=None, files=(), window=None, sessions=None, name=None, today=None,
        search="qmd", hook_rows=None):
    """Write one lesson draft. Returns {"path", "name", "already_known", "was_pushed", "same_as", "written_by"}. Raises DraftError."""
    store, today = store_path(store), today or time.strftime("%Y-%m-%d")
    if not os.path.isdir(store):
        raise DraftError("the memory store is not there (%s); set BRAIN_MEMORY_STORE if it lives elsewhere" % store)
    try:
        project, kind, _, _ = memory_keep.parse_target(to)
    except memory_keep.KeepError as why:
        raise DraftError(str(why)) from None
    if not (job or "").strip() or not (title or "").strip() or not (source or "").strip():
        raise DraftError("a draft needs --job, --title and --source (where the lesson came from)")
    check_limits(store, job, today)
    title, body = " ".join(title.split()), body.strip()
    guard, local_only, why = memory_keep.guard_problem(), False, ""
    if guard:
        local_only, why = True, "the private names list is not usable, so nothing was sent to Haiku"
    else:
        try:
            title, body = drafts.scrub(title), drafts.scrub(body)
        except drafts.Unsure:
            local_only, why = True, "the names filter was not sure, so nothing was sent to Haiku"
    if not local_only and memory_decide.lesson_worth(title, body) is False:
        # The librarian's fixed signals decided that a draft is considered; this only decides whether it is worth
        # writing. Text that the names filter could not clean is never sent (local_only), so it is never asked.
        memory_decide.note("skipped", task="memory-lesson-worth", job=job, to=to)
        raise NotWorth("the decider says job %s is not worth a lesson (memory-lesson-worth); no draft was written" % job)
    by = "fixed-rule"
    if writer_mode() == "fixed":
        why = ""
    elif not local_only:
        lesson, text, why = haiku_lesson(title, body)
        if text:
            by, title, body = "haiku", lesson, text
    note = (already_known(store, project, title, body, search) if not local_only
            else already_known(store, project, title, body, search, decide=False))
    pushed = was_pushed(note, project, window, sessions, hook_rows)
    name = name or _file_name(store, project, title)
    text = front(to, title[:SUMMARY_CHARS], list(files), "yes" if note else "no", pushed, note["rel"] if note else None,
                 today, job, by, why, local_only)
    text += "# %s\n\n%s\n\nSource: %s\n" % (title, body, " ".join(source.split()))
    path = os.path.join(store, "drafts", name)
    drafts._write(store, path, text)
    _log(store, today, name, job, to, note, pushed, by)
    return {"path": path, "name": name, "already_known": bool(note), "was_pushed": pushed,
            "same_as": note["rel"] if note else None, "written_by": by}


def _log(store, today, name, job, to, note, pushed, by):
    row = {"date": today, "week": iso_week(today), "name": name, "job": job, "to": to,
           "already_known": "yes" if note else "no", "was_pushed": pushed, "same_as": note["rel"] if note else None,
           "written_by": by}
    with open(os.path.join(store, LOG), "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


# ---------- the inbox ----------

def waiting(store=None):
    """[{name, date, summary, already_known, was_pushed, same_as, job}] for the memory drafts that wait, oldest first."""
    folder = os.path.join(store_path(store), "drafts")
    out = []
    for name in sorted(os.listdir(folder)) if os.path.isdir(folder) else []:
        if name.endswith(".md") and name not in ("README.md", "CONTEXT.md"):
            try:
                with open(os.path.join(folder, name), encoding="utf-8") as f:
                    fm = memory.front(f.read())
            except (OSError, UnicodeDecodeError):
                continue
            out.append({"name": name, "date": str(fm.get("date") or ""), "summary": fm.get("summary") or "(no summary)", "to": fm.get("to") or "",
                        "already_known": fm.get("already-known") or "?", "was_pushed": fm.get("was-pushed") or "?",
                        "same_as": fm.get("same-as") or "", "job": fm.get("job") or ""})
    return sorted(out, key=lambda d: (d["date"], d["name"]))


def expire(store=None, today=None):
    """Move drafts older than EXPIRE_DAYS (by their date, else the file's age) to history/expired-drafts/. Returns names."""
    store, today = store_path(store), today or time.strftime("%Y-%m-%d")
    moved = []
    for d in waiting(store):
        date = d["date"] if re.fullmatch(r"\d{4}-\d{2}-\d{2}", d["date"]) else time.strftime(
            "%Y-%m-%d", time.localtime(os.path.getmtime(os.path.join(store, "drafts", d["name"]))))
        if memory_flagfile.days_between(date, today) > EXPIRE_DAYS:
            dest = os.path.join(store, EXPIRED, d["name"])
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            if os.path.lexists(dest):
                dest = "%s.%s" % (dest, time.strftime("%H%M%S"))
            os.replace(os.path.join(store, "drafts", d["name"]), dest)
            moved.append(d["name"])
    return moved


def drop(name, store=None, today=None):
    """<user>'s drop: the draft moves to history/dropped-drafts/ (never deleted, never pushed). Returns the new path."""
    store = store_path(store)
    src = os.path.join(store, "drafts", os.path.basename(name))
    if not os.path.isfile(src):
        raise DraftError("no memory draft called %s in the store's drafts/ folder" % name)
    dest = os.path.join(store, "history", "dropped-drafts", os.path.basename(src))
    if os.path.lexists(dest):
        dest = "%s.%s" % (dest, time.strftime("%H%M%S"))
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    os.replace(src, dest)
    return dest


# ---------- command line ----------

def _flag(argv, name):
    if name in argv:
        i = argv.index(name)
        if i + 1 >= len(argv):
            raise DraftError("%s needs a value" % name)
        value = argv[i + 1]
        del argv[i:i + 2]
        return value
    return None


def cli_add(argv):
    to, job, title = _flag(argv, "--to"), _flag(argv, "--job"), _flag(argv, "--title")
    source, files = _flag(argv, "--source"), _flag(argv, "--files")
    window, sessions, name = _flag(argv, "--window"), _flag(argv, "--sessions"), _flag(argv, "--name")
    if argv or not to:
        raise DraftError('usage: brain memory-drafts add --to projects/<repo>/lessons --job ID --title "line" '
                         '--source "where from" [--files a,b] [--window START,END | --sessions a,b] (body on stdin)')
    got = add(to, job, title, source, sys.stdin.read(), files=[f for f in (files or "").split(",") if f.strip()],
              window=tuple(window.split(",", 1)) if window and "," in window else None,
              sessions=[s for s in (sessions or "").split(",") if s], name=name)
    print("draft written: %s (written by %s; already known: %s, was pushed: %s)" % (
        got["path"].replace(os.path.expanduser("~"), "~", 1), got["written_by"], "yes" if got["already_known"] else "no",
        got["was_pushed"]))
    return 0


def main(argv):
    argv, cmd = list(argv), (argv[0] if argv else "list")
    try:
        if cmd == "add":
            return cli_add(argv[1:])
        if cmd == "expire":
            print("\n".join("expired to history/expired-drafts/: " + n for n in expire()) or "no draft is older than 30 days")
        elif cmd == "drop" and len(argv) == 2:
            print("dropped: moved to " + drop(argv[1]).replace(os.path.expanduser("~"), "~", 1))
        elif cmd == "list":
            print("\n".join("%s  %s  [already known: %s, pushed: %s]" % (d["date"], d["name"], d["already_known"],
                  d["was_pushed"]) + "\n    " + d["summary"] for d in waiting()) or "no memory draft waits")
        else:
            print(__doc__.split("\n\n")[0], file=sys.stderr)
            return 2
    except (DraftError, OSError) as why:
        print("brain memory-drafts: %s" % why, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
