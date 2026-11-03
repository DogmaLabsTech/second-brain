"""brain drafts: the check-up's drafts for <user> to keep or drop (t12, <user>'s yes 2026-10-22).

  brain drafts                         list what waits: draft test questions and draft lore stories
  brain drafts run [--days N]          make this week's drafts now (the weekly check-up does this by itself)
  brain drafts keep <id> [note ...] [--use KIND] [--answer "text"]
                                       a draft test question -> the tuning set (eval/seen.jsonl). It needs the note
                                       (or notes) that should answer it; name them here or fill them in the draft file.
  brain drafts keep <story>            a draft lore story -> agent-os lore/ as `insight`, with its line in lore/CONTEXT.md
  brain drafts keep <draft> --to projects/<repo>/lessons [--files a,b] [--pin] [--summary "line"]
                                       a memory draft (rule or lesson) -> the store ~/brain/agents, committed
                                       there (eval/memory_keep.py)
  brain drafts drop <id|story>         throw a draft away; it is not drafted again

What the check-up drafts, from the week's asks (ask/asklog.py) and misses (deciders/tools/learn_misses.py):
  signals    a 👎; a likely miss the router was not to blame for (misses.jsonl, status not-router); the same question
             asked 3+ times in 7 days or again within 10 minutes (the first answer probably failed); a job card
             declined or a job that failed (outcomes.jsonl)
  eval case  one heldout-shaped line per question that had a signal, in drafts/eval-YYYY-MM-DD.jsonl, with
             `expect_paths` empty. It goes to the TUNING set (eval/seen.jsonl) on a keep, never to heldout.jsonl.
             Job asks are counted but get no line: they are not search questions.
  lore       when the same cause shows up twice, or one signal fits a theme of the insights report (THEMES), a story
             in agent-os lore/drafts/<slug>.md with `standing: observation`
  rate       up to 3 answers that were asked again within 10 minutes and that <user> has not rated, with one-press
             `brain rate <id> up|down` lines. The check-up marks each of them 👎 on its own (`auto_rate`, why "auto: asked
             again within 10 minutes"; the only thing here that writes outside the drafts folders: ratings.jsonl). His
             own rating is never touched and a later `up` of his wins.

Rules: the check-up writes only inside the two drafts folders. It never writes lore/, heldout.jsonl, seen.jsonl or
synonyms.tsv; only a keep does, and only <user> runs that. Every draft text goes through decider's names filter
(decider/names.py) first; when the filter is not sure, the draft is skipped and only counted. Nothing here calls a model.

Folders: drafts/ is ~/.local/state/second-brain/drafts (BRAIN_DRAFTS); lore is ~/agent-os/lore (AGENT_OS_LORE) and its
drafts/ folder must already exist (it ships with a CONTEXT.md).
"""
import json
import os
import re
import sys
import tempfile
import time

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "ask"))
import asklog  # noqa: E402

HOME = os.path.expanduser("~")
DECIDER_REPO = os.path.expanduser(os.environ.get("DECIDER_REPO", "~/projects/decider"))
SKIP_FROM = {"cli", "checkup"}   # test runs and the check-up's own questions are not <user> asking (as in learn_misses.py)
REPEAT_COUNT = 3                 # the same question this many times in the window ...
REPEAT_GAP_S = 600               # ... or again within this many seconds
RATE_OFFERS = 3
USES = ("decided", "howto", "business", "chats", "missing", "newer")
FORMAT = "%Y-%m-%dT%H:%M:%S"
# The insights report's repeat problems (~/.claude/usage-data/next-session-reminder.md, 2026-10-21): a signal whose
# words fit one is worth a story on its own.
THEMES = (
    ("usage-limits", "briefs cut off by usage limits", r"usage limit|rate limit|ran out of (usage|tokens)|checkpoint"),
    ("permission-blocks", "permission blocks stall jobs", r"permission|not allowed|unsafe agent|allow rule"),
    ("worker-bugs", "worker first-pass fixes had bugs", r"flaky|miscount|merged before|review round"),
    ("privacy-leak", "private names reached a model", r"family name|private name|names? (filter|leak)|\[name"),
    ("testbox-busy", "the test machine was busy or timed out", r"\btestbox\b|crabbox|queue|timed? ?out"),
    ("wrong-recipient", "a closing note went to the wrong recipient", r"wrong recipient|closing note"),
    ("jargon", "jargon or over-complication", r"jargon|plain words|tailscale|firewall"),
    ("missing-tools", "the same fix said twice, no tool for it", r"\bhook\b|custom skill|headless|lock.and.retry"),
)


