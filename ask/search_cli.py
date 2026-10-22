"""brain search: the same notes `brain ask` would use (newer-first), as "path — snippet" lines.
With BRAIN_SEARCH_SCORES=1 each line starts with the note's score and a tab ("0.718<TAB>path — snippet"), so a caller
(agent-os `think`) can drop weak hits. The scores are rank-based (1, 1/2, 1/3 … with a boost for new notes), not a
measure of how well a note fits."""
import os
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ask  # noqa: E402


def lines(hits, scores=False):
    return [("%.3f\t" % float(h.get("score") or 0) if scores else "")
            + f"{ask.short_path(h['path'])} — {h['snippet'][:160]}" for h in hits]


if __name__ == "__main__":
    for line in lines(ask.search(" ".join(sys.argv[1:])), os.environ.get("BRAIN_SEARCH_SCORES") == "1"):
        print(line)
