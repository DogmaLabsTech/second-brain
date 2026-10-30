#!/usr/bin/env python3
"""Turn Claude Code chat logs into short, redacted markdown notes.

Source : ~/.claude/projects/<encoded-cwd>/<session>.jsonl and each nodeterm account's
         ~/.config/node-terminal/claude-accounts/*/projects/ (canvas agents, 2026-10-30)   (read only, never changed)
Output : ~/brain/chats/<date>-<project>-<id>.md  (low-value chats: chats/low/, not searched)
State  : ~/brain/chats/.state.json

    python3 -I convert.py              only new or changed chats
    python3 -I convert.py --all        redo every chat
    python3 -I convert.py --dry-run    say what would happen, write nothing
    python3 -I convert.py --sample 20  convert 20 random chats into a temp folder

Stdlib only. Safe to call from a reindex script: exit code 0 on success, one
summary line at the end, a lock file stops two runs at once.
"""

import argparse
import fcntl
import glob
import json
import os
import random
import re
import sys
import tempfile
import time
from datetime import datetime, timezone

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from redact import redact  # noqa: E402

HOME = os.path.expanduser("~")
SRC = os.path.join(HOME, ".claude", "projects")
# nodeterm starts its canvas agents with their own Claude folders (one per account); their chats live there, not in
# SRC (2026-10-30). Same layout, read the same way.
NODETERM_SRCS = os.path.join(".config", "node-terminal", "claude-accounts", "*", "projects")   # under HOME
OUT = os.path.join(HOME, "brain", "chats")
STATE_NAME = ".state.json"

USER_MAX = 1000
ASSISTANT_MAX = 2000
NOTE_MAX = 40_000
TITLE_MAX = 80

# Low-value chats still get a note, but in LOW_DIR, which the search skips (index.yml).
# Tests and scratch runs in /tmp or ~/.cache, automated PM builder runs (their reports are in the
# project-manager vault), and chats with almost nothing said ("Reply with just OK").
LOW_DIR = "low"
LOW_MAX_CHARS = 600

# User text that is machine noise, not something <user> typed.
NOISE_PREFIXES = (
    "<local-command-caveat>", "<local-command-stdout>", "<local-command-stderr>",
    "<bash-stdout>", "<bash-stderr>", "<bash-input>", "<task-notification>",
    "<command-message>", "Caveat: The messages below were generated",
    "[Request interrupted", "The run-watch plugin sent a message",
    "Another Claude session sent a message", "Stop hook feedback",
    "Base directory for this skill", "[Image", "[burn-gauge]",
    "This session is being continued from a previous conversation",
    "Your claude.ai usage limit has reset",
)
STRIP_BLOCKS = re.compile(
    r"<(system-reminder|ide_selection|ide_opened_file|ide_diagnostics|user-prompt-submit-hook|"
    r"local-command-caveat|local-command-stdout|task-notification|clean-view[\w-]*|hook[\w-]*)\b[^>]*>.*?</\1>",
    re.S,
)
UNWRAP_TAGS = re.compile(r"</?pasted_content[^>]*>")
CMD_NAME = re.compile(r"<command-name>\s*(/?[^<]*?)\s*</command-name>", re.S)
CMD_ARGS = re.compile(r"<command-args>(.*?)</command-args>", re.S)
ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


# ---------------------------------------------------------------- reading

def read_lines(path):
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except ValueError:
                continue
            if isinstance(d, dict):
                yield d


def clean_user_text(text):
    if not text:
        return ""
    text = ANSI.sub("", text)
    if "<command-name>" in text:
        name = CMD_NAME.search(text)
        args = CMD_ARGS.search(text)
        args = args.group(1).strip() if args else ""
        if not name or not args:
            return ""  # bare /clear, /model ...: noise
        return f"{name.group(1).strip()} {args}"
    text = STRIP_BLOCKS.sub("", text)
    text = UNWRAP_TAGS.sub("", text)
    text = text.strip()
    if not text or text.startswith(NOISE_PREFIXES):
        return ""
    return text


def texts_of(content, want):
    if isinstance(content, str):
        return [content] if want == "text" else []
    out = []
    if isinstance(content, list):
        for b in content:
            if isinstance(b, dict) and b.get("type") == "text" and isinstance(b.get("text"), str):
                out.append(b["text"])
    return out


