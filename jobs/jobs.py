"""Jobs the brain can do: load the job files, turn what <user> said into a job object, run a job.

One JSON file per job in this folder (id, label, phrases, match, needs_confirm, args, command,
message, speak). `brain ask` builds the job object (build()); the island shows it, asks Yes / No
when needs_confirm is true, and runs `brain job run <id> --args-json '<job object>'` (run()).

Safety: run() never trusts the command string inside the job object. It rebuilds the command from
the job file and checks every argument (a known project, an existing note under the brain's
folders, an action from the allowed list, one line of text). No job deletes, sends or spends.

  python3 -I jobs/jobs.py list
  python3 -I jobs/jobs.py build "<what <user> said>" [<job id>]   # prints the job object
  python3 -I jobs/jobs.py run <id> --args-json '<job object>'
"""
import difflib
import glob
import json
import os
import re
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import desktop  # noqa: E402
import details  # noqa: E402
import sendfiles  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
HOME = os.path.expanduser("~")
PROJECTS = os.path.join(HOME, "projects", "Projects")
PM_PROJECTS = os.path.join(HOME, "projects", "project-manager", "projects")
# Where a note opened by open-note may live (the brain's four collections).
NOTE_ROOTS = [os.path.join(HOME, p) for p in
              ("OMARCHY-BRAIN", "user-labs-business", "projects", ".local/share/second-brain/chats")]
WAKE = re.compile(r"^\s*(hey|hi|ok|okay)?\s*claude\b[\s,.:!-]*", re.I)


def load():
    jobs = {}
    for path in sorted(glob.glob(os.path.join(HERE, "*.json"))):
        with open(path) as f:
            job = json.load(f)
        jobs[job["id"]] = job
    return jobs


def clean_text(text):
    return WAKE.sub("", " ".join(str(text).split())).strip(" .?!")


# Words that mean the TV or the music job, never a desktop action ("mute the tv", "next song").
NOT_DESKTOP = re.compile(r"\b(tv|television|telly|songs?|tracks?|music|spotify)\b", re.I)
# Jobs whose own rule beats the decider's "question" or "unsure" (their rules are tight commands, and a
# decider trained before they existed doesn't know their labels).
DESKTOP_JOBS = ("desktop", "open-app", "open-file", "send-file")
# Jobs that sound like questions ("what moved today?"): their rule beats the decider's "question" too, and a
# how-question doesn't undo them (they are new to the decider; add them to the next the local decider round).
DAY_JOBS = ("what-changed", "goodnight")
# Jobs that hand <user>'s words to agent-os (jobs/bin/agent-os-start). Their rules are tight (anchored at the start of
# the sentence), so a fitting rule beats any decider label until the local decider knows them; a line holding two asks never fits.
AGENT_JOBS = ("remember-fix", "start-job")
TWO_ASKS = re.compile(r"\b(and|then|also|plus)\s+(then\s+|also\s+)?(start|open|remind|remember|send|play|pause|fix|do|"
                      r"sort|take|turn|move|lock|check|tell|show|close|put|make|add|write)\b|[.?!;]\s+\w", re.I)


def two_asks(text):
    return bool(TWO_ASKS.search(clean_text(text)))
OVERNIGHT_WORDS = re.compile(r"\b(overnight|last night|while i (slept|was asleep)|since (bed|i went to bed))\b", re.I)


def day_when(text):
    t = clean_text(text)
    if OVERNIGHT_WORDS.search(t):
        return "overnight"
    return "yesterday" if re.search(r"\byesterday\b", t, re.I) else "today"
# "How do I turn on the night light" is a question about it, not the job ("can you ..." still is a job).
HOW_QUESTION = re.compile(r"^(how|why|what|where|when|who|which|did|does|do i|is|was|should|where'?s|what'?s|how'?s)\b"
                          r"(?!.*\b(remind|reminders?)\b)", re.I)


def is_how_question(text):
    return bool(HOW_QUESTION.search(clean_text(text)))


