"""brain private: tag or untag a memory note "this computer only" by hand (brief 20, <user>'s yes 2026-10-28).

  brain private <note> on|off [--json]   on: `local-only: true` (Haiku never gets the note); off: `local-only: false`
  brain private list [--json]            every local-only note: title, path, by whom, when

<note> is a path in the memory store (BRAIN_MEMORY_STORE, default ~/projects/shared, the same rule as
ask/memory.py), a unique part of a file name, or words that are all in one note's title. Several matches: they are
listed and nothing changes. Only notes in the `memory` collection (index/index.yml: not drafts/, README.md, CONTEXT.md)
can be tagged; anything else gets a plain refusal.

A tag records who and when: `local-only-by: owner|filter`, `local-only-at: <date>`. A hand choice (`owner`) is kept by
`brain drafts keep` (eval/memory_keep.py) even when the names filter is not sure. Only those three front matter lines
change; the rest of the file stays byte for byte. The old file is copied first to
~/.local/share/second-brain/backups/private-tag/ (BRAIN_BACKUP_DIR), the new one is written whole (no half-written
moment) and committed in the store when it is a git repo. Claude chats still read local-only notes (no hiding);
only the online backup writer is blocked (ask/ask.py local_only). Python standard library only.

  python3 -I ask/private_tag.py <note> on|off [--json] | list [--json]
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

sys.dont_write_bytecode = True

KEYS = ("local-only", "local-only-by", "local-only-at")
SKIP_DIRS = {".git", "drafts"}
SKIP_FILES = {"README.md", "CONTEXT.md"}
NOT_MEMORY = "only memory notes can be tagged (notes in the memory store %s, not drafts or its README/CONTEXT)"


class TagError(ValueError):
    """Plain words for <user>; nothing was changed. `matches` lists the notes when the name fit several."""
    def __init__(self, message, matches=()):
        super().__init__(message)
        self.matches = list(matches)


def store_path(store=None):
    return os.path.realpath(os.path.expanduser(store or os.environ.get("BRAIN_MEMORY_STORE") or "~/projects/shared"))


def backup_dir():
    return os.path.expanduser(os.environ.get("BRAIN_BACKUP_DIR") or "~/.local/share/second-brain/backups/private-tag")


def _shown(path):
    return path.replace(os.path.expanduser("~"), "~", 1)


# ---------- the notes ----------

def notes(store):
    """Every taggable note, as store-relative paths (sorted): *.md, not in drafts/ or .git/, not README/CONTEXT, not a
    symlink (it could point out of the store)."""
    out = []
    for top, dirs, files in os.walk(store):
        dirs[:] = sorted(d for d in dirs if not (top == store and d in SKIP_DIRS) and d != ".git")
        for f in files:
            if f.endswith(".md") and f not in SKIP_FILES and not os.path.islink(os.path.join(top, f)):
                out.append(os.path.relpath(os.path.join(top, f), store))
    return sorted(out)


def _read(path):
    with open(path, encoding="utf-8", newline="") as f:
        return f.read()


def _front_lines(text):
    """(lines, end) of the front matter: the file's lines (endings kept) and the index of the closing `---`, or None
    when the file has no front matter."""
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].rstrip("\r\n") != "---":
        return lines, None
    end = next((i for i in range(1, len(lines)) if lines[i].rstrip("\r\n").strip() == "---"), None)
    return lines, end


def front(text):
    """The front matter's top-level `key: value` pairs (quoted values decoded)."""
    lines, end = _front_lines(text)
    out = {}
    for line in lines[1:end] if end else []:
        if line[:1].isspace() or ":" not in line:
            continue
        key, _, value = line.partition(":")
        value = value.strip()
        if value.startswith('"'):
            try:
                value = json.loads(value)
            except ValueError:
                pass
        out.setdefault(key.strip(), value)
    return out


def title(text, rel):
    """The note's title: its first heading, else its summary line, else its file name."""
    lines, end = _front_lines(text)
    for line in lines[(end + 1) if end else 0:]:
        m = re.match(r"#+\s+(.+)", line.strip())
        if m:
            return m.group(1).strip()
    return front(text).get("summary") or os.path.splitext(os.path.basename(rel))[0]


