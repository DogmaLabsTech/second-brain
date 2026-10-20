"""Servers by voice: "turn on the LLC namer", "stop the pit wall board".

The names come from the hosting lists the bar's servers light uses (~/.config/hosting/sites.conf and
services.conf, the same files `hostctl` reads). Only entries with a tailnet port are offered: a
service with no link (voice typing, the speech server, Ollama) is never switched off by voice.
Reading the two small files is quick, so the rule can run on every question. Whether a server is up
is only asked at run time, by `bin/servers`.

  python3 -I jobs/servers.py "turn off the llc namer"    # prints what it understood
"""
import os
import re
import sys

HOME = os.path.expanduser("~")
CONFS = ("sites.conf", "services.conf")
SKIP = {"the", "for", "and", "dev", "site", "server", "app", "board"}   # label words that don't name a server
# Words that mean the line is about something else that happens to name a project ("start a claude on example-game").
OTHER_ASK = re.compile(r"\b(claude|job|jobs|team|agent|remind|reminder|remember|note|notes|task)\b", re.I)
# "start a clot on example, tidy the logs" (a misheard "claude"): a team job, not a server. A server ask is short,
# one sentence, and has no "<verb> a <word> on/for" in it.
TEAM_SHAPE = re.compile(r"\b(start|run|open|begin|kick off)\s+(a|an|the|my)?\s*\w+\s+(on|for)\b|[.?!:;,]\s*\w", re.I)
MAX_WORDS = 9
OFF = re.compile(r"\b(off|stop|shut|disable|kill)\b|\btake\b.*\bdown\b", re.I)
ON = re.compile(r"\b(on|start|enable|launch)\b|\b(bring|power|turn) (it |that |this )?(back )?(up|on)\b", re.I)


def conf_dir():
    return os.environ.get("HOSTCTL_CONF_DIR") or os.path.join(HOME, ".config", "hosting")


def entries():
    """[{id, label}] for every hosted thing that has a link, in file order."""
    out = []
    for name in CONFS:
        try:
            with open(os.path.join(conf_dir(), name)) as f:
                lines = f.read().splitlines()
        except OSError:
            continue
        for line in lines:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            f = line.split(None, 5)
            if len(f) == 6 and f[3] != "-":
                out.append({"id": f[0], "label": f[5]})
    return out


def _tokens(label):
    label = re.sub(r"\(.*?\)", " ", label)
    return [w for w in re.findall(r"[a-z0-9]+", label.lower()) if len(w) > 1 and w not in SKIP]


def _spoken(text):
    return re.sub(r"[^a-z0-9 ]+", " ", text.lower())


def action_of(text):
    """"on", "off", or None when the words say neither or both."""
    off, on = bool(OFF.search(text)), bool(ON.search(text))
    return "off" if off and not on else "on" if on and not off else None


def find_server(text, listing=None):
    """The entry the words name, or None. Words in the label all being said beats some being said; then more words win
    ("example-game" is the game, "example-game home" is the tablet page)."""
    spoken = _spoken(text)
    said = set(spoken.split())
    squashed = spoken.replace(" ", "")
    best, best_key = None, None
    listing = entries() if listing is None else listing
    for e in listing:
        toks = _tokens(e["label"])
        if not toks:
            continue
        # "pit wall" for "example-board": a word also counts when the spoken words run together into it
        hit = [t for t in toks if t in said or (len(t) > 3 and t in squashed)]
        id_hit = e["id"].lower() in said
        if not hit and not id_hit:
            continue
        key = (len(hit) == len(toks) or id_hit, len(hit))
        if best_key is None or key > best_key:
            best, best_key = e, key
    if best is None:
        return None
    if best_key[0]:
        return best
    # Half a name is enough only when those words name nobody else ("namer" is the LLC Namer; "example-game" is two).
    toks = _tokens(best["label"])
    said_toks = [t for t in toks if t in said or (len(t) > 3 and t in squashed)]
    others = {t for e in listing if e is not best for t in _tokens(e["label"])}
    return best if said_toks and not any(t in others for t in said_toks) else None


def is_request(text):
    """True when the words are an on/off ask for a server we know."""
    if OTHER_ASK.search(text) or TEAM_SHAPE.search(text) or len(text.split()) > MAX_WORDS:
        return False
    return action_of(text) is not None and find_server(text) is not None


if __name__ == "__main__":
    t = " ".join(sys.argv[1:])
    print(action_of(t), find_server(t), is_request(t))