def route_label(rule, label, text):
    """The decider's label, corrected only where a rule is sure and the decider's job can't do it. A decider
    trained before the send and screen-move jobs existed calls "send it to the laptop" an open-file and "move
    chrome to my other screen" an open-app. A desktop label stays unless no desktop action fits the words, and a
    send-file label gives way to another job's rule (the send rule is strict, so when it doesn't fit, "remind
    me to put the charger on the laptop" is a reminder, not a send)."""
    t = clean_text(text).lower()
    if rule == "send-file":
        if label in ("job:open-file", "job:open-app", "job:open-note"):
            return "job:send-file"
        if label == "job:desktop" and not desktop.find_action(t)[0]:
            return "job:send-file"
    elif label == "job:send-file" and rule:
        return f"job:{rule}"
    if rule == "desktop" and label in ("job:open-file", "job:open-app", "job:open-note") and desktop.is_window_move(t):
        return "job:desktop"
    return label


def match_rule(text, jobs=None):
    """The simple rule: the first job (lowest `order`, default 50) whose `match` regex fits.
    `@desktop.find_action` means: desktop.find_action finds an action; `@sendfiles.is_send_request` means that
    function says yes. Used when the decider is unsure, and to correct it (route_label)."""
    text = clean_text(text).lower()
    for job in sorted((jobs or load()).values(), key=lambda j: j.get("order", 50)):
        m = job.get("match")
        if m == "@desktop.find_action":
            if desktop.is_window_move(text):   # "move spotify to the left screen" is a window move, not music
                return job["id"]
            if not NOT_DESKTOP.search(text) and desktop.find_action(text)[0]:
                return job["id"]
        elif m == "@sendfiles.is_send_request":
            if sendfiles.is_send_request(text):
                return job["id"]
        elif m and re.search(m, text, re.I):
            if job["id"] in AGENT_JOBS and two_asks(text):
                continue
            return job["id"]
    return None


# ---------- arguments ----------

def _norm(s):
    return re.sub(r"[^a-z0-9]", "", s.lower())


def project_names():
    names = set()
    for d in os.listdir(PROJECTS) if os.path.isdir(PROJECTS) else []:
        if os.path.isdir(os.path.join(PROJECTS, d)) and not d.startswith("."):
            names.add(d)
    for f in glob.glob(os.path.join(PM_PROJECTS, "*.md")):
        stem = os.path.basename(f)[:-3]
        if stem not in ("README", "REGISTRY"):
            names.add(stem)
    return sorted(names)


def pretty(repo):
    if repo == "desk":
        return "the whole desk"
    return " ".join(w if w.isupper() or any(c.isupper() for c in w[1:]) else w.capitalize()
                    for w in re.split(r"[-_ ]+", repo))


def find_project(text, local_writer=None):
    """Which project does the text name? Exact (spaces and dashes ignored) first, then close
    spelling (speech to text slips), then, only if both fail, the local writer picks from the list."""
    t = _norm(text)
    if re.search(r"\b(whole )?desk\b", text, re.I):
        return "desk"
    names = project_names()
    hits = [n for n in names if _norm(n) and _norm(n) in t]
    if hits:
        return max(hits, key=lambda n: len(_norm(n)))
    words = re.findall(r"[a-z0-9]+", text.lower())
    grams = {"".join(words[i:i + k]) for k in (1, 2, 3) for i in range(len(words) - k + 1)}
    best, score = None, 0.0
    for n in names:
        for g in grams:
            r = difflib.SequenceMatcher(None, _norm(n), g).ratio()
            if r > score:
                best, score = n, r
    if score >= 0.82:
        return best
    if local_writer:
        try:
            pick = local_writer("Which one of these projects does the request mean? Reply with the exact name "
                                "from the list, or none.\nProjects: " + ", ".join(names) + "\nRequest: " + text)
        except Exception:  # noqa: BLE001
            pick = ""
        pick = (pick or "").strip().strip(".\"'` ")
        for n in names:
            if _norm(n) == _norm(pick):
                return n
    return None


def music_action(text):
    t = text.lower()
    if re.search(r"\b(next|skip)\b", t):
        return "Next"
    if re.search(r"\b(previous|go back|last (song|track)|back one)\b", t):
        return "Previous"
    if re.search(r"\b(pause|stop)\b", t):
        return "Pause"
    if re.search(r"\b(resume|unpause|play)\b", t):
        return "Play"
    return "PlayPause"


