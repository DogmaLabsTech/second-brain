"""keep for memory drafts (agent memory job 1, <user>'s yes 2026-10-27): a draft rule or lesson moves into the store
(~/projects/shared, its own private git, no remote) and is committed there.

  brain drafts keep <draft> --to <where> [--files a,b] [--pin] [--summary "line"]

  <draft>   a file name in the store's drafts/ folder, or a path to a file
  <where>   a folder, or a file, inside the store; project and kind come from it:
              projects/<repo>/rules | lessons [/<name>.md]     project = <repo>
              all-projects/rules | lessons [/<name>.md]        project = all-projects

It fills the front matter (project, kind, date, summary, files, pinned; the format is in the store's README), makes a
one-line summary with the local model (Ollama on this computer, never an online one), shows it so <user> can change it
(on a terminal it asks; otherwise it prints it and the line can be edited in the file), and commits in the store.

Names: the private-list guard (deciders/private_guard.py) and then the names filter (decider/names.py, through
drafts.scrub) run before any model sees the text. The model gets the scrubbed text only. When the guard finds the list
empty, broken or unreadable (or cannot load), or the filter is missing or not sure, no model is called at all, the first
heading stands in for the summary, and the note gets `local-only: true` in its front matter, so nothing that reads the
store may send it to an online model. A summary never keeps a private name: it is stored scrubbed.

A missing store, a store that is not a git repo, a bad target or a name already taken stop `keep` with a plain message
and change nothing. The store path is a parameter (BRAIN_MEMORY_STORE, default ~/projects/shared) so tests use a
temp folder. Standard library only.
"""
import http.client
import json
import os
import re
import subprocess
import sys
import time
import urllib.request

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import drafts  # noqa: E402

KINDS = {"rules": "rule", "lessons": "lesson"}
SEGMENT = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")
LOCAL_HOSTS = ("127.0.0.1", "localhost", "::1")
MODEL_TEXT_MAX = 4000
SUMMARY_MAX = 160
SYSTEM = ("You write one short line (at most 20 words) that says what a note tells an engineer. "
          "Reply with that line only: no quotes, no heading, no extra words.")


class KeepError(ValueError):
    """`keep` cannot go on; the message is plain words for <user>. Nothing has been changed."""


def store_path(store=None):
    return os.path.expanduser(store or os.environ.get("BRAIN_MEMORY_STORE") or "~/projects/shared")


def _git(store, *args):
    try:
        done = subprocess.run(["git", "-C", store, *args], capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError) as why:
        raise KeepError("git could not run in the store: %s" % why) from None
    if done.returncode:
        raise KeepError("git %s failed in the store: %s" % (args[0], (done.stderr or done.stdout).strip()[:300]))
    return done.stdout


# ---------- where the note goes ----------

def parse_target(to):
    """(project, kind, folder parts, file name or None) from the path inside the store. Raises KeepError."""
    bad = KeepError("not a place in the store: %r. Use projects/<repo>/rules|lessons or all-projects/rules|lessons "
                    "(add /<name>.md to choose the file name)." % to)
    parts = [p for p in (to or "").replace("\\", "/").split("/") if p]
    if (to or "").startswith(("/", "~")) or not parts or any(p in (".", "..") for p in parts):
        raise bad
    if parts[0] == "projects" and len(parts) in (3, 4):
        project, rest = parts[1], parts[2:]
        folder = ["projects", project]
    elif parts[0] == "all-projects" and len(parts) in (2, 3):
        project, rest = "all-projects", parts[1:]
        folder = ["all-projects"]
    else:
        raise bad
    if not SEGMENT.fullmatch(project) or rest[0] not in KINDS:
        raise bad
    name = rest[1] if len(rest) == 2 else None
    if name is not None and not (name.endswith(".md") and SEGMENT.fullmatch(name)):
        raise bad
    return project, KINDS[rest[0]], folder + [rest[0]], name


