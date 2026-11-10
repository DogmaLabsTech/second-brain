"""Is the second brain's index keeping up with the notes? Read-only: it looks at the qmd index file, the qmd
config and the note folders, and never re-indexes, embeds or changes anything.

Used by `brain status` (bin/brain) and `brain checkup` (eval/checkup.py). Run on its own:
    python3 -I index/freshness.py [--json]

What it checks, per collection:
  - behind:   the newest note on disk is more than 24 h newer than the newest note the index has seen
  - no vectors: notes older than 24 h that still have no meaning-search vectors
and for the Codex notes, whether the test machine embed (index/codex-testbox.sh, called by index/reindex.sh) worked: that
script leaves one line in ~/.local/share/second-brain/codex-testbox.status after each run.
Collections in RETIRE are only named in the report; nothing is deleted.
"""
import datetime
import fnmatch
import json
import os
import re
import sqlite3
import sys

sys.dont_write_bytecode = True
HOME = os.path.expanduser("~")
LATE_HOURS = 24
# qmd always skips these on its own (index/index.yml header); so does the walk here.
ALWAYS_SKIP = {"node_modules", ".git", ".cache", "vendor", "dist", "build"}
# Collections to retire. Named in the report only; removing one is <user>'s call (qmd collection remove <name>,
# then the block in index/index.yml).
RETIRE = {
    "hermes": "Hermes, the AI agent, stopped in September 2026 and its 3 notes never change. "
              "To retire: qmd collection remove hermes, then delete its block in index/index.yml.",
}


def paths():
    """Where things live. Each can be moved by an environment variable (the tests do)."""
    state = os.environ.get("BRAIN_STATE_DIR") or os.path.join(HOME, ".local", "share", "second-brain")
    return {
        "index": os.environ.get("BRAIN_LIVE_INDEX") or os.path.join(HOME, ".cache", "qmd", "index.sqlite"),
        "config": os.environ.get("BRAIN_QMD_CONFIG") or os.path.join(HOME, ".config", "qmd", "index.yml"),
        "testbox": os.path.join(state, "codex-testbox.status"),
    }


def now_utc():
    return datetime.datetime.now(datetime.timezone.utc)


def parse_time(text):
    """'2026-10-22T09:13:38.495Z' (or with an offset) -> aware datetime; None when it can't be read."""
    try:
        t = datetime.datetime.fromisoformat(str(text).replace("Z", "+00:00"))
    except ValueError:
        return None
    return t if t.tzinfo else t.replace(tzinfo=datetime.timezone.utc)


def ago(then, now):
    """'49m', '4h', '3d' (rounded down) for plain words."""
    if then is None:
        return "never"
    s = max(0, int((now - then).total_seconds()))
    return f"{s // 86400}d" if s >= 2 * 86400 else f"{s // 3600}h" if s >= 3600 else f"{s // 60}m"


# --- which files a collection's pattern covers --------------------------------------------------------------------

def _glob_regex(pattern):
    """qmd-style glob -> regex: ** crosses folders (and may match none), * and ? stay inside one name."""
    out, i = "", 0
    while i < len(pattern):
        if pattern.startswith("**/", i):
            out += "(?:.*/)?"
            i += 3
        elif pattern.startswith("**", i):
            out += ".*"
            i += 2
        elif pattern[i] == "*":
            out += "[^/]*"
            i += 1
        elif pattern[i] == "?":
            out += "[^/]"
            i += 1
        else:
            out += re.escape(pattern[i])
            i += 1
    return re.compile(out + r"\Z")


def _could_match_below(dir_parts, pattern):
    """Can any file under this folder match the pattern? Lets the walk skip folders (node_modules-sized trees)."""
    segs = pattern.split("/")
    for i, d in enumerate(dir_parts):
        if i >= len(segs) - 1:
            return False  # the pattern's last part is a file name: no deeper folders
        if segs[i] == "**":
            return True
        if not fnmatch.fnmatchcase(d, segs[i]):
            return False
    return True