def info(store, rel):
    """One note as <user> (and the Deck) sees it: title, path, local_only, by, at."""
    path = os.path.join(store, rel)
    text = _read(path)
    fm = front(text)
    on = str(fm.get("local-only")).lower() == "true"
    by = fm.get("local-only-by") or ("filter" if on else "")   # an old tag without `by` came from the names filter
    return {"title": title(text, rel), "rel": rel, "path": path, "local_only": on, "by": by,
            "at": fm.get("local-only-at") or ""}


# ---------- which note ----------

def find(note, store):
    """The store-relative path of the one note `note` names. TagError when it is not a memory note, names none, or
    names several (they are in .matches)."""
    all_notes = notes(store)
    raw = os.path.expanduser(note.strip())
    if not raw:
        raise TagError("say which note: brain private <note> on|off")
    if os.path.isabs(raw) or "/" in raw or os.path.exists(raw):
        for path in dict.fromkeys(os.path.realpath(p) for p in (raw, os.path.join(store, raw))):
            inside = os.path.commonpath([store, path]) == store
            if inside and os.path.relpath(path, store) in all_notes:
                return os.path.relpath(path, store)
        if any(os.path.exists(p) for p in (raw, os.path.join(store, raw))):
            raise TagError(NOT_MEMORY % _shown(store))
        raise TagError("no memory note at %s" % note)
    word = raw.lower()
    hits = [r for r in all_notes if word in os.path.basename(r).lower()]
    if not hits:
        words = re.findall(r"\w+", word)
        hits = [r for r in all_notes if words and all(w in title(_read(os.path.join(store, r)), r).lower() for w in words)]
    if len(hits) == 1:
        return hits[0]
    if not hits:
        raise TagError("no memory note matches %r (a path in the store, part of a file name, or title words)" % note)
    raise TagError("%d memory notes match %r; nothing was changed. Say which one:" % (len(hits), note), hits)


# ---------- the edit ----------

def retag(text, on, by, at):
    """The same text with only the three local-only lines set (others with these keys removed, so no two disagree).
    A note without front matter gets a block with just these lines on top."""
    values = {"local-only": "true" if on else "false", "local-only-by": by, "local-only-at": at}
    lines, end = _front_lines(text)
    if end is None:
        nl = "\r\n" if text.split("\n", 1)[0].endswith("\r") else "\n"
        return "---" + nl + "".join("%s: %s%s" % (k, values[k], nl) for k in KEYS) + "---" + nl + text
    nl = lines[0][3:]
    inner, done = [], set()
    for line in lines[1:end]:
        key = line.partition(":")[0].strip() if not line[:1].isspace() and ":" in line else None
        if key in values:
            if key not in done:
                ending = line[len(line.rstrip("\r\n")):] or nl
                inner.append("%s: %s%s" % (key, values[key], ending))
                done.add(key)
            continue
        inner.append(line)
    if inner and not inner[-1].endswith(("\n", "\r")):
        inner[-1] += nl
    inner += ["%s: %s%s" % (k, values[k], nl) for k in KEYS if k not in done]
    return lines[0] + "".join(inner) + "".join(lines[end:])


def _backup(store, rel, text):
    folder = backup_dir()
    os.makedirs(folder, mode=0o700, exist_ok=True)
    dest = os.path.join(folder, "%s-%s" % (time.strftime("%Y-%m-%d-%H%M%S"), rel.replace("/", "__")))
    n = 1
    while os.path.exists(dest):
        n += 1
        dest = os.path.join(folder, "%s-%d-%s" % (time.strftime("%Y-%m-%d-%H%M%S"), n, rel.replace("/", "__")))
    with open(dest, "w", encoding="utf-8", newline="") as f:
        f.write(text)
    return dest


def _write(path, text):
    """Write the whole file without a half-written moment; the old file's permissions are kept."""
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), prefix=".private-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
            f.write(text)
        shutil.copymode(path, tmp)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def _commit(store, rel, on):
    """Commit the one note in the store; None when done or the store is not a git repo, else plain words."""
    if not os.path.exists(os.path.join(store, ".git")):
        return None
    try:
        for args in (["add", "--", rel], ["commit", "-q", "-m", "private: %s %s (by hand)" % ("on" if on else "off", rel),
                                          "--", rel]):
            done = subprocess.run(["git", "-C", store, *args], capture_output=True, text=True, timeout=60)
            if done.returncode:
                return "saved, but not committed in the store: %s" % (done.stderr or done.stdout).strip()[:200]
    except (OSError, subprocess.SubprocessError) as why:
        return "saved, but not committed in the store (%s)" % type(why).__name__
    return None


