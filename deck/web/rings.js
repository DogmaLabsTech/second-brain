// note rings: FRESHNESS, LENGTH, NEAREST in the 04 Target acquired panel.
// Each ring is a 270° instrument: a scale with ticks at real values, a soft track, a gradient arc (conic, masked) with a glowing
// round tip, the value in the middle. Values sweep with an eased tween; on a note change they sweep from the last note's value.
// Test switch: #...&ringt=0.5 freezes every ring half way through its sweep.
const LOG = (v, top) => Math.log(1 + v) / Math.log(1 + top), UNLOG = (p, top) => Math.exp(p * Math.log(1 + top)) - 1;
const clamp = (v, a = 0, b = 1) => Math.min(b, Math.max(a, v)), esc = s => String(s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]);
const ago = d => d < .5 ? 'today' : d < 1.5 ? 'yesterday' : d < 30 ? Math.round(d) + ' days ago' : d < 365 ? Math.max(1, Math.round(d / 30.4)) + (Math.round(d / 30.4) > 1 ? ' months ago' : ' month ago') : Math.round(d / 365) + ' year(s) ago';
const KINDS = {
  fresh: { label: 'FRESHNESS', sub: 'last change', ends: ['1y', 'now'], marks: [1, 7, 30, 90],
    toP: d => 1 - LOG(d, 365), fromP: p => UNLOG(1 - p, 365),
    fmt: d => d < .5 ? ['today', ''] : d < 30 ? [Math.round(d), 'd'] : d < 365 ? [Math.max(1, Math.round(d / 30.4)), 'mo'] : [Math.round(d / 365), 'y'],
    band: d => d <= 7 ? 'hi' : d <= 30 ? 'mid' : 'lo',
    tip: (d, x) => `<b>FRESHNESS</b>Changed <em>${ago(d)}</em> (${x.date}).<i>Full ring = changed today. It empties as the note gets older; a year or more is empty. Ticks: 1 day, 1 week, 1 month, 3 months.</i>` },
  length: { label: 'LENGTH', sub: 'time to read', ends: ['0', '30m'], marks: [1, 5, 15],
    toP: m => LOG(m, 30), fromP: p => UNLOG(p, 30),
    fmt: m => m < .75 ? ['<1', 'min'] : [Math.round(m), 'min'],
    band: m => m >= 8 ? 'hi' : m >= 2 ? 'mid' : 'lo',
    tip: (m, x) => `<b>LENGTH</b>About <em>${m < .75 ? 'under a minute' : Math.round(m) + (Math.round(m) === 1 ? ' minute' : ' minutes')}</em> to read (${x.est ? 'roughly ' : ''}${x.words.toLocaleString()} words).<i>Longer notes fill more of the ring; 30 minutes or more is full. Ticks: 1, 5 and 15 minutes.</i>` },
  near: { label: 'NEAREST', sub: 'closest note', ends: ['50', '100'], marks: [.6, .7, .8, .9],
    toP: s => clamp((s - .5) / .5), fromP: p => .5 + p * .5,
    fmt: s => [Math.round(s * 100), '%'],
    band: s => s >= .85 ? 'hi' : s >= .7 ? 'mid' : 'lo',
    tip: (s, x) => `<b>NEAREST</b>Its closest note in meaning is <em>“${esc(x.name)}”</em>, <em>${Math.round(s * 100)}%</em> alike.<i>Ring runs from 50% (loosely related) to 100% (the same text). Click the ring to open that note.</i>` } };
