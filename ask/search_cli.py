"""brain search: the same notes `brain ask` would use (newer-first), as "path — snippet" lines.
With BRAIN_SEARCH_SCORES=1 each line starts with the note's score and a tab ("0.718<TAB>path — snippet"), so a caller
(agent-os `think`) can drop weak hits. The scores are rank-based (1, 1/2, 1/3 … with a boost for new notes), not a
measure of how well a note fits.
Each search also writes a "from": "cli" line to the search record (ask/searchlog.py), naming the chat or program that
ran it (searchlog.caller). It leaves out the private section unless the Deck or Obsidian ran it (ask.private_hidden,
ask.HIDE_PRIVATE)."""
import os
import sys
import time

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ask  # noqa: E402
import searchlog  # noqa: E402
from expand import expanded_document  # noqa: E402


def lines(hits, scores=False):
    return [("%.3f\t" % float(h.get("score") or 0) if scores else "")
            + f"{ask.short_path(h['path'])} — {h['snippet'][:160]}" for h in hits]


def search(q):
    """ask.search, and its line in the search record (the search lines are the same ones ask.search sends)."""
    t0 = time.monotonic()
    hits = ask.search(q)
    try:
        sent = [dict(zip(("type", "query"), l.split(": ", 1))) for l in expanded_document(q).splitlines()]
    except Exception:  # noqa: BLE001  the record must never break a search
        sent = []
    searchlog.record(searchlog.cli_line(q, sent, hits, round((time.monotonic() - t0) * 1000), searchlog.caller("brain search")))
    return hits


def main():
    ask.HIDE_PRIVATE = ask.private_hidden()   # only the Deck or Obsidian get them
    for line in lines(search(" ".join(sys.argv[1:])), os.environ.get("BRAIN_SEARCH_SCORES") == "1"):
        print(line)


if __name__ == "__main__":
    main()
