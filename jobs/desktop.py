"""Desktop jobs: open an app, open a file or folder, and a short list of Omarchy desktop actions.

Used by jobs.py (build / check / run of the open-app, open-file and desktop jobs) and by bin/desktop.

  open-app   "open spotify", "launch discord", "open a terminal"   -> the app's .desktop entry
  open-file  "open the kingdom map", "open my downloads folder"     -> a file or folder in your home
  desktop    "next theme", "take a screenshot", "lock the screen"  -> one action from ACTIONS

Safety: an app must be an installed, visible .desktop entry; a file must be inside your home (or its HDD
twin), in no hidden folder, and not a program or launcher; a desktop action must be in ACTIONS, and its
value is checked (a theme that exists, 1 to 1440 minutes, a workspace 1 to 10). Log out, restart and
shut down ask first. Nothing deletes, sends or spends.
"""
import configparser
import datetime as dt
import difflib
import glob
import json
import os
import re
import subprocess
import time

HOME = os.path.expanduser("~")
FILE_ROOTS = [HOME, "/mnt/backup/home"]
SKIP_DIRS = ["node_modules", ".git", "__pycache__", ".venv", "venv", "dist", "build", "target", ".cache"]
BAD_EXT = {".desktop", ".sh", ".appimage", ".exe", ".run", ".bin", ".bat", ".cmd", ".ps1", ".jar", ".deb"}
SAFE_ID = re.compile(r"^[A-Za-z0-9._@+-]+$")

# ---------- apps ----------

# Things people say that aren't an app's name.
APP_ALIASES = {
    "browser": "@browser", "web browser": "@browser", "internet": "@browser", "web": "@browser",
    "terminal": "@terminal", "console": "@terminal", "shell": "@terminal",
    "files": "@files", "file manager": "@files", "file browser": "@files", "explorer": "@files",
    "editor": "@editor", "text editor": "@editor", "code editor": "@editor",
}
SPECIAL = {
    "@browser": ("Browser", ["omarchy", "launch", "browser"]),
    "@terminal": ("Terminal", ["omarchy", "launch", "terminal"]),
    "@files": ("Files", ["omarchy", "launch", "nautilus"]),
    "@editor": ("Editor", ["omarchy", "launch", "editor", HOME]),
}


def _app_dirs():
    data = [os.environ.get("XDG_DATA_HOME", os.path.join(HOME, ".local/share"))]
    data += os.environ.get("XDG_DATA_DIRS", "/usr/local/share:/usr/share").split(":")
    return [os.path.join(d, "applications") for d in data if d]


def apps():
    """Installed, visible apps: {id: {name, words, wmclass}}. The first folder wins (your own copies)."""
    found = {}
    for d in _app_dirs():
        for path in glob.glob(os.path.join(d, "**", "*.desktop"), recursive=True):
            app_id = os.path.relpath(path, d).replace(os.sep, "-")[:-len(".desktop")]
            if app_id in found:
                continue
            cp = configparser.RawConfigParser(interpolation=None, strict=False)
            try:
                cp.read(path, encoding="utf-8")
                e = cp["Desktop Entry"]
            except (configparser.Error, KeyError, UnicodeDecodeError):
                continue
            hidden = e.get("NoDisplay", "").lower() == "true" or e.get("Hidden", "").lower() == "true"
            if hidden or e.get("Type", "Application") != "Application" or not e.get("Name"):
                found[app_id] = None  # a hidden copy hides the system one too
                continue
            exe = os.path.basename((e.get("Exec") or "").split(" ")[0]) if e.get("Exec") else ""
            words = [e.get("Name"), e.get("GenericName", ""), exe, app_id.split(".")[-1]]
            words += [k for k in e.get("Keywords", "").split(";") if k]
            found[app_id] = {"name": re.sub(r"\s*\(.*?\)\s*", " ", e.get("Name")).strip() or e.get("Name"),
                             "words": [w.lower() for w in words if w],
                             "wmclass": e.get("StartupWMClass", ""), "exe": exe,
                             "web": "(web)" in e.get("Name", "").lower() or exe == "omarchy-launch-webapp"}
    return {k: v for k, v in found.items() if v}


def _norm(s):
    return re.sub(r"[^a-z0-9]", "", s.lower())


APP_SAID = {"vs code": "visual studio code", "vscode": "visual studio code", "code": "visual studio code",
            "chrome": "google chrome"}


def app_topic(text):
    t = text.strip().strip(" .?!")
    t = re.sub(r"^(please\s+)?((can|could|would|will) you\s+(please\s+)?)?(open|launch|start|run|fire up|bring up|"
               r"pull up|switch to|go to|show)\s+(up\s+)?((my|the|a|an)\s+)?", "", t, flags=re.I)
    # "... and move it to the left screen", "... on my second monitor", "... for me": not part of the name.
    t = re.sub(r"\s+(and|then)\s+(move|put|send|shift|throw|push)\b.*$", "", t, flags=re.I)
    t = re.sub(r"\s+(on|in|onto|to)\s+(my|the|this|that)?\s*(\w+\s+){0,2}(monitor|screen|display|workspace)(\s+\w+)?$",
               "", t, flags=re.I)
    t = re.sub(r"\s+(for me|please|real quick|right now|now)$", "", t, flags=re.I)
    t = re.sub(r"\s+(app|application|program|window)$", "", t, flags=re.I).strip(" .?!,")
    return APP_SAID.get(t.lower(), t)