const A0 = 135, SPAN = 270, RA = 36, pt = (p, r) => { const a = (A0 + SPAN * p) * Math.PI / 180; return [r * Math.cos(a), r * Math.sin(a)]; };
const f2 = v => Math.round(v * 100) / 100, arcD = r => { const [x0, y0] = pt(0, r), [x1, y1] = pt(1, r); return `M${f2(x0)} ${f2(y0)}A${r} ${r} 0 1 1 ${f2(x1)} ${f2(y1)}`; };
const NMIN = 36, last = {}, FREEZE = +((location.hash.match(/[&#]ringt=([\d.]+)/) || [])[1] ?? -1), STILL = location.hash.includes('still');
const ease = k => k < .5 ? 4 * k * k * k : 1 - Math.pow(-2 * k + 2, 3) / 2;
let gen = 0, tip = null, tipT = 0;

function dial(key) { const K = KINDS[key], tick = (p, r0, r1, cls) => { const [a, b] = pt(p, r0), [c, d] = pt(p, r1); return `<line class="${cls}" x1="${f2(a)}" y1="${f2(b)}" x2="${f2(c)}" y2="${f2(d)}"/>`; };
  let mn = ''; for (let n = 0; n <= NMIN; n++) mn += tick(n / NMIN, 43.5, 46.5, 'mn');
  const mj = [0, ...K.marks.map(K.toP), 1].map(p => tick(p, 41.8, 48, 'mj')).join(''), [sx, sy] = pt(0, 44), [ex, ey] = pt(1, 44);
  return `<div class="nr" data-k="${key}"><div class="nr-dial">
    <svg viewBox="-50 -50 100 100"><circle class="face" r="31.5"/><path class="trk" d="${arcD(RA)}"/>${mn}${mj}
      <text class="sc" x="${f2(sx * .62)}" y="${f2(sy + 11)}">${K.ends[0]}</text><text class="sc" x="${f2(ex * .62)}" y="${f2(ey + 11)}">${K.ends[1]}</text></svg>
    <div class="nr-glow"><div class="nr-arc"></div></div>
    <svg viewBox="-50 -50 100 100"><circle class="c0" r="3.5"/><circle class="c1" r="3.7"/><circle class="c2" r="1.5"/></svg>
    <div class="nr-val"></div></div><span class="nr-lb">${K.label}</span><span class="nr-sub">${K.sub}</span></div>`; }

// draw one ring at fill p, showing value v (the exact value at rest, the scale's value while sweeping)
function draw(r, p, v, wait) { const K = KINDS[r.key], el = r.el; last[r.key] = p; el.querySelector('.nr-arc').style.setProperty('--p', p.toFixed(4));
  const [x, y] = pt(p, RA), show = p > .004 ? '' : 'none'; for (const c of el.querySelectorAll('.c1,.c2')) { c.setAttribute('cx', f2(x)); c.setAttribute('cy', f2(y)); c.style.display = show; }
  const c0 = el.querySelector('.c0'), [x0, y0] = pt(0, RA); c0.setAttribute('cx', f2(x0)); c0.setAttribute('cy', f2(y0)); c0.style.display = show;
  el.querySelectorAll('.mn').forEach((t, n) => t.classList.toggle('on', n / NMIN <= p + 1e-6 && p > .004));
  const [big, unit] = K.fmt(v), val = el.querySelector('.nr-val'); val.className = 'nr-val' + (typeof big === 'string' && /[a-z]/.test(big) ? ' word' : '') + (wait ? ' wait' : '');
  val.innerHTML = `<b>${big}${unit ? `<small>${unit}</small>` : ''}</b>`; }

function sweep(r, to, ms, delay) { const K = KINDS[r.key], p0 = r.p, p1 = K.toP(to), g = gen; r.v = to; r.wait = false;
  r.el.style.setProperty('--b', `var(--ring-${K.band(to)})`);
  if (FREEZE >= 0) { r.p = p0 + (p1 - p0) * ease(clamp(FREEZE)); return draw(r, r.p, K.fromP(r.p)); }
  if (STILL || Math.abs(p1 - p0) < 1e-4) { r.p = p1; return draw(r, p1, to); }
  const t0 = performance.now() + delay; (function f(t) { if (g !== gen || r.v !== to) return; const k = clamp((t - t0) / ms); r.p = p0 + (p1 - p0) * ease(k);
    k < 1 ? draw(r, r.p, K.fromP(r.p)) : draw(r, p1, to); if (k < 1) requestAnimationFrame(f); })(performance.now()); }

function showTip(r) { if (!tip) { tip = document.createElement('div'); tip.id = 'nrtip'; document.body.appendChild(tip); }
  const K = KINDS[r.key]; if (r.wait) return; tip.innerHTML = K.tip(r.v, r.x); tip.style.setProperty('--b', getComputedStyle(r.el).getPropertyValue('--b'));
  const b = r.el.querySelector('.nr-dial').getBoundingClientRect(), e = r.el.getBoundingClientRect(), w = tip.offsetWidth, h = tip.offsetHeight;
  let x = b.left + b.width / 2 - w / 2, y = e.bottom + 6; x = clamp(x, 8, innerWidth - w - 8); if (y + h > innerHeight - 8) y = b.top - h - 6;
  tip.style.left = x + 'px'; tip.style.top = y + 'px'; tip.classList.add('on'); }
export function hideRingTip() { clearTimeout(tipT); if (tip) tip.classList.remove('on'); }

let cur = null;
// fill the ring row for a note. o: { i (note index), first, days, date, words (null = not known yet), estWords, sim, name, open }
export function rings(box, o) { gen++; hideRingTip(); box.innerHTML = dial('fresh') + dial('length') + dial('near');
  const R = {}; box.querySelectorAll('.nr').forEach(el => { const key = el.dataset.k; R[key] = { key, el, p: o.first ? 0 : last[key] ?? 0, v: 0, x: o, wait: false }; });
  const ms = o.first ? 1400 : 750, delay = o.first ? 420 : 0;
  sweep(R.fresh, o.days, ms, delay); sweep(R.near, o.sim, ms, delay + (o.first ? 120 : 0));
  if (o.words != null) sweep(R.length, o.words / 220, ms, delay + 60); else { const r = R.length; r.wait = true; draw(r, r.p, KINDS.length.fromP(r.p), true);
    r.fallback = setTimeout(() => r.wait && ringWords(o.i, o.estWords, true), 2500); }
  R.near.el.classList.add('go'); R.near.el.onclick = () => { hideRingTip(); o.open(); };
  for (const r of Object.values(R)) { r.el.onmouseenter = () => { clearTimeout(tipT); tipT = setTimeout(() => showTip(r), 140); }; r.el.onmouseleave = hideRingTip; }
  cur = { R, o }; }
// the reader has the note's text: its word count fills LENGTH (est = a guess from the index pieces when the text never came)
export function ringWords(i, words, est = false) { if (!cur || cur.o.i !== i || !cur.R.length.el.isConnected) return; const r = cur.R.length; clearTimeout(r.fallback);
  r.x = { ...cur.o, words, est }; const was = r.wait; sweep(r, words / 220, was ? 900 : 500, 0); }
