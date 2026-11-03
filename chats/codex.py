#!/usr/bin/env python3
"""Turn Codex chat logs into short, redacted markdown notes, like convert.py does for Claude chats.

Source : ~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl   (read only, never changed)
Output : ~/brain/chats/codex/<date>-codex-<project>-<id>.md  (low-value: codex/low/, not searched)
State  : ~/brain/chats/codex/.state.json

    python3 -I codex.py              only new or changed chats
    python3 -I codex.py --all        redo every chat
    python3 -I codex.py --dry-run    say what would happen, write nothing
    python3 -I codex.py --sample 20  convert 20 random chats into a temp folder

Same rules as convert.py: only what was said (<user>'s messages and Codex's replies; no tool calls, tool output,
reasoning, or the instructions Codex is handed), the same redaction (redact.py), the same set-aside rules, plus
one for Codex: helper sessions (approval reviewers, spawned sub-agents) are set aside like Claude's subagents.
"""

import argparse
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
from convert import (LOW_DIR, TITLE_MAX, clean_user_text, cut_middle, fmt_duration,  # noqa: E402
                     load_sources, lock_out_dir, low_value, one_line, parse_ts, project_slug, read_lines,
                     redact_turns, render_blocks, save_state, trim, write_note)
from redact import redact  # noqa: E402

HOME = os.path.expanduser("~")
SRC = os.path.join(HOME, ".codex", "sessions")
OUT = os.path.join(os.environ.get("BRAIN_HOME") or os.path.join(HOME, "brain"), "chats", "codex")
STATE_NAME = ".state.json"

# What Codex itself puts in the user's turn: the AGENTS.md it read, the environment, plugin and skill lists.
CODEX_NOISE = (
    "# AGENTS.md instructions", "<environment_context>", "<user_instructions>", "<recommended_plugins>",
    "<skill>", "<turn_aborted>", "<permissions instructions>", "<collaboration_mode>",
)
IMAGE_TAGS = re.compile(r"</?image\b[^>]*>")


QUESTION_REPLY = re.compile(r"<send_user_message_question_reply>\s*(.*?)\s*</send_user_message_question_reply>", re.S)


def question_reply(m):
    """<user>'s tap on a Codex question card, as one plain line per question."""
    try:
        items = json.loads(m.group(1))
        return "\n".join(f"(answered a question) {i.get('question', '')} -> {i.get('answer', '')}" for i in items)
    except (ValueError, AttributeError, TypeError):
        return m.group(1)


def clean_codex_user(text):
    text = IMAGE_TAGS.sub("", text or "").strip()
    if not text or text.startswith(CODEX_NOISE):
        return ""
    return clean_user_text(QUESTION_REPLY.sub(question_reply, text))


def is_helper(meta):
    """Approval reviewers ("guardian") and sub-agents another Codex spawned: not <user> talking."""
    src = meta.get("source")
    return isinstance(src, dict) or meta.get("thread_source") in ("subagent", "guardian_review")


def _message_text(p, role):
    """The words of one Codex message: <user>'s with the noise cleaned out, Codex's as written."""
    want = "input_text" if role == "user" else "output_text"
    parts = [b.get("text") for b in p.get("content") or []
             if isinstance(b, dict) and b.get("type") == want and isinstance(b.get("text"), str)]
    if role == "user":
        return "\n\n".join(x for x in (clean_codex_user(s) for s in parts) if x)
    return "\n\n".join(s.strip() for s in parts if s.strip())


def _is_chat_message(t, p):
    return t == "response_item" and p.get("type") == "message" and p.get("role") in ("user", "assistant")


def extract(path):
    """Return (turns=[[role, ts, text]], meta) for one Codex jsonl file."""
    turns, meta, first, last = [], None, None, None
    for d in read_lines(path):
        t, p = d.get("type"), d.get("payload") or {}
        if t == "session_meta":
            meta = meta or p   # a resumed or forked chat repeats it; the first one is this chat
            continue
        if not _is_chat_message(t, p):
            continue
        ts = parse_ts(d.get("timestamp"))
        if ts:
            first, last = first or ts, ts
        role = p["role"]
        text = _message_text(p, role)
        if not text:
            continue
        if turns and turns[-1][0] == role:   # merge a run of replies (or pasted parts) into one message
            turns[-1][2] += "\n\n" + text
        else:
            turns.append([role, ts, text])
    return turns, (meta or {}), first, last


