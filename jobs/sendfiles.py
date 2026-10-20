"""Send files to one of <user>'s devices by voice: which device, which files, and the safety checks.

Used by jobs.py (build and the re-check before running) and by bin/send (which does the sending).

  device_from(text)         "send ... to the lap top"  -> "laptop" (or "testbox", "phone", None)
  plan(text, ...)           what to send -> {"device", "paths", "name", "label", "answer"} or {"answer": ...}
  check_send(device, paths) the one re-check used by build, jobs.run and bin/send; raises ValueError

Devices (the same three as Claude's `send` tool, mods-v3/send/hooks/devices.ts):
  laptop  ~/.local/bin/send-to-laptop (its own folder there: Downloads/From desktop)
  testbox     scp to testbox:Downloads/
  phone   tailscale file cp <file> owners-iphone:   (Files app, Tailscale folder)

Safety: every path must pass desktop.allowed_path (inside home or its HDD twin, no hidden folder, not a
program), nothing that looks like a key or a password, at most 10 files and 300 MB to the laptop, 5 files
and 100 MB to the test machine or phone. A folder only when it is named, with at most 200 files, nothing hidden and no links (shortcuts) inside.
"""
import difflib
import json
import os
import re
import sys
import time

import desktop

DEVICES = {
    "laptop": {"say": "the laptop", "host": "user-laptop", "max_files": 10, "max_mb": 300},
    "testbox": {"say": "the test machine", "host": "testbox", "max_files": 5, "max_mb": 100},
    "phone": {"say": "your iPhone", "host": "owners-iphone", "max_files": 5, "max_mb": 100},
}
LANDS = {
    "laptop": "They go into Downloads, in the From desktop folder, on the laptop.",
    "testbox": "They go into the test machine's Downloads folder.",
    "phone": "They go to your iPhone. Look in the Files app, in the Tailscale folder.",
}
WHICH = "Which one: the laptop, the test machine or your iPhone?"
SHAREABLE = {".md", ".txt", ".pdf", ".docx", ".png", ".jpg", ".jpeg", ".webp", ".zip", ".html", ".mp4", ".csv"}
SKIP_FILES = {"claude.md", "agents.md", "gemini.md", "requirements.txt", "license.txt", "license.md"}
SKIP_PROJECT_DIRS = {"src", "tests", "test", "out", "coverage", ".next", "vendor", "__tests__"}
# Anything that looks like a key or a password stays home, because this leaves the machine.
DENY_NAME = re.compile(r"secret|token|credential|passw|id_rsa|id_ed25519|private[-_ ]?key|\.pem$|\.key$|\.p12$|"
                       r"\.pfx$|\.kdbx$|^\.env|\.env$|\.env\.", re.I)
MAX_PATHS = 10
MAX_FOLDER_FILES = 200
SOURCES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config", "send-sources.json")

# The words for each device, with the slips speech-to-text makes.
DEVICE_WORD = r"(lap ?top|lab ?top|user laptop|testbox(?: handheld)?|rogue|handheld|hand ?held|i ?phone|phone)"
_TO = re.compile(r"\b(?:over |across )?(?:to|on|onto|into|for|with)\s+(?:(?:the|my|his|our|that)\s+)?" + DEVICE_WORD + r"\b",
                 re.I)