def tv_action(text):
    t = text.lower()
    if re.search(r"\bun-?mute|\bmute|\bsilence|\bquiet\b(?! ?down)", t):
        return "mute"
    if re.search(r"\b(up|louder|raise|increase|higher)\b", t):
        return "up"
    if re.search(r"\b(down|quieter|lower|softer|decrease|turn it down)\b", t):
        return "down"
    return None


START_JOB = re.compile(r"^(please |can you |could you )?(start|kick off|begin|open) (a |an )?(new )?(job|run|build) "
                       r"(on|for)\b\s*", re.I)
HOWS = ("voice", "typed")


def job_project(text):
    """"start a job on <project>: <what>" -> (project, what). The project is the first 1-4 words after "on"/"for"
    (or everything before a colon) that best fit a known project name; (None, "") when none does."""
    rest = START_JOB.sub("", clean_text(text), count=1).strip()
    if ":" in rest:
        head, what = rest.split(":", 1)
        repo = find_project(head)
        return (repo, what.strip()) if repo and repo != "desk" else (None, "")
    words = rest.split()
    best, best_k, best_score = None, 0, 0.0
    for k in range(1, min(4, len(words)) + 1):
        cand = " ".join(words[:k])
        repo = find_project(cand)
        if not repo or repo == "desk":
            continue
        score = difflib.SequenceMatcher(None, _norm(repo), _norm(cand)).ratio()
        if score >= 0.82 and score >= best_score:
            best, best_k, best_score = repo, k, score
    return (best, " ".join(words[best_k:]).strip(" ,-")) if best else (None, "")


def one_line(text):
    """The words handed to agent-os: one line (a line break is refused, not joined), no control characters, 1-500
    characters, not starting with '-'. Other runs of spaces are collapsed."""
    t = str(text or "")
    if re.search(r"[\x00-\x08\x0a-\x1f\x7f]", t):
        raise ValueError("the words weren't one plain line")
    t = " ".join(t.split())
    if not t or len(t) > 500 or t.startswith("-"):
        raise ValueError("the words didn't fit on one short line")
    return t


def remember_text(text):
    t = clean_text(text)
    t = re.sub(r"^(please\s+)?(remember|make a note|note down|write down|jot down)\b\s*(that|this|to|:)?\s*",
               "", t, flags=re.I)
    return t.strip()


def note_topic(text):
    t = clean_text(text)
    t = re.sub(r"^(please\s+)?(open|show( me)?|pull up|bring up)\s+(up\s+)?((my|the|a)\s+)?"
               r"((notes?|file|doc|readme)\s+)?((on|about|for|of)\s+)?", "", t, flags=re.I)
    return t.strip() or clean_text(text)


NOTE_WORDS = re.compile(r"\b(notes?|readme|bible|guide|docs?|plan)\b", re.I)
FILE_WORDS = re.compile(r"\b(folder|directory|file|picture|photo|image|video|pdf|spreadsheet|png|jpe?g|mp4|docx|"
                        r"downloads?|documents|screenshots?)\b", re.I)


def resolve_open(job_id, text, search=None):
    """"Open X": an app, a file or folder, or a note? Tries them in the order the words suggest
    (file words: file first; note words: note first; else app first). Returns
    (job id, args, label, answer, sources) or None."""
    t = clean_text(text)
    order = ["open-app", "open-file", "open-note"]
    if FILE_WORDS.search(t) or job_id == "open-file":
        order = ["open-file", "open-app", "open-note"]
    if NOTE_WORDS.search(t) and not FILE_WORDS.search(t):
        order = ["open-note", "open-file", "open-app"]
    if desktop.known_folder(t):
        order.insert(0, "open-file")
    for kind in order:
        if kind == "open-app":
            app_id, name, _ = desktop.find_app(t)
            if app_id:
                return "open-app", {"app": app_id, "name": name}, f"Open {name}", f"Opening {name}.", []
        elif kind == "open-file":
            # Without file words it's an app that isn't installed, so only a project or known folder counts
            # (a loose name search opened window-chrome.ts for "open chrome").
            path, what, _ = desktop.find_file(t, [os.path.join(PROJECTS, p) for p in project_names()],
                                              min_score=0.6 if order[0] == "open-file" else 1.0)
            if path:
                name = os.path.basename(path) or path
                return ("open-file", {"path": path, "name": name}, f"Open {name}",
                        f"Opening the {what} {name}.", [])
        elif search and (order[0] != "open-app" or NOTE_WORDS.search(t)):
            topic = note_topic(t)
            hits = search(topic)
            if hits:
                top = hits[0]
                return ("open-note", {"path": top["path"], "title": top["title"]}, f"Open {top['title']}",
                        f"Opening your note {top['title']}.", hits[:3])
    return None