def find_app(text, catalog=None):
    """(app id, name, score) for the app the text names, or (None, None, 0)."""
    topic = app_topic(text).lower()
    if not topic:
        return None, None, 0.0
    if topic in APP_ALIASES:
        key = APP_ALIASES[topic]
        return key, SPECIAL[key][0], 1.0
    catalog = catalog if catalog is not None else apps()
    nt = _norm(topic)
    scored = []
    for app_id, a in catalog.items():
        name = _norm(a["name"])
        if name == nt:
            score = 1.0
        elif nt and nt in [_norm(w) for w in a["words"][:4]]:
            score = 0.95
        else:
            score = max([difflib.SequenceMatcher(None, nt, _norm(w)).ratio() for w in a["words"][:4] if w] or [0])
            if name and len(nt) >= 4 and (name.startswith(nt) or nt.startswith(name)):
                score = max(score, 0.88)
            # A whole word of the name: "chrome" for "Google Chrome".
            if len(nt) >= 4 and nt in re.findall(r"[a-z0-9]+", a["name"].lower()):
                score = max(score, 0.9)
        # Keywords count a little, so "music" can find Spotify but never beats a real name.
        if score < 0.8 and nt in [_norm(w) for w in a["words"][4:]]:
            score = 0.8
        scored.append((score, app_id, a))
    if not scored:
        return None, None, 0.0
    top = max(s for s, _, _ in scored)
    if top < 0.8:
        return None, None, top
    # A tie ("Discord" the app and "Discord (web)"): one that's open now, then the real app, then the shorter name.
    ties = [(app_id, a) for s, app_id, a in scored if s >= top - 0.02]
    open_now = open_classes() if len(ties) > 1 else set()
    app_id, a = min(ties, key=lambda t: (not _is_open(t[1], open_now), t[1]["web"], len(t[1]["name"])))
    return app_id, a["name"], top


def open_classes():
    try:
        out = subprocess.run(["hyprctl", "clients", "-j"], capture_output=True, text=True, timeout=2).stdout
        return {c.get("class", "").lower() for c in json.loads(out or "[]")}
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return set()


def _is_open(a, classes):
    return any(n and n.lower() in classes for n in (a["wmclass"], a["exe"]))


def app_command(app_id, catalog=None):
    """The command that opens (or focuses, if already open) the app. Raises ValueError if unknown."""
    if app_id in SPECIAL:
        return SPECIAL[app_id][1]
    catalog = catalog if catalog is not None else apps()
    if app_id not in catalog or not SAFE_ID.match(app_id):
        raise ValueError("that app isn't installed")
    a = catalog[app_id]
    # An open window that fits is focused instead of opening a second one. launch-or-focus tries the same
    # pattern on a window's class and on its title, so the short words (the window class, the program, the
    # last part of the id: "code" for VS Code) must be the whole class, never just a word in a title
    # ("Claude Code - ..." in a terminal is not VS Code). Only the app's full name may sit in a title.
    short = [n for n in dict.fromkeys([a["wmclass"], a["exe"], app_id.split(".")[-1], app_id]) if n and len(n) > 2]
    parts = []
    if short:
        parts.append(r"^(?:[\w.-]*\.)?(?:" + "|".join(re.escape(n) for n in short) + r")$")
    if a["name"] and len(a["name"]) > 2:
        parts.append(re.escape(a["name"]))
    pattern = "(?:" + "|".join(parts) + ")" if parts else "^" + re.escape(app_id) + "$"
    return ["omarchy-launch-or-focus", pattern, f"uwsm-app -- {app_id}.desktop"]


# ---------- files and folders ----------

KNOWN_FOLDERS = {
    "home": HOME, "home folder": HOME, "downloads": "Downloads", "download": "Downloads",
    "documents": "Documents", "videos": "Videos", "media": "Media", "archive": "Archive",
    "inbox": "_inbox", "projects": "projects", "code": "projects",
    "brain": "OMARCHY-BRAIN", "business": "user-labs-business", "screenshots": "Media/Pictures/Screenshots",
    "pictures": "Media/Pictures", "photos": "Media/Pictures", "music": "Music",
}
STOP = set("a an the my me of to on in for and with that this please up open show find folder file "
           "directory picture photo image video doc document called named".split())


def file_topic(text):
    t = re.sub(r"^(please\s+)?(can you\s+)?(open|show( me)?|pull up|bring up|find|look at)\s+(up\s+)?"
               r"((my|the|a|an|that)\s+)?", "", text.strip(), flags=re.I)
    return t.strip(" .?!")


KIND_EXT = {
    r"picture|photo|image|png|jpe?g|screenshot": (".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg"),
    r"video|clip|movie|mp4|recording": (".mp4", ".mkv", ".webm", ".mov"),
    r"pdf": (".pdf",),
    r"spreadsheet|sheet": (".xlsx", ".csv", ".ods"),
    r"docx?|word": (".docx", ".doc", ".odt"),
}


def _words(topic):
    return [w for w in re.findall(r"[a-z0-9]+", topic.lower()) if w not in STOP and len(w) > 1]


def allowed_path(path):
    """The real path if it may be opened, else None."""
    real = os.path.realpath(os.path.expanduser(str(path)))
    if not os.path.exists(real):
        return None
    for root in FILE_ROOTS:
        if real == root or real.startswith(root + os.sep):
            rel = os.path.relpath(real, root)
            if rel != "." and any(p.startswith(".") for p in rel.split(os.sep)):
                return None
            break
    else:
        return None
    if os.path.isfile(real):
        if os.path.splitext(real)[1].lower() in BAD_EXT or os.access(real, os.X_OK):
            return None
    return real