_GIVE = re.compile(r"\b(?:send|give|get|bring|hand)\s+(?:(?:the|my|his|our)\s+)?" + DEVICE_WORD + r"\b", re.I)
VERBS = r"(?:send|put|copy|move|share|transfer|push|beam|drop|get|throw|airdrop|give|bring|hand)"
_POLITE = r"^(?:please\s+)?(?:(?:can|could|would|will)\s+you\s+(?:please\s+)?)?(?:(?:i (?:want|need) you to|go ahead and)\s+)?"
_STARTS_SEND = re.compile(_POLITE + VERBS + r"\b", re.I)
_TO_DEVICE = re.compile(_TO.pattern + r"(?!\s*(?:screen|monitor|display))", re.I)
# Desktop actions whose words can sit in a send-shaped sentence: "put the volume up on the laptop",
# "put the night light on for the laptop". Those are the desktop job, not a send.
NOT_SEND_ACTIONS = {"volume-up", "volume-down", "volume-mute", "mic-mute", "nightlight", "nightlight-on",
                    "nightlight-off", "dnd", "stay-awake", "allow-sleep", "bluetooth-on", "bluetooth-off", "lock",
                    "logout", "reboot", "shutdown", "reminder", "reminders-show", "workspace", "window-monitor"}


def _device_id(word):
    w = word.lower().replace(" ", "")
    if w in ("laptop", "labtop", "dogmalaptop"):
        return "laptop"
    if w.startswith("testbox") or w in ("handheld", "handheld"):
        return "testbox"
    return "phone"


def device_from(text):
    """"laptop", "testbox" or "phone" for the device the text sends to, else None."""
    t = " ".join(text.lower().split())
    hits = list(_TO.finditer(t))
    if hits:
        return _device_id(hits[-1].group(1))
    m = _GIVE.search(t)
    return _device_id(m.group(1)) if m else None


def is_send_request(text):
    """True for "send the kingdom map to my phone": the request starts with a send verb (after "please" or
    "can you"), names a device, and what it sends isn't a desktop setting. "Remind me to put the charger on
    the laptop", "take a screenshot and send it to my phone" and "put the volume up on the laptop" are not."""
    t = " ".join(str(text).lower().split()).strip(" .?!,")
    t = re.sub(r"^(hey |hi |ok |okay )?claude\b[\s,.:!-]*", "", t)
    if not _STARTS_SEND.search(t):
        return False
    if not _TO_DEVICE.search(t) and not re.search(_POLITE + r"(?:send|give|get|bring|hand)\s+(?:(?:the|my|his|our)\s+)?"
                                                  + DEVICE_WORD + r"\s+(?:the|my|a|that|this)\b", t):
        return False
    action = desktop.find_action(subject_of(t))[0]
    return action not in NOT_SEND_ACTIONS


def fmt_size(n):
    if n >= 1024 ** 3:
        return f"{n / 1024 ** 3:.1f} GB"
    if n >= 1024 ** 2:
        return f"{n / 1024 ** 2:.0f} MB"
    return f"{max(1, round(n / 1024))} KB"


# ---------- finding the files ----------

def _walk(root, depth, budget, deadline):
    """Files under root, at most `depth` folders down, never into hidden or build folders or symlinked folders."""
    stack = [(root, 0)]
    while stack:
        d, lvl = stack.pop()
        try:
            entries = list(os.scandir(d))
        except OSError:
            continue
        for e in entries:
            budget[0] -= 1
            if budget[0] <= 0 or time.monotonic() > deadline:
                return
            if e.name.startswith(".") or e.name in desktop.SKIP_DIRS:
                continue
            try:
                if e.is_dir(follow_symlinks=False):
                    if lvl < depth:
                        stack.append((e.path, lvl + 1))
                elif e.is_file(follow_symlinks=False):
                    yield e.path
            except OSError:
                continue


def _shareable(path):
    name = os.path.basename(path).lower()
    return os.path.splitext(name)[1] in SHAREABLE and name not in SKIP_FILES and not DENY_NAME.search(name)


def _mtime(path):
    try:
        return os.path.getmtime(path)
    except OSError:
        return 0.0


def _sources():
    try:
        with open(SOURCES) as f:
            data = json.load(f)
    except FileNotFoundError:   # no list of extra folders
        return {}
    except (OSError, ValueError) as why:
        print(f"sendfiles: could not read {SOURCES} ({why}); no extra folders", file=sys.stderr)
        return {}
    return {k: v for k, v in data.items() if isinstance(v, list)} if isinstance(data, dict) else {}


