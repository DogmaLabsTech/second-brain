#!/usr/bin/env python3
"""Draws the README pictures (animated SVG, no images, no fonts to load). Run: python3 make_art.py

The terminal scenes show text that `brain` really printed on a made-up folder (see TERMINAL below). Everything is
drawn with plain shapes; the look is a dark holographic panel with cyan and amber light."""
import html
import os

HERE = os.path.dirname(os.path.abspath(__file__))
C = dict(bg="#04070d", panel="#08111f", panel2="#0b1a2e", line="#1b3a57", cyan="#3be6ff", amber="#ffa62b",
         text="#d4ecff", dim="#6f8aa3", green="#5dffb0", red="#ff6a78")
SANS = "'Segoe UI','Helvetica Neue',Helvetica,Arial,sans-serif"
MONO = "ui-monospace,'SFMono-Regular','Cascadia Mono',Menlo,Consolas,'DejaVu Sans Mono',monospace"


def esc(s):
    return html.escape(s, quote=False)


def svg(w, h, body, extra_style=""):
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 %d %d" width="%d" height="%d">'
            '<defs>%s</defs><style>%s</style>%s</svg>\n' % (w, h, w, h, DEFS, extra_style, body))


DEFS = """
<linearGradient id="sky" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#070f1d"/><stop offset="1" stop-color="#03060b"/></linearGradient>
<linearGradient id="beam" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#3be6ff" stop-opacity="0"/><stop offset=".5" stop-color="#3be6ff" stop-opacity=".9"/><stop offset="1" stop-color="#3be6ff" stop-opacity="0"/></linearGradient>
<linearGradient id="bar" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#ffc766"/><stop offset="1" stop-color="#ff8a00"/></linearGradient>
<linearGradient id="leftfade" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#04070d" stop-opacity=".85"/><stop offset=".6" stop-color="#04070d" stop-opacity=".5"/><stop offset="1" stop-color="#04070d" stop-opacity="0"/></linearGradient>
<filter id="glow" x="-30%" y="-30%" width="160%" height="160%"><feGaussianBlur stdDeviation="3" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
<filter id="glow2" x="-30%" y="-30%" width="160%" height="160%"><feGaussianBlur stdDeviation="7" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
<pattern id="scan" width="4" height="4" patternUnits="userSpaceOnUse"><rect width="4" height="1" fill="#9be8ff" opacity=".05"/></pattern>
<pattern id="hex" width="56" height="97" patternUnits="userSpaceOnUse" patternTransform="scale(.9)"><path d="M28 0 56 16v32L28 64 0 48V16zM28 64v33M0 48l-0 0M56 48v0" fill="none" stroke="#3be6ff" stroke-opacity=".07" stroke-width="1"/></pattern>
"""


def chamfer(x, y, w, h, c):
    return "%g,%g %g,%g %g,%g %g,%g %g,%g %g,%g" % (x + c, y, x + w, y, x + w, y + h - c, x + w - c, y + h, x, y + h, x, y + c)


def brackets(x, y, w, h, n=14, color=None, sw=2):
    color = color or C["amber"]
    d = ("M%g %gv%g h%g M%g %gh%g v%g M%g %gv%g h%g M%g %gh%g v%g" % (
        x, y + n, -n, n, x + w - n, y, n, n, x + w, y + h - n, n, -n, x + n, y + h, -n, -n)).replace("v-14 h14", "v-14 h14")
    return '<path d="%s" fill="none" stroke="%s" stroke-width="%g"/>' % (d, color, sw)


