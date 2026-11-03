#!/usr/bin/env python3
"""Draws the README pictures (animated SVG, no images, no fonts to load). Run: python3 make_art.py

The terminal scenes show text that `brain` really printed on a made-up folder (see TERMINAL below). Everything is
drawn with plain shapes; the look is a dark holographic panel with cyan and amber light."""
import html
import math
import os
import random

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

def brain_points(rnd, cx, cy, a, b, n):
    def outline(t):
        r = 1 + 0.07 * math.sin(5 * t) + 0.04 * math.sin(9 * t + 1)
        x = cx + a * math.cos(t) * r
        y = cy + b * math.sin(t) * r * (0.78 if math.sin(t) > 0 else 1.0)
        return x, y
    poly = [outline(i / 200 * 2 * math.pi) for i in range(200)]

    def inside(px, py):
        ok = False
        j = len(poly) - 1
        for i in range(len(poly)):
            xi, yi = poly[i]
            xj, yj = poly[j]
            if (yi > py) != (yj > py) and px < (xj - xi) * (py - yi) / (yj - yi) + xi:
                ok = not ok
            j = i
        return ok
    pts = []
    while len(pts) < n:
        px, py = cx + rnd.uniform(-a, a), cy + rnd.uniform(-b, b)
        if inside(px, py) and all((px - x) ** 2 + (py - y) ** 2 > 24 ** 2 for x, y in pts):
            pts.append((px, py))
    return poly, pts


def hero():
    rnd = random.Random(11)
    w, h = 1280, 440
    cx, cy = 930, 222
    poly, pts = brain_points(rnd, cx, cy, 235, 150, 86)
    out = ['<rect width="%d" height="%d" fill="url(#sky)"/><rect width="%d" height="%d" fill="url(#hex)"/>' % (w, h, w, h)]
    stars = "".join('<circle cx="%d" cy="%d" r="%.1f" fill="#bfeeff" opacity="%.2f"/>' % (rnd.randint(0, w), rnd.randint(0, h), rnd.uniform(.4, 1.3), rnd.uniform(.15, .6)) for _ in range(90))
    out.append(stars)
    # orbit rings
    for i, (rx, ry, dur, col) in enumerate(((330, 205, 40, C["cyan"]), (300, 188, 55, C["amber"]), (360, 225, 70, C["cyan"]))):
        out.append('<ellipse cx="%d" cy="%d" rx="%d" ry="%d" fill="none" stroke="%s" stroke-opacity=".28" stroke-width="1" stroke-dasharray="3 9">'
                   '<animateTransform attributeName="transform" type="rotate" from="0 %d %d" to="%d %d %d" dur="%ds" repeatCount="indefinite"/></ellipse>'
                   % (cx, cy, rx, ry, col, cx, cy, 360 if i % 2 == 0 else -360, cx, cy, dur))
    # cerebellum and stem
    out.append('<path d="M%d %d q40 34 78 18 q30 -14 14 -44" fill="none" stroke="%s" stroke-width="2" stroke-opacity=".8" filter="url(#glow)"/>' % (cx + 50, cy + 128, C["cyan"]))
    out.append('<path d="M%d %d q6 40 -4 70 h26 q-4 -34 4 -62" fill="%s" fill-opacity=".05" stroke="%s" stroke-width="1.8" stroke-opacity=".8"/>' % (cx - 10, cy + 112, C["cyan"], C["cyan"]))
    # links between near nodes
    lines = []
    for i, p in enumerate(pts):
        for q in pts[i + 1:]:
            d = math.hypot(p[0] - q[0], p[1] - q[1])
            if d < 66:
                lines.append('<line x1="%.0f" y1="%.0f" x2="%.0f" y2="%.0f" stroke-opacity="%.2f"/>' % (p[0], p[1], q[0], q[1], .55 - d / 150))
    out.append('<g stroke="%s" stroke-width="1">%s</g>' % (C["cyan"], "".join(lines)))
    pathd = "M" + " L".join("%.0f %.0f" % p for p in poly) + "Z"
    out.append('<path d="%s" fill="%s" fill-opacity=".05" stroke="%s" stroke-width="2" filter="url(#glow)" stroke-opacity=".9"/>' % (pathd, C["cyan"], C["cyan"]))
    mid = " ".join("%.0f,%.0f" % (cx + math.sin(i / 7) * 14 + (i - 11) * 0.5, cy - 118 + i * 11.2) for i in range(22))
    out.append('<polyline points="%s" fill="none" stroke="%s" stroke-opacity=".55" stroke-width="1.5" stroke-dasharray="4 5"/>' % (mid, C["cyan"]))
    nodes = []
    for i, (x, y) in enumerate(pts):
        amber = i % 9 == 0
        col = C["amber"] if amber else C["cyan"]
        nodes.append('<circle cx="%.0f" cy="%.0f" r="%.1f" fill="%s" filter="url(#glow)"><animate attributeName="opacity" values="1;.25;1" dur="%.1fs" begin="-%.1fs" repeatCount="indefinite"/></circle>'
                     % (x, y, 3.6 if amber else 2.4, col, rnd.uniform(2.2, 5), rnd.uniform(0, 4)))
    out.append("".join(nodes))
    # scan plane
    out.append('<rect x="%d" y="40" width="3" height="360" fill="url(#beam)" opacity=".8"><animate attributeName="x" values="%d;%d;%d" dur="7s" repeatCount="indefinite"/></rect>' % (cx - 250, cx - 250, cx + 250, cx - 250))
    # left text block
    out.append(brackets(48, 60, 600, 320, 22))
    out.append('<text x="84" y="124" font-family="%s" font-size="15" letter-spacing="6" fill="%s">AGENTIC MEMORY  //  ON YOUR COMPUTER</text>' % (SANS, C["amber"]))
    out.append('<text x="80" y="206" font-family="%s" font-size="86" font-weight="700" letter-spacing="4" fill="%s" filter="url(#glow2)">SECOND</text>' % (SANS, C["text"]))
    out.append('<text x="80" y="288" font-family="%s" font-size="86" font-weight="700" letter-spacing="4" fill="%s" filter="url(#glow2)">BRAIN</text>' % (SANS, C["cyan"]))
    out.append('<text x="84" y="334" font-family="%s" font-size="19" fill="%s">Your notes and your AI chats, in one searchable memory.</text>' % (SANS, C["dim"]))
    chips = ("LOCAL", "PRIVATE", "SEARCHABLE")
    x = 84
    for t in chips:
        wd = 24 + len(t) * 11
        out.append('<polygon points="%s" fill="%s" fill-opacity=".08" stroke="%s" stroke-width="1.2"/><text x="%d" y="364" font-family="%s" font-size="12" letter-spacing="3" fill="%s">%s</text>'
                   % (chamfer(x, 344, wd, 28, 7), C["cyan"], C["cyan"], x + 12, SANS, C["cyan"], t))
        x += wd + 14
    out.append('<rect width="%d" height="%d" fill="url(#scan)"/>' % (w, h))
    out.append('<polygon points="%s" fill="none" stroke="%s" stroke-opacity=".5"/>' % (chamfer(1, 1, w - 2, h - 2, 26), C["line"]))
    write("hero.svg", svg(w, h, "".join(out)))


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