def _carries_name(path, root, pn, words):
    """Is this file in a folder named like the project, or does its own name carry the project's name (or all
    its words)? `pn` is the project's name without spaces and dashes."""
    parts = os.path.relpath(path, root).lower().split(os.sep)
    name = parts[-1]
    in_named_folder = any(pn and pn in desktop._norm(p) for p in parts[:-1])
    return bool(in_named_folder or (pn and pn in desktop._norm(os.path.splitext(name)[0])) or
                (len(words) > 1 and all(w in name for w in words)))


def _project_folder_paths(project_dir, budget, deadline):
    """The files in the project's own folder (two levels deep), leaving out build and dependency folders."""
    for path in _walk(project_dir, 2, budget, deadline):
        rel_parts = os.path.relpath(path, project_dir).lower().split(os.sep)[:-1]
        if not any(p in SKIP_PROJECT_DIRS for p in rel_parts):
            yield path


def project_files(project, project_dir=None, seconds=2.5):
    """Shareable files that belong to a project, newest first:
    folders named like it in Downloads, Documents, Media and _inbox; files there that carry its name;
    folders listed in config/send-sources.json; and its own folder (two levels deep)."""
    home = desktop.HOME
    pn = desktop._norm(project)
    words = [w for w in re.split(r"[-_ ]+", project.lower()) if len(w) > 1]
    deadline = time.monotonic() + seconds
    budget = [60000]
    found = {}

    def add(path):
        real = os.path.realpath(path)
        if _shareable(real) and desktop.allowed_path(real):
            found[real] = _mtime(real)

    for area in desktop.USER_AREAS:
        root = os.path.join(home, area)
        if os.path.isdir(root):
            for path in _walk(root, 4, budget, deadline):
                if _carries_name(path, root, pn, words):
                    add(path)
    for folder in _sources().get(project, []):
        root = os.path.expanduser(str(folder))
        if os.path.isdir(root):
            for path in _walk(root, 2, budget, deadline):
                add(path)
    if project_dir and os.path.isdir(project_dir):
        for path in _project_folder_paths(project_dir, budget, deadline):
            add(path)
    return sorted(found, key=lambda p: (-found[p], p))


def kind_files(kind_exts, dirs, seconds=2.5):
    """Newest files of one kind (picture, video, pdf...) in the folders, newest first."""
    deadline = time.monotonic() + seconds
    budget = [60000]
    found = {}
    for root in dirs:
        if os.path.isdir(root):
            for path in _walk(root, 2, budget, deadline):
                if os.path.splitext(path)[1].lower() in kind_exts and not DENY_NAME.search(os.path.basename(path)):
                    real = os.path.realpath(path)
                    if desktop.allowed_path(real):
                        found[real] = _mtime(real)
    return sorted(found, key=lambda p: (-found[p], p))


def newest(paths, many):
    """One file, or the newest plus the ones within an hour of it (at most 5)."""
    if not paths:
        return []
    if not many:
        return paths[:1]
    top = _mtime(paths[0])
    return [p for p in paths if top - _mtime(p) <= 3600][:5]


# ---------- the safety check ----------