def write(name, text):
    path = os.path.join(HERE, name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    print("wrote", name, len(text) // 1024, "KB")


# ------------------------------------------------------------------ hero

# The hero's background is a picture Codex drew from the prompt in source/hero-prompt.txt (variant a). It holds no text.
# The title, chips and the moving lights are drawn here, over it. Positions below are in the picture's own 1672x941 space.
NODES = ((1240, 113), (945, 185), (1405, 220), (1075, 272), (1520, 283), (830, 327), (1218, 400), (1400, 425), (970, 427),
         (1580, 392), (1325, 520), (1250, 585), (1410, 590), (1065, 345))


def hero():
    import base64
    with open(os.path.join(HERE, "source", "hero.jpg"), "rb") as f:
        pic = base64.b64encode(f.read()).decode()
    w, h = 1280, 720
    k = w / 1672
    o = ['<image href="data:image/jpeg;base64,%s" width="%d" height="%d" preserveAspectRatio="xMidYMid slice"/>' % (pic, w, h)]
    o.append('<rect width="620" height="%d" fill="url(#leftfade)"/>' % h)
    # slow beam across the brain
    o.append('<rect x="560" y="60" width="4" height="560" fill="url(#beam)" opacity=".75" filter="url(#glow)"><animate attributeName="x" values="560;1240;560" dur="9s" repeatCount="indefinite"/></rect>')
    # the base ring turns
    o.append('<ellipse cx="%.0f" cy="%.0f" rx="%.0f" ry="%.0f" fill="none" stroke="%s" stroke-width="2" stroke-dasharray="10 14" stroke-opacity=".8">'
             '<animate attributeName="stroke-dashoffset" values="0;48" dur="3s" repeatCount="indefinite"/></ellipse>' % (1170 * k, 836 * k, 395 * k, 52 * k, C["cyan"]))
    # amber nodes breathe
    for i, (x, y) in enumerate(NODES):
        o.append('<circle cx="%.0f" cy="%.0f" r="5" fill="none" stroke="%s" stroke-width="1.5"><animate attributeName="r" values="4;16;4" dur="%.1fs" begin="-%.1fs" repeatCount="indefinite"/>'
                 '<animate attributeName="opacity" values=".9;0;.9" dur="%.1fs" begin="-%.1fs" repeatCount="indefinite"/></circle>'
                 % (x * k, y * k, C["amber"], 3.2 + (i % 4) * .7, i * .6, 3.2 + (i % 4) * .7, i * .6))
    # title block
    o.append(brackets(48, 200, 520, 342, 22))
    o.append('<text x="84" y="258" font-family="%s" font-size="14" letter-spacing="5" fill="%s">AGENTIC MEMORY  //  YOUR COMPUTER</text>' % (SANS, C["amber"]))
    o.append('<text x="80" y="346" font-family="%s" font-size="86" font-weight="700" letter-spacing="4" fill="%s" filter="url(#glow2)">SECOND</text>' % (SANS, C["text"]))
    o.append('<text x="80" y="428" font-family="%s" font-size="86" font-weight="700" letter-spacing="4" fill="%s" filter="url(#glow2)">BRAIN</text>' % (SANS, C["cyan"]))
    o.append('<text x="84" y="470" font-family="%s" font-size="19" fill="%s">Your notes and your AI chats, in one searchable memory.</text>' % (SANS, "#9fb4c8"))
    x = 84
    for t in ("LOCAL", "PRIVATE", "SEARCHABLE"):
        wd = 24 + len(t) * 11
        o.append('<polygon points="%s" fill="%s" fill-opacity=".1" stroke="%s" stroke-width="1.2"/><text x="%d" y="512" font-family="%s" font-size="12" letter-spacing="3" fill="%s">%s</text>'
                 % (chamfer(x, 492, wd, 28, 7), C["cyan"], C["cyan"], x + 12, SANS, C["cyan"], t))
        x += wd + 14
    o.append('<rect width="%d" height="%d" fill="url(#scan)"/>' % (w, h))
    o.append('<polygon points="%s" fill="none" stroke="%s" stroke-opacity=".55" stroke-width="1.5"/>' % (chamfer(1, 1, w - 2, h - 2, 26), C["cyan"]))
    write("hero.svg", svg(w, h, "".join(o)))


# ------------------------------------------------------------------ banners and icons

def banner(n, title, sub):
    w, h = 1000, 84
    b = ['<polygon points="%s" fill="%s" stroke="%s" stroke-width="1.2"/>' % (chamfer(2, 2, w - 4, h - 4, 18), C["panel"], C["line"])]
    b.append('<rect x="2" y="20" width="6" height="44" fill="url(#bar)"/>')
    b.append('<polygon points="%s" fill="%s" fill-opacity=".1" stroke="%s" stroke-width="1.4"/>' % (chamfer(26, 16, 74, 52, 10), C["amber"], C["amber"]))
    b.append('<text x="63" y="53" text-anchor="middle" font-family="%s" font-size="30" font-weight="700" fill="%s" filter="url(#glow)">%02d</text>' % (SANS, C["amber"], n))
    b.append('<text x="124" y="46" font-family="%s" font-size="27" font-weight="700" letter-spacing="5" fill="%s" filter="url(#glow)">%s</text>' % (SANS, C["cyan"], esc(title.upper())))
    b.append('<text x="126" y="67" font-family="%s" font-size="13" letter-spacing="1.5" fill="%s">%s</text>' % (SANS, C["dim"], esc(sub)))
    ticks = "".join('<rect x="%d" y="%d" width="3" height="%d" fill="%s" opacity="%.2f"/>' % (800 + i * 9, 58 - (i * 7) % 24, 6 + (i * 7) % 24, C["cyan"], .25 + (i % 4) * .15) for i in range(20))
    b.append(ticks)
    b.append('<rect x="124" y="2" width="160" height="2" fill="url(#beam)"><animate attributeName="x" values="124;860;124" dur="6s" repeatCount="indefinite"/></rect>')
    b.append('<rect width="%d" height="%d" fill="url(#scan)"/>' % (w, h))
    write("banner-%d.svg" % n, svg(w, h, "".join(b)))


ICONS = {
    "search": '<circle cx="14" cy="14" r="7"/><path d="M19.5 19.5 27 27"/><path d="M11 14h6" stroke="AMB"/>',
    "ask": '<path d="M5 6h22v14H15l-6 6v-6H5z"/><path d="M13 11.5c0-3 6-3 6 0 0 2-3 2-3 4" stroke="AMB"/><circle cx="16" cy="17.6" r=".6" fill="AMB" stroke="AMB"/>',
    "chat": '<path d="M4 5h15v10H11l-4 4v-4H4z"/><path d="M14 18h14v9h-3v3l-4-3h-7z" stroke="AMB"/>',
    "day": '<rect x="5" y="7" width="22" height="20" rx="2"/><path d="M5 13h22M11 4v6M21 4v6"/><path d="m11 20 4 4 7-7" stroke="AMB"/>',
    "shield": '<path d="M16 4 26 8v8c0 6-4 10-10 12C10 26 6 22 6 16V8z"/><path d="m11 16 4 4 6-7" stroke="AMB"/>',
    "deck": '<path d="m16 4 11 6v12l-11 6L5 22V10z"/><path d="M5 10l11 6 11-6M16 16v12" stroke="AMB"/>',
    "local": '<rect x="4" y="7" width="24" height="15" rx="2"/><path d="M10 27h12M16 22v5"/><path d="m12 15 3 3 6-6" stroke="AMB"/>',
    "scrub": '<path d="M5 9h22M5 16h22M5 23h14"/><rect x="9" y="13" width="14" height="6" fill="AMB" fill-opacity=".35" stroke="AMB"/>',
    "list": '<rect x="5" y="4" width="16" height="24" rx="2"/><path d="M9 10h8M9 15h8"/><rect x="18" y="19" width="10" height="9" rx="1.5" stroke="AMB"/><path d="M20.5 19v-3a2.5 2.5 0 0 1 5 0v3" stroke="AMB"/>',
    "folder": '<path d="M4 9h8l3 3h13v14H4z"/><circle cx="16" cy="19" r="3.2" stroke="AMB"/><path d="M9 19c2-4 12-4 14 0-2 4-12 4-14 0z" stroke="AMB" stroke-opacity=".6"/>',
}


def icons():
    for name, body in ICONS.items():
        g = body.replace('"AMB"', '"%s"' % C["amber"])
        s = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 36 36" width="36" height="36"><rect x=".5" y=".5" width="35" height="35" rx="7" fill="%s" stroke="%s"/>'
             '<g transform="translate(2 2)" fill="none" stroke="%s" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">%s</g></svg>\n' % (C["panel"], C["line"], C["cyan"], g))
        write("icons/%s.svg" % name, s)


# ------------------------------------------------------------------ terminal scenes

# Text that `brain` printed on a made-up folder (3 short notes and one made-up Claude Code chat), on 2026-11-03.
# Long lines are cut with an ellipsis; nothing else is changed. The home folder is shown as ~.
TERMINAL = {
    "setup": [
        ("cmd", "brain onboard --plan"),
        ("out", "Brain folder: ~/brain (will be created)"),
        ("out", "Notes folders found:"),
        ("out", "  ~/Documents     3 notes  2026-11-03 to 2026-11-03"),
        ("out", "AI chat histories found:"),
        ("out", "  claude       1 chats  2026-11-03 to 2026-11-03"),
        ("out", "Not supported yet: Gemini chats, ChatGPT exports, Cursor chats"),
        ("ok", "Nothing is ingested unless you choose it."),
        ("gap", ""),
        ("cmd", "brain onboard --yes --notes ~/Documents/notes --sessions claude"),
        ("out", "Done:"),
        ("out", "  brain folder ~/brain"),
        ("out", "  claude chats: chats: 1 sessions, 1 converted, 1 notes written, 0 empty, 0 removed, 0 errors, 10 redactions; …"),
        ("out", "  search config ~/.config/qmd/index.yml (+1 notes collections)"),
        ("ok", "  qmd update ok"),
    ],
    "search": [
        ("cmd", 'brain search "kitchen budget"'),
        ("hit", "~/Documents/notes/kitchen-renovation.md", "Kitchen renovation Budget is 18,000. The quote from Marta's firm covers cabinets and the island. Decision: oak fronts"),
        ("gap", ""),
        ("cmd", 'brain search "coupon subscription cart"'),
        ("hit", "~/brain/chats/2026-11-03-launch-site-s1.md", "Turn 0: we are debugging the pricing page checkout flow. The coupon field breaks when the cart has a subscription. My API key is [redacted] and"),
    ],
}


def terminal(name, title, lines, cycle=16, width=1000, fs=13.5):
    cw = fs * 0.602
    lh = 24
    top = 62
    h = top + lh * len(lines) + 34
    keyfr, body = [], []
    t = 1.0
    cover = C["panel"]
    for i, ln in enumerate(lines):
        kind = ln[0]
        y = top + lh * i + 8
        if kind == "gap":
            continue
        if kind == "cmd":
            txt, tspans, typ = ln[1], [(C["amber"], "$ "), (C["text"], ln[1])], 0.045 * len(ln[1]) + 0.3
            n = len(ln[1]) + 2
        elif kind == "hit":
            room = int((width - 84) / cw) - len(ln[1]) - 2
            snip = ln[2] if len(ln[2]) <= room else ln[2][:room - 1].rstrip() + "…"
            tspans = [(C["green"], ln[1]), (C["dim"], "  " + snip)]
            n = len(ln[1]) + 2 + len(snip)
            typ = 0.5
        else:
            col = C["green"] if kind == "ok" else C["text"] if kind == "out" else C["dim"]
            tspans = [(col, ln[1])]
            n = len(ln[1])
            typ = 0.35
        x0 = 40
        s0, s1 = t / cycle * 100, (t + typ) / cycle * 100
        wpx = min(n * cw + 24, width - 60)
        keyfr.append("@keyframes t%d{0%%{opacity:0}%.2f%%{opacity:1}93%%{opacity:1}97%%{opacity:0}100%%{opacity:0}}"
                     "@keyframes c%d{0%%{transform:translateX(0)}%.2f%%{transform:translateX(0)}%.2f%%{transform:translateX(%.0fpx)}100%%{transform:translateX(%.0fpx)}}" % (i, s0, i, s0, s1, wpx, wpx))
        spans = "".join('<tspan fill="%s">%s</tspan>' % (c, esc(s)) for c, s in tspans)
        body.append('<text x="%d" y="%d" font-family="%s" font-size="%g" xml:space="preserve" style="animation:t%d %ds linear infinite;opacity:0">%s</text>'
                    % (x0, y + 4, MONO, fs, i, cycle, spans))
        body.append('<rect x="%d" y="%d" width="%d" height="%d" fill="%s" style="animation:c%d %ds linear infinite"/>' % (x0 - 4, y - 14, wpx + 4, 22, cover, i, cycle))
        t += typ + (0.9 if kind == "cmd" else 0.18)
    if t + 2 > cycle:
        raise SystemExit("%s: cycle %d too short, needs %.1f" % (name, cycle, t + 2))
    cur_y = top + lh * len(lines) + 8
    body.append('<rect x="40" y="%d" width="9" height="16" fill="%s" opacity=".9"><animate attributeName="opacity" values="1;0;1" dur="1s" repeatCount="indefinite"/></rect>' % (cur_y - 6, C["cyan"]))
    chrome = [
        '<polygon points="%s" fill="%s" stroke="%s" stroke-width="1.3"/>' % (chamfer(2, 2, width - 4, h - 4, 20), C["panel"], C["line"]),
        '<rect x="2" y="2" width="%d" height="36" fill="%s" opacity=".55"/>' % (width - 22, C["panel2"]),
        '<circle cx="28" cy="20" r="4.5" fill="%s"/><circle cx="46" cy="20" r="4.5" fill="%s" opacity=".7"/><circle cx="64" cy="20" r="4.5" fill="%s" opacity=".4"/>' % (C["amber"], C["cyan"], C["cyan"]),
        '<text x="92" y="25" font-family="%s" font-size="12" letter-spacing="3" fill="%s">%s</text>' % (SANS, C["dim"], esc(title.upper())),
        '<text x="%d" y="25" text-anchor="end" font-family="%s" font-size="11" letter-spacing="2" fill="%s">REAL OUTPUT  //  MADE-UP FOLDER</text>' % (width - 28, SANS, C["amber"]),
        brackets(2, 2, width - 4, h - 4, 16, C["cyan"], 1.5),
    ]
    over = '<rect width="%d" height="%d" fill="url(#scan)"/>' % (width, h)
    write(name, svg(width, h, "".join(chrome) + "".join(body) + over, "".join(keyfr)))


# ------------------------------------------------------------------ chats scene

def picture(name, w, h):
    import base64
    with open(os.path.join(HERE, "source", name), "rb") as f:
        return '<image href="data:image/jpeg;base64,%s" width="%d" height="%d"/>' % (base64.b64encode(f.read()).decode(), w, h)


def label(x, y, text, color, size=12, anchor="middle", spacing=3):
    return '<text x="%g" y="%g" text-anchor="%s" font-family="%s" font-size="%g" letter-spacing="%g" font-weight="700" fill="%s" filter="url(#glow)">%s</text>' % (x, y, anchor, SANS, size, spacing, color, esc(text))


def chip(x, y, w, text, color, anim=""):
    return ('<g %s><polygon points="%s" fill="#04070d" fill-opacity=".82" stroke="%s" stroke-width="1.2"/>'
            '<text x="%g" y="%g" text-anchor="middle" font-family="%s" font-size="12.5" fill="%s">%s</text></g>'
            % (anim, chamfer(x - w / 2, y - 16, w, 30, 8), color, x, y + 4, MONO, color, esc(text)))


def chats_scene():
    """Codex drew the picture (source/chat.jpg, prompt in source/scenes-prompt.txt). Captions, the flowing light and the
    key-to-[redacted] callouts are drawn over it. Picture positions are in its own 1672x941 space, scaled by k."""
    w, h, cyc = 1000, 563, 9
    k = w / 1672
    css = ("@keyframes before{0%,50%{opacity:1}60%,100%{opacity:.0}}"
           "@keyframes after{0%,50%{opacity:0}62%,92%{opacity:1}100%{opacity:0}}"
           "@keyframes gate{0%,100%{opacity:.04}50%{opacity:.2}}")
    o = [picture("chat.jpg", w, h)]
    o.append('<ellipse cx="%.0f" cy="%.0f" rx="70" ry="150" fill="%s" opacity=".4" filter="url(#glow2)" style="animation:gate 2.2s ease-in-out infinite"/>' % (850 * k, 400 * k, C["amber"]))
    # light flows from the chat, through the gate, to the note
    path = "M%.0f %.0f C %.0f %.0f %.0f %.0f %.0f %.0f" % (535 * k, 410 * k, 700 * k, 470 * k, 1000 * k, 330 * k, 1205 * k, 388 * k)
    o.append('<path id="flow" d="%s" fill="none"/>' % path)
    for i in range(7):
        col = C["green"] if i % 2 else C["cyan"]
        o.append('<circle r="3.2" fill="%s" filter="url(#glow)"><animateMotion dur="3.4s" begin="-%.1fs" repeatCount="indefinite"><mpath href="#flow"/></animateMotion></circle>' % (col, i * 0.48))
    # captions in the three plates
    for cx, text, col in ((328, "YOUR CHAT", C["cyan"]), (850, "REDACTION PASS", C["amber"]), (1360, "A NOTE IN YOUR BRAIN", C["green"])):
        o.append(label(cx * k, 752 * k + 4, text, col))
    # the key, before and after
    o.append(chip(328 * k, 84, 250, "my key is sk-ant-api03-…", C["amber"], 'style="animation:before %ds linear infinite"' % cyc))
    o.append(chip(1360 * k, 84, 250, "my key is [redacted]", C["green"], 'style="animation:after %ds linear infinite;opacity:0"' % cyc))
    o.append('<path d="M%.0f 100 V%.0f" stroke="%s" stroke-width="1.2" stroke-dasharray="3 4" style="animation:after %ds linear infinite;opacity:0"/>' % (1360 * k, 357 * k - 6, C["green"], cyc))
    o.append('<rect width="%d" height="%d" fill="url(#scan)"/>' % (w, h))
    write("scene-chats.svg", svg(w, h, "".join(o), css))


# ------------------------------------------------------------------ map and privacy

def where_scene():
    """Codex drew the glass panels, the index core and the light conduits (source/map.jpg, prompt in source/map-prompt.txt),
    all empty. The folder names, commands and moving light are drawn over it, so every word is exact."""
    w, h = 1000, 563
    k = w / 1672
    css = "@keyframes core{0%,100%{opacity:.1}50%{opacity:.4}}"
    o = [picture("map.jpg", w, h)]
    o.append('<circle cx="%.0f" cy="%.0f" r="52" fill="%s" filter="url(#glow2)" style="animation:core 2.6s ease-in-out infinite"/>' % (872 * k, 390 * k, C["amber"]))
    # light runs along the two conduits and down to the code strip
    for pid, d in (("c1", "M%.0f %.0f H%.0f" % (556 * k, 385 * k, 705 * k)), ("c2", "M%.0f %.0f H%.0f" % (1046 * k, 385 * k, 1198 * k)),
                   ("c3", "M%.0f %.0f V%.0f H%.0f" % (118 * k, 668 * k, 792 * k, 160 * k))):
        o.append('<path id="%s" d="%s" fill="none"/>' % (pid, d))
        for i in range(3):
            o.append('<circle r="2.6" fill="%s" filter="url(#glow)"><animateMotion dur="2.4s" begin="-%.1fs" repeatCount="indefinite"><mpath href="#%s"/></animateMotion></circle>' % (C["cyan"] if pid != "c2" else C["green"], i * 0.8, pid))
    # left panel: the brain folder
    lx, ly = 62 * k, 100 * k
    o.append(label(lx + 18, ly + 26, "YOUR BRAIN  //  ~/brain", C["cyan"], 12, "start"))
    secs = (("rules", "how you want work done"), ("agents", "lessons your AI learned"), ("projects", "notes per project"), ("private", "never leaves this computer"),
            ("chats", "your AI chats as notes"), ("days", "day pages"), ("inbox", "things to sort"))
    for i, (n, d) in enumerate(secs):
        y = ly + 42 + i * 40
        col = C["amber"] if n == "private" else C["cyan"]
        o.append('<polygon points="%s" fill="%s" fill-opacity=".08" stroke="%s" stroke-width="1"/>' % (chamfer(lx + 14, y, 267, 33, 8), col, col))
        o.append('<text x="%.0f" y="%.0f" font-family="%s" font-size="13.5" font-weight="700" fill="%s">%s/</text><text x="%.0f" y="%.0f" font-family="%s" font-size="11.5" fill="#9fb4c8">%s</text>'
                 % (lx + 26, y + 21, MONO, col, n, lx + 114, y + 21, SANS, esc(d)))
    # centre: the index
    o.append(label(872 * k, 676 * k, "LOCAL SEARCH INDEX  //  qmd", C["amber"], 12))
    # right panel: the command
    rx, ry = 1198 * k, 190 * k
    o.append(label(rx + 18, ry + 26, "THE BRAIN COMMAND", C["cyan"], 12, "start"))
    for i, (c, d) in enumerate((("brain search", "best five notes"), ("brain ask", "short answer + sources"), ("brain onboard", "choose what goes in"),
                                ("brain day", "what moved today"), ("brain status", "is the index fresh?"))):
        y = ry + 58 + i * 38
        o.append('<text x="%.0f" y="%.0f" font-family="%s" font-size="13.5" font-weight="700" fill="%s">%s</text><text x="%.0f" y="%.0f" font-family="%s" font-size="11" fill="#9fb4c8">%s</text>'
                 % (rx + 18, y, MONO, C["text"], c, rx + 18, y + 15, SANS, esc(d)))
    # bottom strip: the code in this repository
    sx, sy = 160 * k, 760 * k
    o.append(label(sx, sy - 8, "THE CODE  //  THIS REPOSITORY", C["amber"], 12, "start"))
    code = ("bin", "ask", "chats", "index", "day", "jobs", "media", "eval", "deciders", "deck")
    cw = (1430 * k - 14) / 10
    for i, n in enumerate(code):
        x = sx + 7 + i * cw
        o.append('<polygon points="%s" fill="%s" fill-opacity=".08" stroke="%s" stroke-opacity=".7"/><text x="%.0f" y="%.0f" text-anchor="middle" font-family="%s" font-size="12.5" fill="%s">%s/</text>'
                 % (chamfer(x, sy + 12, cw - 6, 34, 8), C["cyan"], C["cyan"], x + (cw - 6) / 2, sy + 34, MONO, C["text"], n))
    o.append('<rect width="%d" height="%d" fill="url(#scan)"/>' % (w, h))
    write("scene-where.svg", svg(w, h, "".join(o), css))


def private_scene():
    """Codex drew the picture (source/private.jpg). Captions, the private-list tag and the blocked pulse are drawn over it."""
    w, h = 1000, 563
    k = w / 1672
    css = ("@keyframes lock{0%,100%{opacity:.06}50%{opacity:.3}}"
           "@keyframes try{0%{transform:translateX(0);opacity:0}10%{opacity:1}55%{transform:translateX(@A@px);opacity:1}70%,100%{transform:translateX(@B@px);opacity:0}}"
           ).replace("@A@", "%.0f" % (50 * k)).replace("@B@", "%.0f" % (62 * k))
    o = [picture("private.jpg", w, h)]
    o.append('<circle cx="%.0f" cy="%.0f" r="46" fill="%s" opacity=".4" filter="url(#glow2)" style="animation:lock 2.4s ease-in-out infinite"/>' % (1010 * k, 480 * k, C["amber"]))
    # a try to reach the outside stops at the gate
    for i in range(3):
        o.append('<circle cx="%.0f" cy="%.0f" r="3" fill="%s" filter="url(#glow)" style="animation:try 3s linear infinite;animation-delay:%.1fs;opacity:0"/>' % (1110 * k, 493 * k, C["amber"], i))
    o.append(label(335, 798 * k + 4, "THIS COMPUTER  //  YOUR NOTES, CHATS AND INDEX", C["green"], 12))
    o.append(label(1408 * k, 798 * k + 4, "ONLINE SERVICES", C["dim"], 12))
    o.append(chip(990 * k, 118, 168, "THE PRIVATE LIST", C["amber"]))
    o.append('<path d="M%.0f 134 V%.0f" stroke="%s" stroke-width="1.2" stroke-dasharray="3 4"/>' % (990 * k, 425 * k - 8, C["amber"]))
    o.append('<rect width="%d" height="%d" fill="url(#scan)"/>' % (w, h))
    write("scene-private.svg", svg(w, h, "".join(o), css))


def main():
    hero()
    for i, (t, s) in enumerate((("Meet your brain", "One folder of notes, one search, on your own computer"),
                                ("Your chats become notes", "Claude Code and Codex history, with secrets removed first"),
                                ("Ask it anything", "Plain words in, the best notes and their sources out"),
                                ("Where everything lives", "Your folder, the index, and the code in this repository"),
                                ("Your notes stay yours", "Local by default, redacted by default, private on request")), 1):
        banner(i, t, s)
    icons()
    terminal("scene-setup.svg", "brain // first run", TERMINAL["setup"], cycle=22)
    terminal("scene-search.svg", "brain // search", TERMINAL["search"], cycle=14)
    chats_scene()
    where_scene()
    private_scene()


if __name__ == "__main__":
    main()
