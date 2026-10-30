"""media: the one store for every screenshot, video, GIF and other media an agent makes (2026-10-30).
  media add <file> --why "..." [--project P] [--name WORDS] [--source FILE ...] [--before ID] [--commit SHA] [--date D]
  media find "<words>" [-n N]      the items whose description matches (its path, then what it shows)
  media public <id> [--off]        mark an item public (<user> only; an agent is refused). `media public --list` shows them
  media show <id>                  the sidecar of one item
  media stray [folder ...] [--days N] [--path FILE] [--list] [--worktrees]
                                   media files lying in code folders: a count per project (--list: every file;
                                   --worktrees: also ~/.agent-os/worktrees). Exit 1 when there are some
The store is ~/Media/agents/<project>/<yyyy-mm-dd>-<what>.<ext> (MEDIA_STORE overrides; the folder is on the HDD).
Beside each file is a sidecar `<file>.md`: front matter (file, kind, project, date, commit, by, public, ...) and the why.
Private is the default: `public: false`. Only `media public` writes `public: true`, and the public-repo job takes only those.
Not in git; the brain index has a `media` collection over the sidecars (text only). Plain guide: README.md, "The media store"."""
import argparse
import datetime
import json
import os
import re
import shutil
import subprocess
import sys

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "ask"))

HOME = os.path.expanduser("~")
STORE = os.environ.get("MEDIA_STORE") or os.path.join(HOME, "Media", "agents")
EXTS = {"image": (".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".bmp"),
        "video": (".mp4", ".webm", ".mkv", ".mov", ".avi"),
        "audio": (".mp3", ".wav", ".ogg", ".flac", ".m4a")}
STRAY_EXTS = (".png", ".mp4", ".gif", ".webm")
SKIP_DIRS = {"node_modules", ".git", "dist", "build", ".next", "target", ".venv", "venv", "__pycache__", ".cache", "vendor"}
STRAY_ROOTS = ["~/projects", "~/agent-os"]   # plus ~/.agent-os/worktrees/<repo>/<worktree>
AGENT_PROGRAMS = ("claude", "codex", "gemini", "antigravity", "opencode", "grok", "copilot", "cursor", "crush", "pi")


class MediaError(Exception):
    pass


# ---------- sidecar ----------

def _val(v):
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, list):
        return json.dumps(v, ensure_ascii=False)
    s = str(v)
    return s if re.fullmatch(r"[\w./@+-][\w ./@+()-]*", s) and not s.endswith(" ") else json.dumps(s, ensure_ascii=False)


def write_sidecar(path, meta, body):
    lines = ["---"] + [f"{k}: {_val(v)}" for k, v in meta.items() if v not in (None, "", [])] + ["---", "", body.strip(), ""]
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        f.write("\n".join(lines))
    os.replace(tmp, path)


def read_sidecar(path):
    """(meta, body) of a sidecar; a broken or missing one gives ({}, "")."""
    try:
        with open(path, errors="replace") as f:
            text = f.read()
    except OSError:
        return {}, ""
    m = re.match(r"---\n(.*?)\n---\n(.*)", text, re.S)
    if not m:
        return {}, text
    meta = {}
    for line in m.group(1).splitlines():
        k, _, v = line.partition(": ")
        v = v.strip()
        if v[:1] in '"[':
            try:
                v = json.loads(v)
            except ValueError:
                pass
        meta[k.strip()] = v
    return meta, m.group(2).strip()


def is_public(meta):
    return meta.get("public") == "true"     # anything else, even a damaged line, is private


# ---------- helpers ----------

def kind_of(name):
    ext = os.path.splitext(name)[1].lower()
    return next((k for k, exts in EXTS.items() if ext in exts), "file")


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:60] or "media"