USER_AREAS = ("Downloads", "Documents", "Videos", "Media", "_inbox")


def known_folder(text):
    """The path of a folder everyone knows by name ("downloads", "my inbox folder"), or None."""
    low = file_topic(text).lower()
    plain = re.sub(r"\b(folder|directory|dir)\b", "", low).strip()
    plain = re.sub(r"^(my|the)\s+", "", plain).strip()
    p = KNOWN_FOLDERS.get(plain)
    if not p:
        return None
    p = p if os.path.isabs(p) else os.path.join(HOME, p)
    return p if os.path.isdir(p) else None


def find_file(text, project_dirs=(), min_score=0.6):
    """(path, kind 'folder'|'file', score) for what the text names, or (None, None, 0).
    Known folders and project folders first, then a name search of your home (fd, at most 3 s)."""
    topic = file_topic(text)
    low = topic.lower()
    wants_folder = bool(re.search(r"\b(folder|directory|dir)\b", low))
    if known_folder(text):
        return known_folder(text), "folder", 1.0
    words = _words(topic)
    if not words:
        return None, None, 0.0
    key = _norm("".join(words))
    for d in project_dirs:
        if _norm(os.path.basename(d)) == key and os.path.isdir(d):
            return d, "folder", 1.0
    exts = ()
    for rule, e in KIND_EXT.items():
        if re.search(r"\b(" + rule + r")s?\b", low):
            exts += e
    longest = max(words, key=len)
    cmd = ["fd", "--ignore-case", "--max-depth", "7", "--max-results", "400", "--color", "never"]
    for s in SKIP_DIRS:
        cmd += ["--exclude", s]
    if wants_folder:
        cmd += ["--type", "d"]
    cmd += ["--fixed-strings", longest, HOME]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=3).stdout.splitlines()
    except (OSError, subprocess.TimeoutExpired):
        out = []
    best = (None, None, 0.0)
    for line in out:
        path = line.rstrip("/")
        base = os.path.basename(path).lower()
        stem = os.path.splitext(base)[0] if os.path.isfile(path) else base
        hit = sum(1 for w in words if w in base) / len(words)
        sim = difflib.SequenceMatcher(None, key, _norm(stem)).ratio()
        score = 0.7 * hit + 0.3 * sim
        if os.path.isdir(path) == wants_folder:
            score += 0.05
        if exts:  # "picture", "video", "pdf": the asked-for kind counts a lot
            score += 0.4 if os.path.splitext(base)[1] in exts else -0.3
        score -= 0.01 * path[len(HOME):].count(os.sep)  # shallower wins a close call
        if path[len(HOME) + 1:].startswith(USER_AREAS):
            score += 0.05
        if score > best[2] and allowed_path(path):
            best = (path, "folder" if os.path.isdir(path) else "file", score)
    return best if best[2] >= min_score else (None, None, best[2])


# ---------- screens and windows ----------
# "Move this window to my other screen", "open VS Code on my second monitor". A screen is named by a
# symbolic spec ("other", "left", "right", "top", "bottom", "name:<words>") that is only turned into a
# real monitor at run time, from `hyprctl monitors -j`. Nothing said ever reaches the dispatch as text.

MOVE_VERBS = r"(?:move|put|send|shift|throw|push|drag|bring)"
# Said after "move": a file, not an app. "Move the file to the other screen" must not open a file manager.
NOT_APP_WORDS = re.compile(r"^(?:file|files?|folder|document|doc|picture|photo|image|video|pdf|text|note|notes|page|"
                           r"tab|tabs)$", re.I)
NOT_AN_APP = "I can only move windows to a screen, not files. Say the app's name, or say this window."
OPEN_START = re.compile(r"^(please\s+)?((can|could|would|will)\s+you\s+(please\s+)?)?"
                        r"(open|launch|start|run|fire up|pull up|switch to)\b", re.I)
WINDOW_MOVE = re.compile(r"\b" + MOVE_VERBS + r"\b(?!\s+up\b).*\b(to|onto|on|over to)\b\s+(my|the|that|this|a)?\s*"
                         r"(\w+\s+){0,2}(screen|monitor|display)s?\b", re.I)
SCREEN_PHRASE = re.compile(r"\b(?:to|onto|on|in)\s+(?:(?:my|the|that|this|a)\s+)?((?:[\w-]+\s+){0,2}?)"
                           r"(?:screen|monitor|display)s?\b(?:\s+(\w+))?", re.I)
SCREEN_NUMBER = re.compile(r"\b(?:to|onto|on|in)\s+(?:(?:my|the)\s+)?(?:screen|monitor|display)\s+(\w+)\b", re.I)
SPEC_GRAMMAR = ("other", "left", "right", "top", "bottom", "main")
SPEC_FILLER = {"my", "the", "that", "this", "a", "an", "of", "other", "another", "second", "2nd", "next",
               "different", "opposite", "secondary", "extra", "new", "whole", "entire", "full"}
MAIN_MESSAGE = "I don't know which screen is your main one yet. Say the left screen or the right screen."


def is_window_move(text):
    """True for "move this window to my other screen" (a move verb, then to/on a screen). A request that
    starts with open/launch ("open vs code on my second monitor") is an open-app job, not this."""
    t = text.strip()
    return bool(WINDOW_MOVE.search(t)) and not OPEN_START.search(t)


