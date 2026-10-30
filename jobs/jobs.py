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
import servers  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
HOME = os.path.expanduser("~")
PROJECTS = os.path.join(HOME, "projects", "Projects")
PM_PROJECTS = os.path.join(HOME, "brain", "projects")
# Where a note opened by open-note may live (the brain, and the code projects' guides).
NOTE_ROOTS = [os.path.join(HOME, p) for p in ("brain", "projects")]
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
DESKTOP_JOBS = ("desktop", "open-app", "open-file", "send-file", "team-screen", "servers")   # team-screen: agent-os, 2026-10-19
# Jobs that sound like questions ("what moved today?"): their rule beats the decider's "question" too, and a
# how-question doesn't undo them (they are new to the decider; add them to the next the local decider round).
DAY_JOBS = ("what-changed", "goodnight")
# Jobs that hand <user>'s words to agent-os (jobs/bin/agent-os-start: `boss prepare`). Their rules are tight (anchored at the start of
# the sentence), so a fitting rule beats any decider label until the local decider knows them; a line holding two asks never fits.
AGENT_JOBS = ("remember-fix", "start-job")
TWO_ASKS = re.compile(r"\b(and|then|also|plus)\s+(then\s+|also\s+)?(start|open|remind|remember|send|play|pause|fix|do|"
                      r"sort|take|turn|move|lock|check|tell|show|close|put|make|add|write)\b|[.?!;]\s+\w", re.I)


def two_asks(text, job_id="remember-fix"):
    """Two asks in one line ("fix the thing on my remember list and then open Spotify")? Only for remember-fix:
    start-job's task after the project is free text handed to agent-os, so "fix the bug. Then add tests" is one job."""
    return job_id != "start-job" and bool(TWO_ASKS.search(clean_text(text)))
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


def _send_rule_label(label, t):
    """The send rule fits: the decider's open-file/app/note, or a desktop label with no action, becomes send-file."""
    if label in ("job:open-file", "job:open-app", "job:open-note"):
        return "job:send-file"
    if label == "job:desktop" and not desktop.find_action(t)[0]:
        return "job:send-file"
    return None


def route_label(rule, label, text):
    """The decider's label, corrected only where a rule is sure and the decider's job can't do it. A decider
    trained before the send and screen-move jobs existed calls "send it to the laptop" an open-file and "move
    chrome to my other screen" an open-app. A desktop label stays unless no desktop action fits the words, and a
    send-file label gives way to another job's rule (the send rule is strict, so when it doesn't fit, "remind
    me to put the charger on the laptop" is a reminder, not a send)."""
    t = clean_text(text).lower()
    if rule == "servers" and label.startswith("job:") and label != "job:servers":
        return "job:servers"   # "start the llc namer" is not an open-app: the name is one of the hosted servers
    if rule == "send-file":
        fixed = _send_rule_label(label, t)
        if fixed:
            return fixed
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
        if _rule_fits(job, text):
            return job["id"]
    return None


def _regex_rule_fits(job, text):
    m = job.get("match")
    if not (m and re.search(m, text, re.I)):
        return False
    if job["id"] in AGENT_JOBS and (two_asks(text, job["id"]) or is_how_question(text)):
        return False
    if job["id"] == "start-job" and not all(job_project(text)):
        return False   # "start a run on tuesday" names no project: not this job
    return True


def _desktop_rule_fits(text):
    # "move spotify to the left screen" is a window move, not music
    return bool(desktop.is_window_move(text) or (not NOT_DESKTOP.search(text) and desktop.find_action(text)[0]))


CODE_RULES = {"@desktop.find_action": _desktop_rule_fits,
              "@servers.is_request": lambda text: bool(servers.is_request(text)),
              "@sendfiles.is_send_request": lambda text: bool(sendfiles.is_send_request(text))}


def _rule_fits(job, text):
    """Does this one job's `match` (a regex or an `@module.function` check) fit the text?"""
    check = CODE_RULES.get(job.get("match"))
    return check(text) if check else _regex_rule_fits(job, text)


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