def _folder_info(path):
    """(file count, bytes) of a folder; ValueError if it holds hidden, program or key-like things."""
    count, size = 0, 0
    for dirpath, dirs, files in os.walk(path, followlinks=False):
        for name in dirs + files:
            # A link inside the folder could point anywhere (a hidden folder, a key, something huge), and the
            # copy and the zip would follow it. So a folder with links in it isn't sent.
            if os.path.islink(os.path.join(dirpath, name)):
                raise ValueError(f"the folder {os.path.basename(path)} has shortcuts (links) in it, so I won't "
                                 "send it. Tell me which files you want")
        for d in dirs:
            if d.startswith(".") or d in desktop.SKIP_DIRS or DENY_NAME.search(d):
                raise ValueError(f"the folder {os.path.basename(path)} has hidden or program folders in it, "
                                 "so I won't send it. Tell me which files you want")
        for f in files:
            if f.startswith(".") or DENY_NAME.search(f) or \
                    os.path.splitext(f)[1].lower() in desktop.BAD_EXT:
                raise ValueError(f"the folder {os.path.basename(path)} has files in it I won't send ({f}). "
                                 "Tell me which files you want")
            count += 1
            if count > MAX_FOLDER_FILES:
                raise ValueError(f"the folder {os.path.basename(path)} has more than {MAX_FOLDER_FILES} files. "
                                 "Pick fewer files")
            try:
                size += os.path.getsize(os.path.join(dirpath, f))
            except OSError as why:   # counted but not sized: the size shown may be a little low
                print(f"sendfiles: could not size {os.path.join(dirpath, f)}: {why}", file=sys.stderr)
    return count, size


def check_send(device, paths):
    """(device, [real paths], {"count", "bytes", "dirs"}) for a send that is allowed; ValueError with a plain
    reason otherwise. The one check used when building the card, before running, and inside bin/send."""
    if device not in DEVICES:
        raise ValueError("I only know the laptop, the test machine and your iPhone")
    dev = DEVICES[device]
    if not isinstance(paths, list) or not paths or not all(isinstance(p, str) for p in paths):
        raise ValueError("there was no file to send")
    if len(paths) > MAX_PATHS:
        raise ValueError(f"that's {len(paths)} files and I can send {dev['max_files']} at a time")
    real, dirs, total, count = [], 0, 0, 0
    for p in paths:
        r = desktop.allowed_path(p)
        if not r:
            raise ValueError(f"I'm not allowed to send {os.path.basename(str(p)) or 'that'}: it has to be a plain "
                             "file in your home folder, not hidden and not a program")
        if DENY_NAME.search(os.path.basename(r)):
            raise ValueError(f"{os.path.basename(r)} looks like a key or a password, so I won't send it")
        if r in real:
            continue
        real.append(r)
        if os.path.isdir(r):
            n, size = _folder_info(r)
            dirs += 1
            count += n
            total += size
        else:
            count += 1
            total += os.path.getsize(r)
    if len(real) > dev["max_files"]:
        raise ValueError(f"that's {len(real)} files and I can send {dev['max_files']} at a time to "
                         f"{dev['say']}. Pick fewer files")
    if total > dev["max_mb"] * 1024 * 1024:
        raise ValueError(f"that's {fmt_size(total)}. I can send up to {dev['max_mb']} MB at a time to "
                         f"{dev['say']}. Pick fewer files")
    return device, real, {"count": count, "bytes": total, "dirs": dirs}


# ---------- what <user> asked for ----------

LATEST = re.compile(r"\b(latest|newest|last|recent|most recent|new|current)\b", re.I)
PLURAL = re.compile(r"\b(files|docs|documents|things|stuff|pictures|photos|images|screenshots|videos|pdfs|notes|"
                    r"downloads)\b", re.I)


def subject_of(text):
    """What is being sent, with the polite words, the verb and the device taken off."""
    t = " ".join(text.lower().split()).strip(" .?!,")
    t = re.sub(r"^(hey |ok |okay )?claude\b[\s,.:!-]*", "", t)
    t = re.sub(r"^(please\s+)?((can|could|would|will)\s+you\s+(please\s+)?)?(i (want|need) you to\s+)?", "", t)
    t = re.sub(r"^" + VERBS + r"\s+(up\s+)?", "", t)
    m = None
    for m in _TO.finditer(t):
        pass
    if m:
        t = t[:m.start()] + " " + t[m.end():]
    else:
        t = re.sub(r"^(?:the |my |his |our )?" + DEVICE_WORD + r"\s+", "", t)
    t = re.sub(r"\b(please|real quick|for me|right now)\b", " ", t)
    return " ".join(t.split())


