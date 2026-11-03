#!/usr/bin/env python3
"""brain onboard: the first-run flow. It finds your notes and your AI chat histories, shows what it found, and puts
only what YOU choose into the brain. Nothing is read or written for a source you did not pick.

    brain onboard                          guided, one question per source (needs a terminal)
    brain onboard --plan [--json]          show what it found and what it would do; writes nothing
    brain onboard --yes --notes DIR ...    no questions: ingest exactly what the flags name
        --sessions claude,codex|none       which AI chat histories to turn into notes (default: none)
        --exclude-project GLOB             skip Claude project folders whose name matches (repeatable)
        --brain DIR                        where the brain lives (default: $BRAIN_HOME or ~/brain)
        --no-index                         do not touch the qmd search config or run the indexer
        --dry-run                          do everything except write

Exit codes: 0 done, 2 bad arguments, 3 needs a decision (no terminal and no --yes), 4 done with problems.
Chats are always redacted by the converters (keys, tokens, emails). The only way to skip redaction is to skip the source.
"""
import argparse
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import time

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OK, BAD_ARGS, UNDECIDED, PARTIAL = 0, 2, 3, 4
NOTE_CANDIDATES = ("~/notes", "~/Notes", "~/Documents", "~/Obsidian", "~/vaults", "~/Dropbox/Notes")
SKELETON = ("inbox", "chats", "days", "rules", "agents", "projects", "private")
NOT_SUPPORTED = ("Gemini chats", "ChatGPT exports", "Cursor chats")
MAX_COUNT = 50000


def _when(ts):
    return time.strftime("%Y-%m-%d", time.localtime(ts)) if ts else ""


# ---------------------------------------------------------------- discovery (read-only: names and dates, never contents)

