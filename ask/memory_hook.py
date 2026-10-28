"""The Claude start-of-session memory push: a UserPromptSubmit hook (agent memory job 5, 2026-10-28).

On the first prompt of a Claude session in one of <user>'s projects, it adds that project's notes from the agent memory
store (memory.find: pinned first, then the best match for the prompt, then the project's newest;
all-projects notes only when pinned or matched) to the session's context.
  - once per session: a marker file per session_id in ~/.local/state/second-brain/memory-hook/ (older than 3 days:
    pruned); later prompts get nothing;
  - the project: the git repo's name (a worktree counts as its main repo, via the git common dir; also
    ~/.agent-os/worktrees/<repo>/...), only if it is a folder in ~/projects/. Anything else: nothing;
  - a prompt with no meaning ("continue", "yes", "ok"): no task, so pinned + the project's newest. A prompt that names a brief
    ("Read /.../builder.md and do what it says") also searches with the start of that brief;
  - a hard budget of TOTAL_SECONDS: the search gets SEARCH_SECONDS (slower = find's pinned + newest fallback), and if
    the whole answer is not ready in time the hook says nothing;
  - output: one JSON object, additionalContext under one short header, at most 2,000 tokens (characters / 4);
  - switched off while ~/.local/state/second-brain/memory-hook.off exists;
  - empty store, no notes, store missing (the test machine), bad input, any error: exit 0 with no output. It never blocks.
A line per push goes to ~/.local/state/second-brain/memory-hook.jsonl (what was pushed, how long it took).
Python standard library only; nothing leaves this computer.

  echo '{"session_id": "...", "cwd": "...", "prompt": "..."}' | python3 -I ask/memory_hook.py
"""
import json
import os
import re
import subprocess
import sys
import threading
import time

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

BUDGET = 2000
TOTAL_SECONDS = float(os.environ.get("BRAIN_HOOK_SECONDS", "2.5"))          # the whole answer, or nothing
SEARCH_SECONDS = float(os.environ.get("BRAIN_HOOK_SEARCH_SECONDS", "1.5"))  # slower = pinned + newest
KEEP_DAYS = 3
FILLER = {"continue", "go", "on", "ahead", "yes", "y", "yep", "yeah", "ok", "okay", "k", "sure", "please", "pls",
          "thanks", "thank", "you", "ty", "do", "it", "that", "next", "proceed", "carry", "keep", "going", "fine",
          "good", "great", "done", "and", "no", "nope", "right", "again", "same", "resume", "the", "work", "start"}


def state_dir():
    return os.path.expanduser(os.environ.get("BRAIN_HOOK_STATE") or "~/.local/state/second-brain")


def projects_dir():
    return os.path.expanduser(os.environ.get("BRAIN_PROJECTS_DIR") or "~/projects")


def first_time(session_id):
    """True only the first time a session asks (an atomic marker file); old markers are pruned."""
    if not isinstance(session_id, str) or not re.fullmatch(r"[\w-]{1,128}", session_id):
        return False
    marks = os.path.join(state_dir(), "memory-hook")
    os.makedirs(marks, exist_ok=True)
    prune(marks)
    try:
        os.close(os.open(os.path.join(marks, session_id), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600))
    except FileExistsError:
        return False
    return True


def prune(marks):
    old = time.time() - KEEP_DAYS * 86400
    for name in os.listdir(marks):
        try:
            if os.path.getmtime(os.path.join(marks, name)) < old:
                os.remove(os.path.join(marks, name))
        except OSError:
            pass


def git_repo(cwd):
    """The repo's own name for a folder inside it (a worktree gives its main repo), else None."""
    try:
        out = subprocess.run(["git", "-C", cwd, "rev-parse", "--path-format=absolute", "--git-common-dir"],
                             capture_output=True, text=True, timeout=1, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError):
        return None
    common = out.stdout.strip().rstrip("/")
    if out.returncode or not common:
        return None
    return os.path.basename(os.path.dirname(common)) if os.path.basename(common) == ".git" else None


def project(cwd):
    """The project name for a folder: git first, then the agent worktree path. Only folders in Projects/ count."""
    if not isinstance(cwd, str) or not os.path.isabs(cwd) or not os.path.isdir(cwd):
        return None
    names = [git_repo(cwd)]
    m = re.match(re.escape(os.path.expanduser("~/.agent-os/worktrees")) + r"/([^/]+)/", cwd.rstrip("/") + "/")
    names.append(m.group(1) if m else None)
    for name in names:
        if name and not name.startswith(".") and name in os.listdir(projects_dir()):
            return name
    return None


