"""Details pulled out by the local writer (router upgrade 3, 2026-10-15).

The word rules in jobs.py stay the instant first try. Only when they come up empty for a job
with details (which project...) does build_with_details() ask qwen2.5 through
Ollama (second-brain-ollama.service) to fill in a small fixed form for that job (Ollama's `format` = a JSON
schema, so only those fields, short). The form is turned back into a plain command the word rules understand
("start a claude on example-game") and built again, so every value goes
through the same finding and checking as before: the project must be a known one, and the job runner checks
it all again before it runs (jobs._check). Nothing the writer says is ever run as it is. If the form doesn't lead
to a checked job, the word rules' own one-line question stays.

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

OLLAMA = os.environ.get("OLLAMA_HOST_URL", "127.0.0.1:11434")
MODEL = os.environ.get("BRAIN_DETAILS_MODEL", os.environ.get("BRAIN_LOCAL_MODEL", "qwen2.5:3b"))
SECONDS = float(os.environ.get("BRAIN_DETAILS_SECONDS", "4"))
CONFIG = os.path.join(HERE, "config", "details.json")   # {"on": true|false}, set by the details test
JOBS = ("start-claude",)
SYSTEM = ("<user> said this to his desktop assistant. Fill in the form with what he asked for. Fix speech-to-text "
          "slips in names. Use \"\" (or 0) for anything he did not say. Never make up a name he didn't say.")
# One or two short examples per job (said -> form), so the 3B writer knows what each field means.
EXAMPLES = {
    "start-claude": [("get a helper going on the example-game thing", {"project": "example-game"})],
}


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
    if job_id == "start-claude":
        return _obj({"project": s(enum=["none", "desk"] + list(projects))})
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
    ex = EXAMPLES.get(job_id, [])
    msgs = [{"role": "system", "content": SYSTEM}]
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


def _ground_project(f, t, text):
    p = f["project"]
    names = [w for w in re.split(r"[-_ ]+", p.lower()) if len(w) >= 3]
    if not (p == "desk" and "desk" in t) and not any(said(w, text) for w in names):
        f["project"] = "none"


def ground(job_id, f, text, projects=()):
    """The form with every value <user> didn't actually say blanked out (the 3B writer makes up names)."""
    f = dict(f)
    t = text.lower()
    if job_id == "start-claude" and f.get("project") not in (None, "", "none"):
        _ground_project(f, t, text)
    return f


def _clean(s, n=80):
    return " ".join(w for w in re.sub(r"[^\w .'&+-]", " ", str(s or "")).split() if w.lower() not in ("stuff", "thing"))[:n]


def _text_start_claude(f):
    if f.get("project") in (None, "", "none"):
        return None
    return f"start a claude on {_clean(f['project'])}"


TEXT_OF = {"start-claude": _text_start_claude}


def as_text(job_id, f):
    """The form as a plain command for the word rules, or None. Values are only words here: what they point
    at is found and checked by the normal build, exactly as for a typed command."""
    make = TEXT_OF.get(job_id)
    return make(f) if make else None