def project_of(cwd):
    """The repo name from a folder: projects/<repo>, ~/.agent-os/worktrees/<repo>/..., ~/agent-os; else ''."""
    cwd = os.path.realpath(cwd)
    for base in (os.path.join(HOME, "projects", "Projects"), os.path.join(HOME, ".agent-os", "worktrees")):
        if cwd.startswith(base + os.sep):
            return cwd[len(base) + 1:].split(os.sep)[0]
    if cwd == os.path.join(HOME, "agent-os") or cwd.startswith(os.path.join(HOME, "agent-os") + os.sep):
        return "agent-os"
    return ""


def git_commit(folder):
    try:
        out = subprocess.run(["git", "-C", folder, "rev-parse", "--short", "HEAD"], capture_output=True, text=True, timeout=5)
        return out.stdout.strip() if out.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def caller():
    """(program, title) of whoever runs this; ('', '') when unknown."""
    try:
        import searchlog
        c = searchlog.caller("media")
        return c.get("program") or "", c.get("title") or ""
    except Exception:  # noqa: BLE001  the sidecar is still written
        return "", ""


def items():
    """All sidecars in the store as (id, meta, body); the id is the media file's path inside the store."""
    out = []
    for root, dirs, files in os.walk(STORE):
        dirs[:] = sorted(d for d in dirs if not d.startswith("."))
        for f in sorted(files):
            if f.endswith(".md") and os.path.exists(os.path.join(root, f[:-3])):
                meta, body = read_sidecar(os.path.join(root, f))
                out.append((os.path.relpath(os.path.join(root, f[:-3]), STORE), meta, body))
    return out


def resolve(ident):
    """An id (path inside the store), a full path, or a unique file name / ending -> the id. Raises MediaError."""
    ident = os.path.expanduser(ident)
    if os.path.isabs(ident):
        ident = os.path.relpath(ident, STORE)
    ids = [i for i, _, _ in items()]
    if ident in ids:
        return ident
    hits = [i for i in ids if i.endswith("/" + ident) or i == ident]
    if len(hits) == 1:
        return hits[0]
    raise MediaError(f"no item '{ident}' in the store" if not hits else f"'{ident}' fits several items: " + ", ".join(hits))


# ---------- commands ----------

def add(file, why, project="", name="", sources=(), before="", commit=None, date=None, by="", move=True):
    """Put a file into the store with its sidecar; returns the new path. The why is required."""
    if not (why or "").strip():
        raise MediaError("say why: media add <file> --why \"what it shows and why it was taken\"")
    file = os.path.abspath(os.path.expanduser(file))
    if not os.path.isfile(file):
        raise MediaError(f"not a file: {file}")
    if os.path.realpath(file).startswith(os.path.realpath(STORE) + os.sep):
        raise MediaError("that file is already in the store")
    src = [os.path.abspath(os.path.expanduser(s)) for s in sources]
    for s in src:
        if not os.path.isfile(s):
            raise MediaError(f"source is not a file: {s}")
    if before:
        before = resolve(before)
    project = slug(project) if project else (project_of(os.getcwd()) or project_of(os.path.dirname(file)) or "general")
    date = date or datetime.date.today().isoformat()
    if not re.fullmatch(r"\d{4}-\d\d-\d\d", date):
        raise MediaError("the date is yyyy-mm-dd")
    stem, ext = os.path.splitext(os.path.basename(file))
    what = slug(name or stem)
    what = re.sub(r"^\d{4}-\d\d-\d\d-", "", what) if re.match(r"^\d{4}-\d\d-\d\d-", what) else what
    folder = os.path.join(STORE, project)
    os.makedirs(folder, exist_ok=True)
    n, base = 1, f"{date}-{what}"
    while os.path.exists(os.path.join(folder, base + ext.lower())):
        n += 1
        base = f"{date}-{what}-{n}"
    dest = os.path.join(folder, base + ext.lower())
    kept = []
    for i, s in enumerate(src, 1):
        sdest = os.path.join(folder, f"{base}-source{i if len(src) > 1 else ''}{os.path.splitext(s)[1].lower()}")
        (shutil.move if move else shutil.copy2)(s, sdest)
        kept.append(os.path.relpath(sdest, STORE))
    (shutil.move if move else shutil.copy2)(file, dest)
    program, title = caller()
    by = by or " ".join(x for x in (program, f"({title})" if title else "") if x) or "unknown"
    commit = git_commit(os.getcwd()) if commit is None else commit
    meta = {"file": os.path.basename(dest), "kind": kind_of(dest), "project": project, "date": date, "commit": commit,
            "by": by, "public": False, "size": os.path.getsize(dest), "was": os.path.basename(file),
            "sources": kept, "before": before}
    write_sidecar(dest + ".md", meta, f"# {what.replace('-', ' ')}\n\n{why.strip()}")
    return dest