def chats_scene():
    w, h, cyc = 1000, 312, 9
    css = ("@keyframes sweep{0%{transform:translateX(0);opacity:0}8%{opacity:1}55%{transform:translateX(470px);opacity:1}62%{opacity:0}100%{transform:translateX(470px);opacity:0}}"
           "@keyframes after{0%{opacity:0}50%{opacity:0}62%{opacity:1}92%{opacity:1}100%{opacity:0}}"
           "@keyframes hot{0%,45%{fill:@A@}58%,100%{fill:@D@}}").replace("@A@", C["amber"]).replace("@D@", C["dim"])
    o = []

    def card(x, label, col):
        return ('<polygon points="%s" fill="%s" stroke="%s" stroke-width="1.3"/><text x="%d" y="%d" font-family="%s" font-size="12" letter-spacing="3" fill="%s">%s</text>'
                % (chamfer(x, 30, 360, 240, 16), C["panel"], col, x + 22, 62, SANS, col, label))
    o.append(card(30, "YOUR CHAT", C["cyan"]))
    o.append(card(610, "A NOTE IN YOUR BRAIN", C["green"]))
    left = [("You", C["amber"]), ("we are debugging the checkout flow.", C["text"]), ("My API key is sk-ant-api03-EXAMPLE…", None), ("please do not echo it.", C["text"]),
            ("Claude", C["cyan"]), ("The coupon field reads the cart total", C["text"]), ("before the subscription line is added.", C["text"])]
    y = 96
    for txt, col in left:
        if col is None:
            o.append('<text x="52" y="%d" font-family="%s" font-size="14" style="animation:hot %ds linear infinite" fill="%s">%s</text>' % (y, MONO, cyc, C["amber"], esc(txt)))
        else:
            o.append('<text x="52" y="%d" font-family="%s" font-size="14" fill="%s"%s>%s</text>' % (y, MONO, col, ' font-weight="700"' if txt in ("You", "Claude") else "", esc(txt)))
        y += 25
    right = [("You", C["amber"]), ("we are debugging the checkout flow.", C["text"]), ("My API key is [redacted]", "KEY"), ("please do not echo it.", C["text"]),
             ("Claude", C["cyan"]), ("The coupon field reads the cart total", C["text"]), ("before the subscription line is added.", C["text"])]
    y = 96
    g = []
    for txt, col in right:
        if col == "KEY":
            g.append('<text x="632" y="%d" font-family="%s" font-size="14" fill="%s" filter="url(#glow)">%s</text>' % (y, MONO, C["green"], esc(txt)))
        else:
            g.append('<text x="632" y="%d" font-family="%s" font-size="14" fill="%s"%s>%s</text>' % (y, MONO, col, ' font-weight="700"' if txt in ("You", "Claude") else "", esc(txt)))
        y += 25
    o.append('<g style="animation:after %ds linear infinite;opacity:0">%s</g>' % (cyc, "".join(g)))
    # scanner
    o.append('<g style="animation:sweep %ds linear infinite;opacity:0"><rect x="395" y="34" width="3" height="232" fill="url(#beam)" filter="url(#glow)"/>'
             '<polygon points="386,150 402,150 394,162" fill="%s"/><polygon points="386,138 402,138 394,126" fill="%s"/></g>' % (cyc, C["cyan"], C["cyan"]))
    o.append('<text x="500" y="298" text-anchor="middle" font-family="%s" font-size="12" letter-spacing="4" fill="%s">REDACTION PASS  //  BEFORE ANYTHING IS SAVED</text>' % (SANS, C["amber"]))
    # arrow between cards
    o.append('<path d="M404 150h12m-6-6 6 6-6 6M584 150h12m-6-6 6 6-6 6" stroke="%s" fill="none" stroke-width="2"/>' % C["cyan"])
    o.append('<rect width="%d" height="%d" fill="url(#scan)"/>' % (w, h))
    body = "".join(o)
    write("scene-chats.svg", svg(w, h, body, css))