def monitor_spec(text):
    """The screen the text names, as a spec string, or None when it names none."""
    t = text.lower()
    found = None
    for m in SCREEN_PHRASE.finditer(t):
        words = [w for w in re.findall(r"[a-z0-9-]+", m.group(1) or "")]
        # "screen two" / "monitor 2": the word after the noun counts as a number.
        after = (m.group(2) or "").lower()
        if after in ("2", "two", "second") and not words:
            words = ["second"]
        found = words
    n = SCREEN_NUMBER.search(t)
    if n and (found is None or not found):
        if n.group(1) in ("2", "two", "second"):
            found = ["second"]
        elif n.group(1) in ("1", "one", "first"):
            found = ["first"]
    if found is None:
        return None
    joined = " ".join(found)
    if re.search(r"\b(second|2nd|other|another|next|different|opposite|secondary|extra)\b", joined):
        return "other"
    for word, spec in (("left", "left"), ("leftmost", "left"), ("right", "right"), ("rightmost", "right"),
                       ("top", "top"), ("upper", "top"), ("up", "top"), ("bottom", "bottom"),
                       ("lower", "bottom"), ("down", "bottom")):
        if re.search(r"\b" + word + r"\b", joined):
            return spec
    if re.search(r"\b(main|primary|first|1st|home|default)\b", joined):
        return "main"
    name = " ".join(w for w in found if w not in SPEC_FILLER)
    return ("name:" + name[:30]) if len(name) >= 2 else None


def monitors():
    """The screens that are on now: [{id, name, description, x, y, width, height}]."""
    try:
        out = subprocess.run(["hyprctl", "monitors", "-j"], capture_output=True, text=True, timeout=3).stdout
        data = json.loads(out or "[]")
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return []
    return [m for m in data if isinstance(m, dict) and not m.get("disabled") and m.get("name")]


def _match_name(words, mons):
    w = _norm(words)
    if len(w) < 2:
        return None
    for m in mons:
        if w == _norm(m["name"]) or w in _norm(m["name"]) or w in _norm(m.get("description", "")):
            return m
    return None


def check_monitor_spec(spec, mons=None):
    """The spec back if it is one I know and (for a named screen) one that exists now; ValueError otherwise."""
    spec = str(spec or "")
    if spec == "main":
        raise ValueError(MAIN_MESSAGE.rstrip("."))
    if spec in SPEC_GRAMMAR:
        return spec
    m = re.fullmatch(r"name:([a-z0-9 .-]{2,30})", spec)
    if m and _match_name(m.group(1), monitors() if mons is None else mons):
        return spec
    raise ValueError("I don't see a screen called " + (m.group(1).upper() if m and len(m.group(1)) <= 4
                                                      else m.group(1).title() if m else "that"))


def resolve_monitor(spec, mons, from_id=None):
    """(monitor, None) or (None, plain reason). `other` is the next screen after the one the window is on
    (left to right, wrapping)."""
    if len(mons) < 2:
        return None, "You only have one screen right now."
    order = sorted(mons, key=lambda m: (m.get("x", 0), m.get("y", 0)))
    if spec == "other":
        ids = [m["id"] for m in order]
        if from_id in ids:
            return order[(ids.index(from_id) + 1) % len(order)], None
        focused = next((m for m in order if m.get("focused")), order[0])
        return next(m for m in order if m is not focused), None
    axis = {"left": ("x", min), "right": ("x", max), "top": ("y", min), "bottom": ("y", max)}.get(spec)
    if axis:
        key, pick = axis
        vals = {m.get(key, 0) for m in mons}
        if len(vals) < 2:
            return None, f"None of your screens is on the {spec}."
        v = pick(vals)
        return next(m for m in order if m.get(key, 0) == v), None
    if spec.startswith("name:"):
        m = _match_name(spec[5:], mons)
        if m:
            return m, None
        return None, "I don't see a screen called " + spec[5:].title() + "."
    return None, "I don't know which screen you mean."


def monitor_say(mon, mons):
    """How to say a screen out loud: the left screen, the right screen, the LG screen."""
    if len(mons) > 1:
        xs = {m.get("x", 0) for m in mons}
        if len(xs) > 1:
            if mon.get("x", 0) == min(xs):
                return "the left screen"
            if mon.get("x", 0) == max(xs):
                return "the right screen"
            return "the middle screen"
        ys = {m.get("y", 0) for m in mons}
        if len(ys) > 1:
            return "the top screen" if mon.get("y", 0) == min(ys) else "the bottom screen"
    word = re.sub(r"\b(electronics|technology|group|shenzhen|0x[0-9a-f]+|[0-9]{6,})\b", "",
                  mon.get("description") or mon["name"], flags=re.I).split()
    return "the " + (word[0] if word else mon["name"]) + " screen"


def spec_say(spec):
    """The screen as words for a card, before any real screen is known."""
    if spec == "other":
        return "the other screen"
    if spec in ("left", "right", "top", "bottom"):
        return f"the {spec} screen"
    if spec and spec.startswith("name:"):
        n = spec[5:]
        return f"the {n.upper() if len(n) <= 4 else n.title()} screen"
    return "that screen"


def clients():
    try:
        out = subprocess.run(["hyprctl", "clients", "-j"], capture_output=True, text=True, timeout=3).stdout
        return [c for c in json.loads(out or "[]") if isinstance(c, dict)]
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return []


SPECIAL_CLASSES = {"@browser": r"chrom|firefox|brave|zen|vivaldi|librewolf|edge",
                   "@terminal": r"kitty|alacritty|foot|ghostty|wezterm|terminal|konsole",
                   "@files": r"nautilus|files|thunar|dolphin|nemo",
                   "@editor": r"^code|vscodium|zed|neovide|cursor|sublime"}


