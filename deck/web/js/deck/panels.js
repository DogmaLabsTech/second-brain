import { days, THREE } from '../../hud.js';
import { KC, S, age, clamp, cloud, hidden, hits, lock, lockAt, readerOpen, tl, wk } from '../deck-main.js';
// ---- panels
export const eff = () => S.focus || S.hoverG, mx2 = Math.max(...COLS.map(c => DOCS.filter(d => d.c === c).length));
document.getElementById('groups').innerHTML = COLS.map(c => { const n = DOCS.filter(d => d.c === c).length; return `<div class="row" data-c="${c}" style="--k:${KC(c)};--w:${Math.max(4, n / mx2 * 100)}%"><i></i><span>${NICE[c]}</span><u></u><em>${n}</em><b class="eye" title="hide">◉</b></div>`; }).join('');
document.querySelectorAll('#groups .row').forEach(r => { const c = r.dataset.c;
  r.onclick = () => { S.focus = S.focus === c ? null : c; document.querySelectorAll('#groups .row').forEach(x => x.classList.toggle('on', x.dataset.c === S.focus)); refresh(); renderSection(); };
  r.onmouseenter = () => { S.hoverG = c; refresh(); renderSection(); }; r.onmouseleave = () => { S.hoverG = null; refresh(); renderSection(); };
  r.querySelector('.eye').onclick = e => { e.stopPropagation(); hidden.has(c) ? hidden.delete(c) : hidden.add(c); r.classList.toggle('off', hidden.has(c)); refresh(); }; });
export function renderSection() {
  const c = eff(), a = DOCS.map((d, i) => i).filter(i => !c || DOCS[i].c === c), dd = i => days(DOCS[i].d);
  const w = a.filter(i => dd(i) <= 7).length, m = a.filter(i => dd(i) > 7 && dd(i) <= 30).length, o = a.length - w - m, pc = x => (x / a.length * 100).toFixed(1) + '%';
  document.getElementById('secn').textContent = c ? NICE[c].toUpperCase() : 'ALL SECTIONS';
  let h = `<div class="stat2"><div><b data-to="${a.length}">0</b><span>notes</span></div><div><b class="am" data-to="${w}">0</b><span>this week</span></div><div><b data-to="${Math.round(o / a.length * 100)}" data-sfx="%">0</b><span>older than 30d</span></div></div>
   <div class="fresh"><i style="width:0" data-w="${pc(w)}" style2=""></i><i style="width:0" data-w="${pc(m)}"></i><i style="width:0" data-w="${pc(o)}"></i></div><div class="k" style="font-size:10px;letter-spacing:.1em">■ <span style="color:var(--c)">WEEK</span> &nbsp;■ <span class="am">MONTH</span> &nbsp;■ OLDER</div>`;
  if (c) { const nw = [...a].sort((x, y) => DOCS[x].d < DOCS[y].d ? 1 : DOCS[x].d > DOCS[y].d ? -1 : 0).slice(0, 5);
    h += '<div class="h" style="margin-top:12px"><span>Newest here</span></div>' + nw.map(i => `<a class="nb" data-i="${i}" style="--k:${KC(c)}">${esc(DOCS[i].t.slice(0, 40))} <span class="k">· ${ago(DOCS[i].d)}</span></a>`).join(''); }
  else h += '<div class="h" style="margin-top:12px"><span>Busiest this week</span></div>' + [...COLS].sort((x, y) => wk(y) - wk(x)).slice(0, 6).map(k => { const t = DOCS.filter(d => d.c === k).length, ww = wk(k); return `<div class="mini" style="--k:${KC(k)}"><span style="color:${KC(k)}">${NICE[k]}</span><div class="fresh"><i style="width:0;background:${KC(k)}" data-w="${ww / t * 100}%"></i></div><b>${ww}</b></div>`; }).join('');
  document.getElementById('secbody').innerHTML = h; const fi = document.querySelectorAll('#secbody .fresh')[0]; if (fi) { const [i1, i2, i3] = fi.children; i1.style.background = 'var(--c)'; i2.style.background = 'var(--amber)'; i3.style.background = 'var(--dim)'; } animateIn(document.getElementById('secbody')); document.querySelectorAll('#secbody .nb').forEach(x => x.onclick = () => lock(+x.dataset.i)); }
