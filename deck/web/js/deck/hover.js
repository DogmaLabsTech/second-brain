import { cardInfo, days } from '../../hud.js';
import { rings, hideRingTip } from '../../rings.js';
import { H, KC, RD, S, W, addLabel, animateIn, clamp, clearLabels, closeReader, cur, decode, dotXY, dropTitle, follow, jumpTo, labels, leadSvg, leaveEdit, mdRender, mk, nbLines, note, openReader, refresh, renderSection, ret, xh, xv } from '../deck-main.js';
// ---- hover preview (like Obsidian's page preview): rest on a note link ~300 ms, a small card shows the start of that note
// the same card shows for a note dot in the scene (pvDot, placed beside the dot at pvXY): path, start of the note and its closest notes
export let pvT = 0, pvHideT = 0, pvLink = null, pvI = -1, pvH = '', pvTop = 0; S.testGone = false; export let pvDot = -1, pvXY = null, pvOver = false; export const pvCache = new Map(), PV = RD('pv');
const pvGet = id => { if (!pvCache.has(id)) pvCache.set(id, fetch('/note?id=' + id, { cache: 'no-store' }).then(x => { if (!x.ok) throw x.status; return x.json(); }).catch(e => { pvCache.delete(id); throw e; })); return pvCache.get(id); };
function pvPlace() { const w = PV.offsetWidth, h = PV.offsetHeight, m = 8;
  if (pvXY) { const [x, y] = pvXY, g = 18; PV.style.left = (x + g + w <= W() - m ? x + g : Math.max(m, x - g - w)) + 'px'; PV.style.top = clamp(y - 30, m, H() - h - m) + 'px'; return; }   // beside the dot, so the way onto the card is short
  if (!pvLink) return; const r = pvLink.getBoundingClientRect();
  let top = r.bottom + m; if (top + h > H() - m) top = r.top - m - h >= m ? r.top - m - h : H() - m - h;
  PV.style.left = clamp(r.left - 12, m, W() - w - m) + 'px'; PV.style.top = Math.max(m, top) + 'px'; }
export function pvShow(a, xy) { const i = a ? +a.dataset.i : xy.i, d = DOCS[i]; if (!d) return; clearTimeout(pvHideT); if (pvLink) pvLink.classList.remove('on'); pvLink = a || null; if (a) a.classList.add('on'); pvI = i; pvH = a && a.dataset.h || ''; pvTop = RD('rdb').scrollTop;
  pvDot = a ? -1 : i; pvXY = a ? null : [xy.x, xy.y]; PV.classList.toggle('dot', !a); const cap = a ? 12000 : 1500, ns = d.ns || d.nb.map(() => .5);
  RD('pvp').textContent = d.c + '/' + d.p; RD('pvn').innerHTML = a ? '' : '<b>CLOSEST IN MEANING</b>' + d.nb.slice(0, 3).map((j, n) => `<a data-i="${j}" style="--k:${KC(DOCS[j].c)}"><span>${esc(DOCS[j].t)}</span><em>${Math.round(ns[n] * 100)}%</em></a>`).join('');
  PV.style.setProperty('--k', KC(d.c)); RD('pvg').textContent = NICE[d.c].toUpperCase(); RD('pvd').textContent = ago(d.d).toUpperCase() + ' · ' + d.d; RD('pvt').textContent = d.t;
  const pb = RD('pvb'); pb.innerHTML = '<div class="load">LOADING <span class="cur"></span></div>'; pb.scrollTop = 0; PV.classList.add('on'); pvPlace();
  pvGet(d.id).then(j => { if (pvI !== i) return; const long = j.text.length > cap; pb.innerHTML = mdRender(j.text.slice(0, cap), true, { i, c: d.c, p: d.p }) + (long || j.truncated ? '<p class="k">… click to read the whole note</p>' : ''); dropTitle(pb, [d.t, j.title]); if (pvH) jumpTo(pb, pvH); pvPlace(); })
    .catch(() => { if (pvI === i) pb.innerHTML = '<p class="am">Could not read this note.</p>'; }); }