# ---------- building the job object ----------

def _cmd_string(job, args):
    return " ".join(_fill(job["command"], {"monitor": "", **args}))


def _fill(argv, args):
    subs = {"jobs": HERE, "home": HOME,
            **{k: v if isinstance(v, str) else json.dumps(v) for k, v in args.items()}}
    return [re.sub(r"\{(\w+)\}", lambda m: subs.get(m.group(1), m.group(0)), a) for a in argv]


def _build_window_move(job, text, value):
    """The card for "move this window to my other screen". The window is picked when it runs, not now."""
    plain = lambda msg: {"kind": "answer", "answer": msg, "sources": [], "job": None}  # noqa: E731
    spec, app_id, said = value.get("to"), value.get("app"), value.get("said")
    if said and not app_id:
        return plain(desktop.NOT_AN_APP if value.get("not_app") else f"I couldn't find an app called {said}.")
    if not spec:
        return plain("Which screen? Say the left screen or the right screen.")
    try:
        spec = desktop.check_monitor_spec(spec)
    except ValueError as why:
        return plain(str(why)[:1].upper() + str(why)[1:].rstrip(".") + ".")
    if len(desktop.monitors()) < 2:
        return plain("You only have one screen right now.")
    if app_id and not desktop.app_windows(app_id):
        # Not open yet: open it, then move it.
        name = desktop.app_name(app_id)
        args = {"app": app_id, "name": name, "monitor": spec}
        label = f"Open {name} on {desktop.spec_say(spec)}"
        obj = {"id": "open-app", "label": label, "needs_confirm": False,
               "command": _cmd_string(load()["open-app"], args), "args": args}
        return {"kind": "job", "answer": f"{name} isn't open yet, so I'll open it there.", "sources": [], "job": obj}
    args = {"action": "window-monitor", "value": {"to": spec, "app": app_id}}
    label = desktop.action_label("window-monitor", args["value"])
    obj = {"id": "desktop", "label": label, "needs_confirm": False,
           "command": _cmd_string(job, args), "args": args}
    return {"kind": "job", "answer": label + ".", "sources": [], "job": obj}


def _desktop_job(job, action, value):
    args = {"action": action, "value": value}
    label = desktop.action_label(action, value)
    obj = {"id": "desktop", "label": label, "needs_confirm": desktop.ACTIONS[action][3],
           "command": _cmd_string(job, args), "args": args}
    return {"kind": "job", "answer": label + ".", "sources": [], "job": obj}


MUSIC_WORDS = re.compile(r"\b(play|pause|resume|unpause|stop|next|skip|previous|back)\b", re.I)


