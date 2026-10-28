#!/usr/bin/env python3
"""Prototype server: static files + /note?id=N + /search?q= (06 Ask: `brain search`, read-only, X-Deck: 1).
GET reads the real note file (collection folder from ~/.config/qmd/index.yml + note path), falling back to the
search index copy (read-only). POST saves an edited note: only an existing .md file inside its collection folder,
only if it did not change since it was loaded (hash), with a backup copy first and an atomic write.
Loopback only. No CORS headers (other sites can't read it), a Host check against DNS rebinding, and POST needs the
X-Deck: 1 header plus a JSON body (a plain web form can't send either).
Folders (the second-brain viz/ build): the page files are web/ (served at /, the Deck is /deck.html); the private data stays
out of git: GET /data.js reads ~/.local/share/second-brain/viz/data.js (DECK_DATA overrides), the talk log is
~/.local/state/second-brain/talk-log.jsonl (DECK_TALK_LOG overrides).
Test mode: DECK_TEST_MAP=<file.yml> replaces the collection folders (e.g. {computer: /tmp/x}); DECK_PORT changes the port.
Talking (07 Voice panel), the voice island's way (~/.config/omarchy/plugins/user.brain-island/bin: listen, ask, say, job),
all POST with X-Deck: 1: /talk/stt (any audio -> ffmpeg 16 kHz mono wav -> the warm STT server, else `voxtype transcribe`),
/talk/ask (`brain ask --stream --from deck --how voice`, JSON lines back: first sentence early, then the result with the
notes mapped to collection + path; one line per question in the talk log), /talk/say (one sentence as a WAV from the
island's Kokoro server, voice bm_george; started like bin/say if it is down), /talk/job (runs a job only after the Yes click),
/talk/outcome (said No / stopped, for the brain's check-up). Brief 27: /talk/warm (wake the search and the voice while he talks),
/talk/confirm (a spoken yes/no to a plan; only a plain yes runs it), /talk/stt X-Preroll (talking over the brain: the half second
before the voice was noticed comes first, as a WAV). Jobs run only from the server's own copy of the plan, by the ask's id.
GET /live (brief 15): a read-only stream of every search and ask (the brain's logs + the Deck's own calls) for the live animation.
GET /private?id=N and POST /private {id, on} (brief 22, X-Deck: 1): a memory note's "this computer only" tag. GET reads its front
matter (read-only); POST runs `brain private <note> on|off --json` (the Deck never edits the note itself). Only memory notes.
Test mode: with DECK_TEST_MAP the command is pointed at that map's memory folder (BRAIN_MEMORY_STORE) and a backups folder beside it.
GET /health (brief 26): {"app": "second-brain-deck", "ready": true, "pid": ...} once the server answers. The Electron app waits for it,
and uses it to tell an already running Deck server (reuse it) from some other program on the port (ask, never kill).
DECK_PARENT_WATCH=1 (set by the app): the server reads its stdin pipe and exits when it closes, i.e. when the app is gone, even after a
forced kill, so no server is left behind."""
import http.server, socketserver, sqlite3, hmac, array, math, wave, json, urllib.parse, urllib.request, pathlib, os, sys, hashlib, shutil, tempfile, datetime, subprocess, signal, threading, time, re, yaml
ROOT = pathlib.Path(__file__).resolve().parent.parent / "web"; PORT = int(os.environ.get("DECK_PORT", 8765)); DB = os.path.expanduser("~/.cache/qmd/index.sqlite")
QMD = os.path.expanduser("~/.config/qmd/index.yml"); DATA = pathlib.Path(os.environ.get("DECK_DATA") or os.path.expanduser("~/.local/share/second-brain/viz/data.js")); TEST_MAP = os.environ.get("DECK_TEST_MAP")
BACKUPS = os.path.expanduser("~/.cache/tmp/sb/note-backups"); MAXBODY = 4_000_000; SHOW = 150000
def folders():
    if TEST_MAP: return {k: str(v) for k, v in (yaml.safe_load(open(TEST_MAP)) or {}).items()}
    return {k: v["path"] for k, v in (yaml.safe_load(open(QMD)).get("collections") or {}).items() if v.get("path")}
def row(i):
    c = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    r = c.execute("select d.title,d.collection,d.path,c.doc,d.modified_at from documents d join content c on c.hash=d.hash where d.id=? and d.active=1", (i,)).fetchone(); c.close(); return r
def real_file(col, path):
    """The note's real file, or (None, reason). Must exist, be .md and stay inside the collection folder."""
    base = folders().get(col)
    if not base: return None, f"no folder known for the '{col}' collection"
    if os.path.isabs(path) or ".." in pathlib.PurePosixPath(path).parts: return None, "bad note path"
    base = os.path.realpath(os.path.expanduser(base)); f = os.path.realpath(os.path.join(base, path))
    if not f.startswith(base + os.sep): return None, "the note's file is outside its collection folder"
    if not f.endswith(".md"): return None, "only .md notes can be edited"
    if not os.path.isfile(f): return None, "the note's file was not found (showing the search index copy)"
    return f, ""
sha = lambda b: hashlib.sha256(b).hexdigest()
def private_state(f):
    """A memory note's tag as `brain private` reads it (read-only): local_only, by (an old tag without by came from the filter), at;
    and its title as `brain private` names it (the first heading, else the summary line)."""
    try: lines = open(f, encoding="utf-8", errors="replace").read(20000).splitlines()
    except OSError: return dict(local_only=False, by="", at="", title="")
    fm, end = {}, 0
    if lines and lines[0].strip() == "---":
        for n, l in enumerate(lines[1:], 1):
            if l.strip() == "---": end = n + 1; break
            if l[:1].isspace() or ":" not in l: continue
            k, _, v = l.partition(":"); fm.setdefault(k.strip(), v.strip().strip('"'))
    on = fm.get("local-only", "").lower() == "true"
    head = next((m.group(1).strip() for l in lines[end:] for m in [re.match(r"#+\s+(.+)", l.strip())] if m), "")
    return dict(local_only=on, by=fm.get("local-only-by") or ("filter" if on else ""), at=fm.get("local-only-at", ""), title=head or fm.get("summary", ""))
# ---- talking: the island's settings (read-only, rise.json via its own helper), its brain, STT and Kokoro
def island(module, key, default):
    try:
        a = os.path.expanduser("~/.config/omarchy/plugins/user.rise/addons"); a in sys.path or sys.path.insert(0, a); from addon_config import config
        return config(module, key, default) or default
    except Exception: return default