def _frontmatter(title, local_first, cwd, sid, name_line, turns, first_ts, last_ts, path, helper):
    fm = [
        "---",
        f"title: {json.dumps(title, ensure_ascii=False)}",
        f"date: {local_first:%Y-%m-%d}",
        f"started: {local_first.isoformat(timespec='minutes')}",
        "agent: codex",
        f"project: {json.dumps(cwd)}",
        f"session: {sid}",
    ]
    if name_line:
        fm.append(name_line)
    fm += [
        f"messages: {len(turns)}",
        f"duration: {fmt_duration(first_ts, last_ts)}",
        f"source: {json.dumps(path.replace(HOME, '~', 1))}",
    ]
    if helper:
        fm.append("helper: true")
    fm.append("---")
    return fm


def build_note(path, names=None):
    """Return (filename, text, n_redactions, n_messages) or None if the chat has nothing to keep."""
    turns, meta, first_ts, last_ts = extract(path)
    if not turns:
        return None
    redactions = redact_turns(turns)

    sid = meta.get("id") or meta.get("session_id") or os.path.basename(path)[:-6]
    cwd = meta.get("cwd") or ""
    first = first_ts or parse_ts(meta.get("timestamp")) or datetime.fromtimestamp(os.path.getmtime(path), timezone.utc)
    local_first = first.astimezone()

    first_user = next((t[2] for t in turns if t[0] == "user"), turns[0][2])
    title, k = redact(one_line(first_user))
    redactions += k
    title = trim(title, TITLE_MAX)

    blocks = cut_middle(render_blocks(turns, agent="Codex"))

    # Codex ids are time-ordered, so their first letters repeat: name the note by the last 8.
    name = f"{local_first:%Y-%m-%d}-codex-{project_slug(cwd)}-{sid.replace('-', '')[-8:]}.md"
    helper = is_helper(meta)
    if helper or low_value(cwd, turns):
        name = os.path.join(LOW_DIR, name)
    name_line = None
    if names and names.get(sid):
        thread, k = redact(one_line(names[sid]))
        redactions += k
        name_line = f"name: {json.dumps(trim(thread, TITLE_MAX), ensure_ascii=False)}"
    fm = _frontmatter(title, local_first, cwd, sid, name_line, turns, first_ts, last_ts, path, helper)
    body, k = redact(f"\n# {title}\n\n" + "\n".join(blocks))   # safety net: one more pass over the note
    redactions += k
    return name, "\n".join(fm) + "\n" + body, redactions, len(turns)


def thread_names():
    """<user>'s names for Codex threads (~/.codex/session_index.jsonl), by session id."""
    out = {}
    for d in read_lines(os.path.join(HOME, ".codex", "session_index.jsonl")) if os.path.exists(
            os.path.join(HOME, ".codex", "session_index.jsonl")) else []:
        if d.get("id") and d.get("thread_name"):
            out[d["id"]] = d["thread_name"]
    return out


def signature(path):
    try:
        st = os.stat(path)
        return [int(st.st_mtime), st.st_size]
    except OSError:
        return None


def _parse_args(argv):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--all", action="store_true", help="reconvert every chat")
    ap.add_argument("--dry-run", action="store_true", help="print what would happen, write nothing")
    ap.add_argument("--sample", type=int, metavar="N", help="convert N random chats into a temp folder")
    ap.add_argument("--src", default=SRC, help=argparse.SUPPRESS)
    ap.add_argument("--out", default=OUT, help=argparse.SUPPRESS)
    ap.add_argument("--quiet", action="store_true", help="only the summary line")
    return ap.parse_args(argv)


