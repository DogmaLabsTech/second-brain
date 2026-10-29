"""Details pulled out by the local writer (router upgrade 3, 2026-10-15).

The word rules in jobs.py and desktop.py stay the instant first try. Only when they come up empty for a job
with details (which app, file, device, action, project...) does build_with_details() ask qwen2.5 through
Ollama (second-brain-ollama.service) to fill in a small fixed form for that job (Ollama's `format` = a JSON
schema, so only those fields, short). The form is turned back into a plain command the word rules understand
("open spotify on my left screen", "send the kingdom map to the phone") and built again, so every value goes
through the same finding and checking as before: the app must be installed, the file must exist and be
allowed, the device must be in the list, and the job runner checks it all again before it runs (jobs._check).
Desktop forms are checked with desktop.check_action, the runner's own check. Nothing the writer says is ever
run as it is. If the form doesn't lead to a checked job, the word rules' own one-line question stays.

Speed: word-rule jobs don't change. The writer adds about 1.5 s when it is loaded; when it isn't (a cold load
takes 15-30 s here), it is woken for next time and the word rules' answer is used now.

  python3 -I jobs/details.py <job id> "<what <user> said>"     the form the writer fills in, and the job
"""
import difflib
import http.client
import json
import os
import re
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import desktop  # noqa: E402

OLLAMA = os.environ.get("OLLAMA_HOST_URL", "127.0.0.1:11434")
MODEL = os.environ.get("BRAIN_DETAILS_MODEL", os.environ.get("BRAIN_LOCAL_MODEL", "qwen2.5:3b"))
SECONDS = float(os.environ.get("BRAIN_DETAILS_SECONDS", "4"))
CONFIG = os.path.join(HERE, "config", "details.json")   # {"on": true|false}, set by the details test
JOBS = ("open-app", "open-file", "send-file", "desktop", "start-claude", "tv", "music")
SCREENS = ["", "other", "left", "right", "top", "bottom"]
SYSTEM = ("<user> said this to his desktop assistant. Fill in the form with what he asked for. Fix speech-to-text "
          "slips in names. Use \"\" (or 0) for anything he did not say. Never make up a name he didn't say.")
# One or two short examples per job (said -> form), so the 3B writer knows what each field means.
EXAMPLES = {
    "open-app": [("could you get the music app going on the right one", {"app": "spotify", "screen": "right"}),
                 ("need a terminal", {"app": "terminal", "screen": ""})],
    "open-file": [("that folder with my downloads in it", {"name": "downloads", "kind": "folder"}),
                  ("open up the kingdom map thing", {"name": "kingdom map", "kind": ""})],
    "send-file": [("chuck my latest screen grab on the lap top", {"device": "laptop", "name": "", "kind": "screenshot"}),
                  ("put the pricing doc on my phone", {"device": "phone", "name": "pricing", "kind": ""})],
    "start-claude": [("get a helper going on the example-game thing", {"project": "example-game"})],
    "tv": [("tv's way too loud", {"action": "down"})],
    "music": [("can you get rid of this song", {"action": "Next"})],
}


def desktop_examples():
    """The desktop form's examples, plus what each action means (its label), since the ids alone are cryptic."""
    meanings = "; ".join("%s = %s" % (a, v[0].replace(" {v}", "")) for a, v in desktop.ACTIONS.items())
    ex = [("make it so the screen doesnt go dark", {"action": "stay-awake", "number": 0, "words": "", "screen": ""}),
          ("ping me in half an hour to stretch", {"action": "reminder", "number": 30, "words": "stretch", "screen": ""}),
          ("hop over to the second desktop", {"action": "workspace", "number": 2, "words": "", "screen": ""})]
    return meanings, ex


def on():
    if os.environ.get("BRAIN_DETAILS") in ("0", "1"):
        return os.environ["BRAIN_DETAILS"] == "1"
    try:
        with open(CONFIG) as f:
            return bool(json.load(f).get("on"))
    except FileNotFoundError:   # never set: off
        return False
    except (OSError, ValueError) as why:
        print(f"details: could not read {CONFIG} ({why}); details are off", file=sys.stderr)
        return False