def source_files(conf):
    """Yield (relative path, mtime as UTC datetime) for each note the collection's pattern and ignore list cover."""
    root = os.path.expanduser(conf.get("path", ""))
    if not os.path.isdir(root):
        return
    pats = [p.strip() for p in str(conf.get("pattern", "**/*.md")).split(",") if p.strip()]
    take = [_glob_regex(p) for p in pats]
    skip = [_glob_regex(p) for p in conf.get("ignore") or []]
    for here, dirs, files in os.walk(root):
        rel_dir = os.path.relpath(here, root)
        parts = [] if rel_dir == "." else rel_dir.split(os.sep)
        dirs[:] = [d for d in dirs if d not in ALWAYS_SKIP and not d.startswith(".")
                   and any(_could_match_below(parts + [d], p) for p in pats)]
        for name in files:
            if name.startswith("."):
                continue
            rel = "/".join(parts + [name])
            if not any(r.match(rel) for r in take) or any(r.match(rel) for r in skip):
                continue
            try:
                mtime = os.stat(os.path.join(here, name)).st_mtime
            except OSError:
                continue
            yield rel, datetime.datetime.fromtimestamp(mtime, datetime.timezone.utc)


# --- what the index has seen ---------------------------------------------------------------------------------------

def index_state(db_path):
    """Per collection: notes, newest note the index has seen (qmd keeps the file's own modified time), and notes
    with no vectors (their modified times). None when the index file is missing."""
    if not os.path.exists(db_path):
        return None
    db = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        out = {}
        for name, n, newest in db.execute(
                "SELECT collection, COUNT(*), MAX(modified_at) FROM documents WHERE active = 1 GROUP BY collection"):
            out[name] = {"notes": n, "newest": parse_time(newest), "no_vector": []}
        for name, mod in db.execute(
                "SELECT d.collection, d.modified_at FROM documents d WHERE d.active = 1 "
                "AND NOT EXISTS (SELECT 1 FROM content_vectors v WHERE v.hash = d.hash)"):
            out.setdefault(name, {"notes": 0, "newest": None, "no_vector": []})["no_vector"].append(parse_time(mod))
        stat = {"size_mb": os.path.getsize(db_path) / 1e6,
                "embedded": db.execute("SELECT COUNT(*) FROM content_vectors").fetchone()[0],
                "last_embed": parse_time(db.execute("SELECT MAX(embedded_at) FROM content_vectors").fetchone()[0])}
        return {"collections": out, "index": stat}
    finally:
        db.close()


def rog_status(path):
    """The line index/codex-testbox.sh leaves after each run: {at, result: ok|unreachable|failed, detail, ok_at}.
    None when there is none yet."""
    try:
        with open(path) as f:
            data = json.loads(f.read())
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    return {"at": parse_time(data.get("at")), "result": str(data.get("result", "?")),
            "detail": str(data.get("detail", "")), "ok_at": parse_time(data.get("ok_at"))}


def load_config(path):
    try:
        import yaml
    except ImportError:
        raise RuntimeError("the Python package PyYAML is missing: run  pip install pyyaml  (see docs/getting-started.md)") from None
    try:
        with open(path) as f:
            return (yaml.safe_load(f) or {}).get("collections") or {}
    except OSError:
        return {}


# --- the verdict ---------------------------------------------------------------------------------------------------

def assess(collections, state, testbox, now=None, late_hours=LATE_HOURS):
    """collections: {name: {path, pattern, ignore}}; state: index_state(); testbox: rog_status() or None.
    Returns {"collections": [...], "testbox": {...}, "warnings": [plain sentences], "retire": [(name, why)]}."""
    now = now or now_utc()
    late = datetime.timedelta(hours=late_hours)
    warnings, rows = [], []
    seen = (state or {}).get("collections", {})
    for name, conf in collections.items():
        files = list(source_files(conf))
        newest_src = max((t for _, t in files), default=None)
        have = seen.get(name, {"notes": 0, "newest": None, "no_vector": []})
        lag = newest_src - have["newest"] if newest_src and have["newest"] else None
        is_behind = newest_src is not None and (have["newest"] is None or lag > late)
        old_no_vec = [t for t in have["no_vector"] if t is None or now - t > late]
        row = {"name": name, "path": conf.get("path", ""), "source_files": len(files), "notes": have["notes"],
               "newest_source": newest_src, "newest_indexed": have["newest"], "behind": is_behind,
               "behind_hours": round(lag.total_seconds() / 3600, 1) if is_behind and lag else None,
               "no_vector": len(have["no_vector"]), "no_vector_late": len(old_no_vec),
               "folder_missing": not os.path.isdir(os.path.expanduser(conf.get("path", ""))),
               "retire": RETIRE.get(name)}
        rows.append(row)
        if row["folder_missing"]:
            warnings.append(f"{name}: its folder {conf.get('path')} is not there, so the index can't follow it.")
        elif is_behind:
            when = f"{row['behind_hours']:.0f} h" if lag else "all of it"
            warnings.append(f"{name}: the index is behind by {when}: the newest note on disk "
                            f"({ago(newest_src, now)} ago) is newer than anything the index has "
                            f"({ago(have['newest'], now)} ago). Is the hourly reindex running?")
        if old_no_vec:
            warnings.append(f"{name}: {len(old_no_vec)} note(s) older than {late_hours} h still have no "
                            "meaning-search vectors (keyword search works; the next reindex should embed them).")
    codex = _rog_verdict(testbox, now, late, warnings)
    retire = [(r["name"], r["retire"]) for r in rows if r["retire"]]
    return {"collections": rows, "testbox": codex, "warnings": warnings, "retire": retire}