def _closest_project(text, names):
    """The project whose name is closest to something said (speech to text slips), if close enough."""
    words = re.findall(r"[a-z0-9]+", text.lower())
    grams = {"".join(words[i:i + k]) for k in (1, 2, 3) for i in range(len(words) - k + 1)}
    best, score = None, 0.0
    for n in names:
        for g in grams:
            r = difflib.SequenceMatcher(None, _norm(n), g).ratio()
            if r > score:
                best, score = n, r
    return best if score >= 0.82 else None


def _writer_picks_project(text, names, local_writer):
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
    close = _closest_project(text, names)
    if close:
        return close
    if local_writer:
        return _writer_picks_project(text, names, local_writer)
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
    repo, tail = _lead_project(rest.split())
    return (repo, tail.strip(" ,-")) if repo else (None, "")


def _lead_project(words):
    """The 1-4 words at the start that best fit a known project: (project, the words after them) or (None, "")."""
    best, best_k, best_score = None, 0, 0.0
    for k in range(1, min(4, len(words)) + 1):
        cand = " ".join(words[:k])
        repo = find_project(cand)
        if not repo or repo == "desk":
            continue
        score = difflib.SequenceMatcher(None, _norm(repo), _norm(cand)).ratio()
        if score >= 0.82 and score >= best_score:
            best, best_k, best_score = repo, k, score
    return (best, " ".join(words[best_k:])) if best else (None, "")


TEAM_LEAD = re.compile(r"\b(on|for)\b\s*", re.I)
TEAM_SPLIT = re.compile(r"\s*[,;\u2013\u2014]+\s*|\s+-+\s+")   # a comma, dash or em dash right after the name
TEAM_CONNECT = re.compile(r"^(?:[,;\-\u2013\u2014]+\s*|(?:and|then|to)\b[,\s]*)+", re.I)
TEAM_FILLER = r"(?:please|pls|thanks|thank you|now|like now|right now|too|also|as well)"
TEAM_TRAIL = re.compile(r"(?:^|[\s,;\-]+)" + TEAM_FILLER + r"(?:[\s,;\-]+" + TEAM_FILLER + r")*$", re.I)
# A task never starts with these: chat ("so I can watch", "you know", "I'll tell it") or filler ("ok", "quick").
TEAM_NOT_FIRST = re.compile(r"^(?:so|i|you|we|it|ok|okay|right|cool|quick|too|yes|yeah|sure|thanks|please)\b", re.I)
# After a full stop the task must open with a work verb: another request ("open spotify", "remember ...") or a question
# or chat ("what time is it", "sounds good") is not a task. After a colon, comma or dash the rules stay as they were.
TEAM_DO = re.compile(r"^(?:fix|tidy|clean|add|check|update|write|refactor|build|make|remove|delete|rename|"
                     r"review|test|improve|change|look|find|set up|create|implement|finish|investigate|handle|sort|"
                     r"document|debug|migrate|upgrade|speed|simplify|rewrite|redo|repair|patch|wire|hook|merge|"
                     r"split|move|polish|trim|shorten|tune|audit|compare|summarize|summarise|list|draft|plan|run|"
                     r"go through|work on|take care of|get rid of|clear out|clean up|tidy up)\b", re.I)
TEAM_SENTENCE = re.compile(r"[.!?]+\s+")   # a full stop, question or exclamation mark between the words
TEAM_DESK = re.compile(r"^(?:the )?(?:whole )?desk\b\s*", re.I)


