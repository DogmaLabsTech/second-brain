"""Turn a plain question into a qmd query document: keywords for word search, the question for meaning search.

qmd's word search needs every word to match, so long questions ("how much does ... cost") find
nothing. Dropping the filler words fixes that; the full question still goes to meaning search.
Usage: python3 -I index/structq.py "<question>"  -> prints the query document.
"""
import re, sys

STOP = set("""a about after again all am an and any are as at be been before being but by can could
did do does doing done for from get gets got had has have how i if in into is it its just me my
no not of on or our so some than that the their them then there these they this to too up us was
we were what when where which who whom why will with would you your yours left much many""".split())


def keywords(q):
    words = re.findall(r"[^\W_][\w.-]*", q)   # letters and digits of any language (café, Zürich), not only a-z
    keep = [w for w in words if w.lower() not in STOP and len(w) > 1]
    return " ".join(keep) or q


def document(q):
    """Meaning search on the whole question, word search on all keywords together, and on each
    neighbouring pair of keywords (qmd's word search needs every word, so pairs still match a
    note that uses only some of them). qmd fuses all the lists."""
    q = " ".join(q.split())
    if not q:
        return ""   # nothing to search for: no empty "vec:" and "lex:" lines
    words = keywords(q).split()
    lines = [f"vec: {q}", f"lex: {' '.join(words)}"]
    if len(words) > 2:
        lines += [f"lex: {a} {b}" for a, b in zip(words, words[1:])][:8]
    return "\n".join(lines)


if __name__ == "__main__":
    text = document(" ".join(sys.argv[1:]))
    if not text:
        print("usage: structq.py <question>", file=sys.stderr)
        sys.exit(2)
    print(text)
