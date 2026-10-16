"""Rank check for the second brain: for each question, where does the expected note land?

Run: CRABBOX_LOCAL=1 python3 -I index/search_test.py [search|vsearch|query ...]
Prints a markdown table (rank of the expected file per mode, '-' if not in the top 10).
"""
import json, os, subprocess, sys, time, urllib.request

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from structq import document  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "ask"))
from expand import expanded_document, llm_keywords  # noqa: E402
env = dict(os.environ)
env.setdefault("QMD_LLAMA_GPU", "vulkan")
env.setdefault("QMD_EMBED_PARALLELISM", "1")
env["PATH"] = os.path.expanduser("~/.local/share/mise/shims") + ":" + env.get("PATH", "")


def load():
    out = []
    with open(os.path.join(HERE, "search-questions.tsv")) as f:
        for line in f:
            if line.startswith("#") or not line.strip():
                continue
            q, want = line.rstrip("\n").split("\t")
            out.append((q, want.split("|")))
    return out


def rank(mode, q, want):
    t = time.time()
    # Modes: search / vsearch / query are qmd's own; "struct" = query with keywords + question
    # (see structq.py); a "-norerank" suffix skips the re-ranker.
    if mode.startswith("http-"):
        return http_rank(mode[5:], q, want)
    base, _, flag = mode.partition("-")
    args = ["qmd", "query", document(q)] if base == "struct" else ["qmd", base, q]
    args += ["--json", "-n", "10"] + (["--no-rerank"] if flag == "norerank" else [])
    r = subprocess.run(args, capture_output=True, text=True, env=env)
    secs = time.time() - t
    try:
        files = [hit["file"] for hit in json.loads(r.stdout)]
    except json.JSONDecodeError:
        return None, secs, ["ERROR: " + r.stderr.strip()[-200:]]
    ranks = [files.index(w) + 1 for w in want if w in files]
    return (min(ranks) if ranks else None), secs, files[:3]


def http_rank(mode, q, want):
    """Same question through the shared MCP server (the warm one Claude uses):
    http-vec (meaning only) or http-struct (keywords + meaning), each with optional -norerank."""
    base, _, flag = mode.partition("-")
    body = {"limit": 10, "rerank": flag != "norerank"}
    if base in ("struct", "syn", "llm"):
        # syn = + the synonym list (ask/synonyms.tsv); llm = + 3-5 keywords from the local writer
        doc = {"struct": document, "syn": expanded_document,
               "llm": lambda q: expanded_document(q, llm_keywords(q))}[base](q)
        if base == "llm":
            print(f"  (writer keywords {llm_keywords.last_ms} ms: {doc.splitlines()[2:]})", file=sys.stderr)
        body["searches"] = [dict(zip(("type", "query"), line.split(": ", 1))) for line in doc.splitlines()]
    elif base == "vec":
        body["searches"] = [{"type": "vec", "query": q}]
    else:
        raise SystemExit(f"unknown http mode {mode}")
    req = urllib.request.Request("http://localhost:8181/query", json.dumps(body).encode(),
                                 {"content-type": "application/json"})
    t = time.time()
    try:
        files = [hit["file"] for hit in json.load(urllib.request.urlopen(req, timeout=600))["results"]]
    except Exception as e:  # noqa: BLE001
        return None, time.time() - t, [f"ERROR: {e}"]
    ranks = [files.index(w) + 1 for w in want if w in files]
    return (min(ranks) if ranks else None), time.time() - t, files[:3]


def main():
    modes = sys.argv[1:] or ["search", "vsearch", "query"]
    qs = load()
    print("| # | Question | Expected | " + " | ".join(modes) + " |")
    print("|---|---|---|" + "---|" * len(modes))
    top3 = {m: 0 for m in modes}
    times = {m: 0.0 for m in modes}
    misses = []
    for i, (q, want) in enumerate(qs, 1):
        cells = []
        for m in modes:
            rk, secs, top = rank(m, q, want)
            times[m] += secs
            if rk and rk <= 3:
                top3[m] += 1
            else:
                misses.append((m, q, top))
            cells.append(str(rk) if rk else "-")
        shown = " or ".join(f"`{w.removeprefix('qmd://')}`" for w in want)
        print(f"| {i} | {q} | {shown} | " + " | ".join(cells) + " |")
    print()
    for m in modes:
        print(f"- **{m}**: {top3[m]}/{len(qs)} in the top 3, {times[m] / len(qs):.1f} s per question on average")
    if misses:
        print("\nMisses (what came first instead):\n")
        for m, q, top in misses:
            print(f"- {m}, \"{q}\": " + ", ".join(f"`{f.removeprefix('qmd://')}`" for f in top))


main()