def team_task(text):
    """"start a claude on <project>: <task>" -> (project, task); (None, "") when the words hold no task. The project
    can be "desk" (its task is then not used: the whole desk has no team job). A task is what follows the project
    name after a colon, a full stop (a spoken pause), a comma, a dash or an em dash, or "to" / "and" / "then" ("on example to tidy the logs").
    Plain words after the name ("example's logs", "example-board like now", "so I can watch it", "that's all") are not a
    task, nor is a second project name ("example and example-rpg"): a missed task only gives the old PM chat, a
    guessed one would prepare a job <user> never asked for. "to check in" is a task on purpose: "to" is how people
    say it, and the card shows the task before Yes, which only prepares."""
    t = clean_text(text)
    m = TEAM_LEAD.search(t)
    if not m:
        return None, ""
    parts = _team_parts(t[m.end():])
    if parts is None:
        return None, ""
    repo, tail, via_sep = parts
    task = TEAM_TRAIL.sub("", tail.strip()).strip(" ,;")
    if via_sep and len(task.split()) < 2:
        return None, ""
    if not repo or not task or task[0] in "'\"\u2019" or TEAM_NOT_FIRST.match(task) or not _is_task(task):
        return None, ""
    return repo, task


def _team_parts(rest):
    """(project, the words after it, whether a pause or dash split them) from what follows "start a claude on",
    or None when those words are chat, not a task."""
    desk = TEAM_DESK.match(rest)
    if ":" in rest:
        head, tail = rest.split(":", 1)
        return find_project(head), tail, False
    if desk:
        return "desk", TEAM_CONNECT.sub("", rest[desk.end():].strip(), count=1), False
    if TEAM_SENTENCE.search(rest) and _lead_project(TEAM_SENTENCE.split(rest, 1)[0].split())[0] \
            and not _lead_project(TEAM_SENTENCE.split(rest, 1)[0].split())[1]:
        # Spoken with a pause, the engine writes a full stop: "Start an agent on Example. Tidy the logs." Treat it like
        # a comma: the task needs 2+ words and has to open with a work verb ("Tidy the logs", not "I need the logs").
        head, tail = TEAM_SENTENCE.split(rest, 1)
        if not TEAM_DO.match(tail.strip()):
            return None
        return _lead_project(head.split())[0], tail, True
    return _team_parts_loose(rest)


def _team_parts_loose(rest):
    """The project and task when the name is followed by a comma or dash, a joining word ("to", "and", "then") or
    plain words (which are not a task)."""
    # The comma or dash sticks to the project word _lead_project takes, so split at it first.
    repo, tail = _lead_project(rest.split())
    sep = TEAM_SPLIT.search(rest)
    head_repo, head_left = _lead_project(rest[:sep.start()].split()) if sep else (None, "")
    via_sep = False
    if head_repo and not head_left:
        repo, tail = head_repo, rest[sep.end():]
        # After a comma or dash only a real task counts (2+ words): ", ok", "- quick", ", right" are chat.
        # A joining word ("example, to check in") or a colon is a stronger signal and is exempt.
        via_sep = not re.match(r"(?:and|then|to)\b", tail.strip(), re.I)
    elif not (repo and TEAM_CONNECT.match(tail)):
        repo = None   # words after the name with no joining word: not a task
    tail = TEAM_CONNECT.sub("", tail.strip(), count=1) if repo else ""
    return repo, tail, via_sep


def _is_task(task):
    """Not just a project name ("example-rpg", "the desk"): that is a second project, not something to do."""
    if TEAM_DESK.fullmatch(task):
        return False
    repo, left = _lead_project(task.split())
    return not (repo and not left)


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
    # "add this to my remember list: buy foam" (said to the Deck) -> "buy foam"; "add buy foam to my remember list" -> "buy foam"
    t = re.sub(r"^(please\s+)?(add|put|save|write)\s+(this|that|it)?\s*(to|on|onto|in)\s+(my|the)\s+remember(ed)?\s+list\b[\s:,.-]*",
               "", t, flags=re.I)
    t = re.sub(r"^(please\s+)?(add|put|save|write)\s+(.+?)\s+(to|on|onto|in)\s+(my|the)\s+remember(ed)?\s+list[.!]?$", r"\3", t, flags=re.I)
    return t.strip()


def note_topic(text):
    t = clean_text(text)
    t = re.sub(r"^(please\s+)?(open|show( me)?|pull up|bring up)\s+(up\s+)?((my|the|a)\s+)?"
               r"((notes?|file|doc|readme)\s+)?((on|about|for|of)\s+)?", "", t, flags=re.I)
    return t.strip() or clean_text(text)