def build_with_details(job_id, text, search=None, local_writer=None, fill=None, how="typed"):
    """build(), and when its word rules come up empty (no job) or unsure (an "open" that fell through to a note,
    music with no play/pause/skip word), the local writer's form for that job (details.py), turned back into a
    plain command and built again, so every value is found and checked as usual. Adds "details": "rules",
    "local" (the writer's form made the job) or "none" (it didn't help), and "details_ms"."""
    t0 = time.monotonic()
    first = build(job_id, text, search, local_writer, how=how)
    got = (first.get("job") or {}).get("id")
    unsure = (job_id in ("open-app", "open-file") and got == "open-note") or \
        (job_id == "music" and got and not MUSIC_WORDS.search(text))
    if (got and not unsure) or job_id not in details.JOBS or not details.on():
        return dict(first, details="rules")
    t = clean_text(text)
    f = (fill or details.fill)(job_id, t, project_names() if job_id == "start-claude" else ())
    out = None
    if f and job_id == "desktop":
        checked = details.desktop_args(f)
        if checked and checked[0] == "window-monitor":
            out = _build_window_move(load()["desktop"], t, checked[1])
        elif checked:
            out = _desktop_job(load()["desktop"], *checked)
    elif f and details.as_text(job_id, f):
        out = build(job_id, details.as_text(job_id, f), search, local_writer)
    ms = int((time.monotonic() - t0) * 1000)
    if out and out.get("kind") == "job" and (out["job"]["id"] != "open-note" or not unsure):
        return dict(out, details="local", details_ms=ms, form=f)
    return dict(first, details="none", details_ms=ms, form=f)


def build(job_id, text, search=None, local_writer=None, how="typed"):
    """Turn what <user> said into {kind, answer, sources, job}. `search(topic)` returns hits
    ([{path, title, snippet}]) for open-note. Returns kind "answer" (a polite "I can't") when an
    argument is missing, so the island never runs a half-filled job. `how` (voice or typed) is how the words came,
    for the agent-os jobs."""
    jobs = load()
    job = jobs.get(job_id)
    if not job:
        return {"kind": "answer", "answer": "I don't know how to do that yet.", "sources": [], "job": None}
    sources, args = [], {}
    if job_id in ("open-app", "open-file") or (job_id == "open-note" and not NOTE_WORDS.search(text)):
        picked = resolve_open(job_id, text, search)
        if picked is None:
            return {"kind": "answer", "answer": f"I couldn't find {desktop.app_topic(clean_text(text)) or 'that'} "
                    "as an app, a file or a note.", "sources": [], "job": None}
        job_id, args, label, answer, sources = picked
        job = jobs[job_id]
        spec = desktop.monitor_spec(clean_text(text)) if job_id == "open-app" else None
        if spec:
            try:
                args["monitor"] = desktop.check_monitor_spec(spec)
            except ValueError as why:
                return {"kind": "answer", "answer": str(why)[:1].upper() + str(why)[1:].rstrip(".") + ".",
                        "sources": [], "job": None}
            label += " on " + desktop.spec_say(args["monitor"])
            answer = f"Opening {args['name']} on {desktop.spec_say(args['monitor'])}."
    elif job_id == "desktop":
        t = clean_text(text)
        action, value = desktop.find_action(t)
        if not action:
            return {"kind": "answer", "answer": "I don't know how to do that on the desktop yet.",
                    "sources": [], "job": None}
        if action == "reminder" and not value:
            return {"kind": "answer", "answer": "How long from now? Say, remind me in 10 minutes to stretch.",
                    "sources": [], "job": None}
        if action == "workspace" and not value:
            return {"kind": "answer", "answer": "Which workspace, 1 to 10?", "sources": [], "job": None}
        if action == "window-monitor":
            return _build_window_move(job, t, value)
        return _desktop_job(job, action, value)
    elif job_id == "send-file":
        picked = sendfiles.plan(clean_text(text), find_project=find_project, projects_root=PROJECTS,
                                project_dirs=[os.path.join(PROJECTS, p) for p in project_names()])
        if "paths" not in picked:
            return {"kind": "answer", "answer": picked["answer"], "sources": [], "job": None}
        args = {"device": picked["device"], "paths": picked["paths"], "name": picked["name"]}
        label, answer = picked["label"], picked["answer"]
    elif job_id == "open-note":
        topic = note_topic(text)
        hits = search(topic) if search else []
        if not hits:
            return {"kind": "answer", "answer": f"I couldn't find a note about {topic}.", "sources": [], "job": None}
        top = hits[0]
        args = {"path": top["path"], "title": top["title"]}
        sources = hits[:3]
        answer = f"Opening your note {top['title']}."
        label = f"Open {top['title']}"
    elif job_id == "start-claude":
        repo = find_project(text, local_writer)
        if not repo:
            return {"kind": "answer", "answer": "Which project? I didn't catch a project name I know.",
                    "sources": [], "job": None}
        args = {"project": repo, "name": pretty(repo)}
        if repo == "desk":
            label = "Start the whole-desk PM"
        else:
            label = f"Start a Claude on {pretty(repo)}"
        answer = f"This opens the {pretty(repo)} PM in agent."
    elif job_id == "music":
        args = {"action": music_action(text)}
        label = {"Next": "Next song", "Previous": "Previous song", "Pause": "Pause the music",
                 "Play": "Play the music", "PlayPause": "Play or pause the music"}[args["action"]]
        answer = label + "."
    elif job_id == "tv":
        action = tv_action(text)
        if not action:
            return {"kind": "answer", "answer": "I can only turn the TV up, down, or mute it.",
                    "sources": [], "job": None}
        args = {"action": action}
        label = {"up": "Turn the TV up", "down": "Turn the TV down", "mute": "Mute the TV"}[action]
        answer = label + "."
    elif job_id == "remember":
        what = remember_text(text)
        if not what:
            return {"kind": "answer", "answer": "What should I remember?", "sources": [], "job": None}
        args = {"text": what}
        label = f"Remember: {what[:80]}"
        answer = "I'll add it to your remembered list."
    elif job_id in AGENT_JOBS:
        try:
            words = one_line(clean_text(text))
        except ValueError:
            return {"kind": "answer", "answer": "That was too long for one job. Say it in one short sentence.",
                    "sources": [], "job": None}
        args = {"text": words, "how": how if how in HOWS else "typed"}
        if job_id == "start-job":
            repo, what = job_project(text)
            if not repo:
                return {"kind": "answer", "answer": "Which project? I didn't catch a project name I know.",
                        "sources": [], "job": None}
            if not what:
                return {"kind": "answer", "answer": f"What should the job on {pretty(repo)} do? Say, start a job on "
                        f"{pretty(repo)}, then what to do.", "sources": [], "job": None}
            args = {"project": repo, "name": pretty(repo), **args}
            label = f"Start a job on {pretty(repo)}"
        else:
            label = job["label"]
        answer = "This hands it to agent-os. It will wait for your go before anything is built."
    elif job_id == "what-changed":
        args = {"when": day_when(text)}
        label = {"today": "What moved today", "yesterday": "What moved yesterday",
                 "overnight": "What happened overnight"}[args["when"]]
        answer = "Checking."
    elif job_id == "goodnight":
        label = job["label"]
        answer = "I'll ask what may run tonight, then lock the screen and turn it off."
    else:  # whats-waiting
        label = job["label"]
        answer = "Checking who needs you."
    obj = {"id": job_id, "label": label, "needs_confirm": bool(job.get("needs_confirm")),
           "command": _cmd_string(job, args), "args": args}
    if job.get("speak"):
        obj["speak"] = True
    return {"kind": "job", "answer": answer, "sources": sources, "job": obj}