def window_pattern(app_id, catalog=None):
    """The regex that finds an app's windows (the same words launch-or-focus uses), or None."""
    if app_id in SPECIAL_CLASSES:
        return SPECIAL_CLASSES[app_id]
    try:
        argv = app_command(app_id, catalog)
    except ValueError:
        return None
    return argv[1] if argv[0] == "omarchy-launch-or-focus" else None


def app_windows(app_id, clist=None, catalog=None):
    """The app's open windows, the one focused most recently first. A window class that fits wins over
    a title that fits (launch-or-focus checks both)."""
    pattern = window_pattern(app_id, catalog)
    if not pattern:
        return []
    clist = clients() if clist is None else clist
    try:
        rx = re.compile(r"\b(?:" + pattern + r")\b" if app_id not in SPECIAL_CLASSES else pattern, re.I)
    except re.error:
        return []
    live = [c for c in clist if c.get("mapped", True) and not c.get("hidden") and
            (c.get("workspace") or {}).get("id", 1) > 0]
    by_class = [c for c in live if rx.search(c.get("class", "") or "")]
    # The pattern's short words only fit a whole class (see app_command), so a title only fits by the
    # app's full name: a terminal titled "Claude Code - ..." is not VS Code.
    hits = by_class or ([] if app_id in SPECIAL_CLASSES else [c for c in live if rx.search(c.get("title", "") or "")])
    return sorted(hits, key=lambda c: c.get("focusHistoryID", 99))


def window_move(text):
    """{"to": spec|None, "app": app id|None, "said": what was named|""} for a move request."""
    t = " ".join(text.lower().split()).strip(" .?!")
    m = re.search(r"\b" + MOVE_VERBS + r"\s+(.*?)\s+(?:to|onto|on|over to)\s+(?:(?:my|the|that|this|a)\s+)?"
                  r"(?:[\w-]+\s+){0,2}?(?:screen|monitor|display)s?\b", t)
    said = m.group(1) if m else ""
    while True:
        new = re.sub(r"^(the|my|this|that|a|an|current|active|focused|open|up)\s+", "", said)
        if new == said:
            break
        said = new
    said = re.sub(r"\s+(window|app|application|program|tab)s?$", "", said).strip()
    if said in ("", "it", "this", "that", "window", "one", "thing", "app", "application", "program", "tab"):
        said = ""
    app_id, not_app = None, False
    if said:
        app_id, _, score = find_app(said)
        # An app that isn't open gets opened, with no question asked, so only a sure name may do that:
        # a close spelling or a file word ("the file" fits "File Manager") only counts when it is open.
        if app_id and (score < 0.9 or NOT_APP_WORDS.match(said)) and not app_windows(app_id):
            not_app = bool(NOT_APP_WORDS.match(said))
            app_id = None
        elif not app_id and NOT_APP_WORDS.match(said):
            not_app = True
    out = {"to": monitor_spec(t), "app": app_id, "said": said}
    if not_app:
        out["not_app"] = True
    return out


def app_name(app_id):
    if app_id in SPECIAL:
        return SPECIAL[app_id][0]
    a = apps().get(app_id)
    return a["name"] if a else str(app_id)


# ---------- desktop actions ----------

# id: (what it does, what to say after, command, asks first). {v} is the checked value.
ACTIONS = {
    "theme-next": ("Switch to the next theme", "Switched to {v}.", ["@theme-next"], False),
    "theme-set": ("Switch the theme to {v}", "Switched the theme to {v}.", ["omarchy", "theme", "set", "{v}"], False),
    "theme-picker": ("Open the theme picker", "Here are your themes.", ["omarchy", "theme", "switcher"], False),
    "bg-next": ("Next wallpaper", "Changed the wallpaper.", ["omarchy", "theme", "bg", "next"], False),
    "bg-picker": ("Open the wallpaper picker", "Here are your wallpapers.", ["omarchy", "theme", "bg-switcher"], False),
    "nightlight": ("Toggle the night light", "Toggled the night light.", ["omarchy", "toggle", "nightlight"], False),
    "nightlight-on": ("Turn the night light on", "The night light is on.", ["@nightlight", "on"], False),
    "nightlight-off": ("Turn the night light off", "The night light is off.", ["@nightlight", "off"], False),
    "screenshot": ("Take a screenshot", "Took a screenshot. It's on your clipboard and in your Screenshots folder.", ["@screenshot", "fullscreen"], False),
    "screenshot-area": ("Screenshot a part of the screen", "Drag over the part you want.", ["@screenshot", "region"], False),
    "record-start": ("Start recording the screen", "Recording the screen. Say stop recording when you're done.", ["omarchy", "capture", "screenrecording", "--fullscreen"], False),
    "record-stop": ("Stop the screen recording", "Stopped the recording.", ["omarchy", "capture", "screenrecording", "--stop-recording"], False),
    "volume-up": ("Turn the computer up", "Turned the computer up.", ["omarchy", "audio", "output", "volume", "raise"], False),
    "volume-down": ("Turn the computer down", "Turned the computer down.", ["omarchy", "audio", "output", "volume", "lower"], False),
    "volume-mute": ("Mute or unmute the computer", "Muted or unmuted the computer.", ["omarchy", "audio", "output", "volume", "mute-toggle"], False),
    "mic-mute": ("Mute or unmute the microphone", "Muted or unmuted the microphone.", ["omarchy", "audio", "input", "mute"], False),
    "dnd": ("Toggle do not disturb", "Toggled do not disturb.", ["omarchy", "toggle", "notification", "silencing"], False),
    "stay-awake": ("Keep the screen awake", "The screen will stay awake.", ["omarchy", "toggle", "idle", "stay-awake"], False),
    "allow-sleep": ("Let the screen sleep again", "The screen can sleep again.", ["omarchy", "toggle", "idle", "allow-idle"], False),
    "reminder": ("Remind you {v}", "I'll remind you {v}.", ["@alarm", "set", "{at}", "{message}"], False),
    "reminders-show": ("Say your reminders", "Here are your reminders.", ["@alarm", "list"], False),
    "workspace": ("Go to workspace {v}", "Went to workspace {v}.", ["hyprctl", "dispatch", 'hl.dsp.focus({{ workspace = "{v}" }})'], False),
    "window-monitor": ("Move {v}", "Moved {v}.", ["@window-monitor"], False),
    "keybindings": ("Show your keyboard shortcuts", "Here are your keyboard shortcuts.", ["omarchy", "menu", "keybindings"], False),
    "emoji": ("Open the emoji picker", "Here's the emoji picker.", ["omarchy", "menu", "emoji"], False),
    "clipboard": ("Open your clipboard history", "Here's your clipboard history.", ["omarchy", "menu", "clipboard"], False),
    "bluetooth-on": ("Turn Bluetooth on", "Bluetooth is on.", ["omarchy", "bluetooth", "power", "on"], False),
    "bluetooth-off": ("Turn Bluetooth off", "Bluetooth is off.", ["omarchy", "bluetooth", "power", "off"], False),
    "lock": ("Lock the screen", "Locking the screen.", ["omarchy", "system", "lock"], False),
    "logout": ("Log out", "Logging out.", ["omarchy", "system", "logout"], True),
    "reboot": ("Restart the computer", "Restarting the computer.", ["omarchy", "system", "reboot"], True),
    "shutdown": ("Shut down the computer", "Shutting down.", ["omarchy", "system", "shutdown"], True),
}