def _find_draft(draft, store):
    for path in (os.path.join(store, "drafts", draft), os.path.expanduser(draft)):
        if os.path.isfile(path):
            return os.path.abspath(path)
    raise KeepError("no draft called %s (looked in the store's drafts/ folder and at that path)" % draft)


def _inside(root, path):
    root, real = os.path.realpath(root), os.path.realpath(path)
    return os.path.commonpath([root, real]) == root and real != root


# ---------- the draft's text ----------

def split_draft(text):
    """(files, pinned or None, body): the old front matter's `files` and `pinned` if it had any, and the text after it."""
    m = re.match(r"---\n(.*?)\n---\n", text, re.S)
    if not m:
        return [], None, text
    files, pinned, listing = [], None, False
    for line in m.group(1).splitlines():
        item = re.match(r"\s+-\s+(.+)", line)
        if listing and item:
            files.append(item.group(1).strip())
            continue
        listing = False
        key, _, value = line.partition(":")
        key, value = key.strip(), value.strip()
        if key == "files":
            listing = not value
            if value.startswith("[") and value.endswith("]"):
                files += [v.strip() for v in value[1:-1].split(",") if v.strip()]
        elif key == "pinned":
            pinned = value.lower() == "true"
    return files, pinned, text[m.end():]


def first_line(text):
    """The first real line of the note (a heading counts), for when no model made a summary."""
    for line in text.splitlines():
        line = re.sub(r"^[\s#>*\-]+", "", line).strip()
        if line:
            return _shorten(line)
    return ""


def _shorten(text, limit=SUMMARY_MAX):
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0].rstrip(",;:") + "…"


def _oneline(text):
    return _shorten(re.sub(r"\s+", " ", text or "").strip().strip("\"'`"))


def _yaml(text):
    """A summary as one YAML value: plain when it is safe, in double quotes when not."""
    if re.search(r"(^[\s\-?:,\[\]{}#&*!|>'\"%@`])|(: )|( #)|(\s$)", text) or not text:
        return json.dumps(text, ensure_ascii=False)
    return text


def front_matter(project, kind, date, summary, files, pinned, local_only):
    out = ["---", "project: " + project, "kind: " + kind, "date: " + date, "summary: " + _yaml(summary)]
    out += ["files:"] + ["  - " + f for f in files] if files else ["files: []"]
    out.append("pinned: " + ("true" if pinned else "false"))
    if local_only:
        out.append("local-only: true")
    return "\n".join(out) + "\n---\n"


# ---------- the local model ----------

def _open(req, timeout):
    """Open the request straight, whatever proxy settings the environment has (the text must not go to a proxy)."""
    return urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req, timeout=timeout)


def local_summary(text):
    """One line about `text` from the model on this computer (Ollama). Raises OSError when it is not there, too slow, or
    when the model host is not this computer: nothing ever goes to an online model from here."""
    url = re.sub(r"^https?://", "", os.environ.get("OLLAMA_HOST_URL") or "127.0.0.1:11434").rstrip("/")
    m = re.fullmatch(r"(\[[^\]]+\]|[^:\[\]]+)(?::(\d+))?", url)
    if not m:
        raise OSError("the summary model address is not understood: %s" % url)
    host, port = m.group(1).strip("[]"), m.group(2) or "11434"
    if host not in LOCAL_HOSTS:
        raise OSError("the summary model must run on this computer, not at %s" % host)
    body = {"model": os.environ.get("BRAIN_LOCAL_MODEL") or "qwen2.5:3b", "stream": False, "keep_alive": "5m",
            "options": {"num_ctx": 4096, "temperature": 0.1, "num_predict": 60},
            "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": text[:MODEL_TEXT_MAX]}]}
    req = urllib.request.Request("http://%s:%s/api/chat" % ("[::1]" if ":" in host else host, port),
                                 json.dumps(body).encode(), {"Content-Type": "application/json"})
    try:
        with _open(req, 60) as resp:
            answer = (json.loads(resp.read()).get("message") or {}).get("content") or ""
    except (ValueError, AttributeError, http.client.HTTPException) as why:
        raise OSError("the summary model gave no usable answer: %s" % why) from None
    line = next((l for l in str(answer).splitlines() if l.strip()), "")
    line = _oneline(line)
    if not line:
        raise OSError("the summary model gave an empty answer")
    return line