def parse_ts(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def _record_title(d, t, titles):
    """summary / custom-title / ai-title lines carry the chat's title, not talk: True when this line was one."""
    if t == "summary" and d.get("summary"):
        titles.setdefault("summary", d["summary"])
    elif t == "custom-title" and d.get("customTitle"):
        titles["custom"] = d["customTitle"]
    elif t == "ai-title" and d.get("aiTitle"):
        titles["ai"] = d["aiTitle"]
    else:
        return False
    return True


def _note_clock_and_ids(d, ts, meta):
    if ts:
        meta["first"] = meta["first"] or ts
        meta["last"] = ts
    meta["cwd"] = meta["cwd"] or d.get("cwd")
    meta["session"] = meta["session"] or d.get("sessionId")


def _machine_line(d, t):
    """Lines Claude Code writes for itself: meta, compact summaries, API errors."""
    if d.get("isMeta") or d.get("isCompactSummary") or d.get("isVisibleInTranscriptOnly"):
        return True
    return t == "assistant" and d.get("isApiErrorMessage")


def _add_user_turns(turns, content, ts):
    for raw in texts_of(content, "text"):
        text = clean_user_text(raw)
        if text:
            turns.append(["user", ts, text])


def _add_assistant_turns(turns, content, ts):
    for raw in texts_of(content, "text"):
        text = raw.strip()
        if not text or text == "No response requested.":
            continue
        # Claude Code writes one line per content block: merge consecutive replies.
        if turns and turns[-1][0] == "assistant":
            turns[-1][2] += "\n\n" + text
        else:
            turns.append(["assistant", ts, text])


def extract(path, include_sidechain):
    """Return dict(turns=[(role, ts, text)], meta=...) for one jsonl file."""
    turns = []
    meta = {"titles": {}, "cwd": None, "first": None, "last": None, "session": None}
    for d in read_lines(path):
        t = d.get("type")
        if _record_title(d, t, meta["titles"]):
            continue
        if t not in ("user", "assistant"):
            continue
        if d.get("isSidechain") and not include_sidechain:
            continue
        ts = parse_ts(d.get("timestamp"))
        _note_clock_and_ids(d, ts, meta)
        if _machine_line(d, t):
            continue
        content = (d.get("message") or {}).get("content")
        if t == "user":
            _add_user_turns(turns, content, ts)
        else:
            _add_assistant_turns(turns, content, ts)
    return turns, meta


# ---------------------------------------------------------------- naming

def project_from_dir(dirname):
    """Best-effort decode of '-home-user-foo-bar' (dashes are ambiguous)."""
    return "/" + dirname.lstrip("-").replace("--", "/.").replace("-", "/")


def project_slug(cwd):
    p = cwd or ""
    if p.startswith(HOME):
        p = p[len(HOME):]
    p = p.strip("/")
    for prefix in ("projects/", "projects/experiments/", "projects/third-party/",
                   "projects/", ".agent-os/worktrees/", ".config/omarchy/plugins/", ".config/"):
        if p.startswith(prefix):
            p = p[len(prefix):]
            break
    slug = re.sub(r"[^a-z0-9]+", "-", p.lower()).strip("-")
    slug = slug[:40].strip("-")
    return slug or "home"


def fmt_duration(first, last):
    if not first or not last:
        return "0m"
    secs = int((last - first).total_seconds())
    h, m = divmod(max(secs, 0) // 60, 60)
    return f"{h}h {m}m" if h else f"{m}m"


def trim(text, limit):
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + " […]"


def one_line(text):
    return re.sub(r"\s+", " ", text).strip()


# ---------------------------------------------------------------- one session

class Session:
    def __init__(self, key, main, subagents, projdir):
        self.key = key            # state key: main jsonl path, or the orphan folder
        self.main = main          # path or None
        self.subagents = subagents
        self.projdir = projdir

    def signature(self):
        files = ([self.main] if self.main else []) + self.subagents
        sig = []
        for f in files:
            try:
                st = os.stat(f)
                sig.append([os.path.basename(f), int(st.st_mtime), st.st_size])
            except OSError as why:   # left out of the signature, so the session is read again next time
                print(f"convert: could not stat {f}: {why}", file=sys.stderr)
        return sig


def low_value(cwd, turns):
    p = cwd or ""
    if p == "/tmp" or p.startswith(("/tmp/", os.path.join(HOME, ".cache") + "/")):
        return True
    if re.search(r"/pm-run(-\d+)?(/|$)", p):
        return True
    return sum(len(t[2]) for t in turns) < LOW_MAX_CHARS


def _fold_subagent_meta(meta, m2):
    for k in ("cwd", "session"):
        meta[k] = meta[k] or m2[k]
    if m2["first"] and (not meta["first"] or m2["first"] < meta["first"]):
        meta["first"] = m2["first"]
    if m2["last"] and (not meta["last"] or m2["last"] > meta["last"]):
        meta["last"] = m2["last"]


def _read_turns(sess):
    """(turns, meta, used_sub): the main chat, or the subagents' talk when they are all there is."""
    turns, meta = ([], {"titles": {}, "cwd": None, "first": None, "last": None, "session": None})
    if sess.main:
        turns, meta = extract(sess.main, include_sidechain=False)
    used_sub = False
    if not turns and sess.subagents:
        # Subagent transcripts only when they are all there is.
        used_sub = True
        for f in sorted(sess.subagents):
            t2, m2 = extract(f, include_sidechain=True)
            turns.extend(t2)
            _fold_subagent_meta(meta, m2)
    return turns, meta, used_sub


def redact_turns(turns):
    """Redact every message in place; how many things were hidden."""
    redactions = 0
    for t in turns:
        t[2], k = redact(t[2])
        redactions += k
    return redactions


def render_blocks(turns, agent="Claude"):
    blocks = []
    for role, ts, text in turns:
        who = "<user>" if role == "user" else agent
        when = ts.astimezone().strftime("%H:%M") if ts else ""
        body = trim(text, USER_MAX if role == "user" else ASSISTANT_MAX)
        blocks.append(f"**{who}** ({when}):\n\n{body}\n")
    return blocks


def cut_middle(blocks):
    """A note over NOTE_MAX keeps its start and its end, with a line saying how many messages were cut."""
    if sum(len(b) + 1 for b in blocks) <= NOTE_MAX:
        return blocks
    budget_head, budget_tail = int(NOTE_MAX * 0.55), int(NOTE_MAX * 0.4)
    head, size = [], 0
    for b in blocks:
        if size + len(b) > budget_head and head:
            break
        head.append(b)
        size += len(b) + 1
    tail, size = [], 0
    for b in reversed(blocks[len(head):]):
        if size + len(b) > budget_tail and tail:
            break
        tail.insert(0, b)
        size += len(b) + 1
    cut = len(blocks) - len(head) - len(tail)
    return head + [f"*[… {cut} messages cut from the middle to keep this note short …]*\n"] + tail


def _frontmatter(title, local_first, cwd, session_id, turns, meta, sess, used_sub):
    fm = [
        "---",
        f"title: {json.dumps(title, ensure_ascii=False)}",
        f"date: {local_first:%Y-%m-%d}",
        f"started: {local_first.isoformat(timespec='minutes')}",
        f"project: {json.dumps(cwd)}",
        f"session: {session_id}",
        f"messages: {len(turns)}",
        f"duration: {fmt_duration(meta['first'], meta['last'])}",
        f"source: {json.dumps(sess.key.replace(HOME, '~', 1))}",
    ]
    if used_sub:
        fm.append("subagents_only: true")
    fm.append("---")
    return fm


def build_note(sess):
    """Return (filename, text, n_redactions, n_messages) or None if the chat has nothing to keep."""
    turns, meta, used_sub = _read_turns(sess)
    if not turns:
        return None
    redactions = redact_turns(turns)

    session_id = meta["session"] or os.path.basename(sess.key).replace(".jsonl", "")
    cwd = meta["cwd"] or project_from_dir(sess.projdir)
    first = meta["first"] or datetime.fromtimestamp(os.path.getmtime(sess.main or sess.subagents[0]), timezone.utc)
    local_first = first.astimezone()

    titles = meta["titles"]
    first_user = next((t[2] for t in turns if t[0] == "user"), turns[0][2])
    title_src = titles.get("custom") or titles.get("summary") or titles.get("ai") or first_user
    title, k = redact(one_line(title_src))
    redactions += k
    title = trim(title, TITLE_MAX)

    blocks = cut_middle(render_blocks(turns))

    short = session_id.replace("-", "")[:8]
    name = f"{local_first:%Y-%m-%d}-{project_slug(cwd)}-{short}.md"
    if low_value(cwd, turns):
        name = os.path.join(LOW_DIR, name)
    fm = _frontmatter(title, local_first, cwd, session_id, turns, meta, sess, used_sub)
    text = "\n".join(fm) + f"\n\n# {title}\n\n" + "\n".join(blocks)
    # Safety net: one more pass over the finished note.
    text_body = text.split("\n---\n", 1)
    body, k = redact(text_body[1])
    redactions += k
    text = text_body[0] + "\n---\n" + body
    return name, text, redactions, len(turns)


# ---------------------------------------------------------------- discovery

def sources():
    """Every Claude projects folder: ~/.claude's and each nodeterm account's."""
    return [SRC] + sorted(glob.glob(os.path.join(HOME, NODETERM_SRCS)))


def _sessions_in(src, projdir, all_mains):
    """The sessions of one project folder: each main chat, or a folder of subagents with no main chat anywhere."""
    pdir = os.path.join(src, projdir)
    mains = {os.path.basename(f)[:-6]: f for f in glob.glob(os.path.join(pdir, "*.jsonl"))
             if not os.path.basename(f).startswith("agent-")}
    dirs = {d for d in os.listdir(pdir) if os.path.isdir(os.path.join(pdir, d)) and d != "memory"}
    sessions = []
    for sid in sorted(set(mains) | dirs):
        subs = glob.glob(os.path.join(pdir, sid, "subagents", "agent-*.jsonl"))
        main = mains.get(sid)
        if not main and (not subs or sid in all_mains):
            continue  # nothing to read, or the main chat lives in another project folder
        sessions.append(Session(main or os.path.join(pdir, sid), main, subs, projdir))
    return sessions


def find_sessions():
    srcs = [s for s in sources() if os.path.isdir(s)]
    all_mains = {os.path.basename(f)[:-6] for s in srcs for f in glob.glob(os.path.join(s, "*", "*.jsonl"))}
    sessions = []
    for src in srcs:
        for projdir in sorted(os.listdir(src)):
            if os.path.isdir(os.path.join(src, projdir)):
                sessions += _sessions_in(src, projdir, all_mains)
    return sessions


# ---------------------------------------------------------------- main

def load_state(path):
    try:
        with open(path) as fh:
            return json.load(fh)
    except FileNotFoundError:   # first run
        return {}
    except (OSError, ValueError) as why:
        print(f"convert: could not read the state file {path} ({why}); starting from an empty state", file=sys.stderr)
        return {}


def save_state(path, state):
    tmp = path + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(state, fh, indent=1, sort_keys=True)
    os.replace(tmp, path)


def write_note(out_dir, name, text):
    path = os.path.join(out_dir, name)
    os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(text)
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)


def _parse_args(argv):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--all", action="store_true", help="reconvert every chat")
    ap.add_argument("--dry-run", action="store_true", help="print what would happen, write nothing")
    ap.add_argument("--sample", type=int, metavar="N", help="convert N random chats into a temp folder")
    ap.add_argument("--out", default=OUT, help=argparse.SUPPRESS)
    ap.add_argument("--quiet", action="store_true", help="only the summary line")
    return ap.parse_args(argv)


def _write_sample(n, sessions):
    out_dir = tempfile.mkdtemp(prefix="chat-sample-")
    os.chmod(out_dir, 0o700)
    random.seed()
    picked = random.sample(sessions, min(n, len(sessions)))
    red = 0
    for s in picked:
        r = build_note(s)
        if r:
            write_note(out_dir, r[0], r[1])
            red += r[2]
            print(f"{r[0]}  ({r[3]} msgs, {len(r[1])//1024} KB, {r[2]} redactions)")
        else:
            print(f"(empty) {s.key}")
    print(f"sample written to {out_dir}  redactions={red}")
    return 0


def lock_out_dir(out_dir):
    """Make the private output folder and take its lock; the open lock file, or None when another run holds it."""
    os.makedirs(out_dir, mode=0o700, exist_ok=True)
    os.chmod(out_dir, 0o700)  # private: chats hold business and family talk
    lock = open(os.path.join(out_dir, ".lock"), "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        return None
    return lock


def load_sources(state_path):
    state = load_state(state_path)
    if not isinstance(state.get("sources"), dict):
        state = {"version": 1, "sources": {}}
    return state


def _what_changed(sessions, src_state, redo_all):
    """(todo, gone): the sessions to convert (with their signature) and the state keys whose source vanished."""
    seen = set()
    todo = []
    for s in sessions:
        seen.add(s.key)
        sig = s.signature()
        old = src_state.get(s.key)
        if redo_all or not old or old.get("sig") != sig:
            todo.append((s, sig))
    return todo, [k for k in src_state if k not in seen]


def _drop_note(out_dir, entry):
    note = entry.get("note") if entry else None
    if note and os.path.exists(os.path.join(out_dir, note)):
        os.remove(os.path.join(out_dir, note))


def _say_dry_run(sessions, todo, gone, src_state):
    for k in gone:
        print(f"would delete note for vanished source {k}: {src_state[k].get('note')}")
    for s, _ in todo:
        print(f"would convert {s.key}")
    print(f"dry run: {len(todo)} to convert, {len(gone)} to delete, {len(sessions) - len(todo)} unchanged")


def _convert_todo(todo, src_state, out_dir, state_path, state, stats, quiet, t0):
    for i, (s, sig) in enumerate(todo, 1):
        old = src_state.get(s.key)
        try:
            r = build_note(s)
        except Exception as e:  # one bad file must not stop the run
            stats["errors"] += 1
            print(f"error: {s.key}: {e!r}", file=sys.stderr)
            continue
        stats["converted"] += 1
        new_note = None
        if r:
            name, text, red, _n = r
            write_note(out_dir, name, text)
            new_note = name
            stats["written"] += 1
            stats["redactions"] += red
        else:
            stats["empty"] += 1
        if old and old.get("note") and old.get("note") != new_note:
            _drop_note(out_dir, old)
        src_state[s.key] = {"sig": sig, "note": new_note}
        if i % 100 == 0:
            save_state(state_path, state)
            if not quiet:
                print(f"  {i}/{len(todo)} sessions  ({time.time() - t0:.0f}s, {stats['redactions']} redactions)", flush=True)


def _summary_line(sessions, stats, out_dir, t0):
    notes = [f for f in os.listdir(out_dir) if f.endswith(".md")]
    size = sum(os.path.getsize(os.path.join(out_dir, f)) for f in notes)
    low_path = os.path.join(out_dir, LOW_DIR)
    n_low = len([f for f in os.listdir(low_path) if f.endswith(".md")]) if os.path.isdir(low_path) else 0
    return (
        f"chats: {len(sessions)} sessions, {stats['converted']} converted, {stats['written']} notes written, "
        f"{stats['empty']} empty, {stats['removed']} removed, {stats['errors']} errors, "
        f"{stats['redactions']} redactions; folder has {len(notes)} notes, {size / 1e6:.1f} MB, {n_low} set aside in {LOW_DIR}/; "
        f"{time.time() - t0:.0f}s"
    )


def main(argv=None):
    args = _parse_args(argv)
    t0 = time.time()
    sessions = find_sessions()

    if args.sample:
        return _write_sample(args.sample, sessions)

    out_dir = args.out
    if not args.dry_run:
        lock = lock_out_dir(out_dir)   # kept until main returns
        if lock is None:
            print("convert.py: another run is busy, skipping")
            return 0
    state_path = os.path.join(out_dir, STATE_NAME)
    state = load_sources(state_path)
    src_state = state["sources"]

    todo, gone = _what_changed(sessions, src_state, args.all)
    stats = {"converted": 0, "written": 0, "empty": 0, "removed": 0, "redactions": 0, "errors": 0}

    if args.dry_run:
        _say_dry_run(sessions, todo, gone, src_state)
        return 0

    for k in gone:
        _drop_note(out_dir, src_state.pop(k))
        stats["removed"] += 1

    _convert_todo(todo, src_state, out_dir, state_path, state, stats, args.quiet, t0)

    save_state(state_path, state)
    print(_summary_line(sessions, stats, out_dir, t0))
    return 1 if stats["errors"] and not stats["converted"] else 0


if __name__ == "__main__":
    sys.exit(main())