def _rog_verdict(testbox, now, late, warnings):
    if testbox is None:
        return {"state": "unknown", "line": "no record yet (the next reindex writes one)"}
    last_ok = testbox["ok_at"] or (testbox["at"] if testbox["result"] == "ok" else None)
    ok_ago = ago(last_ok, now) + " ago" if last_ok else "never"
    if testbox["result"] == "ok":
        return {"state": "ok", "line": f"worked {ago(testbox['at'], now)} ago"}
    if testbox["result"] == "failed":
        warnings.append(f"The Codex vectors made on the test machine failed ({testbox['detail'] or 'no reason recorded'}), "
                        f"{ago(testbox['at'], now)} ago; last good run {ok_ago}. The Codex notes keep keyword search "
                        "but get no new meaning-search until it works.")
        return {"state": "failed", "line": f"FAILED {ago(testbox['at'], now)} ago ({testbox['detail']}); last good {ok_ago}"}
    # unreachable: normal when the test machine is off for a while, a problem when it lasts
    if last_ok is None or now - last_ok > late:
        warnings.append(f"The test machine has not been reachable for the Codex vectors; last good run {ok_ago}.")
        return {"state": "unreachable", "line": f"test machine not reachable at the last run; last good {ok_ago}"}
    return {"state": "waiting", "line": f"test machine not reachable at the last run (it will try again); last good {ok_ago}"}


def check(now=None):
    """The real thing: read the live index, config and test machine status file."""
    p = paths()
    state = index_state(p["index"])
    report = assess(load_config(p["config"]), state, rog_status(p["testbox"]), now)
    report["index"] = (state or {}).get("index")
    report["index_missing"] = state is None
    if state is None:
        report["warnings"].insert(0, f"The search index file ({p['index']}) is not there.")
    return report


def _text(report, now):
    """Plain-words lines for `brain status`."""
    lines = []
    ix = report.get("index")
    if ix:
        lines.append(f"Index: {ix['size_mb']:.0f} MB, {ix['embedded']} pieces with vectors, last vectors made "
                     f"{ago(ix['last_embed'], now)} ago")
    lines.append("")
    w = max([len(r["name"]) for r in report["collections"]] or [4])
    for r in report["collections"]:
        flags = []
        if r["folder_missing"]:
            flags.append("FOLDER MISSING")
        if r["behind"]:
            flags.append("BEHIND" + (f" {r['behind_hours']:.0f}h" if r["behind_hours"] else ""))
        if r["no_vector"]:
            flags.append(f"{r['no_vector']} without vectors")
        if r["retire"]:
            flags.append("RETIRE")
        lines.append(f"  {r['name']:<{w}}  {r['notes']:>4} notes (folder has {r['source_files']}), newest on disk "
                     f"{ago(r['newest_source'], now)} ago, in index {ago(r['newest_indexed'], now)} ago"
                     + (f"  [{', '.join(flags)}]" if flags else "  [ok]"))
    lines += ["", "Codex vectors on the test machine: " + report["testbox"]["line"]]
    if report["retire"]:
        lines += ["", "To retire (not deleted):"] + [f"  {n}: {why}" for n, why in report["retire"]]
    lines += ["", "Warnings:" if report["warnings"] else "No warnings."]
    lines += [f"  ! {x}" for x in report["warnings"]]
    return lines


def main(argv):
    now = now_utc()
    try:
        report = check(now)
    except RuntimeError as e:
        print(f"brain status: {e}", file=sys.stderr)
        return 2
    if "--json" in argv:
        print(json.dumps(report, default=lambda o: o.isoformat() if hasattr(o, "isoformat") else str(o), indent=1))
    else:
        print("\n".join(_text(report, now)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