BRAIN = os.environ.get("DECK_BRAIN") or shutil.which(os.path.expanduser(island("brain", "executable", "brain"))) or os.path.expanduser("~/.local/bin/brain")   # DECK_BRAIN: tests only
STT_URL = os.environ.get("BRAIN_STT_URL") or island("brainVoice", "sttEndpoint", "http://127.0.0.1:8183/transcribe")
TTS = island("brainVoice", "ttsEndpoint", "") or "http://127.0.0.1:%d" % int(os.environ.get("EXPLAIN_VOICE_PORT", "47821"))
TTS_SERVER = [island("brainVoice", "python", "python3"), "-I", island("brainVoice", "server", "")]
VOICE = os.environ.get("DECK_VOICE", "bm_george"); TALKLOG = pathlib.Path(os.environ.get("DECK_TALK_LOG") or os.path.expanduser("~/.local/state/second-brain/talk-log.jsonl")); MAXAUDIO = 12_000_000
def run(cmd, timeout, **k):
    """A helper process in its own group, killed whole on timeout (like the island's helpers)."""
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, start_new_session=True, **k)
    try: out, err = p.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        os.killpg(p.pid, signal.SIGKILL); p.communicate(); raise
    return p.returncode, out, err
# what the STT says when it heard nothing (voxtype: "No speech detected, skipping transcription."); never a question for the brain
NOSPEECH = re.compile(r"^\W*(no (speech|audio|voice)( (was )?(detected|found|heard))?[,.;:]?( skipping transcription)?|nothing (was )?(heard|detected)|skipping transcription|blank_audio|silence)\W*$", re.I)
# a transcript with no real words in it: empty, only punctuation, one letter, or only fillers ("um", "uh huh", "hmm.")
FILLER = {"um", "umm", "uh", "uhh", "uhm", "erm", "er", "ah", "ahh", "oh", "eh", "hm", "hmm", "hmmm", "mm", "mmm", "mhm", "huh", "uh-huh", "mm-hmm", "hm-hmm"}
def said_nothing(text):
    words = re.findall(r"[^\W_]+(?:-[^\W_]+)*", text.lower())
    return NOSPEECH.search(text) is not None or len("".join(words)) <= 1 or all(w in FILLER for w in words)
SILENT_DB, TARGET_DB, MAXGAIN_DB = -62.0, -3.0, 36.0   # voxtype hears nothing below about -50 dBFS peak; a voice down there is raised, true silence stops here
def loudness(wav):
    """Peak and RMS (dBFS) of a 16-bit mono wav; a quiet voice is raised so its peak sits at -3 dBFS (at most +36 dB), so the
    STT's speech detector can find it. Returns (peak_db, rms_db, gain_db)."""
    with wave.open(wav, "rb") as w: n = w.getnframes(); a = array.array("h", w.readframes(n)); rate = w.getframerate()
    if sys.byteorder == "big": a.byteswap()
    if not a: return -120.0, -120.0, 0.0
    a2 = a[int(rate * .08):] or a   # skip the first 80 ms (the click of the mic opening)
    peak = max(max(a2), -min(a2)) or 1; rms = math.sqrt(sum(x * x for x in a2) / len(a2)) or 1
    pdb, rdb = 20 * math.log10(peak / 32768), 20 * math.log10(rms / 32768)
    gain = 0.0 if pdb < SILENT_DB else max(0.0, min(MAXGAIN_DB, TARGET_DB - pdb))
    if gain >= 1:
        k = 10 ** (gain / 20); b = array.array("h", (max(-32768, min(32767, int(x * k))) for x in a))
        if sys.byteorder == "big": b.byteswap()
        with wave.open(wav, "wb") as w: w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate); w.writeframes(b.tobytes())
    return round(pdb, 1), round(rdb, 1), round(gain, 1)
def transcribe(audio, pre=0):
    """Browser audio (webm/ogg/wav) -> 16 kHz mono s16 wav (ffmpeg) -> loudness check (silence: stop here; quiet: raise it)
    -> the warm STT server, else voxtype (bin/listen's order). heard=False means nothing was heard: don't ask the brain.
    pre > 0 (talking over the brain): the first `pre` bytes are a WAV of the half second before the page noticed the voice,
    joined in front of the recording, so the first word is not cut off."""
    t0 = time.monotonic(); d = tempfile.mkdtemp(prefix="deck-talk-", dir=os.environ.get("XDG_RUNTIME_DIR") or None)
    try:
        src, wav, head = os.path.join(d, "in.audio"), os.path.join(d, "q.wav"), os.path.join(d, "pre.wav"); open(src, "wb").write(audio[pre:])
        conv = ["-ac", "1", "-ar", "16000", "-sample_fmt", "s16", wav]
        if pre:
            open(head, "wb").write(audio[:pre])
            conv = ["-i", head, "-i", src, "-filter_complex", "[0:a]aresample=16000,aformat=channel_layouts=mono[a];[1:a]aresample=16000,aformat=channel_layouts=mono[b];[a][b]concat=n=2:v=0:a=1"] + conv
        else: conv = ["-i", src] + conv
        code, _, err = run(["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y"] + conv, 30)
        if code: return dict(error="could not read the recording: " + (err.strip().splitlines() or ["ffmpeg failed"])[-1][:160])
        try: pdb, rdb, gain = loudness(wav)
        except (OSError, EOFError, wave.Error) as e: return dict(error=f"could not read the recording: {e}")
        with wave.open(wav, "rb") as w: secs = round(w.getnframes() / w.getframerate(), 2)
        lv = dict(peak_db=pdb, rms_db=rdb, gain_db=gain, secs=secs); ms_conv = int((time.monotonic() - t0) * 1000); t1 = time.monotonic()
        def got(text, engine):
            text = " ".join(str(text or "").split()); heard = not said_nothing(text)
            return dict(text=text if heard else "", heard=heard, said=text if not heard else "", engine=engine, ms_convert=ms_conv, ms_stt=int((time.monotonic() - t1) * 1000), **lv)
        if pdb < SILENT_DB: return dict(got("", "none"), why="silent")
        try:
            with urllib.request.urlopen(urllib.request.Request(STT_URL, open(wav, "rb").read(), {"content-type": "audio/wav"}), timeout=15) as r:
                return got(json.load(r).get("text"), "stt-server")
        except Exception: pass
        try: code, out, err = run(["voxtype", "transcribe", wav], 90)
        except (OSError, subprocess.TimeoutExpired) as e: return dict(error=f"voxtype: {e}")
        if code: return dict(error="voxtype: " + ((err.strip().splitlines() or ["failed"])[-1])[:160])
        lines = [l.strip() for l in out.splitlines() if l.strip()]; text = lines[-1] if lines else ""
        if any(n in text for n in ("Loading audio file", "Audio format", "Processing ", "VAD:", " INFO", "\x1b[")): text = ""
        return got(text, "voxtype")
    finally: shutil.rmtree(d, ignore_errors=True)