def task_of(prompt):
    """The prompt as a search task, or None when it has no meaning to match ("continue", "yes", "ok")."""
    words = re.findall(r"[a-z0-9']+", (prompt or "").lower())
    if not words or sum(len(w) for w in words) < 4 or all(w.strip("'") in FILLER for w in words):
        return None
    return " ".join(prompt.split())[:1000]


def with_brief(task, cwd):
    """A "Read <brief>.md and do what it says" prompt (nodeterm and agent windows) matches on the brief's own words:
    the start of the first .md file it names, paths left out, is added to the task."""
    m = re.search(r"(?:^|\s)([~/.\w-][^\s'\"`]*\.md)\b", task or "")
    if not m:
        return task
    path = os.path.join(cwd, os.path.expanduser(m.group(1)))
    if not os.path.isfile(path):   # a FIFO or device could block the read
        return task
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            text = f.read(4000)
    except OSError:
        return task
    words = [w for w in text.split() if "/" not in w and not re.fullmatch(r"[#*>|`-]+", w)]
    return " ".join([task] + words)[:1000]


def header(repo, count):
    return (f"Agent memory for {repo}: {count} note{'' if count == 1 else 's'} from <user>'s memory store (rules and "
            f"lessons; pinned first, then the best match for this first prompt), pushed once per session by the "
            f"memory hook. Each line is a stored summary; the path holds the full note. More: the `memory` tool "
            f"(brain MCP) or `brain memory {repo} \"task\"`.\n\n")


def push(repo, task):
    """The hook's JSON for one project and task, or None (no notes, store missing)."""
    import memory
    memory.SEARCH_SECONDS = SEARCH_SECONDS
    room = BUDGET - memory.tokens(header(repo, 999))
    out = memory.find(repo, task, budget=room)
    if not out["notes"]:
        return None
    text = header(repo, len(out["notes"])) + out["text"]
    used = memory.tokens(text)
    return {"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": text},
            "systemMessage": f"Memory: {len(out['notes'])} notes pushed ({used} tokens) for {repo}.",
            "_log": {"repo": repo, "task": (task or "")[:200], "notes": len(out["notes"]), "left_out": out["left_out"],
                     "tokens": used, "fallback": out["fallback"]}}


def in_time(fn, seconds):
    """fn()'s answer if it is ready within `seconds`, else None (the worker thread is left behind, not waited for)."""
    box = []

    def work():
        try:
            box.append(fn())
        except Exception:  # noqa: BLE001  no push, and no traceback in the session
            pass
    worker = threading.Thread(target=work, daemon=True)
    worker.start()
    worker.join(max(0.0, seconds))
    return box[0] if box else None


def log(session_id, entry, started):
    entry = dict(entry, when=time.strftime("%Y-%m-%dT%H:%M:%S"), session=session_id,
                 seconds=round(time.monotonic() - started, 3))
    try:
        with open(os.path.join(state_dir(), "memory-hook.jsonl"), "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except OSError:
        pass


def run(stdin_text, started):
    """The hook's stdout text ("" = say nothing)."""
    event = json.loads(stdin_text)
    if not isinstance(event, dict) or os.path.exists(os.path.join(state_dir(), "memory-hook.off")):
        return ""
    repo = project(event.get("cwd"))
    if not repo or not first_time(event.get("session_id")):
        return ""
    task = task_of(event.get("prompt") if isinstance(event.get("prompt"), str) else "")
    # The brief is read inside the budget too: a slow disk or mount must not hold the session.
    out = in_time(lambda: push(repo, with_brief(task, event["cwd"])), TOTAL_SECONDS - (time.monotonic() - started))
    if not out:
        return ""
    log(event["session_id"], out.pop("_log"), started)
    return json.dumps(out)


def main():
    started = time.monotonic()
    try:
        text = run(sys.stdin.read(1_000_000), started)
    except Exception:  # noqa: BLE001  the hook never fails a session: any trouble means no push
        text = ""
    if text:
        sys.stdout.write(text + "\n")
        sys.stdout.flush()
    os._exit(0)   # don't wait for a search thread that missed the budget


if __name__ == "__main__":
    main()