# First pattern that fits wins, so the narrow ones go first.
ACTION_RULES = [
    ("window-monitor", "@window-move"),
    ("record-stop", r"\bstop\b.*\brecord|\brecording\b.*\bstop|\bend\b.*\brecording"),
    ("record-start", r"\b(record|recording)\b.*\bscreen|\bscreen ?record|\bstart (a )?recording"),
    ("screenshot-area", r"\bscreen ?(shot|grab)\b.*\b(part|area|region|bit|piece|select)|\b(snip|snippet)\b"),
    ("screenshot", r"\bscreen ?(shot|grab|cap)\b|\bcapture (the|my) screen"),
    ("reminders-show", r"\b(show|list|what are|any)\b.*\breminders?\b"),
    ("reminder", r"\bremind me\b|\bset (a |an )?(reminder|timer)\b|\btimer\b"),
    ("theme-picker", r"\btheme (picker|switcher|menu|list)\b|\bpick a theme\b|\bshow (me )?(the )?themes\b"),
    ("theme-next", r"\b(next|another|different|new|random|change( the)?|switch( the)?) theme\b|\btheme\b.*\b(next|change)\b"),
    ("theme-set", r"\btheme\b"),
    ("bg-picker", r"\b(wallpaper|background) (picker|switcher|menu)\b|\bpick a (wallpaper|background)\b"),
    ("bg-next", r"\b(wallpaper|background)\b"),
    ("nightlight-off", r"\b(night ?light|night mode|blue light)\b.*\boff\b|\boff\b.*\b(night ?light|night mode)\b"),
    ("nightlight-on", r"\b(night ?light|night mode|blue light)\b.*\bon\b|\bon\b.*\b(night ?light|night mode)\b"),
    ("nightlight", r"\bnight ?light\b|\bnight mode\b|\bblue light\b|\bwarm(er)? screen\b"),
    ("mic-mute", r"\b(mic|microphone)\b"),
    ("volume-mute", r"\b(un)?mute\b|\bsilence (the )?(computer|sound|speakers)"),
    ("volume-up", r"\b(volume|sound|speakers?|computer)\b.*\b(up|louder|higher|raise)\b|\b(louder|turn it up)\b"),
    ("volume-down", r"\b(volume|sound|speakers?|computer)\b.*\b(down|quieter|lower|softer)\b|\b(quieter|turn it down)\b"),
    ("dnd", r"\bdo not disturb\b|\bdnd\b|\b(silence|mute|hide|pause) (my )?notifications\b|\bnotifications (off|on)\b"),
    ("allow-sleep", r"\b(let|allow)\b.*\b(sleep|idle|go to sleep)\b|\bstop keeping\b.*\bawake"),
    ("stay-awake", r"\b(stay|keep)\b.*\bawake\b|\bdon'?t (let it )?(sleep|lock)\b|\bcaffeine\b"),
    ("workspace", r"\b(workspace|desktop|space)\s+(number\s+)?(\d+|one|two|three|four|five|six|seven|eight|nine|ten)\b"),
    ("keybindings", r"\b(key ?bindings?|keyboard shortcuts?|shortcuts|hotkeys)\b"),
    ("emoji", r"\bemoji"),
    ("clipboard", r"\bclipboard\b"),
    ("bluetooth-off", r"\bbluetooth\b.*\boff\b|\b(turn|switch) off\b.*\bbluetooth\b"),
    ("bluetooth-on", r"\bbluetooth\b"),
    ("lock", r"\block\b.*\b(screen|computer|pc|it|up)\b|\block screen\b|^lock$"),
    ("logout", r"\blog ?(me )?out\b|\bsign ?(me )?out\b"),
    ("reboot", r"\b(restart|reboot)\b.*\b(computer|pc|machine|system)\b|^reboot\b"),
    ("shutdown", r"\b(shut ?down|power off|turn off)\b.*\b(computer|pc|machine|system)\b|^shut ?down\b"),
]