class Unsure(Exception):
    """The names filter could not make the text safe for sure: do not write it."""


# ---------- folders ----------

def drafts_dir():
    return os.path.expanduser(os.environ.get("BRAIN_DRAFTS") or os.path.join(asklog.STATE, "drafts"))


def lore_dir():
    return os.path.expanduser(os.environ.get("AGENT_OS_LORE") or "~/agent-os/lore")


def lore_drafts_dir():
    return os.path.join(lore_dir(), "drafts")


def seen_path():
    return os.path.join(HERE, "seen.jsonl")


def _inside(root, path):
    """The path itself, after checking it sits inside root (so a draft can never be written anywhere else)."""
    root, real = os.path.realpath(root), os.path.realpath(path)
    if os.path.commonpath([root, real]) != root or real == root:
        raise ValueError("refusing to write outside %s: %s" % (root, path))
    return path


def _write(root, path, text):
    """Write a whole file inside root without a half-written moment."""
    _inside(root, path)
    os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), prefix=".draft-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def _read_jsonl(path):
    try:
        with open(path, encoding="utf-8") as f:
            return [json.loads(l) for l in f if l.strip()]
    except FileNotFoundError:
        return []


def _jsonl(rows):
    return "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)


# ---------- the names filter ----------

def _names():
    if DECIDER_REPO not in sys.path:
        sys.path.append(DECIDER_REPO)
    from decider import names
    return names


def scrub(text):
    """The text with every private name swapped for [NAME]. Raises Unsure when the filter is missing or not sure."""
    try:
        return _names().scrub(text)
    except Exception as why:  # noqa: BLE001 - names.Unsafe, no filter, no list: never write
        raise Unsure(type(why).__name__) from None


# ---------- the week's signals ----------

def norm(q):
    return " ".join(re.sub(r"[^a-z0-9 ]", " ", (q or "").lower()).split())


def _words(q):
    return {w for w in norm(q).split() if len(w) > 2}


def _ts(row):
    return time.mktime(time.strptime(row["at"], FORMAT))


def _since(days, now):
    return time.strftime(FORMAT, time.localtime(now - days * 86400))


def _repeats(asks):
    """Ids of the first ask of each question that was asked 3+ times, or twice within 10 minutes."""
    groups = {}
    for a in asks:
        if a.get("kind") == "answer" and norm(a.get("q")):
            groups.setdefault(norm(a["q"]), []).append(a)
    out = set()
    for g in groups.values():
        g.sort(key=_ts)
        if len(g) >= REPEAT_COUNT or any(_ts(b) - _ts(a) <= REPEAT_GAP_S for a, b in zip(g, g[1:])):
            out.add(g[0]["id"])
    return out


def gather(asks, ratings, outcomes, misses, days=7, now=None):
    """{ask id: signal} for the week. A signal: id, q, kind, why (labels), found, sources, job, detail."""
    now = now or time.time()
    since = _since(days, now)
    by_id = {a["id"]: a for a in asks}
    week = [a for a in asks if a.get("at", "") >= since and a.get("from") not in SKIP_FROM]
    out = {}

    def add(qid, label, detail=""):
        a = by_id.get(qid)
        if not a:
            return
        s = out.setdefault(qid, {"id": qid, "q": a.get("q") or "", "kind": a.get("kind"), "why": [],
                                 "found": a.get("found", True), "sources": a.get("sources") or [],
                                 "job": a.get("job"), "answer": a.get("answer") or "", "detail": ""})
        if label not in s["why"]:
            s["why"].append(label)
        s["detail"] = (s["detail"] + " " + detail).strip()

    votes = {}
    for r in ratings:
        if r.get("at", "") >= since:
            votes[r["id"]] = r   # the newest vote of an ask wins
    for qid, r in votes.items():
        if r.get("verdict") == "down":
            add(qid, "down", r.get("why") or "")
    for m in misses:
        if m.get("status") == "not-router" and m.get("at", "") >= since and m.get("from") not in SKIP_FROM:
            add(m["id"], "miss")
    for qid in _repeats(week):
        add(qid, "repeat")
    for o in outcomes:
        if o.get("at", "") >= since and o.get("what") in ("declined", "job-failed"):
            add(o["id"], o["what"], o.get("detail") or "")
    return out