# ---------- running ----------

def _check(job_id, args):
    """Rebuild and check the arguments; raises ValueError with a plain reason."""
    a = dict(args or {})
    if job_id == "open-note":
        path = os.path.realpath(os.path.expanduser(str(a.get("path", ""))))
        if not os.path.isfile(path) or not any(path.startswith(r + os.sep) for r in NOTE_ROOTS):
            raise ValueError("that note isn't in your brain's folders")
        return {"path": path, "title": str(a.get("title") or os.path.basename(path))}
    if job_id == "start-claude":
        repo = str(a.get("project", ""))
        if repo != "desk" and repo not in project_names():
            raise ValueError(f"I don't know a project called {repo or 'that'}")
        return {"project": repo, "name": pretty(repo)}
    if job_id == "open-app":
        app_id = str(a.get("app", ""))
        desktop.app_command(app_id)  # raises if it isn't installed
        monitor = a.get("monitor")
        if monitor not in (None, ""):
            monitor = desktop.check_monitor_spec(monitor)
        return {"app": app_id, "name": str(a.get("name") or app_id), "monitor": monitor or ""}
    if job_id == "send-file":
        device, paths, _ = sendfiles.check_send(a.get("device"), a.get("paths"))
        name = re.sub(r"[^\w .&'-]", "", str(a.get("name") or "Files"))[:40].strip() or "Files"
        return {"device": device, "paths": paths, "name": name}
    if job_id == "open-file":
        path = desktop.allowed_path(a.get("path", ""))
        if not path:
            raise ValueError("that isn't a file or folder I'm allowed to open")
        return {"path": path, "name": os.path.basename(path) or path}
    if job_id == "desktop":
        action, value = desktop.check_action(str(a.get("action", "")), a.get("value"))
        return {"action": action, "value": value}
    if job_id in ("music", "tv"):
        allowed = load()[job_id]["args"]["action"]
        if a.get("action") not in allowed:
            raise ValueError("that isn't something I can do")
        return {"action": a["action"]}
    if job_id in AGENT_JOBS:
        out = {"text": one_line(a.get("text")), "how": a.get("how") if a.get("how") in HOWS else "typed"}
        if job_id == "start-job":
            repo = str(a.get("project", ""))
            if repo == "desk" or repo not in project_names():
                raise ValueError(f"I don't know a project called {repo or 'that'}")
            out = {"project": repo, "name": pretty(repo), **out}
        return out
    if job_id == "what-changed":
        if a.get("when") not in load()[job_id]["args"]["when"]:
            raise ValueError("I can only say today, yesterday or overnight")
        return {"when": a["when"]}
    if job_id == "remember":
        text = " ".join(str(a.get("text", "")).split())[:500]
        if not text:
            raise ValueError("there was nothing to remember")
        return {"text": text}
    return {}