def where(path):
    """An answer's note (absolute path) -> (collection, path inside it), so the page can find it in data.js."""
    try: f = os.path.realpath(os.path.expanduser(path))
    except Exception: return None, None
    best = None   # the deepest folder wins (chats/codex sits inside chats)
    real = [(k, v["path"]) for k, v in (yaml.safe_load(open(QMD)).get("collections") or {}).items() if v.get("path")] if TEST_MAP else []
    for col, base in list(folders().items()) + real:   # test mode: a real path (a search result) still names its collection
        b = os.path.realpath(os.path.expanduser(base))
        if f.startswith(b + os.sep) and (not best or len(b) > len(best[1])): best = (col, b)
    return (best[0], os.path.relpath(f, best[1])) if best else (None, None)
def tts_up():
    try:
        with urllib.request.urlopen(TTS + "/health", timeout=.5) as r: return r.read() == b"ok"
    except OSError: return False
_tts_lock = threading.Lock()
def ensure_tts():
    """bin/say's way: start the island's Kokoro server if it is down (it quits by itself after 15 idle minutes)."""
    with _tts_lock:
        if tts_up(): return True
        if not TTS_SERVER[2] or not os.path.isfile(TTS_SERVER[2]) or not shutil.which(TTS_SERVER[0]): return False
        subprocess.Popen(TTS_SERVER, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        for _ in range(60):
            time.sleep(.25)
            if tts_up(): return True
        return False
def talklog(**row):
    TALKLOG.parent.mkdir(parents=True, exist_ok=True)
    with open(TALKLOG, "a") as f: f.write(json.dumps(dict(time=datetime.datetime.now().isoformat(timespec="seconds"), **row)) + "\n")
SEARCH_URL = os.environ.get("BRAIN_URL") or island("brain", "endpoint", "http://localhost:8181")
def stt_up():
    try:
        with urllib.request.urlopen(STT_URL.rsplit("/", 1)[0] + "/health", timeout=.3) as r: return json.load(r).get("ok") is True
    except Exception: return False
def warm():
    """While <user> talks (bin/listen's warm_brain, plus the voice): wake the brain's search server (after 5 quiet minutes it lets go of
    its models and the first search takes ~5 s) and start Kokoro if it is down, so the first sentence can be said sooner. Never waits."""
    def ping():
        try: urllib.request.urlopen(urllib.request.Request(SEARCH_URL + "/query", json.dumps(dict(searches=[dict(type="vec", query="hello")], limit=1, rerank=False)).encode(), {"content-type": "application/json"}), timeout=30).read()
        except Exception: pass
    if os.environ.get("DECK_NO_WARM") != "1":
        threading.Thread(target=ping, daemon=True).start(); threading.Thread(target=ensure_tts, daemon=True).start()
    return dict(ok=True, stt="warm" if stt_up() else "slow", tts=tts_up())
# ---- the gate for jobs (brief 27): the server keeps every plan the brain proposed (by its ask id, 10 minutes, used once) and runs only
# that copy, never a job the page sends. It runs after a Yes click, or a spoken answer the server itself hears as a plain yes.
PLANS, PLAN_SECONDS = {}, 600; _plans_lock = threading.Lock()
def plan_keep(i, job):
    with _plans_lock:
        now = time.monotonic(); [PLANS.pop(k) for k in [k for k, (_, at) in PLANS.items() if now - at > PLAN_SECONDS]]
        PLANS[i] = (job, now)
def plan_take(i, keep=False):
    with _plans_lock:
        got = PLANS.get(i)
        if not got or time.monotonic() - got[1] > PLAN_SECONDS: PLANS.pop(i, None); return None
        if not keep: PLANS.pop(i, None)
        return got[0]
YES_START = re.compile(r"^(yes|yeah|yep|yup|yea|ya|sure|ok|okay|alright|all right|go ahead|go for it|do it|please do|confirm|confirmed|absolutely|definitely|correct|that's right|right|affirmative)\b")
NO_START = re.compile(r"^(no|nope|nah|cancel|stop|don't|do not|never|not now|negative|abort|forget it)\b")
NOT_YES = re.compile(r"\b(no|not|don't|dont|never|cancel|stop|wait|hold|but|later|abort|why|what|how|which|maybe|unless)\b")
def yes_no(said):
    """A spoken answer to "shall I?": 'yes' only for a short, plain yes with nothing against it ("yes, go ahead"); 'no' for a plain no;
    everything else (silence, a question, "yes but wait", a long sentence) is 'unclear', which does nothing."""
    t = re.sub(r"[^\w' ]+", " ", str(said or "").lower().replace("’", "'")); t = " ".join(t.split())
    if not t or len(t.split()) > 8: return "unclear"
    if NO_START.match(t): return "no"
    if YES_START.match(t) and not NOT_YES.search(t): return "yes"
    return "unclear"
# ---- live searches (brief 15): GET /live is a read-only Server-Sent Events stream, one event per search or ask anywhere:
# it tails asks.jsonl (every `brain ask`) and searches.jsonl (the chats' MCP searches and `brain search`; it may appear later),
# read-only, and the Deck's own /search and /talk/ask emit directly (their own log lines are then skipped, so nothing shows twice).
# Test mode: DECK_ASKS_LOG / DECK_SEARCHES_LOG point at temp copies. The page's token is put into deck.html as it is served.
STATE = os.path.expanduser("~/.local/state/second-brain")
LOGS = dict(asks=os.environ.get("DECK_ASKS_LOG") or os.path.join(STATE, "asks.jsonl"), searches=os.environ.get("DECK_SEARCHES_LOG") or os.path.join(STATE, "searches.jsonl"))
LIVE_TOKEN = hashlib.sha256(os.urandom(32)).hexdigest()[:32]; LIVE_MAX = 40
_live = dict(seq=0, events=[], own=[]); _live_cv = threading.Condition()
WHO = dict(deck="Deck", island="voice island", chat="chat", cli="terminal", obsidian="Obsidian", mcp="chat")
HOME = os.path.expanduser("~")
AGENTS = dict(claude="Claude", codex="Codex", gemini="Gemini", opencode="opencode", cursor="Cursor", copilot="Copilot", grok="Grok", antigravity="Antigravity", hermes="Hermes", agy="Antigravity")
def qdb(sql, args=()):
    """A read-only look in the brain's index (titles, docids, globs); [] if it is busy or missing."""
    try:
        c = sqlite3.connect(f"file:{DB}?mode=ro", uri=True, timeout=.5)
        try: return c.execute(sql, args).fetchall()
        finally: c.close()
    except sqlite3.Error: return []
def live_hit(path, col=None, score=None):
    """One result or opened file -> {c, p, t, path, score}. The logs hold real paths (absolute or ~), qmd's own 'collection/path'
    (qmd://… too), or a docid (#abc123). The recorder's own collection wins over the folder guess (chats/codex sits inside chats).
    c/p are qmd's collection and path (what data.js uses); t is the note's title, so a note newer than data.js still has a name."""
    path = re.sub(r"(\.md|^#[0-9a-fA-F]+):\d+(:\d+)?$", r"\1", path.strip()); fs = folders(); c = rel = None   # get's line range (file.md:30:20) is not part of the name
    if path.startswith("#"):
        r = qdb("select collection, path from documents where active=1 and hash like ? limit 1", (path[1:].lower() + "%",)) if re.fullmatch(r"#[0-9a-fA-F]{4,64}", path) else []
        if r: c, rel = r[0]
    elif path.startswith(("/", "~")):
        f, base = os.path.realpath(os.path.expanduser(path)), fs.get(col) if col else None
        b = os.path.realpath(os.path.expanduser(base)) if base else None
        if b and f.startswith(b + os.sep): c, rel = col, os.path.relpath(f, b)
        else: c, rel = where(path)
    else:
        head, _, rest = path.removeprefix("qmd://").partition("/")
        c, rel = (head, rest) if rest and head in fs else (col if col in fs else None, path.removeprefix("qmd://"))
    t = i = None
    if rel:
        r = qdb("select collection, path, title, id from documents where active=1 and lower(path)=lower(?)" + (" and collection=?" if c else "") + " limit 1", (rel, c) if c else (rel,))
        if r: c, rel, t, i = r[0]
    shown = path if path.startswith("#") else path.replace(os.path.expanduser("~"), "~", 1)
    return dict(c=c, p=rel, t=t or os.path.basename(rel or path), path=shown, score=score if isinstance(score, (int, float)) else None, id=i)
def live_hits(paths):
    out = []
    for x in paths[:10]:
        path, col, score = (x.get("path"), x.get("collection"), x.get("score")) if isinstance(x, dict) else (x, None, None)
        if isinstance(path, str) and path.strip(): out.append(live_hit(path, col, score))
    return out
def read_hits(what):
    """A chat's get / multi_get argument -> the notes it opened: one file, a comma list, docids or a glob (looked up in the index)."""
    out = []
    for w in [x.strip() for x in what.split(",") if x.strip()][:8]:
        if any(ch in w for ch in "*?["):
            g = w.removeprefix("qmd://"); out += [live_hit(f"{c}/{p}") for c, p in qdb("select collection, path from documents where active=1 and (collection || '/' || path glob ? or path glob ?) order by modified_at desc limit 8", (g, g))]
        else: out.append(live_hit(w))
    return out[:8]
def _proc(pid):
    """(program, cwd, parent pid, command line) of a running process, or None."""
    try:
        d = f"/proc/{int(pid)}"; comm = open(d + "/comm").read().strip(); stat = open(d + "/stat").read()
        cmd = open(d + "/cmdline", "rb").read().replace(b"\0", b" ").decode(errors="replace")
        return comm, os.readlink(d + "/cwd"), int(stat.rsplit(")", 1)[1].split()[1]), cmd
    except (OSError, ValueError, IndexError): return None
def agent_of(pid):
    """Walk up from a process (a `brain` call's shell) to who started it: 'Claude · folder', 'Codex · folder', 'Deck', or None."""
    for _ in range(14):
        p = _proc(pid)
        if not p or pid <= 1: return None
        comm, cwd, ppid, cmd = p; name = comm.lower().split("-")[0]
        if name in AGENTS: return " · ".join(x for x in (AGENTS[name], os.path.basename(cwd.rstrip("/")) if cwd.rstrip("/") != HOME else "") if x)
        if "server.py" in cmd and "brain-prototypes" in (cmd + cwd): return "Deck"
        pid = ppid
    return None
def ask_caller(q):
    """`brain ask` logs no caller; if its process is still around, find who started it (an agent's shell), else None."""
    for d in os.listdir("/proc"):
        if not d.isdigit(): continue
        p = _proc(d)
        if p and "ask/ask.py" in p[3] and q[:40] in " ".join(p[3].split()): return agent_of(p[2])
    return None
def live_who(o, src):
    """Who asked, in a few words: 'Claude · second-brain', 'Codex · …', 'terminal', 'voice island', 'Deck', 'Obsidian'."""
    f = str(o.get("from") or "?"); cl = o.get("client") if isinstance(o.get("client"), dict) else {}
    if f == "mcp":
        prog = str(cl.get("program") or "").lower(); folder = os.path.basename(str(cl.get("folder") or "").rstrip("/").removeprefix("~"))   # a chat started in ~ is just 'Claude'
        name = AGENTS.get(prog.split("-")[0]) or str(cl.get("name") or "") or (prog if prog not in ("python3", "python", "node", "bun") else "") or "chat"
        return " · ".join(x for x in (name, folder) if x)
    if f == "cli" and src == "searches" and cl.get("pid"): return agent_of(cl["pid"]) or "terminal"
    if f == "cli" and src == "asks": return ask_caller(" ".join(str(o.get("q") or "").split())) or "terminal"
    return WHO.get(f, f)
def live_event(src, o):
    """A log line -> one event, or None (not a search, no question, or the Deck's own call that was already sent)."""
    if not isinstance(o, dict): return None
    q = " ".join(str(o.get("q") or "").split())[:300]; kind = str(o.get("kind") or "search")
    if not q: return None
    if src == "asks": kind, hits = "ask", live_hits(o.get("sources") or [])
    elif kind == "search": hits = live_hits(o.get("results") or [])
    elif kind == "read":
        tool, _, what = q.partition(" "); hits = read_hits(what or q)
        q = (hits[0]["t"] if hits else what or q) + (f"  +{len(hits) - 1}" if len(hits) > 1 else "")
    else: return None
    cl = o.get("client") if isinstance(o.get("client"), dict) else {}
    if src == "searches" and o.get("from") == "cli" and cl.get("pid") == os.getpid(): return None   # this server's own /search (already sent)
    if src == "asks" and o.get("from") == "deck":   # this server's own /talk/ask: each one skips its own log line once
        with _live_cv:
            k = next((x for x in _live["own"] if x[0] == q.lower() and time.monotonic() - x[1] < 180), None)
            if k: _live["own"].remove(k); return None
    return dict(src=src, kind=kind, at=str(o.get("at") or "")[:19], who=live_who(o, src), q=q, hits=hits, ms=o.get("ms"))
def live_emit(ev, own=False):
    with _live_cv:
        if own and ev["kind"] == "ask": _live["own"] = [x for x in _live["own"] if time.monotonic() - x[1] < 180] + [(ev["q"].lower(), time.monotonic())]
        _live["seq"] += 1; ev["id"] = _live["seq"]; ev["sent"] = time.time(); _live["events"] = (_live["events"] + [ev])[-LIVE_MAX:]; _live_cv.notify_all()
def live_tail():
    """Follows both logs (read-only), every 0.05 s (a terminal's `brain search` shell is often gone soon after; a quick look still finds who started it): every new line, in order (two identical lines are two events). A log that
    appears later is read from its start. A trimmed or replaced log (the recorder keeps its last 5,000 lines, swapped in whole)
    is read again and picked up right after the last line already read. Before the first poll, the last few lines of each
    become the feed's history (marked past: shown in the list, not animated)."""
    pos, last, started = {}, {}, (datetime.datetime.now() - datetime.timedelta(seconds=60)).isoformat(timespec="seconds")
    key = lambda o: json.dumps(o, sort_keys=True)
    def read(f, start):
        try:
            st = os.stat(f)
            with open(f, "rb") as fh:
                fh.seek(start); data = fh.read(8_000_000)
        except OSError: return None, []
        cut = data.rfind(b"\n") + 1; lines = []
        for raw in data[:cut].splitlines():
            try: lines.append(json.loads(raw))
            except ValueError: pass
        return (st.st_ino, start + cut), lines
    hist = []
    for src, f in LOGS.items():
        try: size = os.path.getsize(f)
        except OSError: pos[src] = None; continue
        p, lines = read(f, max(0, size - 200_000)); pos[src] = p
        if lines: last[src] = key(lines[-1])
        hist += [e for e in (live_event(src, x) for x in lines[-30:]) if e]
    for e in sorted(hist, key=lambda e: e["at"])[-20:]: e["past"] = True; live_emit(e)
    while True:
        time.sleep(.05)
        for src, f in LOGS.items():
            try: st = os.stat(f)
            except OSError: pos[src] = None; continue
            p, again = pos.get(src), False
            if p is None: start, again = 0, True                                         # appeared (or came back) since the last look
            elif st.st_ino != p[0] or st.st_size < p[1]: start, again = 0, True          # replaced or trimmed: read it again
            elif st.st_size == p[1]: continue
            else: start = p[1]
            np, lines = read(f, start)
            if np is None: continue
            pos[src] = np
            if again:
                ks = [key(o) for o in lines]; j = max((n for n, k in enumerate(ks) if k == last.get(src)), default=None)
                lines = lines[j + 1:] if j is not None else [o for o in lines if str(o.get("at") or "") >= started]
            if lines: last[src] = key(lines[-1])
            for o in lines:
                e = live_event(src, o)
                if e: live_emit(e)
threading.Thread(target=live_tail, daemon=True).start()
class H(http.server.SimpleHTTPRequestHandler):
    def __init__(s, *a, **k): super().__init__(*a, directory=str(ROOT), **k)
    def log_message(s, *a): pass
    def end_headers(s):
        # static files (the Deck's html/css/js): no-cache = the browser must check with us before using its copy (a cheap 304 when
        # unchanged). Without it Chromium guessed "fresh for 10% of the file's age" and kept an old hud.css after an edit (brief 12).
        if b"Cache-Control" not in b"".join(getattr(s, "_headers_buffer", [])): s.send_header("Cache-Control", "no-cache")
        super().end_headers()
    def ok_host(s): return s.headers.get("Host", "") in (f"127.0.0.1:{PORT}", f"localhost:{PORT}")
    def js(s, code, obj):
        body = json.dumps(obj).encode()
        s.send_response(code); s.send_header("Content-Type", "application/json; charset=utf-8"); s.send_header("Cache-Control", "no-store"); s.send_header("Content-Length", str(len(body))); s.end_headers(); s.wfile.write(body)
    def note_id(s):
        try: return int(urllib.parse.parse_qs(urllib.parse.urlparse(s.path).query).get("id", ["x"])[0])
        except ValueError: return None
    def do_GET(s):
        if not s.ok_host(): return s.send_error(403)
        if urllib.parse.urlparse(s.path).path == "/health": return s.js(200, dict(app="second-brain-deck", ready=True, pid=os.getpid(), data=DATA.exists()))
        if urllib.parse.urlparse(s.path).path == "/search": return s.search()
        if urllib.parse.urlparse(s.path).path == "/live": return s.live()
        if urllib.parse.urlparse(s.path).path == "/private": return s.private()
        if urllib.parse.urlparse(s.path).path in ("/", "/hud/deck.html"): s.send_response(302); s.send_header("Location", "/deck.html"); s.send_header("Content-Length", "0"); s.end_headers(); return
        if urllib.parse.urlparse(s.path).path == "/data.js":   # private, outside git (tools/ writes it there)
            try: body = DATA.read_bytes()
            except OSError: return s.send_error(404, "no data.js yet: run tools/build_data.py and tools/add_sim.py")
            s.send_response(200); s.send_header("Content-Type", "text/javascript; charset=utf-8"); s.send_header("Content-Length", str(len(body))); s.end_headers(); s.wfile.write(body); return
        if urllib.parse.urlparse(s.path).path == "/deck.html":   # the page carries this server's live token (never cached: a new server, a new token)
            body = (ROOT / "deck.html").read_bytes().replace(b'<meta name="deck-live" content="">', f'<meta name="deck-live" content="{LIVE_TOKEN}">'.encode(), 1)
            s.send_response(200); s.send_header("Content-Type", "text/html; charset=utf-8"); s.send_header("Cache-Control", "no-store"); s.send_header("Content-Length", str(len(body))); s.end_headers(); s.wfile.write(body); return
        if urllib.parse.urlparse(s.path).path == "/note":
            i = s.note_id()
            if i is None: return s.send_error(400)
            r = row(i)
            if not r: return s.send_error(404)
            f, why = real_file(r[1], r[2]); text, h, mod, src = r[3], "", r[4], "index"
            if f:
                b = open(f, "rb").read(); h = sha(b); src = "file"; text = b.decode("utf-8", "replace")
                mod = datetime.datetime.fromtimestamp(os.path.getmtime(f)).isoformat(timespec="seconds")
            cut = len(text) > SHOW
            if f and cut: why = "this note is too long to edit here"
            return s.js(200, dict(title=r[0], collection=r[1], path=r[2], text=text[:SHOW], truncated=cut, modified=mod, source=src, hash=h, editable=bool(f) and not cut, why=why, test=bool(TEST_MAP)))
        return super().do_GET()
    def live(s):
        """Server-Sent Events: first `history` (the last few searches, not animated), then one `live` event per search or ask.
        An EventSource can't send a custom header, so: the Host check, a same-origin check (Sec-Fetch-Site / Origin) and the
        token that only the Deck's own page carries (another site can't read the page). Read-only; a ping every 15 s."""
        qs = urllib.parse.parse_qs(urllib.parse.urlparse(s.path).query)
        sf, o = s.headers.get("Sec-Fetch-Site"), s.headers.get("Origin")
        if (sf and sf != "same-origin") or (o and o not in (f"http://127.0.0.1:{PORT}", f"http://localhost:{PORT}")) or not hmac.compare_digest(qs.get("k", [""])[0], LIVE_TOKEN): return s.js(403, dict(error="not the Deck"))
        s.send_response(200); s.send_header("Content-Type", "text/event-stream"); s.send_header("Cache-Control", "no-store"); s.send_header("X-Accel-Buffering", "no"); s.end_headers()
        def send(kind, obj): s.wfile.write(f"event: {kind}\ndata: {json.dumps(obj)}\n\n".encode()); s.wfile.flush()
        try:
            with _live_cv: last = _live["seq"]; hist = list(_live["events"])
            send("history", hist[-20:])
            while True:
                with _live_cv:
                    _live_cv.wait_for(lambda: _live["seq"] > last, timeout=15); new = [e for e in _live["events"] if e["id"] > last]; last = _live["seq"]
                if not new: s.wfile.write(b": ping\n\n"); s.wfile.flush()
                for e in new: send("live", e)
        except (OSError, ValueError): return
    def search(s):
        """06 Ask: `brain search` (the brain's meaning search, the notes `brain ask` would use), read-only. Needs X-Deck: 1, so
        another site can't even start one (a custom header needs a CORS preflight, which this server never allows).
        The scores are rank-based (1, 1/2, 1/3 ... with a boost for new notes), not a measure of fit."""
        if s.headers.get("X-Deck") != "1": return s.js(403, dict(error="missing the Deck's header"))
        q = " ".join(str(urllib.parse.parse_qs(urllib.parse.urlparse(s.path).query).get("q", [""])[0]).split())[:300]
        if not q: return s.js(400, dict(error="say what to look for"))
        t0 = time.monotonic()
        try: code, out, err = run([BRAIN, "search", q], 60, env=dict(os.environ, BRAIN_SEARCH_SCORES="1"))
        except subprocess.TimeoutExpired: return s.js(504, dict(error="the search took too long"))
        except OSError as e: return s.js(500, dict(error=f"could not start the search: {e}"))
        if code: return s.js(502, dict(error=((err.strip().splitlines() or ["brain search failed"])[-1])[:200]))
        res = []
        for line in out.splitlines():
            score, _, rest = line.partition("\t"); path, _, snip = rest.partition(" \u2014 ")
            try: score = float(score)
            except ValueError: continue
            c, rel = where(path.strip()); r = qdb("select id, title from documents where active=1 and collection=? and path=? limit 1", (c, rel)) if c else []
            res.append(dict(score=score, path=path.strip(), c=c, p=rel, snippet=snip.strip()[:200], id=r[0][0] if r else None, t=r[0][1] if r else None))
        ms = int((time.monotonic() - t0) * 1000)
        live_emit(dict(src="deck", kind="search", at=datetime.datetime.now().isoformat(timespec="seconds"), who="Deck", q=q, hits=live_hits(res), ms=ms, nonce=str(s.headers.get("X-Deck-Live") or "")[:40]), own=True)
        return s.js(200, dict(q=q, results=res, ms=ms))
    def do_POST(s):
        if not s.ok_host(): return s.send_error(403)
        u = urllib.parse.urlparse(s.path).path
        if u not in ("/note", "/private") and not u.startswith("/talk/"): return s.send_error(404)
        if s.headers.get("X-Deck") != "1" or not (u == "/talk/stt" or s.headers.get("Content-Type", "").startswith("application/json")): return s.js(403, dict(error="missing the Deck's header"))
        o = s.headers.get("Origin")
        if o and o not in (f"http://127.0.0.1:{PORT}", f"http://localhost:{PORT}"): return s.js(403, dict(error="wrong origin"))
        if u.startswith("/talk/"): return s.talk(u[6:])
        if u == "/private": return s.private()
        n = int(s.headers.get("Content-Length") or 0)
        if not 0 < n <= MAXBODY: return s.js(413, dict(error="the note is too big to save here"))
        i = s.note_id()
        try: body = json.loads(s.rfile.read(n)); text, old = body["text"], body["hash"]; assert isinstance(text, str) and isinstance(old, str)
        except Exception: return s.js(400, dict(error="bad request"))
        r = row(i) if i is not None else None
        if not r: return s.js(404, dict(error="note not found in the index"))
        f, why = real_file(r[1], r[2])
        if not f: return s.js(403, dict(error=why))
        cur = open(f, "rb").read()
        if sha(cur) != old: return s.js(409, dict(error="this note changed on disk after you opened it, so it was not saved"))
        if b"\r\n" in cur: text = text.replace("\r\n", "\n").replace("\n", "\r\n")
        new = text.encode("utf-8")
        os.makedirs(BACKUPS, exist_ok=True)
        bk = os.path.join(BACKUPS, datetime.datetime.now().strftime("%Y-%m-%d-%H%M%S-") + os.path.basename(f))
        shutil.copy2(f, bk)
        fd, tmp = tempfile.mkstemp(prefix="." + os.path.basename(f) + ".", suffix=".tmp", dir=os.path.dirname(f))
        try:
            with os.fdopen(fd, "wb") as w: w.write(new); w.flush(); os.fsync(w.fileno())
            os.chmod(tmp, os.stat(f).st_mode & 0o7777); os.replace(tmp, f)
        except Exception as e:
            if os.path.exists(tmp): os.unlink(tmp)
            return s.js(500, dict(error=f"could not save: {e}"))
        return s.js(200, dict(hash=sha(new), backup=bk, modified=datetime.datetime.now().isoformat(timespec="seconds")))
    def private(s):
        """Brief 22: a memory note's "this computer only" tag (online writers never get the note). GET ?id= reads its state from
        the front matter; POST {id, on} runs `brain private <note> on|off --json` and returns its JSON. X-Deck: 1 both ways (a
        custom header needs a CORS preflight, which this server never allows); POST has the Origin check of the other POSTs."""
        if s.headers.get("X-Deck") != "1": return s.js(403, dict(ok=False, error="missing the Deck's header"))
        if s.command == "POST":
            n = int(s.headers.get("Content-Length") or 0)
            if not 0 < n <= 10_000: return s.js(413, dict(ok=False, error="too big"))
            try: body = json.loads(s.rfile.read(n)); i, on = int(body["id"]), body["on"]; assert isinstance(on, bool)
            except Exception: return s.js(400, dict(ok=False, error="bad request"))
        else:
            i = s.note_id()
            if i is None: return s.js(400, dict(ok=False, error="bad request"))
        r = row(i)
        if not r: return s.js(404, dict(ok=False, error="note not found in the index"))
        if r[1] != "memory": return s.js(200, dict(ok=True, memory=False))
        f, why = real_file(r[1], r[2])
        if not f: return s.js(200, dict(ok=False, memory=True, error=why))
        if s.command == "GET": return s.js(200, dict(ok=True, memory=True, **private_state(f)))
        store = os.path.realpath(os.path.expanduser(folders()["memory"]))
        env = dict(os.environ, BRAIN_MEMORY_STORE=store)   # the command tags the same file the reader shows
        if TEST_MAP: env["BRAIN_BACKUP_DIR"] = os.path.join(os.path.dirname(store), "private-backups")
        try: code, out, err = run([BRAIN, "private", r[2], "on" if on else "off", "--json"], 30, env=env)
        except subprocess.TimeoutExpired: return s.js(504, dict(ok=False, memory=True, error="brain private took too long"))
        except OSError as e: return s.js(500, dict(ok=False, memory=True, error=f"could not start brain private: {e}"))
        try: res = json.loads(out.strip().splitlines()[-1]); assert isinstance(res, dict)
        except Exception: return s.js(502, dict(ok=False, memory=True, error=((err.strip().splitlines() or ["brain private gave no answer"])[-1])[:200]))
        return s.js(200, dict(res, memory=True, **({} if not res.get("ok") else dict(state=private_state(f)))))
    def talk(s, what):
        n = int(s.headers.get("Content-Length") or 0)
        if not 0 < n <= (MAXAUDIO if what == "stt" else 200_000): return s.js(413, dict(error="too big"))
        raw = s.rfile.read(n)
        if what == "stt":
            try: pre = int(s.headers.get("X-Preroll") or 0); assert 0 <= pre < n and (not pre or raw[:4] == b"RIFF")
            except Exception: return s.js(400, dict(error="bad pre-roll"))
            r = transcribe(raw, pre); return s.js(500 if "error" in r else 200, r)
        try: body = json.loads(raw); assert isinstance(body, dict)
        except Exception: return s.js(400, dict(error="bad request"))
        if what == "warm": return s.js(200, warm())
        if what == "confirm": return s.confirm(body)
        if what == "say":
            text = " ".join(str(body.get("text") or "").split())[:600]
            if not text: return s.js(400, dict(error="nothing to say"))
            t0 = time.monotonic()
            if not ensure_tts(): return s.js(503, dict(error="the voice (Kokoro) did not start"))
            try:
                with urllib.request.urlopen(TTS + "/say?" + urllib.parse.urlencode(dict(text=text, voice=VOICE)), timeout=60) as r: wav = r.read()
            except Exception as e: return s.js(502, dict(error=f"the voice failed: {e}"))
            s.send_response(200); s.send_header("Content-Type", "audio/wav"); s.send_header("Cache-Control", "no-store"); s.send_header("Content-Length", str(len(wav)))
            s.send_header("X-Voice", VOICE); s.send_header("X-Ms-Tts", str(int((time.monotonic() - t0) * 1000))); s.end_headers(); s.wfile.write(wav); return
        if what == "ask": return s.ask(body)
        if what == "job": return s.job(body)
        if what == "outcome":
            i, w = str(body.get("id") or ""), str(body.get("what") or "")
            if not re.fullmatch(r"[\w-]{3,64}", i) or w not in ("declined", "stopped"): return s.js(400, dict(error="bad outcome"))
            try: run([BRAIN, "outcome", i, w], 20)
            except Exception: pass
            return s.js(200, dict(ok=True))
        return s.js(404, dict(error="unknown"))
    def ask(s, body):
        """`brain ask --stream` as bin/ask does; JSON lines back as they come: {event:first,text} early, then {event:done,...}."""
        q = " ".join(str(body.get("q") or "").split())[:500]
        if said_nothing(q): return s.js(400, dict(error="no question", heard=False))
        t0 = time.monotonic(); stt = body.get("stt") if isinstance(body.get("stt"), dict) else {}
        s.send_response(200); s.send_header("Content-Type", "application/x-ndjson"); s.send_header("Cache-Control", "no-store"); s.end_headers()
        def out(o): s.wfile.write((json.dumps(o) + "\n").encode()); s.wfile.flush()
        res, first_ms, err = None, None, ""
        try:
            p = subprocess.Popen([BRAIN, "ask", "--stream", "--from", "deck", "--how", "voice", q], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, start_new_session=True)
            timer = threading.Timer(60, lambda: os.killpg(p.pid, signal.SIGKILL)); timer.start()
            try:
                for line in p.stdout:
                    try: ev = json.loads(line)
                    except ValueError: continue
                    if not isinstance(ev, dict): continue
                    if ev.get("event") == "first" and ev.get("text"):
                        first_ms = int((time.monotonic() - t0) * 1000)
                        try: out(dict(event="first", text=str(ev["text"]), ms=first_ms))
                        except OSError: pass
                    elif ev.get("kind") in ("answer", "job"): res = ev
                p.wait(); err = p.stderr.read().strip()
            finally: timer.cancel()
        except OSError as e: err = str(e)
        ms = int((time.monotonic() - t0) * 1000)
        if not res: res = dict(kind="answer", answer="The brain didn't answer, so I can't look in your notes right now.", sources=[], job=None, writer="none", error=(err.splitlines() or ["brain ask failed"])[-1][:200])
        src = []
        for x in (res.get("sources") or [])[:3]:
            if isinstance(x, dict) and x.get("path"):
                c, rel = where(str(x["path"])); src.append(dict(title=str(x.get("title") or os.path.basename(str(x["path"]))), snippet=str(x.get("snippet") or "")[:300], c=c, p=rel))
        job = res.get("job") if isinstance(res.get("job"), dict) and res["job"].get("id") else None
        done = dict(event="done", kind="job" if res.get("kind") == "job" and job else "answer", answer=str(res.get("answer") or ""), first=str(res.get("first") or ""), rest=str(res.get("rest") or ""),
                    sources=src, job=job, writer=str(res.get("writer") or "?"), id=str(res.get("id") or ""), ms=ms, error=res.get("error", ""))
        if done["kind"] == "job":   # the plan the gate will run (only this copy), under the ask's id
            if not re.fullmatch(r"[\w-]{3,64}", done["id"]): done["id"] = "deck-" + os.urandom(6).hex()
            plan_keep(done["id"], job)
        try: talklog(question=q, how=str(body.get("how") or "voice"), answer=done["answer"][:200], kind=done["kind"], job=(job or {}).get("id"), notes=[f"{x['c']}/{x['p']}" for x in src if x["c"]], brain_id=done["id"], writer=done["writer"],
                     timings=dict(ms_record=stt.get("ms_record"), ms_convert=stt.get("ms_convert"), ms_stt=stt.get("ms_stt"), stt_engine=stt.get("engine"), ms_first_sentence=first_ms, ms_ask=ms))
        except Exception: pass
        live_emit(dict(src="deck", kind="ask", at=datetime.datetime.now().isoformat(timespec="seconds"), who="Deck " + ("voice" if str(body.get("how") or "voice") == "voice" else str(body.get("how"))[:20]), q=q,
                       hits=live_hits([x for x in (res.get("sources") or []) if isinstance(x, dict)]), ms=ms, nonce=str(body.get("live") or "")[:40]), own=True)
        try: out(done)
        except OSError: pass
    def job(s, body):
        """Runs a job the brain proposed, only after the Yes click on the page (the same call as bin/job). The job is the server's own
        copy of the plan (by the ask's id), never the one the page sends; a plan runs once."""
        i = str(body.get("id") or "")
        if body.get("confirmed") is not True or not re.fullmatch(r"[\w-]{3,64}", i): return s.js(400, dict(ok=False, message="That job had no name, so I did nothing."))
        job = plan_take(i)
        if not job: return s.js(409, dict(ok=False, message="That plan is too old or already done, so I did nothing. Ask again."))
        return s.js(200, s.run_job(job, i))
    def confirm(s, body):
        """A spoken answer to the plan: {id, said} (the transcript). Only a plain yes runs it (yes_no); a no drops the plan; anything
        else (silence, unclear) does nothing and keeps the plan for a click."""
        i = str(body.get("id") or "")
        if not re.fullmatch(r"[\w-]{3,64}", i): return s.js(400, dict(ok=False, decision="unclear", message="That job had no name, so I did nothing."))
        said = " ".join(str(body.get("said") or "").split())[:200]; d = yes_no(said) if not said_nothing(said) else "unclear"
        try: talklog(question=said, how="click" if body.get("how") == "click" else "voice", kind="confirm", brain_id=i, decision=d)
        except Exception: pass
        if d == "no":
            plan_take(i)
            try: run([BRAIN, "outcome", i, "declined"], 20)
            except Exception: pass
            return s.js(200, dict(ok=True, decision="no", message="Okay, I won't."))
        if d == "unclear": return s.js(200, dict(ok=True, decision="unclear", heard=said, kept=plan_take(i, keep=True) is not None,
                                                  message="I didn't hear a clear yes, so I did nothing. Say yes or click Yes."))
        job = plan_take(i)
        if not job: return s.js(409, dict(ok=False, decision="yes", message="That plan is too old or already done, so I did nothing. Ask again."))
        return s.js(200, dict(s.run_job(job, i), decision="yes"))
    def run_job(s, job, i):
        try: code, out, err = run([BRAIN, "job", "run", str(job["id"]), "--args-json", json.dumps(job)], 60)
        except subprocess.TimeoutExpired: return dict(ok=False, message="That job took too long, so I stopped waiting.")
        except OSError as e: return dict(ok=False, message=f"I couldn't start that job: {e}")
        msg, speak = "", False
        for line in reversed(out.splitlines()):
            try: o = json.loads(line)
            except ValueError: continue
            if isinstance(o, dict): msg, speak = str(o.get("message") or o.get("answer") or ""), bool(o.get("speak")); break
        ok = code == 0
        if not msg: msg = "Done: %s." % (job.get("label") or "that") if ok else "That didn't work: %s." % ((err.strip().splitlines() or ["code %d" % code])[0].removeprefix("brain: ")[:160].rstrip("."))
        try: run([BRAIN, "outcome", i, "job-ok" if ok else "job-failed", "" if ok else msg[:200]], 20)
        except Exception: pass
        return dict(ok=ok, message=msg, speak=speak)
class S(socketserver.ThreadingMixIn, http.server.HTTPServer): daemon_threads = True; allow_reuse_address = True
def parent_watch():   # the app holds the other end of our stdin: end of file = the app is gone (closed or killed)
    try:
        while sys.stdin.buffer.read(4096): pass
    finally: os._exit(0)
if os.environ.get("DECK_PARENT_WATCH") == "1": threading.Thread(target=parent_watch, daemon=True).start()
S(("127.0.0.1", PORT), H).serve_forever()