def cause(sig):
    """Why it went wrong, in a word: job:<id>:declined|failed, answer:not-found, answer:down|miss|repeat."""
    if sig["kind"] == "job":
        return "job:%s:%s" % (sig["job"] or "?", "declined" if "declined" in sig["why"] else "failed")
    if sig["found"] is False:
        return "answer:not-found"
    return "answer:" + next((w for w in ("down", "miss", "repeat") if w in sig["why"]), "wrong")


def theme_of(sig):
    text = " ".join([sig["q"], sig["answer"], sig["detail"]]).lower()
    return next((t for t in THEMES if re.search(t[2], text)), None)


def guess_use(q):
    q = norm(q)
    if re.match(r"(what|why) (did|have) we (decide|pick|choose|agree)|decided|did we decide", q):
        return "decided"
    return "howto"


# ---------- eval drafts ----------

def _existing_eval(decided):
    """({id}, {normalised question}) of everything already drafted, kept (seen.jsonl) or dropped."""
    ids, qs = {d["id"] for d in decided}, {d["normq"] for d in decided if d.get("normq")}
    for f in _draft_files():
        for r in _read_jsonl(f):
            ids.add(r["id"])
            qs.add(norm(r["q"]))
    for r in _read_jsonl(seen_path()):
        qs.add(norm(r.get("q")))
        ids.add(r.get("source", "").replace("ask ", "d-", 1))
    return ids, qs


def _draft_files():
    d = drafts_dir()
    try:
        return sorted(os.path.join(d, f) for f in os.listdir(d) if re.fullmatch(r"eval-\d{4}-\d{2}-\d{2}\.jsonl", f))
    except FileNotFoundError:
        return []


def _decided():
    return _read_jsonl(os.path.join(drafts_dir(), "decided.jsonl"))


def _note_decided(entry):
    path = os.path.join(drafts_dir(), "decided.jsonl")
    _write(drafts_dir(), path, _jsonl(_decided() + [dict(entry, at=time.strftime(FORMAT))]))


LABELS = {"down": "👎", "miss": "likely miss", "repeat": "asked again", "declined": "declined", "job-failed": "job failed"}


def eval_drafts(signals, decided, today):
    """(new draft lines, skipped by the names filter, already drafted). Writes nothing."""
    ids, qs = _existing_eval(decided)
    new, skipped, old = [], 0, 0
    for sig in sorted(signals.values(), key=lambda s: s["id"]):
        if sig["kind"] != "answer":
            continue
        if "d-" + sig["id"] in ids or norm(sig["q"]) in qs:
            old += 1
            continue
        try:
            q = scrub(sig["q"])
            used = [scrub(p) for p in sig["sources"]]
        except Unsure:
            skipped += 1
            continue
        qs.add(norm(sig["q"]))
        new.append({"id": "d-" + sig["id"], "use": guess_use(q), "q": q, "expect_paths": [], "expect_answer": "",
                    "stale_paths": [], "from": "check-up %s: %s" % (today, ", ".join(LABELS[w] for w in sig["why"])),
                    "source": "ask " + sig["id"], "signals": sig["why"],
                    "notes_used": [p.replace(HOME, "~") for p in used]})
    return new, skipped, old


# ---------- lore drafts ----------

def _slug(key):
    return "checkup-" + re.sub(r"[^a-z0-9]+", "-", key.lower()).strip("-")


def lore_groups(signals):
    """{key: [signals]} where a story is worth drafting: a cause seen twice, or one signal that fits a theme."""
    by_cause, by_theme, themes = {}, {}, {}
    for sig in signals.values():
        by_cause.setdefault(cause(sig), []).append(sig)
        t = theme_of(sig)
        if t:
            by_theme.setdefault(t[0], []).append(sig)
            themes[t[0]] = t
    out = {k: v for k, v in by_cause.items() if len(v) >= 2}
    out.update({k: v for k, v in by_theme.items()})
    return out, themes