# ---------- the private names list ----------

def _guard_module():
    deciders = os.path.join(os.path.dirname(HERE), "deciders")
    if deciders not in sys.path:
        sys.path.append(deciders)
    import private_guard   # the one guard of the private list (empty, broken or unreadable = nothing is sent)
    return private_guard


def guard_problem():
    """Plain words when the private names list is empty, broken or unreadable (deciders/private_guard.py), or when the
    guard itself cannot be used; None when the list is fine or not there. Never holds a name."""
    try:
        return _guard_module().problem(drafts._names().private_file())
    except Exception as why:  # noqa: BLE001 - no guard, no filter: treat as unsure
        return "The private names guard could not be used (%s). Nothing is sent to any model until it is fixed." \
            % type(why).__name__


# ---------- keep ----------

def _check_store(store):
    """The store folder as a path; KeepError (plain words) when it is missing or not a git repo."""
    shown = store.replace(os.path.expanduser("~"), "~")
    if not os.path.isdir(store):
        raise KeepError("the memory store is not there (%s). Nothing was kept. The store is made by agent memory job 1; "
                        "set BRAIN_MEMORY_STORE if it lives somewhere else." % shown)
    if not os.path.exists(os.path.join(store, ".git")):
        raise KeepError("the memory store (%s) is not a git repo, so keep cannot commit there. Nothing was kept." % shown)
    return store


def _plan(draft, to, store):
    """(project, kind, source draft, destination) for this keep. KeepError when the target or the name is not fine."""
    project, kind, folder, name = parse_target(to)
    src = _find_draft(draft, store)
    name = name or os.path.basename(src)
    if not (name.endswith(".md") and SEGMENT.fullmatch(name)):
        raise KeepError("the draft's file name (%s) must be a plain .md name; choose one with --to .../<name>.md" % name)
    dest = os.path.join(store, *folder, name)
    if not _inside(store, dest):
        raise KeepError("not a place in the store: %r" % to)
    if os.path.lexists(dest):
        raise KeepError("%s is already in the store; keep it under another name or retire the old one first"
                        % os.path.relpath(dest, store))
    return project, kind, src, dest


def _summary_and_filter(body, summary, confirm, summarize):
    """(summary line, who made it, local_only, guard words). The guard and the names filter run first; unsure (or no
    filter) means no model sees anything and the note is local-only. The line is shown to `confirm` for <user>'s edit."""
    guard = guard_problem()   # a bad names list counts as unsure, whatever the filter says
    local_only, scrubbed = bool(guard), ""
    if not guard:
        try:
            scrubbed = drafts.scrub(body)
        except drafts.Unsure:
            local_only = True
    by = "given"
    if summary is None:
        by, line = "fallback", first_line(body)
        if not local_only:
            try:
                line, by = _oneline((summarize or local_summary)(scrubbed)), "model"
            except (OSError, ValueError, TimeoutError):
                pass   # no model on this computer: the first line stands in; <user> edits it
    else:
        line = _oneline(summary)
    if confirm:
        edited = _oneline(confirm(line) or line)
        if edited != line:
            line, by = edited, "edited"
    try:
        if guard:
            raise drafts.Unsure("guard")
        line = _oneline(drafts.scrub(line))   # what agents get word for word never holds a private name
    except drafts.Unsure:
        local_only = True
    return line, by, local_only, guard