def _obj(props):
    return {"type": "object", "properties": props, "required": list(props)}


def schema(job_id, projects=()):
    """The form for one job, from the details its job file's `args` describe."""
    s = lambda **k: {"type": "string", **k}  # noqa: E731
    if job_id == "open-app":
        return _obj({"app": s(description="the app's name"), "screen": s(enum=SCREENS)})
    if job_id == "open-file":
        return _obj({"name": s(description="the file or folder's name, without words like open or the"),
                     "kind": s(enum=["", "folder", "picture", "video", "pdf", "document", "screenshot"])})
    if job_id == "send-file":
        return _obj({"device": s(enum=["", "laptop", "testbox", "phone"]),
                     "name": s(description="the file's or project's name, without words like file, picture or latest"),
                     "kind": s(enum=["", "screenshot", "picture", "pdf", "video", "files"])})
    if job_id == "desktop":   # small on purpose: every extra field costs time on the processor
        return _obj({"action": s(enum=["none"] + list(desktop.ACTIONS)),
                     "number": {"type": "integer", "description": "reminder minutes or workspace number"},
                     "words": s(description="the reminder's words, a theme name, or the app to move"),
                     "screen": s(enum=SCREENS)})
    if job_id == "start-claude":
        return _obj({"project": s(enum=["none", "desk"] + list(projects))})
    if job_id == "tv":
        return _obj({"action": s(enum=["none", "up", "down", "mute"])})
    if job_id == "music":
        return _obj({"action": s(enum=["none", "PlayPause", "Play", "Pause", "Next", "Previous"])})
    return None


def loaded():
    try:
        with urllib.request.urlopen(f"http://{OLLAMA}/api/ps", timeout=0.5) as r:
            return any(m.get("name") == MODEL or m.get("model") == MODEL for m in json.load(r).get("models", []))
    except Exception:  # noqa: BLE001
        return False


def _timed_out(why):
    return isinstance(why, TimeoutError) or isinstance(getattr(why, "reason", None), TimeoutError)


def wake():
    try:
        req = urllib.request.Request(f"http://{OLLAMA}/api/generate", json.dumps({"model": MODEL, "keep_alive": "5m"}).encode(),
                                     {"content-type": "application/json"})
        urllib.request.urlopen(req, timeout=0.3)
    except Exception as why:  # noqa: BLE001
        if not _timed_out(why):   # a timeout is the plan: it keeps loading after we stop waiting
            print(f"details: could not wake the writer: {why}", file=sys.stderr)


def fill(job_id, text, projects=(), timeout=SECONDS):
    """The writer's form for this job, or None (not loaded, too slow, bad JSON)."""
    form = schema(job_id, projects)
    if not form:
        return None
    if not loaded():
        wake()
        return None
    system, ex = SYSTEM, EXAMPLES.get(job_id, [])
    if job_id == "desktop":
        meanings, ex = desktop_examples()
        system += " Actions: " + meanings + ". A quarter hour is 15 minutes."
    msgs = [{"role": "system", "content": system}]
    for said, f in ex:
        msgs += [{"role": "user", "content": said}, {"role": "assistant", "content": json.dumps(f)}]
    body = {"model": MODEL, "stream": False, "keep_alive": "5m", "format": form,
            "options": {"temperature": 0, "num_predict": 80, "num_ctx": 4096},   # ask.py's size, or Ollama reloads (13 s)
            "messages": msgs + [{"role": "user", "content": text}]}
    host, _, port = OLLAMA.partition(":")
    try:
        conn = http.client.HTTPConnection(host, int(port or 11434), timeout=timeout)
        conn.request("POST", "/api/chat", json.dumps(body), {"content-type": "application/json"})
        r = conn.getresponse()
        out = json.loads(json.loads(r.read())["message"]["content"]) if r.status == 200 else None
        conn.close()
    except (OSError, ValueError, KeyError) as why:
        if not _timed_out(why):   # too slow is expected; anything else is said
            print(f"details: the writer failed ({type(why).__name__}: {why}); no details", file=sys.stderr)
        return None
    return ground(job_id, out, text, projects) if isinstance(out, dict) else None