# ------------------------------------------------------------------ map and privacy

def where_scene():
    w, h = 1000, 470
    o = ['<rect width="%d" height="%d" fill="url(#hex)" opacity=".8"/>' % (w, h)]
    # left: the brain folder
    o.append('<polygon points="%s" fill="%s" stroke="%s" stroke-width="1.3"/>' % (chamfer(20, 20, 400, 330, 20), C["panel"], C["cyan"]))
    o.append('<text x="44" y="54" font-family="%s" font-size="13" letter-spacing="3" fill="%s">YOUR BRAIN  //  ~/brain</text>' % (SANS, C["cyan"]))
    secs = (("rules", "how you want work done"), ("agents", "lessons your AI learned"), ("projects", "notes per project"), ("private", "never leaves this computer"),
            ("chats", "your AI chats as notes"), ("days", "day pages"), ("inbox", "things to sort"))
    for i, (n, d) in enumerate(secs):
        y = 74 + i * 38
        priv = n == "private"
        col = C["amber"] if priv else C["cyan"]
        o.append('<polygon points="%s" fill="%s" fill-opacity=".07" stroke="%s" stroke-width="1"/>' % (chamfer(44, y, 352, 30, 8), col, col))
        o.append('<text x="60" y="%d" font-family="%s" font-size="14" font-weight="700" fill="%s">%s/</text><text x="150" y="%d" font-family="%s" font-size="12.5" fill="%s">%s</text>' % (y + 20, MONO, col, n, y + 20, SANS, C["dim"], esc(d)))
    # middle: index
    o.append('<path d="M420 190h96" stroke="%s" stroke-width="2" stroke-dasharray="6 6" fill="none"><animate attributeName="stroke-dashoffset" values="24;0" dur="1.2s" repeatCount="indefinite"/></path>' % C["cyan"])
    o.append('<polygon points="%s" fill="%s" stroke="%s" stroke-width="1.3"/>' % (chamfer(516, 130, 130, 120, 14), C["panel2"], C["amber"]))
    o.append('<text x="581" y="176" text-anchor="middle" font-family="%s" font-size="12" letter-spacing="3" fill="%s">LOCAL</text><text x="581" y="200" text-anchor="middle" font-family="%s" font-size="22" font-weight="700" fill="%s" filter="url(#glow)">qmd</text><text x="581" y="226" text-anchor="middle" font-family="%s" font-size="11" fill="%s">search index</text>' % (SANS, C["amber"], SANS, C["text"], SANS, C["dim"]))
    o.append('<path d="M646 190h72" stroke="%s" stroke-width="2" stroke-dasharray="6 6" fill="none"><animate attributeName="stroke-dashoffset" values="24;0" dur="1.2s" repeatCount="indefinite"/></path>' % C["cyan"])
    # right: commands
    o.append('<polygon points="%s" fill="%s" stroke="%s" stroke-width="1.3"/>' % (chamfer(718, 70, 262, 240, 18), C["panel"], C["cyan"]))
    o.append('<text x="740" y="102" font-family="%s" font-size="13" letter-spacing="3" fill="%s">THE BRAIN COMMAND</text>' % (SANS, C["cyan"]))
    for i, (c, d) in enumerate((("brain search", "best five notes"), ("brain ask", "short answer + sources"), ("brain onboard", "choose what goes in"), ("brain day", "what moved today"), ("brain status", "is the index fresh?"))):
        y = 136 + i * 34
        o.append('<text x="740" y="%d" font-family="%s" font-size="14" font-weight="700" fill="%s">%s</text><text x="740" y="%d" font-family="%s" font-size="11.5" fill="%s">%s</text>' % (y, MONO, C["text"], c, y + 16, SANS, C["dim"], d))
    # bottom: the code folders
    o.append('<text x="20" y="392" font-family="%s" font-size="13" letter-spacing="3" fill="%s">THE CODE  //  THIS REPOSITORY</text>' % (SANS, C["amber"]))
    code = ("bin", "ask", "chats", "index", "day", "jobs", "media", "eval", "deciders", "deck")
    for i, n in enumerate(code):
        x = 20 + i * 96.5
        o.append('<polygon points="%s" fill="%s" fill-opacity=".06" stroke="%s" stroke-opacity=".7"/><text x="%g" y="438" text-anchor="middle" font-family="%s" font-size="13" fill="%s">%s/</text>' % (chamfer(x, 406, 88, 44, 9), C["cyan"], C["cyan"], x + 44, MONO, C["text"], n))
    o.append('<rect width="%d" height="%d" fill="url(#scan)"/>' % (w, h))
    write("scene-where.svg", svg(w, h, "".join(o)))