NOTE_WORDS = re.compile(r"\b(notes?|readme|bible|guide|docs?|plan)\b", re.I)
FILE_WORDS = re.compile(r"\b(folder|directory|file|picture|photo|image|video|pdf|spreadsheet|png|jpe?g|mp4|docx|"
                        r"downloads?|documents|screenshots?)\b", re.I)


def _open_order(job_id, t):
    order = ["open-app", "open-file", "open-note"]
    if FILE_WORDS.search(t) or job_id == "open-file":
        order = ["open-file", "open-app", "open-note"]
    if NOTE_WORDS.search(t) and not FILE_WORDS.search(t):
        order = ["open-note", "open-file", "open-app"]
    if desktop.known_folder(t):
        order.insert(0, "open-file")
    return order


def _try_open_file(t, order):
    # Without file words it's an app that isn't installed, so only a project or known folder counts
    # (a loose name search opened window-chrome.ts for "open chrome").
    path, what, _ = desktop.find_file(t, [os.path.join(PROJECTS, p) for p in project_names()],
                                      min_score=0.6 if order[0] == "open-file" else 1.0)
    if not path:
        return None
    name = os.path.basename(path) or path
    return ("open-file", {"path": path, "name": name}, f"Open {name}", f"Opening the {what} {name}.", [])


def _try_open_note(t, order, search):
    if not (search and (order[0] != "open-app" or NOTE_WORDS.search(t))):
        return None
    hits = search(note_topic(t))
    if not hits:
        return None
    top = hits[0]
    return ("open-note", {"path": top["path"], "title": top["title"]}, f"Open {top['title']}",
            f"Opening your note {top['title']}.", hits[:3])


def resolve_open(job_id, text, search=None):
    """"Open X": an app, a file or folder, or a note? Tries them in the order the words suggest
    (file words: file first; note words: note first; else app first). Returns
    (job id, args, label, answer, sources) or None."""
    t = clean_text(text)
    order = _open_order(job_id, t)
    for kind in order:
        if kind == "open-app":
            app_id, name, _ = desktop.find_app(t)
            found = ("open-app", {"app": app_id, "name": name}, f"Open {name}", f"Opening {name}.", []) if app_id else None
        elif kind == "open-file":
            found = _try_open_file(t, order)
        else:
            found = _try_open_note(t, order, search)
        if found:
            return found
    return None


# ---------- building the job object ----------

def _command(job, args):
    """A job's command; start-claude with a task (args.text) prepares a team job instead of opening the PM chat."""
    return job["team_command"] if job.get("team_command") and args.get("text") else job["command"]


def _cmd_string(job, args):
    return " ".join(_fill(_command(job, args), {"monitor": "", **args}))


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


def _unsure_first(job_id, got, text):
    """The word rules built something, but a job the writer should check instead: an "open" that fell through to a
    note, or music with no play/pause/skip word."""
    return (job_id in ("open-app", "open-file") and got == "open-note") or \
        (job_id == "music" and got and not MUSIC_WORDS.search(text))


def _job_from_form(job_id, t, f, search, local_writer):
    """The job the writer's form `f` makes, built again from plain words so every value is found and checked as usual."""
    if f and job_id == "desktop":
        checked = details.desktop_args(f)
        if checked and checked[0] == "window-monitor":
            return _build_window_move(load()["desktop"], t, checked[1])
        if checked:
            return _desktop_job(load()["desktop"], *checked)
    elif f and details.as_text(job_id, f):
        return build(job_id, details.as_text(job_id, f), search, local_writer)
    return None