NUMBERS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
           "nine": 9, "ten": 10, "fifteen": 15, "twenty": 20, "thirty": 30, "forty": 40, "forty five": 45,
           "sixty": 60, "a": 1, "an": 1, "half an": 0.5, "half a": 0.5}


def themes():
    """Installed theme names as `omarchy theme set` takes them (lowercase, dashes)."""
    try:
        out = subprocess.run(["omarchy", "theme", "list"], capture_output=True, text=True, timeout=5).stdout
    except (OSError, subprocess.TimeoutExpired):
        return []
    return [re.sub(r"\s+", "-", n.strip().lower()) for n in out.splitlines() if n.strip()]


def find_theme(text, names=None):
    names = names if names is not None else themes()
    t = re.sub(r"\b(switch|change|set|make|use|put|the|my|to|theme|on|please|it|a|look|like)\b", " ", text.lower())
    t = _norm(t)
    if not t:
        return None
    hits = [n for n in names if _norm(n) == t] or [n for n in names if _norm(n) and _norm(n) in t]
    if hits:
        return max(hits, key=len)
    best = max(names, key=lambda n: difflib.SequenceMatcher(None, t, _norm(n)).ratio(), default=None)
    if best and difflib.SequenceMatcher(None, t, _norm(best)).ratio() >= 0.8:
        return best
    return None


def parse_reminder(text):
    """(minutes, message) from "remind me in 10 minutes to check the oven", or (None, None)."""
    t = text.lower()
    num = r"(\d+(?:\.\d+)?|half an?|an?|one|two|three|four|five|six|seven|eight|nine|ten|fifteen|twenty|thirty|forty five|forty|sixty)"
    m = re.search(num + r"\s*(minutes?|mins?|hours?|hrs?|h|m)\b", t)
    if not m:
        return None, None
    n = m.group(1)
    n = float(n) if re.match(r"\d", n) else NUMBERS.get(n, None)
    if n is None:
        return None, None
    minutes = int(round(n * (60 if m.group(2).startswith("h") else 1)))
    msg = (text[:m.start()] + " " + text[m.end():])
    msg = re.sub(r"\b(please|hey claude|remind me|set (a |an )?(reminder|timer)( for)?|in|to|that|about|after)\b",
                 " ", msg, flags=re.I)
    msg = " ".join(msg.split()).strip(" ,.?!")
    return minutes, (msg[:1].upper() + msg[1:]) if msg else "Reminder"


HOUR_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
              "ten": 10, "eleven": 11, "twelve": 12}
WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
CLOCK = re.compile(
    r"\b(?:(?P<day1>today|tonight|tomorrow|on (?:monday|tuesday|wednesday|thursday|friday|saturday|sunday))\s+)?"
    r"at\s+(?:(?P<noon>noon|midday|midnight)|(?P<h>\d{1,2}|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)"
    r"(?:[:.](?P<m>\d{2}))?(?:\s*(?P<ampm>a\.?m\.?|p\.?m\.?)|\s+o'?clock)?"
    r"(?:\s+in the (?P<part>morning|afternoon|evening)|\s+at night)?)"
    r"(?:\s+(?P<day2>today|tonight|tomorrow|on (?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)))?(?=\W|$)", re.I)


def parse_clock(text, now=None):
    """(epoch, message) from "remind me at 2pm to go outside with Ollie" ("at 9:30", "tomorrow at 8am", "at 7 on
    friday", "at noon"), or (None, None). A bare hour ("at 2") is the next 2:00 or 14:00 to come; a time that has
    gone by today is tomorrow."""
    now = dt.datetime.fromtimestamp(now or time.time())
    m = CLOCK.search(text)
    if not m:
        return None, None
    day = (m.group("day1") or m.group("day2") or "").lower()
    ampm = (m.group("ampm") or "").replace(".", "").lower()
    part = (m.group("part") or "").lower()
    if m.group("noon"):
        hour, minute, fixed = (0 if m.group("noon").lower() == "midnight" else 12), 0, True
    else:
        h = m.group("h").lower()
        hour = int(h) if h.isdigit() else HOUR_WORDS[h]
        minute = int(m.group("m") or 0)
        if hour > 23 or minute > 59 or (ampm and not 1 <= hour <= 12):
            return None, None
        fixed = bool(ampm or part or hour == 0 or hour > 12 or "at night" in m.group(0).lower())
        if ampm == "pm" or part in ("afternoon", "evening") or "at night" in m.group(0).lower() or day == "tonight":
            hour = hour % 12 + 12
            fixed = True
        elif ampm == "am" or part == "morning":
            hour = hour % 12
    base = now.date()
    if day == "tomorrow":
        base += dt.timedelta(days=1)
    elif day.startswith("on "):
        ahead = (WEEKDAYS.index(day[3:]) - base.weekday()) % 7
        base += dt.timedelta(days=ahead)
    when = dt.datetime.combine(base, dt.time(hour, minute))
    if not fixed and 1 <= hour <= 6:
        when += dt.timedelta(hours=12)          # "at 7 on friday" may be morning, but "at 3" is the afternoon
    elif not fixed and when <= now and hour < 12 and when + dt.timedelta(hours=12) > now:
        when += dt.timedelta(hours=12)          # "at 2" said at 12:47 is 2 pm
    if when <= now:
        when += dt.timedelta(days=7 if day.startswith("on ") else 1)
    msg = text[:m.start()] + " " + text[m.end():]
    msg = re.sub(r"\b(please|hey claude|remind me|set (a |an )?(reminder|alarm)( for)?|to|that|about)\b", " ", msg,
                 flags=re.I)
    msg = " ".join(msg.split()).strip(" ,.?!")
    return int(when.timestamp()), (msg[:1].upper() + msg[1:]) if msg else "Reminder"