# ---------- only what was said ----------

FILLER = set("a an the my me of to on in for and with that this please up it its thing stuff one some".split())
KIND_SAID = {"picture": r"\b(pic|pics|picture|pictures|photo|photos|image|images|png|jpe?g)\b",
             "video": r"\b(video|videos|vid|vids|clip|movie|mp4)\b", "pdf": r"\bpdf\b",
             "screenshot": r"\bscreen ?(shot|grab|cap)s?\b|\bscreenshots?\b", "folder": r"\b(folder|directory|dir)\b",
             "document": r"\b(doc|docs|document|documents|docx)\b", "files": r"\b(files|stuff)\b"}
SCREEN_SAID = {"other": r"\b(other|second|another|next)\b", "left": r"\bleft\b", "right": r"\bright\b",
               "top": r"\b(top|upper|above)\b", "bottom": r"\b(bottom|lower|below)\b"}


def _said_words(text):
    return re.findall(r"[a-z0-9]+", text.lower())


def said(value, text, ratio=0.75):
    """Every real word of value is in what was said (close spelling counts: "tavern light" ~ "example-rpg")."""
    have = _said_words(text)
    joined = "".join(have)
    words = [w for w in _said_words(str(value)) if w not in FILLER]
    if not words:
        return False
    for w in words:
        if w in have or (len(w) >= 4 and w in joined):
            continue
        if not any(difflib.SequenceMatcher(None, w, h).ratio() >= ratio for h in have):
            return False
    return True


# A desktop action from the writer counts only if a word of its kind was said ("brightness up" is not volume).
ACTION_SAID = [("volume", r"volume|sound|loud|quiet|speaker|audio|computer"), ("mic", r"mic"),
               ("nightlight", r"night|blue light|warm"), ("screenshot", r"screen|shot|grab|snip|capture"),
               ("record", r"record"), ("bluetooth", r"bluetooth"), ("lock", r"lock"), ("logout", r"log|sign"),
               ("reboot", r"restart|reboot"), ("shutdown", r"shut|power|turn off"),
               ("stay-awake", r"awake|sleep|dark|dim|idle|caffeine|lock"), ("allow-sleep", r"sleep|idle|awake"),
               ("theme", r"theme|look|colou?r"), ("bg", r"wallpaper|background"), ("dnd", r"disturb|notification|quiet|ping"),
               ("emoji", r"emoji"), ("clipboard", r"clipboard|copied|paste"), ("keybindings", r"shortcut|key|hotkey"),
               ("reminder", r"remind|timer|ping|alert|minute|hour"), ("workspace", r"workspace|desktop|space"),
               ("window-monitor", r"screen|monitor|display")]


def action_said(action, text):
    rule = next((r for k, r in ACTION_SAID if action.startswith(k)), None)
    return rule is None or bool(re.search(rule, text.lower()))


def _ground_project(f, t, text):
    p = f["project"]
    names = [w for w in re.split(r"[-_ ]+", p.lower()) if len(w) >= 3]
    if not (p == "desk" and "desk" in t) and not any(said(w, text) for w in names):
        f["project"] = "none"


def _ground_desktop_action(f, text):
    if not f.get("number") and f.get("action") in ("reminder", "workspace"):
        f["action"] = "none"
    if f.get("action") in desktop.ACTIONS and not action_said(f["action"], text):
        f["action"] = "none"


def _blank_unsaid_values(f, t, text):
    """Blank the screen, kind, app, name and words the writer made up (<user> didn't say them)."""
    if "screen" in f and f["screen"] and not re.search(SCREEN_SAID.get(f["screen"], r"$^"), t):
        f["screen"] = ""
    if "kind" in f and f["kind"] and not re.search(KIND_SAID.get(f["kind"], r"$^"), t):
        f["kind"] = ""
    for k in ("app", "name"):
        if f.get(k) and not said(f[k], text):
            f[k] = ""
    if f.get("words") and f.get("action") in ("theme-set", "window-monitor") and not said(f["words"], text):
        f["words"] = ""