def _write_sample(n, files, names):
    out_dir = tempfile.mkdtemp(prefix="codex-sample-")
    os.chmod(out_dir, 0o700)
    red = 0
    for f in random.sample(files, min(n, len(files))):
        r = build_note(f, names)
        if r:
            write_note(out_dir, r[0], r[1])
            red += r[2]
            print(f"{r[0]}  ({r[3]} msgs, {len(r[1]) // 1024} KB, {r[2]} redactions)")
        else:
            print(f"(empty) {f}")
    print(f"sample written to {out_dir}  redactions={red}")
    return 0


def _drop_note(out_dir, note):
    if note and os.path.exists(os.path.join(out_dir, note)):
        os.remove(os.path.join(out_dir, note))


def _convert_todo(todo, src_state, names, out_dir, state_path, state, stats, quiet, t0):
    for i, (f, sig) in enumerate(todo, 1):
        old = src_state.get(f)
        try:
            r = build_note(f, names)
        except Exception as e:  # one bad file must not stop the run
            stats["errors"] += 1
            print(f"error: {f}: {e!r}", file=sys.stderr)
            continue
        stats["converted"] += 1
        new_note = None
        if r:
            write_note(out_dir, r[0], r[1])
            new_note = r[0]
            stats["written"] += 1
            stats["redactions"] += r[2]
        else:
            stats["empty"] += 1
        if old and old.get("note") and old.get("note") != new_note:
            _drop_note(out_dir, old["note"])
        src_state[f] = {"sig": sig, "note": new_note}
        if i % 100 == 0:
            save_state(state_path, state)
            if not quiet:
                print(f"  {i}/{len(todo)} chats  ({time.time() - t0:.0f}s)", flush=True)


def _summary_line(files, stats, out_dir, t0):
    notes = [n for n in os.listdir(out_dir) if n.endswith(".md")]
    low = os.path.join(out_dir, LOW_DIR)
    n_low = len([n for n in os.listdir(low) if n.endswith(".md")]) if os.path.isdir(low) else 0
    return (f"codex chats: {len(files)} sessions, {stats['converted']} converted, {stats['written']} notes written, "
            f"{stats['empty']} empty, {stats['removed']} removed, {stats['errors']} errors, "
            f"{stats['redactions']} redactions; folder has {len(notes)} notes, {n_low} set aside in {LOW_DIR}/; "
            f"{time.time() - t0:.0f}s")


def _todo_and_gone(files, src_state, redo_all):
    """The chats to convert (with their signature) and the state keys whose source vanished."""
    todo = [(f, signature(f)) for f in files
            if redo_all or not src_state.get(f) or src_state[f].get("sig") != signature(f)]
    return todo, [k for k in src_state if k not in set(files)]


def _say_dry_run(files, todo, gone, src_state):
    for k in gone:
        print(f"would delete note for vanished source {k}: {src_state[k].get('note')}")
    for f, _ in todo:
        print(f"would convert {f}")
    print(f"dry run: {len(todo)} to convert, {len(gone)} to delete, {len(files) - len(todo)} unchanged")


def main(argv=None):
    args = _parse_args(argv)

    t0 = time.time()
    files = sorted(glob.glob(os.path.join(args.src, "**", "*.jsonl"), recursive=True))
    names = thread_names()

    if args.sample:
        return _write_sample(args.sample, files, names)

    out_dir = args.out
    if not args.dry_run:
        lock = lock_out_dir(out_dir)   # kept until main returns
        if lock is None:
            print("codex.py: another run is busy, skipping")
            return 0
    state_path = os.path.join(out_dir, STATE_NAME)
    state = load_sources(state_path)
    src_state = state["sources"]

    todo, gone = _todo_and_gone(files, src_state, args.all)
    stats = {"converted": 0, "written": 0, "empty": 0, "removed": 0, "redactions": 0, "errors": 0}

    if args.dry_run:
        _say_dry_run(files, todo, gone, src_state)
        return 0

    for k in gone:
        _drop_note(out_dir, src_state.pop(k).get("note"))
        stats["removed"] += 1

    _convert_todo(todo, src_state, names, out_dir, state_path, state, stats, args.quiet, t0)

    save_state(state_path, state)
    print(_summary_line(files, stats, out_dir, t0))
    return 1 if stats["errors"] and not stats["converted"] else 0


if __name__ == "__main__":
    sys.exit(main())
