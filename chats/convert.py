#!/usr/bin/env python3
"""Turn Claude Code chat logs into short, redacted markdown notes.

Source : ~/.claude/projects/<encoded-cwd>/<session>.jsonl   (read only, never changed)
Output : ~/.local/share/second-brain/chats/<date>-<project>-<id>.md  (low-value chats: chats/low/, not searched)
State  : ~/.local/share/second-brain/chats/.state.json

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
OUT = os.path.join(HOME, ".local", "share", "second-brain", "chats")
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


def extract(path, include_sidechain):
    """Return dict(turns=[(role, ts, text)], meta=...) for one jsonl file."""
    turns = []
    meta = {"titles": {}, "cwd": None, "first": None, "last": None, "session": None}
    for d in read_lines(path):
        t = d.get("type")
        if t == "summary" and d.get("summary"):
            meta["titles"].setdefault("summary", d["summary"])
            continue
        if t == "custom-title" and d.get("customTitle"):
            meta["titles"]["custom"] = d["customTitle"]
            continue
        if t == "ai-title" and d.get("aiTitle"):
            meta["titles"]["ai"] = d["aiTitle"]
            continue
        if t not in ("user", "assistant"):
            continue
        if d.get("isSidechain") and not include_sidechain:
            continue
        ts = parse_ts(d.get("timestamp"))
        if ts:
            meta["first"] = meta["first"] or ts
            meta["last"] = ts
        meta["cwd"] = meta["cwd"] or d.get("cwd")
        meta["session"] = meta["session"] or d.get("sessionId")
        if d.get("isMeta") or d.get("isCompactSummary") or d.get("isVisibleInTranscriptOnly"):
            continue
        if t == "assistant" and d.get("isApiErrorMessage"):
            continue
        msg = d.get("message") or {}
        content = msg.get("content")
        if t == "user":
            for raw in texts_of(content, "text"):
                text = clean_user_text(raw)
                if text:
                    turns.append(["user", ts, text])
        else:
            for raw in texts_of(content, "text"):
                text = raw.strip()
                if not text or text == "No response requested.":
                    continue
                # Claude Code writes one line per content block: merge consecutive replies.
                if turns and turns[-1][0] == "assistant":
                    turns[-1][2] += "\n\n" + text
                else:
                    turns.append(["assistant", ts, text])
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
            except OSError:
                pass
        return sig


def low_value(cwd, turns):
    p = cwd or ""
    if p == "/tmp" or p.startswith(("/tmp/", os.path.join(HOME, ".cache") + "/")):
        return True
    if re.search(r"/pm-run(-\d+)?(/|$)", p):
        return True
    return sum(len(t[2]) for t in turns) < LOW_MAX_CHARS


def build_note(sess):
    """Return (filename, text, n_redactions, n_messages) or None if the chat has nothing to keep."""
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
            for k in ("cwd", "session"):
                meta[k] = meta[k] or m2[k]
            if m2["first"] and (not meta["first"] or m2["first"] < meta["first"]):
                meta["first"] = m2["first"]
            if m2["last"] and (not meta["last"] or m2["last"] > meta["last"]):
                meta["last"] = m2["last"]
    if not turns:
        return None

    redactions = 0
    for t in turns:
        t[2], k = redact(t[2])
        redactions += k

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

    blocks = []
    for role, ts, text in turns:
        who = "<user>" if role == "user" else "Claude"
        when = ts.astimezone().strftime("%H:%M") if ts else ""
        body = trim(text, USER_MAX if role == "user" else ASSISTANT_MAX)
        blocks.append(f"**{who}** ({when}):\n\n{body}\n")

    total = sum(len(b) + 1 for b in blocks)
    if total > NOTE_MAX:
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
        blocks = head + [f"*[… {cut} messages cut from the middle to keep this note short …]*\n"] + tail

    short = session_id.replace("-", "")[:8]
    name = f"{local_first:%Y-%m-%d}-{project_slug(cwd)}-{short}.md"
    if low_value(cwd, turns):
        name = os.path.join(LOW_DIR, name)
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
    text = "\n".join(fm) + f"\n\n# {title}\n\n" + "\n".join(blocks)
    # Safety net: one more pass over the finished note.
    text_body = text.split("\n---\n", 1)
    body, k = redact(text_body[1])
    redactions += k
    text = text_body[0] + "\n---\n" + body
    return name, text, redactions, len(turns)


# ---------------------------------------------------------------- discovery

def find_sessions():
    sessions = []
    all_mains = {os.path.basename(f)[:-6] for f in glob.glob(os.path.join(SRC, "*", "*.jsonl"))}
    for projdir in sorted(os.listdir(SRC)):
        pdir = os.path.join(SRC, projdir)
        if not os.path.isdir(pdir):
            continue
        mains = {os.path.basename(f)[:-6]: f for f in glob.glob(os.path.join(pdir, "*.jsonl"))
                 if not os.path.basename(f).startswith("agent-")}
        dirs = {d for d in os.listdir(pdir) if os.path.isdir(os.path.join(pdir, d)) and d != "memory"}
        for sid in sorted(set(mains) | dirs):
            subs = glob.glob(os.path.join(pdir, sid, "subagents", "agent-*.jsonl"))
            main = mains.get(sid)
            if not main and (not subs or sid in all_mains):
                continue  # nothing to read, or the main chat lives in another project folder
            key = main or os.path.join(pdir, sid)
            sessions.append(Session(key, main, subs, projdir))
    return sessions


# ---------------------------------------------------------------- main

def load_state(path):
    try:
        with open(path) as fh:
            return json.load(fh)
    except (OSError, ValueError):
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


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--all", action="store_true", help="reconvert every chat")
    ap.add_argument("--dry-run", action="store_true", help="print what would happen, write nothing")
    ap.add_argument("--sample", type=int, metavar="N", help="convert N random chats into a temp folder")
    ap.add_argument("--out", default=OUT, help=argparse.SUPPRESS)
    ap.add_argument("--quiet", action="store_true", help="only the summary line")
    args = ap.parse_args(argv)

    t0 = time.time()
    sessions = find_sessions()

    if args.sample:
        out_dir = tempfile.mkdtemp(prefix="chat-sample-")
        os.chmod(out_dir, 0o700)
        random.seed()
        picked = random.sample(sessions, min(args.sample, len(sessions)))
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

    out_dir = args.out
    if not args.dry_run:
        os.makedirs(out_dir, mode=0o700, exist_ok=True)
        os.chmod(out_dir, 0o700)  # private: chats hold business and family talk
        lock = open(os.path.join(out_dir, ".lock"), "w")
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            print("convert.py: another run is busy, skipping")
            return 0
    state_path = os.path.join(out_dir, STATE_NAME)
    state = load_state(state_path)
    if not isinstance(state.get("sources"), dict):
        state = {"version": 1, "sources": {}}
    src_state = state["sources"]

    seen = set()
    todo = []
    for s in sessions:
        seen.add(s.key)
        sig = s.signature()
        old = src_state.get(s.key)
        if args.all or not old or old.get("sig") != sig:
            todo.append((s, sig))

    gone = [k for k in src_state if k not in seen]
    stats = {"converted": 0, "written": 0, "empty": 0, "removed": 0, "redactions": 0, "errors": 0}

    def drop_note(entry):
        note = entry.get("note") if entry else None
        if note and os.path.exists(os.path.join(out_dir, note)):
            if args.dry_run:
                return
            os.remove(os.path.join(out_dir, note))

    for k in gone:
        if args.dry_run:
            print(f"would delete note for vanished source {k}: {src_state[k].get('note')}")
        else:
            drop_note(src_state.pop(k))
        stats["removed"] += 1

    if args.dry_run:
        for s, _ in todo:
            print(f"would convert {s.key}")
        print(f"dry run: {len(todo)} to convert, {len(gone)} to delete, {len(sessions) - len(todo)} unchanged")
        return 0

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
            drop_note(old)
        src_state[s.key] = {"sig": sig, "note": new_note}
        if i % 100 == 0:
            save_state(state_path, state)
            if not args.quiet:
                print(f"  {i}/{len(todo)} sessions  ({time.time() - t0:.0f}s, {stats['redactions']} redactions)", flush=True)

    save_state(state_path, state)
    notes = [f for f in os.listdir(out_dir) if f.endswith(".md")]
    size = sum(os.path.getsize(os.path.join(out_dir, f)) for f in notes)
    low_path = os.path.join(out_dir, LOW_DIR)
    n_low = len([f for f in os.listdir(low_path) if f.endswith(".md")]) if os.path.isdir(low_path) else 0
    print(
        f"chats: {len(sessions)} sessions, {stats['converted']} converted, {stats['written']} notes written, "
        f"{stats['empty']} empty, {stats['removed']} removed, {stats['errors']} errors, "
        f"{stats['redactions']} redactions; folder has {len(notes)} notes, {size / 1e6:.1f} MB, {n_low} set aside in {LOW_DIR}/; "
        f"{time.time() - t0:.0f}s"
    )
    return 1 if stats["errors"] and not stats["converted"] else 0


if __name__ == "__main__":
    sys.exit(main())