def build_with_details(job_id, text, search=None, local_writer=None, fill=None, how="typed"):
    """build(), and when its word rules come up empty (no job) or unsure (an "open" that fell through to a note,
    music with no play/pause/skip word), the local writer's form for that job (details.py), turned back into a
    plain command and built again, so every value is found and checked as usual. Adds "details": "rules",
    "local" (the writer's form made the job) or "none" (it didn't help), and "details_ms"."""
    t0 = time.monotonic()
    first = build(job_id, text, search, local_writer, how=how)
    got = (first.get("job") or {}).get("id")
    unsure = _unsure_first(job_id, got, text)
    if (got and not unsure) or job_id not in details.JOBS or not details.on():
        return dict(first, details="rules")
    t = clean_text(text)
    f = (fill or details.fill)(job_id, t, project_names() if job_id == "start-claude" else ())
    out = _job_from_form(job_id, t, f, search, local_writer)
    ms = int((time.monotonic() - t0) * 1000)
    if out and out.get("kind") == "job" and (out["job"]["id"] != "open-note" or not unsure):
        return dict(out, details="local", details_ms=ms, form=f)
    return dict(first, details="none", details_ms=ms, form=f)


def _plain(answer):
    return {"kind": "answer", "answer": answer, "sources": [], "job": None}


def _sentence(why):
    """A ValueError's reason as a spoken sentence."""
    return str(why)[:1].upper() + str(why)[1:].rstrip(".") + "."


TOO_LONG = "That was too long for one job. Say it in one short sentence."
NO_PROJECT = "Which project? I didn't catch a project name I know."
# Each _build_* below gets (job, job_id, text, search, local_writer, how) and gives back either a finished
# answer dict (nothing to run) or (job_id, args, label, answer, sources) for the job card.


def _build_open(job, job_id, text, search, local_writer, how):
    picked = resolve_open(job_id, text, search)
    if picked is None:
        return _plain(f"I couldn't find {desktop.app_topic(clean_text(text)) or 'that'} as an app, a file or a note.")
    job_id, args, label, answer, sources = picked
    spec = desktop.monitor_spec(clean_text(text)) if job_id == "open-app" else None
    if spec:
        try:
            args["monitor"] = desktop.check_monitor_spec(spec)
        except ValueError as why:
            return _plain(_sentence(why))
        label += " on " + desktop.spec_say(args["monitor"])
        answer = f"Opening {args['name']} on {desktop.spec_say(args['monitor'])}."
    return job_id, args, label, answer, sources


def _build_desktop(job, job_id, text, search, local_writer, how):
    t = clean_text(text)
    action, value = desktop.find_action(t)
    if not action:
        return _plain("I don't know how to do that on the desktop yet.")
    if action == "reminder" and not value:
        return _plain("When? Say, remind me at 2pm to stretch, or in 10 minutes.")
    if action == "workspace" and not value:
        return _plain("Which workspace, 1 to 10?")
    if action == "window-monitor":
        return _build_window_move(job, t, value)
    return _desktop_job(job, action, value)


def _build_send(job, job_id, text, search, local_writer, how):
    picked = sendfiles.plan(clean_text(text), find_project=find_project, projects_root=PROJECTS,
                            project_dirs=[os.path.join(PROJECTS, p) for p in project_names()])
    if "paths" not in picked:
        return _plain(picked["answer"])
    args = {"device": picked["device"], "paths": picked["paths"], "name": picked["name"]}
    return job_id, args, picked["label"], picked["answer"], []


def _build_note(job, job_id, text, search, local_writer, how):
    topic = note_topic(text)
    hits = search(topic) if search else []
    if not hits:
        return _plain(f"I couldn't find a note about {topic}.")
    top = hits[0]
    args = {"path": top["path"], "title": top["title"]}
    return job_id, args, f"Open {top['title']}", f"Opening your note {top['title']}.", hits[:3]


def _build_team(job, job_id, text, search, local_writer, how):
    repo, task = team_task(text)
    try:
        task = one_line(task)
    except ValueError:
        return _plain(TOO_LONG)
    args = {"project": repo, "name": pretty(repo), "text": task, "how": how if how in HOWS else "typed"}
    answer = (f"This prepares a team job on {pretty(repo)}: {task}. Nothing starts until you say go at the desk.")
    return job_id, args, f"Start a team on {pretty(repo)}", answer, []