export function pvHide() { clearTimeout(pvT); clearTimeout(pvHideT); PV.classList.remove('on'); if (pvLink) pvLink.classList.remove('on'); pvLink = null; pvI = -1; pvDot = -1; pvXY = null; }
const pvHideSoon = () => { clearTimeout(pvHideT); pvHideT = setTimeout(pvHide, 220); };
function linkClick(e) { const a = e.target.closest('a.nl'); if (!a) return false; e.preventDefault(); e.stopPropagation(); follow(+a.dataset.i, a.dataset.h); return true; }
RD('rdb').addEventListener('click', linkClick);
RD('rdb').addEventListener('mouseover', e => { const a = e.target.closest('a.nl'); if (!a) return; if (a === pvLink) return clearTimeout(pvHideT); clearTimeout(pvT); pvT = setTimeout(() => pvShow(a), 300); });
RD('rdb').addEventListener('mouseout', e => { const a = e.target.closest('a.nl'); if (!a || a.contains(e.relatedTarget)) return; clearTimeout(pvT); if (a === pvLink) pvHideSoon(); });
RD('rdb').addEventListener('scroll', () => { if (pvLink && Math.abs(RD('rdb').scrollTop - pvTop) > 4) pvHide(); });   // the link moved away from the card
PV.onmouseenter = () => { pvOver = true; clearTimeout(pvHideT); }; PV.onmouseleave = () => { pvOver = false; pvHideSoon(); };
PV.onclick = e => { if (linkClick(e) || e.target.closest('a.lk')) return; const nb = e.target.closest('.pv-n a'), i = nb ? +nb.dataset.i : pvI, h = nb ? '' : pvH; if (i >= 0) { S.pickQuiet = [S.mx, S.my]; follow(i, h); } };
// a note dot under the mouse: wait ~200 ms before the card shows (so passing over dots doesn't flicker it), keep it ~320 ms after the mouse leaves the dot and while the mouse is on it.
// After a click opens a note no card shows until the mouse moves (the camera turns to the note and dots slide under a still mouse).
let hovWas = -1, hovAt = 0, offAt = 0; S.pickQuiet = null;
export function dotHover(t) { if (S.hov !== hovWas) { hovWas = S.hov; hovAt = t; } if (pvLink) return;
  if (S.hov >= 0 && !S.pickQuiet) { offAt = 0; if (pvDot === S.hov) clearTimeout(pvHideT); else if (t - hovAt > (pvDot >= 0 ? 320 : 200)) { const [x, y] = dotXY(S.hov); pvShow(null, { i: S.hov, x, y }); } }
  else if (pvDot >= 0 && !pvOver) { if (!offAt) offAt = t; else if (t - offAt > 320) pvHide(); } else offAt = 0; }
S.leadT = 1; export let lockAt = 0;
export function lock(i) {
  if (i !== S.sel && !leaveEdit()) return;
  const first = S.sel < 0; S.sel = i; const d = DOCS[i], c = cardInfo(i), p = document.getElementById('lockp'), ns = d.ns || d.nb.map(() => .5), dd = days(d.d), k = KC(d.c);
  document.getElementById('right').classList.add('locked'); p.style.display = 'block'; p.style.setProperty('--k', k); p.classList.remove('open', 'swap'); p.classList.toggle('quiet', !first); if (first) { void p.offsetWidth; p.classList.add('open'); }
  document.getElementById('tid').textContent = 'N-' + String(d.id).padStart(4, '0');
  document.getElementById('tgbody').innerHTML = `<div class="tg-sub rise" style="--i:0"><span class="tg-chip" style="--k:${k}">${NICE[d.c].toUpperCase()}</span><span>${dd <= 0 ? 'CHANGED TODAY' : dd === 1 ? 'CHANGED YESTERDAY' : 'CHANGED ' + dd + ' DAYS AGO'}</span></div>
    <div class="tg-title" id="t"></div><div class="tg-path rise" style="--i:1" id="path">${esc(c.path)}</div>
    <div class="rgs rise" style="--i:2" id="rgs"></div>
    <div class="tg-sec rise" style="--i:3"><span>CLOSEST IN MEANING</span><span>${d.nb.length} LINKS</span></div>
    ${d.nb.map((j, n) => `<a class="nb2" data-i="${j}" style="--k:${KC(DOCS[j].c)};--i:${n};--w:${Math.round(ns[n] * 100)}%"><i>${String(n + 1).padStart(2, '0')}</i><span class="nm">${esc(DOCS[j].t)}</span><em>${Math.round(ns[n] * 100)}%</em><u></u></a>`).join('')}
    <div class="hint">ESC CLOSES THE NOTE, THEN RELEASES · CLICK A LINK TO JUMP</div>`;
  decode(document.getElementById('t'), c.title, first ? 22 : 8);
  rings(document.getElementById('rgs'), { i, first, days: Math.max(0, dd), date: d.d, words: note && note.i === i && note.text ? (note.text.match(/\S+/g) || []).length : null, estWords: d.n * 300, sim: ns[0], name: DOCS[d.nb[0]].t, open: () => lock(d.nb[0]) }); animateIn(document.getElementById('tgbody')); if (!first) { const tb = document.getElementById('tgbody'); tb.style.animation = 'none'; void tb.offsetWidth; tb.style.animation = 'swapin .25s ease-out both'; }
  document.querySelectorAll('#tgbody .nb2').forEach(a => a.onclick = () => lock(+a.dataset.i));
  clearLabels(); addLabel(i, DOCS[i].t, '◎'); DOCS[i].nb.forEach((j, n) => { const el = mk('lbl tag'); el.style.setProperty('--k', KC(DOCS[j].c)); el.innerHTML = `<i>${String(n + 1).padStart(2, '0')}</i>`; labels.push({ i: j, el }); }); S.ty = Math.atan2(-cur[i * 3], cur[i * 3 + 2]); S.autoCam = false;
  if (first) { ret.classList.remove('go'); void ret.offsetWidth; ret.classList.add('go'); S.leadT = 0; lockAt = performance.now(); } openReader(i); }
export function unlock() { if (closeReader() === false) return false; hideRingTip(); document.getElementById('right').classList.remove('locked'); S.sel = -1; document.getElementById('lockp').style.display = 'none'; clearLabels(); ret.style.display = 'none'; xh.style.display = xv.style.display = 'none'; leadSvg.style.display = 'none'; nbLines.visible = false; S.focus = null; document.querySelectorAll('#groups .row').forEach(x => x.classList.remove('on')); refresh(); renderSection(); }
document.getElementById('x').onclick = unlock;