def set_private(note, on, store=None, today=None):
    """Tag (`on`) or untag one memory note by hand. Returns its info plus changed, backup, commit_problem.
    Raises TagError (plain words) with nothing changed."""
    store = store_path(store)
    if not os.path.isdir(store):
        raise TagError("the memory store is not there (%s); nothing was changed" % _shown(store))
    rel = find(note, store)
    path = os.path.join(store, rel)
    old = _read(path)
    if _front_lines(old)[1] is None and old.startswith("---"):
        raise TagError("%s has front matter that never closes (no second ---); fix it by hand first" % rel)
    now = info(store, rel)
    if now["local_only"] == on and now["by"] == "owner":
        return dict(now, changed=False, backup=None, commit_problem=None)
    new = retag(old, on, "owner", today or time.strftime("%Y-%m-%d"))
    backup = _backup(store, rel, old)
    _write(path, new)
    return dict(info(store, rel), changed=True, backup=backup, commit_problem=_commit(store, rel, on))


def list_private(store=None):
    """Every local-only memory note's info, by path."""
    store = store_path(store)
    if not os.path.isdir(store):
        raise TagError("the memory store is not there (%s)" % _shown(store))
    out = []
    for rel in notes(store):
        try:
            n = info(store, rel)
        except (OSError, UnicodeDecodeError):
            continue
        if n["local_only"]:
            out.append(n)
    return out


# ---------- command line ----------

WHO = {"owner": "you, by hand", "filter": "the names filter (it was not sure)"}


def _public(n):
    return {k: (_shown(v) if k in ("path", "backup") and v else v) for k, v in n.items()}


def main(argv):
    argv = list(argv)
    as_json = "--json" in argv
    argv = [a for a in argv if a != "--json"]
    try:
        if argv == ["list"]:
            got = list_private()
            if as_json:
                print(json.dumps({"ok": True, "notes": [_public(n) for n in got]}, ensure_ascii=False))
                return 0
            if not got:
                print("No memory note is marked this-computer-only.")
            else:
                print("This-computer-only memory notes (%d). Haiku never gets these; Claude chats still read them." % len(got))
                for n in got:
                    print("- %s\n  %s\n  marked by %s%s" % (n["title"], _shown(n["path"]), WHO.get(n["by"], n["by"]),
                                                           ", on " + n["at"] if n["at"] else ""))
            return 0
        if len(argv) < 2 or argv[-1] not in ("on", "off"):
            raise TagError("say which note and on or off: brain private <note> on|off, or brain private list")
        on = argv[-1] == "on"
        got = set_private(" ".join(argv[:-1]), on)
    except TagError as why:
        if as_json:
            print(json.dumps({"ok": False, "error": str(why), "matches": why.matches}, ensure_ascii=False))
        else:
            print("brain private: %s" % why, file=sys.stderr)
            for m in why.matches:
                print("  " + m, file=sys.stderr)
        return 1
    except (OSError, UnicodeDecodeError) as why:
        msg = "could not change the note (%s); nothing was changed" % why
        print(json.dumps({"ok": False, "error": msg, "matches": []}) if as_json else "brain private: " + msg,
              file=sys.stdout if as_json else sys.stderr)
        return 1
    if as_json:
        print(json.dumps(dict(_public(got), ok=True), ensure_ascii=False))
        return 0
    if got["changed"]:
        state = ("marked this computer only: Haiku will never get it (Claude chats still read it)" if on
                 else "no longer this computer only: Haiku may get it again (after the names filter)")
    else:
        state = "already %s by your choice; nothing changed" % ("this computer only" if on else "not this computer only")
    print("%s\n  %s\n  %s." % (got["title"], _shown(got["path"]), state))
    if got["changed"]:
        print("  The old file is kept at %s." % _shown(got["backup"]))
    if got["commit_problem"]:
        print("  " + got["commit_problem"])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