def _project_dir(project, projects_root):
    d = os.path.join(projects_root, project)
    return d if os.path.isdir(d) else None


def _pretty(project):
    return " ".join(w if w.isupper() else w.capitalize() for w in re.split(r"[-_ ]+", project))


# Words that name no file: "send it", "a text", "the call", "the time". With nothing else named, ask.
GENERIC = {"it", "them", "this", "these", "those", "that", "one", "ones", "file", "files", "thing", "things",
           "stuff", "something", "everything", "me", "us", "him", "her", "over", "here", "there", "now"}
NOT_FILE = {"text", "texts", "message", "messages", "sms", "call", "calls", "time", "date", "music", "song", "songs",
            "tv", "television", "location", "email", "emails", "link", "reminder", "volume", "note", "notes",
            "window", "screen", "app", "apps", "game", "games"}
KEY_WORDS = re.compile(r"(^|\s)\.?env\b|\b(ssh|keys?|passwords?|passwd|tokens?|secrets?|credentials?|"
                       r"private key|api key|keyring|wallet)\b", re.I)
NOT_A_FILE = "I can only send files. Tell me the name of the file."
# "send a text to mom": a message, not a file.
MESSAGE_START = re.compile(r"^(?:(?:a|an|the|my)\s+)?(?:text|texts|message|messages|sms|email|e-mail|call|voice ?note)\b")


def _close(word, tokens):
    return word in tokens or any(len(word) >= 4 and len(t) >= 4 and (t.startswith(word) or
                                 difflib.SequenceMatcher(None, word, t).ratio() >= 0.8) for t in tokens)


def _name_fits(path, named, subject):
    """A file the name search found is only used when it is plainly what was said: every word named is in
    its name (close spellings count), and it is a document, picture or video, unless its whole name
    (with the ending) was said. A folder only when "folder" was said."""
    base = os.path.basename(path.rstrip("/")).lower()
    if os.path.isdir(path):
        if not re.search(r"\b(folder|directory)\b", subject):
            return False
    elif base not in subject and not _shareable(path):
        return False
    tokens = re.findall(r"[a-z0-9]+", base)
    return all(_close(w, tokens) or w in base for w in named)


def _refusal(subject, named, kind_rx, project, wants_folder, has_ext):
    """The plain answer when what was said cannot be a file: no name, a message, or an app. None otherwise."""
    if kind_rx or project or desktop.known_folder(subject):
        return None
    if not named:
        return {"answer": "Which file should I send? Tell me its name."}
    if (all(w in NOT_FILE for w in named) or MESSAGE_START.match(subject)) and not wants_folder:
        return {"answer": NOT_A_FILE}
    if not wants_folder and not has_ext:
        app_id, app_name, score = desktop.find_app(subject)
        if app_id and score >= 0.9:
            return {"answer": f"{app_name} is an app, and I can only send files. Tell me the name of the file."}
    return None


def _newest_of_kind(subject, kind_rx, many):
    """"the screenshot", "the latest pdf": a kind of file and no name, so the newest of that kind."""
    exts = tuple(e for _, es in kind_rx for e in es)
    home = desktop.HOME
    shots = os.path.join(home, "Media", "Pictures", "Screenshots")
    dirs = [shots] if "screenshot" in subject else \
        [os.path.join(home, a) for a in ("Downloads", "Media/Pictures", "Documents", "_inbox")] + [shots]
    return newest(kind_files(exts, dirs), many)


def _find_by_name(subject, named, wants_folder, many, project_dirs):
    """The file (or the project's newest files) the name points at: (paths, project_name)."""
    path, what, score = desktop.find_file(subject, project_dirs, min_score=0.6)
    exact = path and score >= 1.0   # a known folder or a project folder, by its name
    if path and not exact and not _name_fits(path, named, subject):
        path = None
    if not path:
        return [], None
    is_project_dir = os.path.basename(path) in {os.path.basename(d) for d in project_dirs}
    if is_project_dir and not wants_folder:
        proj = os.path.basename(path)
        return newest(project_files(proj, path), many), _pretty(proj)
    return [path], None