def _write_and_commit(store, src, dest, original, text, message):
    """Write the note, remove the draft and commit both in the store; returns the short commit hash. On any failure the
    draft is put back and the new file removed."""
    rel = os.path.relpath(dest, store)
    src_in = _inside(store, src)
    src_rel = os.path.relpath(src, store) if src_in else None
    tracked = bool(src_in) and subprocess.run(["git", "-C", store, "ls-files", "--error-unmatch", "--", src_rel],
                                              capture_output=True, timeout=60).returncode == 0
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    try:
        drafts._write(store, dest, text)
        os.unlink(src)
        paths = [rel] + ([src_rel] if tracked else [])
        _git(store, "add", "-A", "--", *paths)
        _git(store, "commit", "-q", "-m", message, "--", *paths)
        return _git(store, "rev-parse", "--short", "HEAD").strip()
    except BaseException:
        # Put everything back: the draft where it was, nothing new in the store.
        if not os.path.exists(src):
            _restore(src, original)
        if os.path.exists(dest):
            os.unlink(dest)
        try:
            subprocess.run(["git", "-C", store, "reset", "-q", "--", rel] + ([src_rel] if tracked else []),
                           capture_output=True, timeout=60)
        except subprocess.SubprocessError:
            pass  # the first failure is the one to report
        raise


def keep(draft, to, store=None, summary=None, files=None, pin=None, confirm=None, summarize=None, today=None):
    """Move one draft into the store and commit it. Returns {path, project, kind, summary, summary_by, local_only,
    guard, commit}. `summary` skips the model; `confirm(summary)` shows the line and returns the one to keep (or
    None/the same); `summarize(text)` is the model call (default: local_summary). Raises KeepError, with nothing changed."""
    store = _check_store(store_path(store))
    project, kind, src, dest = _plan(draft, to, store)
    with open(src, encoding="utf-8") as fh:
        original = fh.read()
    old_files, old_pin, body = split_draft(original)
    line, by, local_only, guard = _summary_and_filter(body, summary, confirm, summarize)
    text = front_matter(project, kind, today or time.strftime("%Y-%m-%d"), line,
                        list(files) if files is not None else old_files,
                        old_pin if pin is None else pin, local_only) + body.lstrip("\n")
    commit = _write_and_commit(store, src, dest, original, text,
                               "keep: %s/%s: %s\n\n%s" % (project, kind, os.path.basename(dest), line))
    return {"path": dest, "project": project, "kind": kind, "summary": line, "summary_by": by,
            "local_only": local_only, "guard": guard, "commit": commit}


def _restore(path, text):
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


# ---------- command line (called from drafts.main) ----------

def cli(argv, to):
    """`brain drafts keep <draft> --to <where> [--files a,b] [--pin] [--summary line]`; argv has --to already taken out."""
    argv = list(argv)
    files, summary = drafts._flag(argv, "--files"), drafts._flag(argv, "--summary")
    pin = None
    if "--pin" in argv:
        argv.remove("--pin")
        pin = True
    if len(argv) != 1:
        raise KeepError("say which draft: brain drafts keep <draft> --to projects/<repo>/lessons")
    confirm = _ask if sys.stdin.isatty() else None
    got = keep(argv[0], to, summary=summary, pin=pin, confirm=confirm,
               files=[f.strip() for f in files.split(",") if f.strip()] if files is not None else None)
    shown = got["path"].replace(os.path.expanduser("~"), "~", 1)
    print("kept in the store: %s (%s, %s), committed %s" % (shown, got["project"], got["kind"], got["commit"]))
    print("summary%s: %s" % ({"model": " (local model)", "given": "", "edited": " (your edit)",
                              "fallback": " (first line; no model made one)"}[got["summary_by"]], got["summary"]))
    if got["guard"]:
        print(got["guard"])
    if got["local_only"]:
        print("The names filter was not sure about this note, so no model saw it and it is marked local-only "
              "(local-only: true). Check the summary line.")
    print("To change the summary later, edit its line in the note and commit in the store.")
    return 0


def _ask(summary):
    print("summary: %s" % summary)
    try:
        return input("Enter keeps it; type a new line to change it: ").strip() or summary
    except EOFError:
        return summary
