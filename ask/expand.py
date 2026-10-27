"""Add the notes' own words to a question before searching (ask/synonyms.tsv).

<user> says "reload", his notes say "restart"; he says "lore", the note is a "world bible".
Word search can't bridge that, so a tiny hand-kept list adds the notes' words as extra
word-search lines. Cost: under a millisecond. Usage: python3 -I ask/expand.py "<question>".
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "index"))
from structq import document  # noqa: E402

_RULES = None
USE_LEX = os.environ.get("BRAIN_LEX", "0") == "1"   # the word-search line; off since 2026-10-27


def rules():
    global _RULES
    if _RULES is None:
        _RULES = []
        with open(os.path.join(HERE, "synonyms.tsv")) as f:
            for line in f:
                if line.startswith("#") or "\t" not in line:
                    continue
                pat, words = line.rstrip("\n").split("\t", 1)
                _RULES.append((re.compile(pat, re.I), [w.strip() for w in words.split(",") if w.strip()]))
    return _RULES


def extra_words(q):
    out = []
    for pat, words in rules():
        if pat.search(q):
            out += [w for w in words if w.lower() not in q.lower() and w not in out]
    return out


def expanded_document(q, extra=None):
    """One meaning-search line (the question as said) and, when the list knows <user>'s words, a second
    meaning-search line with the notes' words added. No word-search line (BRAIN_LEX=1 brings it back):
    measured 2026-10-27 on the fair test (docs/checkup.md), the word-search line outvoted the meaning
    search and pushed the right note down; without it right-note-first went 7/34 to 12/34 and top 3
    18/34 to 21/34, with no kind of question worse. History: many keyword lines found 14/34 (2026-10-15),
    one keyword line plus meaning search 21/34 then, 18/34 once the notes grew."""
    words = extra_words(q) if extra is None else extra
    out = []
    if USE_LEX:
        key = next((l for l in document(q).splitlines() if l.startswith("lex: ")), None)
        out += [key] if key else []
    out.append(f"vec: {q}")
    if words:
        out.append(f"vec: {q} {' '.join(words)}")
    return "\n".join(out)


def llm_keywords(q, model="qwen2.5:3b", timeout=60):
    """Ask the local writer for 3-5 search keywords (the tried-and-timed option b)."""
    import json
    import time
    import urllib.request
    body = {"model": model, "stream": False, "keep_alive": "5m",
            "options": {"num_ctx": 1024, "temperature": 0, "num_predict": 40},
            "messages": [{"role": "system", "content":
                          "Give 3 to 5 search keywords or short phrases a note answering this question would "
                          "likely contain, including synonyms of the question's words. Comma-separated, nothing else."},
                         {"role": "user", "content": q}]}
    if model.startswith("granite"):
        body["think"] = False
    t = time.time()
    req = urllib.request.Request("http://127.0.0.1:11434/api/chat", json.dumps(body).encode())
    text = json.load(urllib.request.urlopen(req, timeout=timeout))["message"]["content"]
    llm_keywords.last_ms = int((time.time() - t) * 1000)
    words = [w.strip(" .\"'") for w in text.replace("\n", ",").split(",")]
    return [w for w in words if w and len(w) < 40][:5]


if __name__ == "__main__":
    print(expanded_document(" ".join(sys.argv[1:])))