def _story(key, group, theme, today):
    what = theme[1] if theme else key
    asked = "\n".join("- \"%s\" (%s)" % (s["q"][:140], ", ".join(LABELS[w] for w in s["why"])) for s in group[:5])
    return (
        "---\nstanding: observation\n"
        "draft: made by the check-up on %s from %d signal(s); not a lesson until <user> keeps it (`brain drafts keep|drop %s`)\n"
        "lesson-line: %s: still to be written by the librarian.\n---\n"
        "# Draft: %s\n\n"
        "**The ask.** %d asks this week went wrong the same way (%s):\n%s\n\n"
        "**The choice.** Not known yet. The librarian fills in what was chosen and why.\n\n"
        "**What happened.** Not known yet. Look the asks up with `brain log`; the ids are in the sources.\n\n"
        "**The lesson.** Not written yet.\n\n"
        "**Where the fix lives.** Not known yet.\n\n"
        "Sources: asks %s (asks.jsonl), check-up %s.\n"
    ) % (today, len(group), _slug(key), what.capitalize(), what, len(group), key, asked,
         ", ".join(s["id"] for s in group), today)


def lore_new(signals, decided, today):
    """([(slug, text)] new, skipped by the names filter). Writes nothing. Needs agent-os lore/drafts/ to exist."""
    if not os.path.isdir(lore_drafts_dir()):
        return [], 0
    groups, themes = lore_groups(signals)
    have = {d["id"] for d in decided}
    have |= {f[:-3] for f in os.listdir(lore_drafts_dir()) if f.endswith(".md")}
    have |= {f[:-3] for f in os.listdir(lore_dir()) if f.endswith(".md")}
    new, skipped = [], 0
    for key, group in sorted(groups.items()):
        slug = _slug(key)
        if slug in have:
            continue
        try:
            new.append((slug, scrub(_story(key, group, themes.get(key), today))))
        except Unsure:
            skipped += 1
    return new, skipped


# ---------- rate offers ----------

AUTO_WHY = "auto: asked again within 10 minutes"


def asked_again(asks, ratings, days=7, now=None, auto_open=False):
    """The week's answers that were asked again (same words, or half the words, within 10 minutes) from the same
    place, oldest first: the first answer probably failed. Only ones <user> has not rated; `auto_open` also keeps
    the ones whose newest rating is the check-up's own auto mark (AUTO_WHY)."""
    now = now or time.time()
    since = _since(days, now)
    newest = {}
    for r in ratings:
        newest[r["id"]] = r   # the newest vote of an ask wins
    rated = {i for i, r in newest.items() if not (auto_open and r.get("why") == AUTO_WHY)}
    week = sorted((a for a in asks if a.get("at", "") >= since and a.get("from") not in SKIP_FROM), key=_ts)
    out = []
    for i, a in enumerate(week):
        if a.get("kind") != "answer" or a["id"] in rated:
            continue
        wa = _words(a.get("q"))
        for b in week[i + 1:]:
            if _ts(b) - _ts(a) > REPEAT_GAP_S:
                break
            wb = _words(b.get("q"))
            if b.get("from") == a.get("from") and (norm(a["q"]) == norm(b.get("q")) or
                                                    (wa and wb and len(wa & wb) / len(wa | wb) >= 0.5)):
                out.append(a)
                break
    return out


def auto_rate(days=7, now=None):
    """Mark every unrated answer that was asked again within 10 minutes as a 👎 (why: AUTO_WHY), so the check-up
    counts it without <user> pressing anything. A rating of his own is never touched (only unrated asks are marked),
    his later `brain rate <id> up` wins (the newest vote counts), and running again marks nothing twice.
    Returns the marked asks."""
    marked = asked_again(asklog.read(asklog.ASKS), asklog.read(asklog.RATINGS), days, now)
    for a in marked:
        asklog.rate(a["id"], "down", AUTO_WHY)
    return marked


def rate_offers(asks, ratings, days=7, now=None):
    """Up to 3 newest answers that were asked again and have no rating of <user>'s (unrated, or only auto-marked by
    the check-up), so a press can still say the first answer was fine."""
    out = asked_again(asks, ratings, days, now, auto_open=True)
    offers = []
    for a in out[-RATE_OFFERS:][::-1]:
        try:
            q = scrub(a["q"])
        except Unsure:
            q = None   # the id alone: `brain log` shows the words
        offers.append({"id": a["id"], "q": q})
    return offers


# ---------- run ----------