def _from_subject(subject, project, many, latest, project_dirs):
    """Look for the files by kind, then by name: (paths, project_name, answer). An answer means stop and say it."""
    kind_rx = [(rule, exts) for rule, exts in desktop.KIND_EXT.items()
               if re.search(r"\b(" + rule + r")s?\b", subject)]
    named = [w for w in desktop._words(subject)
             if not LATEST.search(w) and not PLURAL.search(w) and w not in GENERIC and
             not any(re.fullmatch(r"(" + rule + r")s?", w) for rule, _ in kind_rx)]
    wants_folder = bool(re.search(r"\b(folder|directory)\b", subject))
    has_ext = bool(re.search(r"\.[a-z0-9]{2,4}\b", subject))
    refusal = _refusal(subject, named, kind_rx, project, wants_folder, has_ext)
    if refusal:
        return [], None, refusal
    paths = []
    if kind_rx and not project and (latest or not named):
        paths = _newest_of_kind(subject, kind_rx, many)
    if paths:
        return paths, None, None
    paths, project_name = _find_by_name(subject, named, wants_folder, many, project_dirs)
    return paths, project_name, None


def _nothing_found(subject, project, project_name):
    if project_name or project:
        return {"answer": f"I couldn't find any {_pretty(project)} files to send. Tell me the name of the file."}
    if not subject:
        return {"answer": "Which file should I send? Tell me its name."}
    return {"answer": f"I couldn't find a file for {subject}. Tell me the name of the file."}


def _card(device, real, info, project_name):
    """The label and the answer <user> hears for a send that passed the safety check."""
    dev = DEVICES[device]
    names = [os.path.basename(p) for p in real]
    if len(real) == 1:
        what_label = names[0]
    else:
        what_label = f"{len(real)} " + (f"{project_name} files" if project_name else "files")
    label = f"Send {what_label} to {dev['say']}"
    if len(names) == 1:
        listed = names[0]
    else:
        listed = ", ".join(names[:-1]) + " and " + names[-1]
    inside = f"{info['count']} files, " if info["dirs"] else ""
    where = ""
    if len(real) == 1 and not info["dirs"]:   # a single file: say which folder it came from, so a wrong guess shows
        where = f", from the {os.path.basename(os.path.dirname(real[0])) or 'home'} folder"
    answer = f"{listed} ({inside}{fmt_size(info['bytes'])}){where}. {LANDS[device]}"
    name = project_name or "Files"
    return {"device": device, "paths": real, "name": name, "label": label, "answer": answer}


def plan(text, find_project=None, projects_root=None, project_dirs=()):
    """Work out the send: {"device", "paths", "name", "label", "answer"} or {"answer": a plain reply}.
    find_project(text) -> project folder name or None (jobs.find_project)."""
    device = device_from(text)
    if not device:
        return {"answer": WHICH}
    subject = subject_of(text)
    if KEY_WORDS.search(subject):
        return {"answer": "That looks like a key or a password, so I won't send it."}
    many = bool(PLURAL.search(subject))
    latest = bool(LATEST.search(subject))
    project = find_project(subject) if find_project and subject else None
    if project == "desk":
        project = None
    paths, project_name = [], None
    if project and (latest or many):
        paths = newest(project_files(project, _project_dir(project, projects_root)), many)
        project_name = _pretty(project)
    if not paths and subject:
        paths, found_name, answer = _from_subject(subject, project, many, latest, project_dirs)
        if answer:
            return answer
        project_name = found_name or project_name
    if not paths:
        return _nothing_found(subject, project, project_name)
    try:
        device, real, info = check_send(device, paths)
    except ValueError as why:
        msg = str(why)
        return {"answer": msg[:1].upper() + msg[1:].rstrip(".") + "."}
    return _card(device, real, info, project_name)