def md_stats(path):
    """How many .md notes are under path, their total size and date range; flags file names that look like secrets."""
    count = size = 0
    first = last = None
    flags = set()
    for root, dirs, files in os.walk(path):
        dirs[:] = [d for d in dirs if not d.startswith(".") and d != "node_modules"]
        for name in files:
            low = name.lower()
            if low.startswith(".env") or "secret" in low:
                flags.add("has files named like secrets (never read)")
                continue
            if not low.endswith(".md"):
                continue
            try:
                st = os.stat(os.path.join(root, name))
            except OSError:
                continue
            count += 1
            size += st.st_size
            first = st.st_mtime if first is None else min(first, st.st_mtime)
            last = st.st_mtime if last is None else max(last, st.st_mtime)
            if count >= MAX_COUNT:
                flags.add("very large: counted up to %d" % MAX_COUNT)
                return dict(path=path, count=count, kb=size // 1024, first=_when(first), last=_when(last), flags=sorted(flags))
    return dict(path=path, count=count, kb=size // 1024, first=_when(first), last=_when(last), flags=sorted(flags))


def session_stats(source_id, files, projects=None):
    times = []
    for f in files:
        try:
            times.append(os.stat(f).st_mtime)
        except OSError:
            pass
    return dict(id=source_id, count=len(times), first=_when(min(times)) if times else "", last=_when(max(times)) if times else "",
                projects=projects or {}, default="skip")


def scan(home, brain):
    claude_files = [f for f in glob.glob(os.path.join(home, ".claude", "projects", "*", "*.jsonl"))
                    if not os.path.basename(f).startswith("agent-")]
    projects = {}
    for f in claude_files:
        name = os.path.basename(os.path.dirname(f))
        projects[name] = projects.get(name, 0) + 1
    codex_files = glob.glob(os.path.join(home, ".codex", "sessions", "**", "*.jsonl"), recursive=True)
    notes = []
    for cand in NOTE_CANDIDATES:
        p = os.path.join(home, cand[2:])
        if os.path.isdir(p) and os.path.abspath(p) != os.path.abspath(brain):
            st = md_stats(p)
            if st["count"]:
                st["default"] = "skip"
                notes.append(st)
    return dict(
        brain=dict(path=brain, exists=os.path.isdir(brain)),
        notes=notes,
        sessions=[s for s in (session_stats("claude", claude_files, projects), session_stats("codex", codex_files)) if s["count"]],
        unsupported=list(NOT_SUPPORTED),
        tools={t: bool(shutil.which(t)) for t in ("qmd", "ollama", "claude")},
    )


def show(found):
    out = ["Brain folder: %s (%s)" % (found["brain"]["path"], "exists" if found["brain"]["exists"] else "will be created")]
    out.append("Notes folders found:" if found["notes"] else "No notes folders found in the usual places (give one with --notes DIR).")
    for n in found["notes"]:
        out.append("  %-28s %5d notes  %s to %s%s" % (n["path"], n["count"], n["first"], n["last"], "  [%s]" % "; ".join(n["flags"]) if n["flags"] else ""))
    out.append("AI chat histories found:" if found["sessions"] else "No Claude Code or Codex chat histories found.")
    for s in found["sessions"]:
        out.append("  %-8s %5d chats  %s to %s" % (s["id"], s["count"], s["first"], s["last"]))
    out.append("Not supported yet: " + ", ".join(found["unsupported"]))
    out.append("Tools: " + ", ".join("%s %s" % (t, "found" if ok else "missing") for t, ok in found["tools"].items()))
    out.append("Nothing is ingested unless you choose it.")
    return "\n".join(out)


# ---------------------------------------------------------------- the choices

def ask_yes(question):
    try:
        return input("%s [y/N] " % question).strip().lower() in ("y", "yes")
    except EOFError:
        return False


def interactive(found):
    print(show(found))
    notes = [n["path"] for n in found["notes"] if ask_yes("Put the notes in %s into the brain?" % n["path"])]
    while True:
        try:
            extra = input("Another notes folder (blank to finish): ").strip()
        except EOFError:
            break
        if not extra:
            break
        extra = os.path.abspath(os.path.expanduser(extra))
        if os.path.isdir(extra):
            notes.append(extra)
        else:
            print("  not a folder, skipped")
    sessions = [s["id"] for s in found["sessions"] if ask_yes("Turn your %s chats (%d) into notes? Secrets are removed first." % (s["id"], s["count"]))]
    excludes = []
    if "claude" in sessions:
        print("Claude projects: " + ", ".join(sorted(found["sessions"][0]["projects"]))[:600])
        raw = input("Project name patterns to leave out, comma separated (blank for none): ").strip()
        excludes = [g.strip() for g in raw.split(",") if g.strip()]
    return notes, sessions, excludes


# ---------------------------------------------------------------- doing it

def slug(path, taken):
    base = "notes-" + (re.sub(r"[^a-z0-9]+", "-", os.path.basename(path.rstrip("/")).lower()).strip("-") or "folder")
    name, i = base, 2
    while name in taken:
        name, i = "%s-%d" % (base, i), i + 1
    return name


COLLECTION_HEAD = re.compile(r"^  ([A-Za-z0-9_-]+):\s*$")


def collection_blocks(text):
    """{name: text of its block} for the `collections:` part of a qmd config written in the plain two-space form."""
    blocks, name, lines = {}, None, []
    inside = False
    for line in text.splitlines(keepends=True):
        if re.match(r"^collections:\s*$", line):
            inside = True
        elif inside and re.match(r"^\S", line) and not line.startswith("#"):
            inside = False
        elif inside:
            m = COLLECTION_HEAD.match(line)
            if m:
                if name:
                    blocks[name] = "".join(lines)
                name, lines = m.group(1), [line]
            elif name:
                lines.append(line)
    if name:
        blocks[name] = "".join(lines)
    return blocks


def merge_collections(current, template):
    """Your qmd config plus the collections in the template that it lacks. Nothing you have is changed or removed.
    None when the file is in a form that cannot be extended safely (collections is not the last key)."""
    mine, wanted = collection_blocks(current), collection_blocks(template)
    if not re.search(r"^collections:\s*$", current, re.M):
        return template if re.match(r"^\s*(global_context:.*\n)?\s*collections:\s*\{\}\s*$", current.strip() + "\n") or not mine else None
    after = current[re.search(r"^collections:\s*$", current, re.M).end():]
    if any(re.match(r"^[A-Za-z_]", l) for l in after.splitlines()):
        return None
    extra = "".join(b for n, b in wanted.items() if n not in mine)
    if not extra:
        return current
    return current + ("" if current.endswith("\n") else "\n") + extra


def write_qmd_config(notes, brain, home, dry):
    """~/.config/qmd/index.yml = the shipped sections + one collection for every notes folder chosen (qmd does not follow links)."""
    template = open(os.path.join(HERE, "index.yml"), encoding="utf-8").read()
    if brain != os.path.join(home, "brain"):
        template = template.replace("~/brain", brain)
    taken, added = set(), []
    for n in notes:
        name = slug(n, taken)
        taken.add(name)
        added.append(name)
        template += '  %s:\n    includeByDefault: false\n    path: "%s"\n    pattern: "**/*.md"\n    context:\n      "/": "Your notes from %s."\n' % (name, n, os.path.basename(n.rstrip("/")))
    conf = os.path.join(os.environ.get("XDG_CONFIG_HOME") or os.path.join(home, ".config"), "qmd", "index.yml")
    if not dry:
        os.makedirs(os.path.dirname(conf), exist_ok=True)
        if os.path.isfile(conf):
            current = open(conf, encoding="utf-8").read()
            merged = merge_collections(current, template)
            if merged is None:      # a config we cannot extend safely: leave it alone and say so
                added = []
            elif merged != current:
                shutil.copy2(conf, conf + ".bak-" + time.strftime("%Y%m%d-%H%M%S"))
                open(conf, "w", encoding="utf-8").write(merged)
        else:
            open(conf, "w", encoding="utf-8").write(template)
    return conf, added


def run_converter(script, out, excludes, dry):
    cmd = [sys.executable, "-I", os.path.join(ROOT, "chats", script), "--out", out, "--quiet"] + (["--dry-run"] if dry else [])
    env = dict(os.environ, BRAIN_EXCLUDE_PROJECTS=",".join(excludes))
    p = subprocess.run(cmd, capture_output=True, text=True, env=env)
    return p.returncode, (p.stdout.strip().splitlines() or [""])[-1]


def execute(brain, home, notes, sessions, excludes, index, dry):
    done, errors = [], []
    if not dry:
        fresh = not os.path.isdir(brain)
        os.makedirs(brain, exist_ok=True)
        if fresh:
            os.chmod(brain, 0o700)   # a brain made by this flow is private to you
        for sub in SKELETON:
            os.makedirs(os.path.join(brain, sub), mode=0o700, exist_ok=True)
        readme = os.path.join(brain, "README.md")
        if not os.path.exists(readme):
            open(readme, "w", encoding="utf-8").write("# Your brain\n\nOne folder for everything the agents should know.\n\n"
                                                      "- rules: how you want work done\n- agents: lessons agents learned\n- projects: notes per project\n"
                                                      "- private: notes that never leave this computer\n- chats: your AI chats as notes (secrets removed)\n"
                                                      "- days: day pages\n- inbox: things to sort\n")
    done.append("brain folder %s%s" % (brain, " (dry run)" if dry else ""))
    if "claude" in sessions:
        rc, last = run_converter("convert.py", os.path.join(brain, "chats"), excludes, dry)
        (done if rc == 0 else errors).append("claude chats: " + (last or "failed"))
    if "codex" in sessions:
        rc, last = run_converter("codex.py", os.path.join(brain, "chats", "codex"), [], dry)
        (done if rc == 0 else errors).append("codex chats: " + (last or "failed"))
    collections = []
    if index:
        conf, collections = write_qmd_config(notes, brain, home, dry)
        done.append("search config %s (+%d notes collections)%s" % (conf, len(collections), " (dry run)" if dry else ""))
        if not dry:
            if shutil.which("qmd"):
                p = subprocess.run(["qmd", "update"], capture_output=True, text=True, timeout=900)
                (done if p.returncode == 0 else errors).append("qmd update " + ("ok" if p.returncode == 0 else "failed"))
            else:
                done.append("qmd is not installed: search is off. Install qmd, then run: brain reindex")
    if not dry:
        receipt = os.path.join(home, ".config", "second-brain", "onboard.json")
        os.makedirs(os.path.dirname(receipt), mode=0o700, exist_ok=True)
        with open(receipt, "w", encoding="utf-8") as f:
            json.dump(dict(version=1, date=time.strftime("%Y-%m-%d %H:%M"), brain=brain, notes=notes, sessions=sessions,
                           exclude_projects=excludes, collections=collections), f, indent=2)
        os.chmod(receipt, 0o600)
        done.append("receipt " + receipt)
    return done, errors


# ---------------------------------------------------------------- command line

def parse(argv):
    ap = argparse.ArgumentParser(prog="brain onboard", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--plan", action="store_true")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--yes", action="store_true")
    ap.add_argument("--notes", action="append", default=[], metavar="DIR")
    ap.add_argument("--sessions", metavar="claude,codex|none")
    ap.add_argument("--exclude-project", action="append", default=[], metavar="GLOB")
    ap.add_argument("--brain", metavar="DIR")
    ap.add_argument("--no-index", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    return ap.parse_args(argv)


def main(argv=None):
    args = parse(sys.argv[1:] if argv is None else argv)
    home = os.path.expanduser("~")
    brain = os.path.abspath(os.path.expanduser(args.brain or os.environ.get("BRAIN_HOME") or os.path.join(home, "brain")))
    found = scan(home, brain)
    if args.plan:
        print(json.dumps(found, indent=2) if args.json else show(found))
        return OK
    sessions = None
    if args.sessions is not None:
        sessions = [] if args.sessions.strip().lower() == "none" else [s.strip().lower() for s in args.sessions.split(",") if s.strip()]
        bad = [s for s in sessions if s not in ("claude", "codex")]
        if bad:
            print("brain onboard: unknown --sessions value: %s (use claude, codex or none)" % ", ".join(bad), file=sys.stderr)
            return BAD_ARGS
    notes = [os.path.abspath(os.path.expanduser(n)) for n in args.notes]
    missing = [n for n in notes if not os.path.isdir(n)]
    if missing or any(os.path.abspath(n) == brain for n in notes):
        print("brain onboard: not a notes folder (or it is the brain itself): " + ", ".join(missing or [brain]), file=sys.stderr)
        return BAD_ARGS
    excludes = list(args.exclude_project)
    if args.yes:
        if not notes and sessions is None:
            print("brain onboard --yes needs a choice: --notes DIR and/or --sessions claude,codex|none. Nothing is ingested by default.", file=sys.stderr)
            return BAD_ARGS
    elif sys.stdin.isatty() and sys.stdout.isatty():
        notes, sessions, excludes = interactive(found)
        if not (notes or sessions):
            print("Nothing chosen, nothing done. Run brain onboard again any time.")
            return OK
        if not ask_yes("Go?"):
            print("Stopped. Nothing was changed.")
            return OK
    else:
        print(show(found))
        print("\nThis needs a decision. Run it in a terminal, or add --yes with --notes DIR and/or --sessions claude,codex|none.")
        return UNDECIDED
    done, errors = execute(brain, home, notes, sessions or [], excludes, not args.no_index, args.dry_run)
    print("\n".join(["Done:"] + ["  " + d for d in done] + (["Problems:"] + ["  " + e for e in errors] if errors else [])))
    return PARTIAL if errors else OK


if __name__ == "__main__":
    sys.exit(main())