def words_match(text, query):
    low = text.lower()
    ws = [w for w in re.findall(r"\w+", query.lower()) if len(w) > 1]
    return bool(ws) and all(w in low for w in ws)


def find(query, limit=10):
    """Items whose id or sidecar holds every word of the query (newest first), then the brain index's other hits.
    Returns [(id, line)]. The first part reads the sidecars directly, so a new item is found before the hourly reindex."""
    out, seen = [], set()
    rows = sorted(items(), key=lambda r: (r[1].get("date", ""), r[0]), reverse=True)
    for ident, meta, body in rows:
        if words_match(ident + " " + body + " " + meta.get("by", "") + " " + meta.get("project", ""), query):
            out.append((ident, _line(meta, body)))
            seen.add(ident)
    if len(out) < limit:
        try:
            import ask
            for h in ask.search(query, limit=limit * 3):
                p = h["path"]
                if p.startswith(os.path.realpath(STORE) + os.sep) or p.startswith(STORE + os.sep):
                    ident = os.path.relpath(p, STORE)[:-3] if p.endswith(".md") else os.path.relpath(p, STORE)
                    if ident not in seen and os.path.exists(os.path.join(STORE, ident)):
                        seen.add(ident)
                        meta, body = read_sidecar(os.path.join(STORE, ident + ".md"))
                        out.append((ident, _line(meta, body)))
        except Exception:  # noqa: BLE001  no search server: the direct hits are still good
            pass
    return out[:limit]


def _line(meta, body):
    text = re.sub(r"^#.*\n", "", body).strip().replace("\n", " ")
    return f"{meta.get('date', '')} {meta.get('kind', '')}{' PUBLIC' if is_public(meta) else ''} — {text[:160]}"


def set_public(ident, on=True):
    ident = resolve(ident)
    path = os.path.join(STORE, ident + ".md")
    meta, body = read_sidecar(path)
    if not meta:
        raise MediaError(f"{ident} has no readable sidecar")
    meta["public"] = on
    write_sidecar(path, meta, body)
    return ident


def public_items():
    """Absolute paths of the items marked public (the public-repo job takes these and no others)."""
    return [os.path.join(STORE, i) for i, m, _ in items() if is_public(m)]


def stray(roots=None, days=None, path=None, worktrees=False):
    """Media files lying in code folders: untracked or git-ignored png/mp4/gif/webm (tracked ones are the product's own
    images). `days`: only files changed in the last N days. `path`: check just that file.
    `worktrees`: also walk ~/.agent-os/worktrees (off by default). Returns a sorted list."""
    import time
    found = set()
    cutoff = time.time() - days * 86400 if days else 0

    def fresh(p):
        try:
            return os.path.getmtime(p) >= cutoff
        except OSError:
            return False

    if path:
        p = os.path.abspath(path)
        if p.lower().endswith(STRAY_EXTS) and not p.startswith(os.path.realpath(STORE) + os.sep) and _untracked(p):
            found.add(p)
        return sorted(found)
    for root in roots or _stray_roots(worktrees):
        for cur, dirs, files in os.walk(root):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
            for f in files:
                p = os.path.join(cur, f)
                if f.lower().endswith(STRAY_EXTS) and fresh(p) and _untracked(p):
                    found.add(p)
    return sorted(found)