def ground(job_id, f, text, projects=()):
    """The form with every value <user> didn't actually say blanked out (the 3B writer makes up names and screens)."""
    f = dict(f)
    t = text.lower()
    _blank_unsaid_values(f, t, text)
    if job_id == "start-claude" and f.get("project") not in (None, "", "none"):
        _ground_project(f, t, text)
    if job_id == "desktop":
        _ground_desktop_action(f, text)
    return f


def _clean(s, n=80):
    return " ".join(w for w in re.sub(r"[^\w .'&+-]", " ", str(s or "")).split() if w.lower() not in ("stuff", "thing"))[:n]


DEVICE_SAY = {"laptop": "the laptop", "testbox": "the testbox", "phone": "my phone"}


def _text_open_app(f):
    if not _clean(f.get("app")):
        return None
    scr = f.get("screen") if f.get("screen") in SCREENS else ""
    return f"open {_clean(f['app'])}" + (f" on my {scr} screen" if scr else "")


def _text_open_file(f):
    if not _clean(f.get("name")):
        return None
    kind = f.get("kind") if f.get("kind") in ("folder", "picture", "video", "pdf", "screenshot") else ""
    return f"open the {_clean(f['name'])} {kind}".strip()


def _text_send_file(f):
    if f.get("device") not in DEVICE_SAY:
        return None
    name = re.sub(r"\b(latest|newest|last|recent|most recent)\b", " ", _clean(f.get("name")), flags=re.I).strip()
    kind = f.get("kind") if f.get("kind") in ("screenshot", "picture", "pdf", "video") else ""
    if name and f.get("kind") == "files":
        return f"send the latest {name} files to {DEVICE_SAY[f['device']]}"   # a project's newest files
    if name or kind:
        return f"send {name or 'the latest ' + kind} to {DEVICE_SAY[f['device']]}"
    return None


def _text_start_claude(f):
    if f.get("project") in (None, "", "none"):
        return None
    return f"start a claude on {_clean(f['project'])}"


def _text_tv(f):
    if f.get("action") in ("up", "down", "mute"):
        return {"up": "turn the tv up", "down": "turn the tv down", "mute": "mute the tv"}[f["action"]]
    return None


def _text_music(f):
    if f.get("action") in ("Play", "Pause", "Next", "Previous", "PlayPause"):
        return {"Play": "play", "Pause": "pause", "Next": "next song", "Previous": "previous song",
                "PlayPause": "play or pause the music"}[f["action"]]
    return None


TEXT_OF = {"open-app": _text_open_app, "open-file": _text_open_file, "send-file": _text_send_file,
           "start-claude": _text_start_claude, "tv": _text_tv, "music": _text_music}


def as_text(job_id, f):
    """The form as a plain command for the word rules, or None. Values are only words here: what they point
    at is found and checked by the normal build, exactly as for a typed command."""
    make = TEXT_OF.get(job_id)
    return make(f) if make else None


def _action_value(action, f, words):
    """The value a desktop form's action needs, as the runner's check expects it. None can mean a window app
    that isn't there (second item False)."""
    if action == "reminder":
        return {"minutes": f.get("number"), "message": words or "Reminder"}, True
    if action == "workspace":
        return f.get("number"), True
    if action == "theme-set":
        return desktop.find_theme(words), True
    if action == "window-monitor":
        app = desktop.find_app("open " + words)[0] if words else None
        if words and not app:
            return None, False
        return {"to": f.get("screen") or None, "app": app}, True
    return None, True


def desktop_args(f):
    """(action, value) from a desktop form, checked with desktop.check_action (the runner's own check), or None."""
    action = f.get("action")
    if action not in desktop.ACTIONS:
        return None
    value, ok = _action_value(action, f, _clean(f.get("words"), 120))
    if not ok:
        return None
    try:
        return desktop.check_action(action, value)
    except ValueError:
        return None