def word_number(s):
    return int(s) if s.isdigit() else NUMBERS.get(s)


def find_action(text):
    """(action id, value) for what the text asks, or (None, None)."""
    t = text.lower().strip(" .?!")
    for action, rule in ACTION_RULES:
        if rule == "@window-move":
            if is_window_move(t):
                return action, window_move(t)
            continue
        m = re.search(rule, t)
        if not m:
            continue
        if action in ("theme-next", "theme-set"):
            name = find_theme(text)
            if name:
                return "theme-set", name
            return ("theme-next", None) if action == "theme-next" else ("theme-picker", None)
        if action == "reminder":
            at, msg = parse_clock(text)
            if at:
                return "reminder", {"at": at, "message": msg}
            minutes, msg = parse_reminder(text)
            return ("reminder", {"minutes": minutes, "message": msg}) if minutes else ("reminder", None)
        if action == "workspace":
            return "workspace", word_number(m.group(3))
        return action, None
    return None, None


def describe(minutes):
    if minutes % 60 == 0 and minutes >= 60:
        h = minutes // 60
        return f"{h} hour" + ("s" if h != 1 else "")
    return f"{minutes} minute" + ("s" if minutes != 1 else "")


def clock_words(ts):
    """'2 pm', 'tomorrow 9:30 am', 'Friday 7 pm'."""
    t = dt.datetime.fromtimestamp(ts)
    words = t.strftime("%-I:%M %p").lower().replace(":00 ", " ")
    days = (t.date() - dt.date.today()).days
    return ("tomorrow " if days == 1 else t.strftime("%A ") if days > 1 else "") + words


def check_action(action, value):
    """Rebuild a checked (action, value); raises ValueError with a plain reason."""
    if action not in ACTIONS:
        raise ValueError("that isn't a desktop job I know")
    if action == "theme-set":
        if str(value) not in themes():
            raise ValueError(f"there's no theme called {value}")
        return action, str(value)
    if action == "reminder":
        v = value if isinstance(value, dict) else {}
        message = " ".join(str(v.get("message") or "Reminder").split())[:120]
        if v.get("at") not in (None, ""):
            try:
                at = int(v.get("at"))
            except (TypeError, ValueError):
                raise ValueError("I didn't catch when") from None
            if not time.time() + 30 <= at <= time.time() + 7 * 24 * 3600:
                raise ValueError("reminders can be from now to a week ahead")
            return action, {"at": at, "message": message}
        try:
            minutes = int(v.get("minutes"))
        except (TypeError, ValueError):
            raise ValueError("I didn't catch how long to wait") from None
        if not 1 <= minutes <= 1440:
            raise ValueError("reminders can be 1 minute to 24 hours")
        return action, {"minutes": minutes, "message": message}
    if action == "window-monitor":
        v = value if isinstance(value, dict) else {}
        spec = check_monitor_spec(v.get("to"))
        app_id = v.get("app")
        if app_id in (None, ""):
            app_id = None
        else:
            app_command(str(app_id))  # raises if it isn't an installed app
            app_id = str(app_id)
        return action, {"to": spec, "app": app_id}
    if action == "workspace":
        try:
            n = int(value)
        except (TypeError, ValueError):
            raise ValueError("which workspace?") from None
        if not 1 <= n <= 10:
            raise ValueError("workspaces go from 1 to 10")
        return action, n
    return action, None


def action_label(action, value, done=False):
    """What the job card says (or, with done, what to say after it ran)."""
    text = ACTIONS[action][1 if done else 0]
    if action == "reminder":
        return text.format(v=describe(value["minutes"])) if done else \
            f"Remind you in {describe(value['minutes'])}: {value['message']}"
    if action == "window-monitor":
        who = app_name(value["app"]) if value.get("app") else "this window"
        return text.format(v=f"{who} to {spec_say(value['to'])}")
    if action in ("theme-set", "theme-next") and value:
        return text.format(v=value.replace("-", " ").title())
    return text.format(v=value)


def action_command(action, value):
    argv = ACTIONS[action][2]
    subs = {"v": str(value)}
    if action == "reminder":
        at = value.get("at") or int(time.time()) + 60 * value["minutes"]
        subs = {"at": str(at), "message": value["message"]}
    return [re.sub(r"\{(\w+)\}", lambda m: subs.get(m.group(1), m.group(0)), a).replace("{{", "{").replace("}}", "}")
            for a in argv]


def next_theme():
    names, cur = themes(), ""
    try:
        cur = subprocess.run(["omarchy", "theme", "current"], capture_output=True, text=True, timeout=5).stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        pass
    cur = re.sub(r"\s+", "-", cur.lower())
    if not names:
        return None
    return names[(names.index(cur) + 1) % len(names)] if cur in names else names[0]


if __name__ == "__main__":
    import sys
    what, text = sys.argv[1], " ".join(sys.argv[2:])
    print(json.dumps({"app": find_app, "file": find_file, "action": find_action}[what](text)))