export const tip = document.getElementById('tip'), tmp = new THREE.Vector3(), labels = [];
export const visible = i => !hidden.has(DOCS[i].c), match = i => !hits || hits.has(i), shown = i => tl.alpha(age(DOCS[i]));   // hits: the 06 Ask search's notes (null = no search)
export function refresh() { const e = eff(); DOCS.forEach((d, i) => { const b = shown(i); cloud.A[i] = !visible(i) || !b ? 0 : ((e && d.c !== e) ? .1 : match(i) ? 1 : .06) * b; }); cloud.flush(); }
export function mk(cls = 'lbl') { const e = document.createElement('div'); e.className = cls; document.body.append(e); return e; }
export function clearLabels() { labels.forEach(l => l.el.remove()); labels.length = 0; }
export function addLabel(i, txt, tag) { const el = mk(); el.style.setProperty('--k', KC(DOCS[i].c)); const t = tag || String(labels.length + 1).padStart(2, '0'); if (tag === '◎' || S.sel >= 0) { el.classList.add('tag'); el.innerHTML = `<i>${tag === '◎' ? '' : t}</i>`; if (tag === '◎') el.style.display = 'none'; } else el.innerHTML = `<i>${t}</i>${esc(txt.slice(0, 28))}`; labels.push({ i, el }); }
export const ret = mk('ret2'); ret.style.display = 'none';
const tickSvg = Array.from({ length: 36 }, (_, i) => { const a = i / 36 * Math.PI * 2, l = i % 3 ? 4 : 9; return `<line x1="${66 + Math.cos(a) * 62}" y1="${66 + Math.sin(a) * 62}" x2="${66 + Math.cos(a) * (62 - l)}" y2="${66 + Math.sin(a) * (62 - l)}"/>`; }).join('');
ret.innerHTML = `<svg viewBox="0 0 132 132" fill="none" style="stroke:var(--c)"><g class="g3" stroke-width="1" opacity=".8">${tickSvg}</g><g class="g1" stroke-width="2"><path d="M66 12a54 54 0 0 1 46 26" /><path d="M120 66a54 54 0 0 1-26 46"/><path d="M66 120a54 54 0 0 1-46-26"/><path d="M12 66a54 54 0 0 1 26-46"/></g>
  <g class="g2" stroke-width="1.5" stroke-dasharray="3 5" opacity=".85"><circle cx="66" cy="66" r="40"/></g><circle cx="66" cy="66" r="22" style="stroke:var(--amber)" stroke-width="1.5"/>
  <path d="M66 36v14M66 82v14M36 66h14M82 66h14" style="stroke:var(--hi)" stroke-width="1.5"/><circle cx="66" cy="66" r="2.5" style="fill:var(--amber);stroke:none"/>
  <path d="M4 20V4h16M112 4h16v16M128 112v16h-16M20 128H4v-16" stroke-width="2" style="opacity:var(--corner)"/></svg><div class="shock"></div>`;
export const xh = mk('xh'), xv = mk('xv'); xh.style.display = xv.style.display = 'none';
document.body.insertAdjacentHTML('beforeend', '<svg id="lead" style="display:none"><polyline id="leadl" points=""/><circle id="leadn" r="4" style="fill:var(--amber)"/><circle id="leadp" r="2.5" style="fill:var(--hi)"/></svg>');
export const leadSvg = document.getElementById('lead'), leadL = document.getElementById('leadl'), leadN = document.getElementById('leadn'), leadP = document.getElementById('leadp');
export function lead(x, y, t) { const pr = document.getElementById(readerOpen ? 'reader' : 'lockp').getBoundingClientRect(); if (!pr.width) return; const tx = pr.left, ex = tx - 34;
  const yE = clamp(y, pr.top + 26, pr.bottom - 36), dy = clamp(yE - y, -34, 34), P = [[x, y], [x + Math.abs(dy), y + dy], [ex, y + dy], [ex, yE], [tx, yE]], seg = P.slice(1).map((p, i) => Math.hypot(p[0] - P[i][0], p[1] - P[i][1])), tot = seg.reduce((a, b) => a + b, 0);
  S.leadT = location.hash.includes('still') ? 1 : Math.min(1, (t - lockAt - 250) / 650); const lim = Math.max(0, S.leadT) * tot; let acc = 0, pts = [P[0]];
  for (let k = 0; k < seg.length; k++) { if (acc + seg[k] <= lim) { pts.push(P[k + 1]); acc += seg[k]; } else { const f = (lim - acc) / seg[k]; pts.push([P[k][0] + (P[k + 1][0] - P[k][0]) * f, P[k][1] + (P[k + 1][1] - P[k][1]) * f]); break; } }
  leadSvg.style.display = 'block'; leadL.setAttribute('points', pts.map(p => p.join(',')).join(' ')); const e = pts[pts.length - 1]; leadN.setAttribute('cx', e[0]); leadN.setAttribute('cy', e[1]); leadN.style.opacity = S.leadT > 0 ? 1 : 0;
  const pk = ((t * .0007) % 1) * tot; let a2 = 0, px = x, py = y; for (let k = 0; k < seg.length; k++) { if (a2 + seg[k] >= pk) { const f = (pk - a2) / (seg[k] || 1); px = P[k][0] + (P[k + 1][0] - P[k][0]) * f; py = P[k][1] + (P[k + 1][1] - P[k][1]) * f; break; } a2 += seg[k]; }
  leadP.setAttribute('cx', px); leadP.setAttribute('cy', py); leadP.style.opacity = S.leadT >= 1 ? 1 : 0; }
const GL = 'ABCDEF0123456789#$%&@<>/\\|';
export function decode(el, text, ms = 22) { clearInterval(el._d); let n = 0; el._d = setInterval(() => { n += 1.3; el.textContent = text.slice(0, Math.floor(n)) + Array.from(text.slice(Math.floor(n), Math.floor(n) + 6), ch => ch === ' ' ? ' ' : GL[Math.random() * GL.length | 0]).join(''); if (n >= text.length) { clearInterval(el._d); el.textContent = text; } }, ms); }
function countUp(el, to, ms = 900, sfx = '') { const t0 = performance.now(); (function f(t) { const k = clamp((t - t0) / ms), v = Math.round(to * (1 - Math.pow(1 - k, 3))); el.textContent = v.toLocaleString() + sfx; if (k < 1) requestAnimationFrame(f); })(t0); }
export function animateIn(root) { requestAnimationFrame(() => requestAnimationFrame(() => { root.querySelectorAll('[data-off]').forEach(e => e.style.strokeDashoffset = e.dataset.off); root.querySelectorAll('[data-w]').forEach(e => { e.style.transition = 'width 1.1s cubic-bezier(.2,.8,.2,1) .3s'; e.style.width = e.dataset.w; }); root.querySelectorAll('[data-to]').forEach(e => countUp(e, +e.dataset.to, 900, e.dataset.sfx || '')); })); }