def run(days=7, now=None, today=None):
    """Make this week's drafts (only inside the two drafts folders). Returns the report for `lines`."""
    now = now or time.time()
    today = today or time.strftime("%Y-%m-%d", time.localtime(now))
    asks, ratings = asklog.read(asklog.ASKS), asklog.read(asklog.RATINGS)
    outcomes = asklog.read(asklog.OUTCOMES)
    misses = _read_jsonl(os.path.join(asklog.STATE, "misses.jsonl"))
    signals = gather(asks, ratings, outcomes, misses, days, now)
    decided = _decided()
    new_eval, eval_skipped, _ = eval_drafts(signals, decided, today)
    new_lore, lore_skipped = lore_new(signals, decided, today)
    if new_eval:
        path = os.path.join(drafts_dir(), "eval-%s.jsonl" % today)
        _write(drafts_dir(), path, _jsonl(_read_jsonl(path) + new_eval))
    for slug, text in new_lore:
        _write(lore_drafts_dir(), os.path.join(lore_drafts_dir(), slug + ".md"), text)
    count = {}
    for s in signals.values():
        for w in s["why"]:
            count[w] = count.get(w, 0) + 1
    return {"signals": count, "eval_new": len(new_eval), "lore_new": [s for s, _ in new_lore],
            "skipped": eval_skipped + lore_skipped, "waiting": waiting(),
            "offers": rate_offers(asks, ratings, days, now)}


def waiting():
    return {"eval": sum(len(_read_jsonl(f)) for f in _draft_files()), "lore": len(lore_list())}


def lines(report):
    """The check-up's drafts block: [] when there is nothing to say."""
    w, sig = report["waiting"], report["signals"]
    if not (sig or w["eval"] or w["lore"] or report["offers"] or report["skipped"]):
        return []
    out = ["Drafts for <user> (none of these is a lesson or a test question until he keeps it):"]
    out.append("  signals: " + (", ".join("%d %s" % (n, LABELS[k]) for k, n in sorted(sig.items())) or "none"))
    out.append("  new: %d test questions, %d lore stories%s" % (
        report["eval_new"], len(report["lore_new"]),
        "; %d skipped, the names filter was not sure" % report["skipped"] if report["skipped"] else ""))
    if w["eval"] or w["lore"]:
        out.append("  waiting: %d test questions, %d lore stories: `brain drafts`" % (w["eval"], w["lore"]))
    if report["offers"]:
        out.append("  Asked again within 10 minutes and not rated by you (marked 👎 on its own; press up if the first answer was fine):")
        for o in report["offers"]:
            out.append("    brain rate %s up|down" % o["id"] + ("   \"%s\"" % o["q"][:80] if o["q"] else ""))
    return out


# ---------- list, keep, drop ----------

def lore_list():
    d = lore_drafts_dir()
    try:
        return sorted(f[:-3] for f in os.listdir(d) if f.endswith(".md") and f != "CONTEXT.md")
    except FileNotFoundError:
        return []


def _front(text):
    """({key: value} of the front matter, the text after it)."""
    m = re.match(r"---\n(.*?)\n---\n", text, re.S)
    if not m:
        return {}, text
    meta = {}
    for line in m.group(1).splitlines():
        key, sep, value = line.partition(":")
        if sep:
            meta[key.strip()] = value.strip()
    return meta, text[m.end():]


def _find_eval(draft_id):
    for f in _draft_files():
        rows = _read_jsonl(f)
        for r in rows:
            if r["id"] == draft_id:
                return f, rows, r
    return None, None, None


def listing():
    out = []
    for f in _draft_files():
        for r in _read_jsonl(f):
            have = "notes it used: " + ", ".join(os.path.basename(p) for p in r.get("notes_used", [])) \
                if r.get("notes_used") else "no notes were used"
            out.append("  %s  \"%s\"  (%s; %s)%s" % (r["id"], r["q"][:90], r["from"].split(": ", 1)[-1], have,
                                                   "" if r["expect_paths"] else "  needs its note"))
    for slug in lore_list():
        with open(os.path.join(lore_drafts_dir(), slug + ".md"), encoding="utf-8") as fh:
            meta, _ = _front(fh.read())
        out.append("  %s  (lore story) %s" % (slug, meta.get("lesson-line", "")[:100]))
    return out or ["  nothing waits"]