def run(job_id, job_obj):
    jobs = load()
    job = jobs.get(job_id)
    if not job:
        print(json.dumps({"message": f"There is no job called {job_id}."}))
        return 2
    try:
        args = _check(job_id, (job_obj or {}).get("args"))
    except ValueError as why:
        print(json.dumps({"message": f"I didn't do it: {why}."}))
        return 2
    argv = _fill(job["command"], args)
    if job_id == "start-claude" and args["project"] == "desk":
        argv = [argv[0], "open", "--desk", "--launch"]
    if job_id == "open-note":   # don't wait for the viewer app
        subprocess.Popen(argv, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        print(json.dumps({"message": job["message"].format(**args)}))
        return 0
    try:
        out = subprocess.run(argv, capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired) as why:
        print(json.dumps({"message": f"That didn't work: {why}."}))
        return 1
    message, speak = None, bool(job.get("speak"))
    for line in reversed(out.stdout.splitlines()):
        try:
            obj = json.loads(line)
        except ValueError:
            continue
        if isinstance(obj, dict) and obj.get("message"):
            message, speak = obj["message"], bool(obj.get("speak", speak))
            break
    if message is None:
        if out.returncode == 0:
            message = job.get("message", "Done.").format(**args)
        else:
            err = (out.stderr or out.stdout).strip().splitlines()
            message = "That didn't work" + (f": {err[-1][:160]}" if err else ".")
    print(json.dumps({"message": message, "speak": speak} if speak else {"message": message}))
    return out.returncode


def main(argv):
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__.split("\n\n")[-1])
        return 0
    if argv[0] == "list":
        for j in load().values():
            c = j.get("needs_confirm")
            c = "sometimes" if isinstance(c, str) else "asks first" if c else "no confirm"
            print(f"{j['id']:14} {c:11} e.g. \"{j['phrases'][0]}\"")
        return 0
    if argv[0] == "build":
        text = argv[1]
        jid = argv[2] if len(argv) > 2 else match_rule(text)
        print(json.dumps(build(jid, text) if jid else None))
        return 0
    if argv[0] == "run" and len(argv) >= 2:
        obj = {}
        if "--args-json" in argv:
            try:
                obj = json.loads(argv[argv.index("--args-json") + 1])
            except (ValueError, IndexError):
                print(json.dumps({"message": "The job's details didn't make sense, so I did nothing."}))
                return 2
        return run(argv[1], obj if isinstance(obj, dict) else {})
    print("jobs: unknown command", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
