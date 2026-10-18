"""Chat search vs the island's search, on the fair test (eval/heldout.jsonl).

Asks every fair-test question through the `brain` MCP `query` tool the way a Claude chat does (one lex line of
key words + one vec line with the question, rerank off, as ~/.claude/CLAUDE.md says), and through the island's
own search (ask.search), and prints right note first / in the top 3 for each.

  python3 -I eval/chat_search_test.py [--url http://localhost:8181] [--plain]

--plain also tries the tool's plain `query` mode (qmd expands it itself; slow, loads its expansion model).
"""
import json
import os
import sys
import urllib.request

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path[:0] = [os.path.join(ROOT, "ask"), os.path.join(ROOT, "index")]
import ask  # noqa: E402
from structq import keywords  # noqa: E402

HOME = os.path.expanduser("~")


def mcp_query(url, args):
    body = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "query", "arguments": args}}
    req = urllib.request.Request(url + "/mcp", json.dumps(body).encode(),
                                 {"content-type": "application/json", "accept": "application/json, text/event-stream"})
    raw = urllib.request.urlopen(req, timeout=180).read().decode()
    if raw.lstrip().startswith("event:") or raw.lstrip().startswith("data:"):
        raw = "".join(l[5:].strip() for l in raw.splitlines() if l.startswith("data:"))
    res = json.loads(raw)["result"]["structuredContent"]["results"]
    return [ask.real_path("qmd://" + r["file"]).replace(HOME, "~") for r in res]


def chat_style(url, q):
    return mcp_query(url, {"searches": [{"type": "lex", "query": keywords(q)}, {"type": "vec", "query": q}],
                           "limit": 5, "rerank": False})


def plain(url, q):
    return mcp_query(url, {"query": q, "limit": 5})


def island(_url, q):
    return [h["path"].replace(HOME, "~") for h in ask.search(q)]


def score(rows, fn, url):
    top1 = top3 = n = 0
    misses = []
    for r in rows:
        if r["use"] == "missing":
            continue
        got = fn(url, r["q"])
        rank = next((i for i, p in enumerate(got) if p in set(r["expect_paths"])), None)
        n += 1
        top1 += rank == 0
        if rank is not None and rank < 3:
            top3 += 1
        else:
            misses.append(r["id"])
    return top1, top3, n, misses


def main(argv):
    url = argv[argv.index("--url") + 1] if "--url" in argv else "http://localhost:8181"
    with open(os.path.join(HERE, "heldout.jsonl")) as f:
        rows = [json.loads(l) for l in f if l.strip()]
    ways = [("chat (lex + vec)", chat_style), ("island", island)]
    if "--plain" in argv:
        ways.insert(1, ("chat (plain query)", plain))
    for name, fn in ways:
        t1, t3, n, miss = score(rows, fn, url)
        print(f"{name:20} first {t1}/{n}  top 3 {t3}/{n}  misses: {' '.join(miss)}")


if __name__ == "__main__":
    main(sys.argv[1:])