def _build_desk_pm(job, job_id, text, search, local_writer, how):
    repo = find_project(text, local_writer)
    if not repo:
        return _plain(NO_PROJECT)
    if repo != "desk":      # per-project PM chats were retired 2026-10-19: a project gets a team job, with a task
        return _plain(f"What should the team do on {pretty(repo)}? Say it with the task, like: "
                      f"start a claude on {pretty(repo)}, tidy the logs.")
    args = {"project": repo, "name": pretty(repo)}
    answer = f"This opens a Claude on {pretty(repo)}."
    if team_task(text)[0] == "desk":
        answer = "The whole desk has no team job, so this opens a Claude on the desk; your task was not used."
    return job_id, args, "Start a Claude on the whole desk", answer, []


def _build_music(job, job_id, text, search, local_writer, how):
    args = {"action": music_action(text)}
    label = {"Next": "Next song", "Previous": "Previous song", "Pause": "Pause the music",
             "Play": "Play the music", "PlayPause": "Play or pause the music"}[args["action"]]
    return job_id, args, label, label + ".", []


def _build_tv(job, job_id, text, search, local_writer, how):
    action = tv_action(text)
    if not action:
        return _plain("I can only turn the TV up, down, or mute it.")
    label = {"up": "Turn the TV up", "down": "Turn the TV down", "mute": "Mute the TV"}[action]
    return job_id, {"action": action}, label, label + ".", []


def _build_servers(job, job_id, text, search, local_writer, how):
    t = clean_text(text)
    action, site = servers.action_of(t), servers.find_server(t)
    if not action or not site:
        return _plain("Which server, and on or off? Say, turn on the LLC namer.")
    label = f"Turn {action} {site['label']}"
    return job_id, {"site": site["id"], "action": action}, label, label + ".", []


def _build_remember(job, job_id, text, search, local_writer, how):
    what = remember_text(text)
    if not what:
        return _plain("What should I remember?")
    return job_id, {"text": what}, f"Remember: {what[:80]}", "I'll add it to your remembered list.", []


def _build_start_job(job, job_id, text, args):
    repo, what = job_project(text)
    if not repo:
        return _plain(NO_PROJECT)
    if not what:
        return _plain(f"What should the job on {pretty(repo)} do? Say, start a job on "
                      f"{pretty(repo)}, then what to do.")
    what = re.sub(r"^(to|and|then)\s+(?=\S)", "", what.strip(), flags=re.I)   # "on example-game to fix it"
    args = {"project": repo, "name": pretty(repo), **args, "text": one_line(what)}
    answer = (f"This prepares a team job on {pretty(repo)}: {what[:80].rstrip('.!?')}. It will wait for your go before anything "
              "is built.")
    return job_id, args, f"Start a job on {pretty(repo)}", answer, []


def _build_agent(job, job_id, text, search, local_writer, how):
    try:
        words = one_line(clean_text(text))
    except ValueError:
        return _plain(TOO_LONG)
    args = {"text": words, "how": how if how in HOWS else "typed"}
    if job_id == "start-job":
        return _build_start_job(job, job_id, text, args)
    return job_id, args, job["label"], "This hands it to agent-os. It will wait for your go before anything is built.", []


def _build_what_changed(job, job_id, text, search, local_writer, how):
    args = {"when": day_when(text)}
    label = {"today": "What moved today", "yesterday": "What moved yesterday",
             "overnight": "What happened overnight"}[args["when"]]
    return job_id, args, label, "Checking.", []


def _build_goodnight(job, job_id, text, search, local_writer, how):
    return job_id, {}, job["label"], "I'll sum up the day, clear what's done and ask what may run tonight.", []


def _build_team_screen(job, job_id, text, search, local_writer, how):
    return job_id, {}, job["label"], "Opening the team screen.", []


def _build_whats_waiting(job, job_id, text, search, local_writer, how):
    return job_id, {}, job["label"], "Checking who needs you.", []


BUILDERS = {"desktop": _build_desktop, "send-file": _build_send, "open-note": _build_note, "music": _build_music,
            "tv": _build_tv, "servers": _build_servers, "remember": _build_remember,
            "what-changed": _build_what_changed, "goodnight": _build_goodnight, "team-screen": _build_team_screen,
            **{j: _build_agent for j in AGENT_JOBS}}