def keep_eval(draft_id, paths=(), use=None, answer=None):
    f, rows, r = _find_eval(draft_id)
    if not r:
        raise KeyError(draft_id)
    paths = [p.replace(HOME, "~", 1) if p.startswith(HOME) else p for p in (paths or r["expect_paths"])]
    if not paths:
        raise ValueError("say which note answers it: brain drafts keep %s <note path> ..." % draft_id)
    gone = [p for p in paths if not os.path.exists(os.path.expanduser(p))]
    if gone:
        raise ValueError("no such note: " + ", ".join(gone))
    use = use or r["use"]
    if use not in USES:
        raise ValueError("kind of question: one of " + ", ".join(USES))
    seen = _read_jsonl(seen_path())
    nums = [int(m.group(1)) for s in seen for m in [re.fullmatch(r"s(\d+)", s.get("id", ""))] if m]
    row = {"id": "s%02d" % (max(nums, default=0) + 1), "use": use, "q": r["q"], "expect_paths": paths,
           "expect_answer": answer if answer is not None else r["expect_answer"], "stale_paths": r["stale_paths"],
           "from": r["from"], "source": r["source"]}
    with open(seen_path(), "a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    _drop_eval(f, rows, r, "kept as " + row["id"])
    return row["id"]


def _drop_eval(f, rows, r, action):
    rest = [x for x in rows if x["id"] != r["id"]]
    if rest:
        _write(drafts_dir(), f, _jsonl(rest))
    else:
        os.unlink(_inside(drafts_dir(), f))
    _note_decided({"id": r["id"], "normq": norm(r["q"]), "action": action})


def keep_lore(slug):
    src = os.path.join(lore_drafts_dir(), slug + ".md")
    with open(_inside(lore_drafts_dir(), src), encoding="utf-8") as fh:
        meta, body = _front(fh.read())
    dest = os.path.join(lore_dir(), slug + ".md")
    if os.path.exists(dest):
        raise ValueError("lore/%s.md is already there" % slug)
    row = "| `%s.md` | %s |\n" % (slug, meta.get("lesson-line", slug))
    ctx = os.path.join(lore_dir(), "CONTEXT.md")
    with open(ctx, encoding="utf-8") as fh:
        rows = fh.read().splitlines(keepends=True)
    last = max((i for i, l in enumerate(rows) if l.startswith("| `")), default=len(rows) - 1)
    rows.insert(last + 1, row if rows[last].endswith("\n") else "\n" + row)
    _write(lore_dir(), dest, "---\nstanding: insight\n---\n" + body)
    _write(lore_dir(), ctx, "".join(rows))
    os.unlink(src)
    _note_decided({"id": slug, "action": "kept as lore"})


def drop(name):
    f, rows, r = _find_eval(name)
    if r:
        return _drop_eval(f, rows, r, "dropped")
    src = os.path.join(lore_drafts_dir(), name + ".md")
    if not os.path.isfile(src):
        raise KeyError(name)
    os.unlink(_inside(lore_drafts_dir(), src))
    _note_decided({"id": name, "action": "dropped"})


def _flag(argv, name):
    if name not in argv:
        return None
    i = argv.index(name)
    value = argv[i + 1] if i + 1 < len(argv) else ""
    del argv[i:i + 2]
    return value


def main(argv):
    argv = list(argv)
    cmd = argv.pop(0) if argv else "list"
    try:
        if cmd == "list":
            print("Waiting for <user>:\n" + "\n".join(listing()))
        elif cmd == "run":
            days = int(_flag(argv, "--days") or 7)
            print("\n".join(lines(run(days)) or ["nothing to draft"]))
        elif cmd == "keep" and argv and (to := _flag(argv, "--to")) is not None:
            sys.path.insert(0, HERE)   # python3 -I (bin/brain) leaves the script's own folder off the path
            import memory_keep   # a memory draft -> the store (eval/memory_keep.py)
            return memory_keep.cli(argv, to)
        elif cmd == "keep" and argv:
            use, answer = _flag(argv, "--use"), _flag(argv, "--answer")
            name = argv.pop(0)
            if name in lore_list():
                keep_lore(name)
                print("kept as lore/%s.md (insight); its line is in lore/CONTEXT.md. Commit it in agent-os." % name)
            else:
                print("kept as %s in eval/seen.jsonl (the tuning set). Commit it in second-brain." % keep_eval(name, argv, use, answer))
        elif cmd == "drop" and argv:
            drop(argv[0])
            print("dropped " + argv[0])
        else:
            print(__doc__.split("\n\n")[0], file=sys.stderr)
            return 2
    except (KeyError, ValueError, OSError) as why:
        print("brain drafts: %s" % (("no draft called %s" % why) if isinstance(why, KeyError) else why), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