def private_scene():
    w, h = 1000, 340
    o = ['<rect width="%d" height="%d" fill="url(#hex)" opacity=".8"/>' % (w, h)]
    o.append('<polygon points="%s" fill="%s" fill-opacity=".5" stroke="%s" stroke-width="1.6"/>' % (chamfer(20, 20, 640, 300, 24), C["panel"], C["green"]))
    o.append('<text x="46" y="56" font-family="%s" font-size="13" letter-spacing="4" fill="%s">THIS COMPUTER</text>' % (SANS, C["green"]))
    parts = ((46, "your notes", "read in place,", "never changed"), (232, "your chats", "secrets removed", "before saving"), (418, "the index", "built here,", "searched here"))
    for x, a, b, c in parts:
        o.append('<polygon points="%s" fill="%s" stroke="%s"/>' % (chamfer(x, 92, 166, 112, 12), C["panel2"], C["cyan"]))
        o.append('<text x="%d" y="126" text-anchor="middle" font-family="%s" font-size="16" font-weight="700" fill="%s">%s</text>' % (x + 83, SANS, C["text"], a))
        o.append('<text x="%d" y="156" text-anchor="middle" font-family="%s" font-size="12.5" fill="%s">%s</text><text x="%d" y="176" text-anchor="middle" font-family="%s" font-size="12.5" fill="%s">%s</text>' % (x + 83, SANS, C["dim"], b, x + 83, SANS, C["dim"], c))
    o.append('<polygon points="%s" fill="%s" fill-opacity=".08" stroke="%s" stroke-width="1.4"/>' % (chamfer(46, 232, 538, 56, 12), C["amber"], C["amber"]))
    o.append('<text x="315" y="256" text-anchor="middle" font-family="%s" font-size="13" letter-spacing="2" font-weight="700" fill="%s">THE PRIVATE LIST</text><text x="315" y="276" text-anchor="middle" font-family="%s" font-size="12.5" fill="%s">words you choose keep a question away from any online model</text>' % (SANS, C["amber"], SANS, C["text"]))
    # gate and outside
    o.append('<path d="M660 170h110" stroke="%s" stroke-width="2" stroke-dasharray="4 8" fill="none" stroke-opacity=".6"/>' % C["red"])
    o.append('<polygon points="%s" fill="%s" stroke="%s" stroke-width="2"/><path d="M706 156l28 28M734 156l-28 28" stroke="%s" stroke-width="3"/>' % (chamfer(694, 144, 52, 52, 10), C["panel"], C["red"], C["red"]))
    o.append('<polygon points="%s" fill="%s" stroke="%s" stroke-dasharray="6 5" stroke-width="1.4"/>' % (chamfer(790, 100, 190, 140, 16), C["panel"], C["dim"]))
    o.append('<text x="885" y="150" text-anchor="middle" font-family="%s" font-size="13" letter-spacing="3" fill="%s">ONLINE</text><text x="885" y="174" text-anchor="middle" font-family="%s" font-size="16" font-weight="700" fill="%s">models and services</text><text x="885" y="204" text-anchor="middle" font-family="%s" font-size="12" fill="%s">only if you set one up</text>' % (SANS, C["dim"], SANS, C["text"], SANS, C["dim"]))
    o.append('<rect width="%d" height="%d" fill="url(#scan)"/>' % (w, h))
    write("scene-private.svg", svg(w, h, "".join(o)))


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