def _builder_for(job_id, text):
    if job_id in ("open-app", "open-file") or (job_id == "open-note" and not NOTE_WORDS.search(text)):
        return _build_open
    if job_id == "start-claude":
        return _build_team if team_task(text)[0] not in (None, "desk") else _build_desk_pm
    return BUILDERS.get(job_id, _build_whats_waiting)


def _job_card(jobs, job_id, args, label, answer, sources):
    job = jobs[job_id]
    obj = {"id": job_id, "label": label, "needs_confirm": bool(job.get("needs_confirm")),
           "command": _cmd_string(job, args), "args": args}
    if job_id == "servers":   # turning one on just happens; turning one off asks first (someone may be using it)
        obj["needs_confirm"] = args["action"] == "off"
    if job.get("speak") or "text" in args and job_id == "start-claude":
        obj["speak"] = True
    return {"kind": "job", "answer": answer, "sources": sources, "job": obj}


def build(job_id, text, search=None, local_writer=None, how="typed"):
    """Turn what <user> said into {kind, answer, sources, job}. `search(topic)` returns hits
    ([{path, title, snippet}]) for open-note. Returns kind "answer" (a polite "I can't") when an
    argument is missing, so the island never runs a half-filled job. `how` (voice or typed) is how the words came,
    for the agent-os jobs."""
    jobs = load()
    job = jobs.get(job_id)
    if not job:
        return _plain("I don't know how to do that yet.")
    made = _builder_for(job_id, text)(job, job_id, text, search, local_writer, how)
    if isinstance(made, dict):
        return made
    return _job_card(jobs, *made)


# ---------- running ----------

def _check_note(job_id, a):
    path = os.path.realpath(os.path.expanduser(str(a.get("path", ""))))
    if not os.path.isfile(path) or not any(path.startswith(r + os.sep) for r in NOTE_ROOTS):
        raise ValueError("that note isn't in your brain's folders")
    return {"path": path, "title": str(a.get("title") or os.path.basename(path))}


def _check_claude(job_id, a):
    repo = str(a.get("project", ""))
    if repo != "desk" and repo not in project_names():
        raise ValueError(f"I don't know a project called {repo or 'that'}")
    if a.get("text") not in (None, ""):   # a team job: the whole desk has none
        if repo == "desk":
            raise ValueError("the whole desk has no team job")
        return {"project": repo, "name": pretty(repo), "text": one_line(a.get("text")),
                "how": a.get("how") if a.get("how") in HOWS else "typed"}
    return {"project": repo, "name": pretty(repo)}


def _check_app(job_id, a):
    app_id = str(a.get("app", ""))
    desktop.app_command(app_id)  # raises if it isn't installed
    monitor = a.get("monitor")
    if monitor not in (None, ""):
        monitor = desktop.check_monitor_spec(monitor)
    return {"app": app_id, "name": str(a.get("name") or app_id), "monitor": monitor or ""}


def _check_send(job_id, a):
    device, paths, _ = sendfiles.check_send(a.get("device"), a.get("paths"))
    name = re.sub(r"[^\w .&'-]", "", str(a.get("name") or "Files"))[:40].strip() or "Files"
    return {"device": device, "paths": paths, "name": name}


def _check_file(job_id, a):
    path = desktop.allowed_path(a.get("path", ""))
    if not path:
        raise ValueError("that isn't a file or folder I'm allowed to open")
    return {"path": path, "name": os.path.basename(path) or path}


def _check_desktop(job_id, a):
    action, value = desktop.check_action(str(a.get("action", "")), a.get("value"))
    return {"action": action, "value": value}


def _check_choice(job_id, a):
    allowed = load()[job_id]["args"]["action"]
    if a.get("action") not in allowed:
        raise ValueError("that isn't something I can do")
    return {"action": a["action"]}