def _stray_roots(worktrees=False):
    roots = [os.path.expanduser(r) for r in STRAY_ROOTS]
    wt = os.path.join(HOME, ".agent-os", "worktrees")
    if worktrees and os.path.isdir(wt):
        for repo in sorted(os.listdir(wt)):
            roots.append(os.path.join(wt, repo))
    return [r for r in roots if os.path.isdir(r)]


def _untracked(p):
    """True unless git tracks the file. A file outside any git repo counts as stray too."""
    folder = os.path.dirname(p)
    try:
        r = subprocess.run(["git", "-C", folder, "ls-files", "--error-unmatch", "--", p], capture_output=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return True
    return r.returncode != 0


# ---------- command line ----------

def main(argv=None):
    ap = argparse.ArgumentParser(prog="media", description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd")
    a = sub.add_parser("add")
    a.add_argument("file")
    a.add_argument("--why", default="")
    a.add_argument("--project", default="")
    a.add_argument("--name", default="")
    a.add_argument("--source", action="append", default=[])
    a.add_argument("--before", default="")
    a.add_argument("--commit", default=None)
    a.add_argument("--date", default=None)
    a.add_argument("--by", default="")
    a.add_argument("--copy", action="store_true", help="keep the original too")
    f = sub.add_parser("find")
    f.add_argument("words", nargs="+")
    f.add_argument("-n", type=int, default=10)
    p = sub.add_parser("public")
    p.add_argument("id", nargs="?")
    p.add_argument("--off", action="store_true")
    p.add_argument("--list", action="store_true")
    s = sub.add_parser("show")
    s.add_argument("id")
    t = sub.add_parser("stray")
    t.add_argument("folders", nargs="*")
    t.add_argument("--days", type=int, default=None)
    t.add_argument("--path", default=None)
    t.add_argument("--list", action="store_true", help="print every file, not a count per project")
    t.add_argument("--worktrees", action="store_true", help="also look in ~/.agent-os/worktrees")
    args = ap.parse_args(argv)
    try:
        if args.cmd == "add":
            dest = add(args.file, args.why, args.project, args.name, args.source, args.before, args.commit, args.date, args.by,
                       move=not args.copy)
            print(dest)
        elif args.cmd == "find":
            rows = find(" ".join(args.words), args.n)
            for ident, line in rows:
                print(f"{os.path.join(STORE, ident)} — {line}")
            return 0 if rows else 1
        elif args.cmd == "public":
            if args.list:
                print("\n".join(public_items()))
                return 0
            if not args.id:
                raise MediaError("which item? media public <id> (or --list)")
            program, _ = caller()
            if program in AGENT_PROGRAMS and not args.off:
                raise MediaError("only <user> marks an item public: ask him to run `media public " + args.id + "`")
            print(("private: " if args.off else "public: ") + os.path.join(STORE, set_public(args.id, not args.off)))
        elif args.cmd == "show":
            with open(os.path.join(STORE, resolve(args.id) + ".md")) as f:
                print(f.read())
        elif args.cmd == "stray":
            found = stray([os.path.expanduser(x) for x in args.folders] or None, args.days, args.path, args.worktrees)
            if args.list:
                for p_ in found:
                    print(f"stray {p_}")
            else:
                counts = {}
                for p_ in found:
                    name = project_of(os.path.dirname(p_)) or "(other)"
                    counts[name] = counts.get(name, 0) + 1
                for name in sorted(counts):
                    print(f"{counts[name]:>5}  {name}")
                if found:
                    print(f"{len(found):>5}  total")
            if found:
                print(f"{len(found)} media file(s) in code folders: put each in the store with "
                      "`media add <file> --why \"...\"` (`media stray --list` shows the files)", file=sys.stderr)
            return 1 if found else 0
        else:
            ap.print_help()
            return 2
    except MediaError as e:
        print(f"media: {e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
