"""The one check of the private names list (private.json) before anything goes to an online model (the second decider, Haiku).

`problem(path)` is None when the file is fine or not there at all (a missing file stays as it was), and plain words
when the file is there but empty, broken, unreadable or of the wrong shape. Then the caller sends nothing online
(<user>'s lesson 6: if unsure, nothing gets sent). It never prints or returns what is in the file.

Used by brain_decide.py (the second decider), ask/ask.py and ask/haiku_standby.py (Haiku), deciders/tools/haiku.py (the example
makers) and eval/checkup.py (the warning). Standard library only.
"""
import json
import os
import re
import unicodedata

SEND_NOTE = "Nothing is sent to any online model until it is fixed."


def _usable(text):
    """True when the filter (decider/names.py) would keep this text as a name: after the accents and invisible
    characters are folded away, 2 or more letters and digits are left (it splits on everything else)."""
    t = unicodedata.normalize("NFKD", text)
    t = "".join(c for c in t if not unicodedata.combining(c) and unicodedata.category(c) != "Cf")
    return len(re.sub(r"[^a-z0-9]+", "", t.lower())) >= 2


def _names_in(data):
    """True when the list holds at least one usable name: a word in `words`, or any other top-level text whose key
    does not start with "_" (`partner`, `kid`)."""
    others = [v for k, v in data.items() if k != "words" and isinstance(v, str) and not k.startswith("_")]
    return any(_usable(w) for w in data.get("words", [])) or any(_usable(v) for v in others)


def load(path):
    """(data, problem): the list as a dict and None when it is fine; ({}, None) when there is no file; ({}, plain
    words) when the file is empty, broken, unreadable or of the wrong shape."""
    home = os.path.expanduser("~")
    shown = str(path)
    if shown.startswith(home + os.sep):
        shown = "~" + shown[len(home):]
    label = "The private names list (%s)" % shown
    try:
        with open(path) as f:
            text = f.read()
    except FileNotFoundError:
        return {}, None
    except (OSError, ValueError):   # ValueError: bytes that are not text
        return {}, "%s can't be read. %s" % (label, SEND_NOTE)
    if not text.strip():
        return {}, "%s is empty. %s" % (label, SEND_NOTE)
    try:
        data = json.loads(text)
    except ValueError:
        return {}, "%s is broken (it is not valid JSON, maybe a stray comma). %s" % (label, SEND_NOTE)
    if not isinstance(data, dict) or not isinstance(data.get("words", []), list) \
            or not all(isinstance(w, str) for w in data.get("words", [])):
        return {}, ("%s has the wrong shape (it must be an object whose 'words' is a list of words). %s"
                    % (label, SEND_NOTE))
    if not _names_in(data):
        return {}, "%s has no usable names in it. %s" % (label, SEND_NOTE)
    return data, None


def problem(path):
    """Plain words about what is wrong with the private names list at `path`, or None (fine, or no file)."""
    return load(path)[1]