def _check_agent(job_id, a):
    out = {"text": one_line(a.get("text")), "how": a.get("how") if a.get("how") in HOWS else "typed"}
    if job_id == "start-job":
        repo = str(a.get("project", ""))
        if repo == "desk" or repo not in project_names():
            raise ValueError(f"I don't know a project called {repo or 'that'}")
        out = {"project": repo, "name": pretty(repo), **out}
    return out


def _check_servers(job_id, a):
    known = {e["id"]: e["label"] for e in servers.entries()}
    if a.get("action") not in ("on", "off") or a.get("site") not in known:
        raise ValueError("I don't know that server")
    return {"site": a["site"], "action": a["action"]}


def _check_what_changed(job_id, a):
    if a.get("when") not in load()[job_id]["args"]["when"]:
        raise ValueError("I can only say today, yesterday or overnight")
    return {"when": a["when"]}


def _check_remember(job_id, a):
    text = " ".join(str(a.get("text", "")).split())[:500]
    if not text:
        raise ValueError("there was nothing to remember")
    return {"text": text}


CHECKS = {"open-note": _check_note, "start-claude": _check_claude, "open-app": _check_app,
          "send-file": _check_send, "open-file": _check_file, "desktop": _check_desktop, "music": _check_choice,
          "tv": _check_choice, "servers": _check_servers, "what-changed": _check_what_changed,
          "remember": _check_remember, **{j: _check_agent for j in AGENT_JOBS}}


def _check(job_id, args):
    """Rebuild and check the arguments; raises ValueError with a plain reason."""
    check = CHECKS.get(job_id)
    return check(job_id, dict(args or {})) if check else {}


def _json_message(stdout, default_speak):
    """(message, speak) from the last stdout line that is a JSON object with a message, else (None, default)."""
    for line in reversed(stdout.splitlines()):
        try:
            obj = json.loads(line)
        except ValueError:
            continue
        if isinstance(obj, dict) and obj.get("message"):
            return obj["message"], bool(obj.get("speak", default_speak))
    return None, default_speak


def _no_message(job, args, out):
    """What to say when the job printed no message of its own."""
    if out.returncode == 0:
        return (job["team_message"] if _command(job, args) is job.get("team_command")
                else job.get("message", "Done.")).format(**args)
    err = (out.stderr or out.stdout).strip().splitlines()
    return "That didn't work" + (f": {err[-1][:160]}" if err else ".")


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
    argv = _fill(_command(job, args), args)
    if job_id == "open-note":   # don't wait for the viewer app
        subprocess.Popen(argv, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        print(json.dumps({"message": job["message"].format(**args)}))
        return 0
    try:
        out = subprocess.run(argv, capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired) as why:
        print(json.dumps({"message": f"That didn't work: {why}."}))
        return 1
    message, speak = _json_message(out.stdout, bool(job.get("speak")))
    if message is None:
        message = _no_message(job, args, out)
    print(json.dumps({"message": message, "speak": speak} if speak else {"message": message}))
    return out.returncode


def _cmd_list():
    for j in load().values():
        c = j.get("needs_confirm")
        c = "sometimes" if isinstance(c, str) else "asks first" if c else "no confirm"
        print(f"{j['id']:14} {c:11} e.g. \"{j['phrases'][0]}\"")
    return 0


def _cmd_build(argv):
    text = argv[1]
    jid = argv[2] if len(argv) > 2 else match_rule(text)
    print(json.dumps(build(jid, text) if jid else None))
    return 0


def _cmd_run(argv):
    obj = {}
    if "--args-json" in argv:
        try:
            obj = json.loads(argv[argv.index("--args-json") + 1])
        except (ValueError, IndexError):
            print(json.dumps({"message": "The job's details didn't make sense, so I did nothing."}))
            return 2
    return run(argv[1], obj if isinstance(obj, dict) else {})


def main(argv):
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__.split("\n\n")[-1])
        return 0
    if argv[0] == "list":
        return _cmd_list()
    if argv[0] == "build":
        return _cmd_build(argv)
    if argv[0] == "run" and len(argv) >= 2:
        return _cmd_run(argv)
    print("jobs: unknown command", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
