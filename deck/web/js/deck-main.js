import { THREE, NOW, chrome, boot, typeInto, makeCloud, lineMat, project, days, hex3, cardInfo } from '../hud.js';
import { makeShell, DOT_GLSL } from '../shell.js';
import { makeSkins } from '../skins.js';
import { movable, replaceAll } from '../movable.js'; import { makeTimeline } from '../timeline.js'; import { makeAsk } from '../ask.js';
import { rings, ringWords, hideRingTip } from '../rings.js'; import { makeLive, makeFeed } from '../live.js';
import { H, KC, LAY, Lmap, N, S, TAU, VIEW, W, age, camFrom, camera, clamp, cloud, cur, delay, ease, fitView, go, hidden, mats, nbLines, paint, renderer, root, say, scanFrom, scanOp0, scanner, scene, sets, shell, skins, slice, sweepG, thM, to, view, viewDist, vis, yOf } from './deck/scene.js'; export * from './deck/scene.js';
import { anchors, invertKey, labelCur, labelEls, labelOff, setOpen, settings, wk } from './deck/settings.js'; export * from './deck/settings.js';
import { addLabel, animateIn, clearLabels, decode, eff, labels, lead, leadL, leadSvg, mk, refresh, renderSection, ret, shown, tip, tmp, visible, xh, xv } from './deck/panels.js'; export * from './deck/panels.js';
import { byAny, byPath, mdRender, nh, pick, pk } from './deck/links.js'; export * from './deck/links.js';
import { RD, STILL, asking, cancelEdit, closeReader, docOf, dropTitle, editing, exitEdit, follow, histGo, jumpTo, keepEditing, layoutReader, leaveEdit, loose, note, openReader, readerOpen, readerW, renderNote, saveEdit, startEdit } from './deck/reader.js'; export * from './deck/reader.js';
import './deck/lock-tag.js'; export * from './deck/lock-tag.js';
// ---- hover preview (like Obsidian's page preview): rest on a note link ~300 ms, a small card shows the start of that note
// the same card shows for a note dot in the scene (pvDot, placed beside the dot at pvXY): path, start of the note and its closest notes
let pvT = 0, pvHideT = 0, pvLink = null, pvI = -1, pvH = '', pvTop = 0; S.testGone = false; let pvDot = -1, pvXY = null, pvOver = false; export const pvCache = new Map(), PV = RD('pv');
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
function dotHover(t) { if (S.hov !== hovWas) { hovWas = S.hov; hovAt = t; } if (pvLink) return;
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
function unlock() { if (closeReader() === false) return false; hideRingTip(); document.getElementById('right').classList.remove('locked'); S.sel = -1; document.getElementById('lockp').style.display = 'none'; clearLabels(); ret.style.display = 'none'; xh.style.display = xv.style.display = 'none'; leadSvg.style.display = 'none'; nbLines.visible = false; S.focus = null; document.querySelectorAll('#groups .row').forEach(x => x.classList.remove('on')); refresh(); renderSection(); }
document.getElementById('x').onclick = unlock;
// 05 Timeline and 06 Ask: self-contained panels (timeline.js, ask.js), both movable by their title bar (movable.js)
export let hits = null;
export const tl = makeTimeline(RD('tlp'), { ages: DOCS.map(age), NOW, count: d => DOCS.filter((x, i) => age(x) >= d && visible(i)).length, onChange: c => { S.cutoff = c; refresh(); } });
addEventListener('keydown', e => { if (e.target.id === 'q') { if (e.key === 'Escape') e.target.blur(); return; }
  if (e.key === 'Escape' && pvI >= 0) { e.preventDefault(); S.pickQuiet = [S.mx, S.my]; return pvHide(); }   // stays shut until the mouse moves
  if (editing) { const k = e.key.toLowerCase(); if ((e.ctrlKey || e.metaKey) && k === 's') { e.preventDefault(); saveEdit(); } else if (e.key === 'Escape') { e.preventDefault(); asking ? keepEditing() : cancelEdit(); } else if (asking && k === 'd' && e.target.id !== 'rde') { e.preventDefault(); exitEdit(); } return; }
  if (e.altKey && readerOpen && (e.key === 'ArrowLeft' || e.key === 'ArrowRight')) { e.preventDefault(); return histGo(e.key === 'ArrowLeft' ? -1 : 1); }
  if (e.ctrlKey || e.metaKey || e.altKey) return; if (e.key === '/') { e.preventDefault(); document.getElementById('q').focus(); } else if (e.key === '1') go('map'); else if (e.key === '2') go('tunnel'); else if (e.key === '3') go('radar'); else if (e.key.toLowerCase() === 't') toggleLeft(); else if (e.key.toLowerCase() === 'k') { skins.next(e.shiftKey ? -1 : 1); say('SKIN  ›  ' + skins.label.toUpperCase()); } else if (e.key.toLowerCase() === 'i') invertKey(); else if (e.key === ',') settings(); else if (e.key.toLowerCase() === 'e' && readerOpen) { e.preventDefault(); startEdit(); } else if (e.key === 'Escape') { if (readerOpen) closeReader(); else unlock(); } else if (e.key === 'Enter' && S.sel >= 0 && !readerOpen) openReader(S.sel); });
const ask = makeAsk(RD('askp'), { chips: Object.keys(BRAIN.asks), docs: DOCS, kc: KC, nice: NICE, esc, find: h => h.c ? byPath.get(h.c + ':' + pk(h.p)) : undefined, onOpen: i => lock(i), onOpenLoose: h => openReader(loose(h)),
  live: () => liveNonce(),
  onResults: (list, q) => { hits = list.length ? new Set(list) : null; refresh(); liveOwn({ q, who: 'Deck', kind: 'search', list }); if (!list.length) return; if (S.sel < 0) { clearLabels(); list.forEach(i => addLabel(i, DOCS[i].t)); } say('FOUND ' + list.length + ' NOTES  ›  “' + q.toUpperCase() + '”'); },
  onClear: () => { hits = null; if (S.sel < 0) clearLabels(); refresh(); } });
const moveTl = movable(RD('tlp'), { key: 'timeline', onMove: () => ask.place() }), moveAsk = movable(RD('askp'), { key: 'ask', onMove: () => ask.place() });
// ---- 08 Live (brief 15): every search and ask, from anywhere (chats, the voice island, the terminal, this Deck), as it happens.
// GET /live on the Deck server (read-only events; the token comes in this page's html). Each one plays the live animation
// (live.js) and gets a line in the 08 Live panel. The Ask box and the voice play their own results at once (liveOwn) and tag
// their calls with a nonce, so the server's copy of the same search is skipped here. L / the LIVE button / ✕ show or hide the panel.
const live = makeLive({ cur, root, camera, project, V: new THREE.Vector3(), cloud, docs: DOCS, kc: KC, cols: COLS, esc, shell, seen: i => visible(i) && shown(i) > .05, pulse: () => notePulse(), W, H });
const LIVEP = RD('livep'), mine = new Set(), LTOK = document.querySelector('meta[name=deck-live]')?.content || '';
function liveNonce() { const n = Math.random().toString(36).slice(2, 10); mine.add(n); return n; }
// a found note -> its dot: collection + path first, then the same path in any collection (qmd lists some files in two); undefined = newer than data.js
const liveIdx = h => !h.p ? undefined : (h.c && byPath.get(h.c + ':' + pk(h.p))) ?? pick(byAny.get(pk(h.p)), h.c);
function liveOwn(ev) { feed.add(ev); return live.play({ ...ev, own: true }); }
// a server event -> the feed and the animation. A read (a chat opening a note) plays light; notes newer than data.js light their section.
const LIVELOG = /[#&]livelog/.test(location.hash);   // test switch: keep each live event and when its first line drew (window.__liveGot)
function fromServer(e, past) { if (!e || !e.q || (e.nonce && mine.has(e.nonce))) return; const idx = (e.hits || []).map(liveIdx);
  const ev = { key: 's' + e.id + '.' + e.sent, q: e.q, who: e.who, kind: e.kind, at: e.at, hits: e.hits, idx, list: idx.filter(i => i !== undefined), secs: e.hits.filter((h, k) => idx[k] === undefined && h.c).map(h => h.c), light: e.kind === 'read', past: past || e.past };
  feed.add(ev); const pl = ev.past ? null : live.play(ev); if (LIVELOG && !ev.past) (window.__liveGot ||= []).push({ id: e.id, q: e.q, kind: e.kind, who: e.who, at: e.at, sent: e.sent, got: Date.now(), n: ev.list.length, secs: ev.secs.length, hits: e.hits.length, pl }); }
const feed = makeFeed(LIVEP, { docs: DOCS, kc: KC, nice: NICE, esc, onOpen: (i, h) => i !== undefined ? lock(i) : h && h.id && openReader(loose(h)), onReplay: ev => live.play({ ...ev, own: false, hold: false }), onHide: () => liveShow(false) });
const moveLive = movable(LIVEP, { key: 'live' });
document.querySelector('#topbar .stat').insertAdjacentHTML('afterend', '<button id="livebtn" title="the live feed of searches  (L)"><i>●</i> LIVE</button>');
const LB = RD('livebtn'); let liveOn = localStorage.getItem('deckLiveHidden') !== '1';
function liveShow(on) { liveOn = on; try { localStorage.setItem('deckLiveHidden', on ? '0' : '1'); } catch {} LIVEP.classList.toggle('off', !on); LB.classList.toggle('on', on); if (on) moveLive.place(false); }
LB.onclick = () => liveShow(!liveOn); liveShow(liveOn);
addEventListener('keydown', e => { if (e.key.toLowerCase() !== 'l' || e.ctrlKey || e.metaKey || e.altKey || editing || setOpen || typingIn(e.target)) return; liveShow(!liveOn); say(liveOn ? 'LIVE FEED SHOWN' : 'LIVE FEED HIDDEN  ·  PRESS L TO SHOW'); });
if (!LTOK) feed.status('restart the Deck server', 'bad');
else { const es = new EventSource('/live?k=' + LTOK);
  es.addEventListener('open', () => { feed.status('listening', 'ok'); LB.classList.add('ok'); });
  es.addEventListener('history', m => { try { JSON.parse(m.data).forEach(e => fromServer(e, true)); } catch {} });
  es.addEventListener('live', m => { try { fromServer(JSON.parse(m.data)); } catch {} });
  es.onerror = () => { LB.classList.remove('ok'); feed.status(es.readyState === 2 ? 'server restarted: reload' : 'reconnecting', 'bad'); }; }
// input
// picking: the nearest shown dot within PICK px of the mouse (screen space, this frame's camera and layout) wins
const PICK = 16, dotXY = i => { tmp.set(cur[i * 3], cur[i * 3 + 1], cur[i * 3 + 2]).applyMatrix4(root.matrixWorld); return project(tmp, camera, W(), H()); };
function nearDot(x0, y0, r = PICK) { let best = -1, bd = r; for (let i = 0; i < N; i++) { if (cloud.A[i] < .5) continue; const [x, y, z] = dotXY(i); if (z > 1) continue; const d = Math.hypot(x - x0, y - y0); if (d < bd) { bd = d; best = i; } } return [best, bd]; }
let downDot = -1;   // the dot is chosen when the button goes down (the hover is paused while the button is held, so it can't be read at mouseup)
renderer.domElement.onmousedown = e => { S.drag = [e.clientX, e.clientY]; S.moved = 0; downDot = S.hov >= 0 ? S.hov : nearDot(e.clientX, e.clientY)[0]; S.ty = null; S.autoCam = false; };
addEventListener('mouseup', () => { if (S.drag && S.moved < 5 && downDot >= 0) { S.pickQuiet = [S.mx, S.my]; lock(downDot); } S.drag = null; downDot = -1; });
addEventListener('mousemove', e => { S.mx = e.clientX; S.my = e.clientY; if (S.pickQuiet && Math.hypot(S.mx - S.pickQuiet[0], S.my - S.pickQuiet[1]) > 4) S.pickQuiet = null; S.overRd = !!(e.target.closest && e.target.closest('#reader,#pv,.mov,#setp,#setveil')); if (S.drag) { S.yaw += (e.clientX - S.drag[0]) * .006; S.pT = S.pitch = clamp(S.pitch + (e.clientY - S.drag[1]) * .006, -.2, 1.5); S.moved += Math.abs(e.clientX - S.drag[0]) + Math.abs(e.clientY - S.drag[1]); S.drag = [e.clientX, e.clientY]; } });
renderer.domElement.onwheel = e => { e.preventDefault(); S.dT = S.dist = clamp(S.dist * Math.exp(e.deltaY * .001), 4, 22); };
addEventListener('resize', () => { clearTimeout(window._rz); window._rz = setTimeout(() => { applyZ(false); S.dT = viewDist(view); S.autoCam = true; }, 120); if (readerOpen) layoutReader(); renderer.setSize(W(), H()); camera.aspect = W() / H(); fitView(); camera.updateProjectionMatrix(); cloud.m.uniforms.uScale.value = H() * .5; });
// left column (View + Sections): slide away / bring back (key T, the ◂ buttons, the tab)
let leftAway = location.hash.includes('leftaway') || localStorage.getItem('deckLeftAway') === '1';
export const leftW = () => 272 * Z;   // the left column's space stays reserved, so nothing else moves when it is hidden
function applyLeft(anim) { const ps = [document.getElementById('viewp'), document.getElementById('sections'), document.getElementById('voicep')], t = document.getElementById('secTab'), L = document.getElementById('left');
  if (leftAway) { ps.forEach(p => p.classList.add('away')); setTimeout(() => { if (leftAway) { ps.forEach(p => p.style.display = 'none'); L.classList.add('hidden'); } }, anim ? 270 : 0); t.style.display = 'block'; }
  else { L.classList.remove('hidden'); ps.forEach(p => { p.style.display = ''; void p.offsetWidth; p.classList.remove('away'); }); t.style.display = 'none'; }
  if (anim) { applyZ(false); S.dT = viewDist(view); S.autoCam = true; } }
function toggleLeft() { leftAway = !leftAway; localStorage.setItem('deckLeftAway', leftAway ? '1' : '0'); applyLeft(true); say(leftAway ? 'PANELS HIDDEN  ·  PRESS T TO SHOW' : 'PANELS SHOWN'); }
document.getElementById('secHide').onclick = toggleLeft; document.getElementById('viewHide').onclick = toggleLeft; document.getElementById('voiceHide').onclick = toggleLeft; document.getElementById('secTab').onclick = toggleLeft;
// panel size: + / - keys
const zh = location.hash.match(/z=([\d.]+)/); let userM = +(localStorage.getItem('deckM') || 1);
function pickZ() { let z = clamp((.6 + W() / 2560) * userM, .9, 1.8); while (W() - (32 + 604 * z + 28) < 600 && z > .9) z -= .05; return Math.round(z * 100) / 100; }
export let Z = zh ? +zh[1] : pickZ();
function applyZ(say_) { if (!zh) Z = pickZ(); document.documentElement.style.setProperty('--z', Z); document.getElementById('left').classList.toggle('narrow', W() < 1250);
  const L = document.getElementById('left'), R = document.getElementById('right'), B = document.getElementById('bottom'), top = 56 / Z * 1.0;
  L.style.left = 16 / Z + 'px'; R.style.right = 16 / Z + 'px'; L.style.top = R.style.top = (50 + 8 * Z) / Z + 'px'; L.style.bottom = R.style.bottom = B.style.bottom = 14 / Z + 'px';
  B.style.left = (16 + 272 * Z + 14) / Z + 'px'; B.style.right = (16 + 332 * Z + 14) / Z + 'px'; S.baseOffX = (332 * Z - leftW()) / 2; S.targetOffX = S.baseOffX + (readerOpen ? readerW / 2 : 0); S.offX = S.targetOffX; S.offY = Math.max(40, (B.getBoundingClientRect().height + 14 - 60) / 2); fitView(); camera.updateProjectionMatrix(); if (readerOpen) layoutReader(); replaceAll(); if (say_) say('PANEL SIZE  ' + Math.round(userM * 100) + '%'); }
addEventListener('keydown', e => { if (e.target.id === 'q' || editing || e.ctrlKey || e.metaKey) return; if (e.key === '+' || e.key === '=') { userM = clamp(userM + .1, .6, 1.6); localStorage.setItem('deckM', userM); applyZ(true); S.dT = viewDist(view); } else if (e.key === '-' || e.key === '_') { userM = clamp(userM - .1, .6, 1.6); localStorage.setItem('deckM', userM); applyZ(true); S.dT = viewDist(view); } });
applyZ(false); applyLeft(false); setTimeout(() => { applyZ(false); S.dist = S.dT = viewDist(view); }, 150);
// ---- 07 Voice: talk to the brain like the voice island (the TALK button, or hold Space). Mic -> /talk/stt -> /talk/ask
// (first sentence early) -> /talk/say per sentence (Kokoro bm_george), played through an analyser so the shell follows the voice.
const TV = RD('voicep'), TB = RD('tbtn'), MUTE = location.hash.includes('mute'), post = (u, body, sig) => fetch(u, { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Deck': '1' }, body: JSON.stringify(body), signal: sig });
const TSUB = { idle: 'click talk or hold space', listening: 'talk now · click or let go to send', thinking: 'looking in your notes', speaking: 'click or esc to stop', unheard: 'speak closer or louder · check the mic below' };
const TBL = { listening: 'SEND', thinking: 'STOP', speaking: 'STOP' };
let talk = 'idle', tgen = 0, tAbort = null, ac = null, mic = null, rec = null, recBits = [], recMode = '', recAt = 0, heardAt = 0, quietAt = 0; S.micAn = null; S.outAn = null; S.src = null; let sayQ = [], sayChain = null, sayMore = false, pumping = false, tJob = null, tId = '', tFake = '', voiceEv = null;   // voiceEv: the voice answer's live event, held while it speaks
const talkBuf = new Float32Array(2048);   // ~43 ms of sound per reading: a steadier loudness than one short window
function tState(st, sub) { talk = st; if (st !== 'speaking' && st !== 'thinking' && voiceEv) { live.release(voiceEv); voiceEv = null; }   /* the voice finished (or stopped): its lines fade calmly now */ TV.dataset.s = st; shell.set(st === 'job' || st === 'unheard' ? 'idle' : st); RD('tbl').textContent = TBL[st] || 'TALK'; RD('tstate').textContent = st === 'error' ? 'ERROR' : st === 'job' ? 'WAITING FOR YOU' : st === 'unheard' ? "I DIDN'T HEAR YOU" : st === 'idle' ? 'READY' : st.toUpperCase(); RD('tsub').textContent = sub ?? TSUB[st] ?? ''; RD('tsub').title = RD('tsub').textContent; }
function tErr(t) { tState('error', t); }
const notePulse = () => shell.voice * 1.1;   // the answer's notes pulse with the voice
const audio = () => ac || (ac = new AudioContext());
function rms(an) { an.getFloatTimeDomainData(talkBuf); let a = 0; for (let k = 0; k < talkBuf.length; k++) a += talkBuf[k] * talkBuf[k]; return Math.sqrt(a / talkBuf.length); }
const LVI = RD('tlvi'), LVB = RD('tlv'); let floor = .2, lvShown = -1, barLv = 0, barT = 0;   // floor: the room's noise level, so a quiet mic still counts as talking above it
// soft(): the loudness as the shell feels it: a soft knee at the bottom (room noise doesn't flicker) and a soft top (a loud word doesn't slam to the max)
const soft = x => { x = x < -.1 ? 0 : x < .1 ? (x + .1) * (x + .1) / .4 : x; return clamp((1 - Math.exp(-1.8 * x)) / (1 - Math.exp(-1.8))); };
function talkFrame(t) { let lv = 0, felt = 0;
  if (tFake) lv = tFake === 'listening' ? .5 + .3 * Math.sin(t / 130) * Math.sin(t / 410) : tFake === 'speaking' ? Math.max(0, .55 + .45 * Math.sin(t / 90) * Math.sin(t / 260)) : 0;
  else if (talk === 'listening' && S.micAn) { lv = clamp((20 * Math.log10(Math.max(rms(S.micAn), 1e-5)) + 52) / 34); felt = soft((lv - floor - .04) / (.85 - floor)); const now = performance.now(), th = clamp(floor + .16, .22, .38);
    floor = lv < floor ? floor + (lv - floor) * .2 : floor + (lv - floor) * .004; LVB.style.setProperty('--th', Math.round(th * 100) + '%'); LVB.classList.toggle('hear', lv > th);
    if (recMode === 'click') { if (lv > th) { heardAt = heardAt || now; quietAt = now; }   // the island's rule: stop 1.3 s after the voice ends, or 8 s with no voice
      if ((heardAt && now - quietAt > 1300) || (!heardAt && now - recAt > 8000) || now - recAt > 30000) stopRec(true); } }
  else if (talk === 'speaking' && S.outAn) felt = soft(lv = clamp((20 * Math.log10(Math.max(rms(S.outAn), 1e-5)) + 45) / 32));
  if (tFake) felt = lv; S.voiceLv = lv; shell.level(felt, talk === 'speaking' && !S.src && !tFake);   // between two sentences the shell holds the voice
  const dt = Math.min(.05, barT ? (t - barT) / 1000 : .016); barT = t; barLv = lv > barLv ? lv : barLv + (lv - barLv) * (1 - Math.exp(-dt / .15));   // the bar: up at once, down calmly
  const w = Math.round(barLv * 200); if (w !== lvShown && !leftAway) { LVI.style.transform = `scaleX(${w / 200})`; lvShown = w; } }
// the mic picker: the browser's inputs (names show after the first mic permission), remembered; the first time it picks the Yeti
const MICK = 'deckMic', DEV = RD('tdev');
async function listMics() { let ds = []; try { ds = (await navigator.mediaDevices.enumerateDevices()).filter(d => d.kind === 'audioinput' && d.deviceId && d.deviceId !== 'default' && d.deviceId !== 'communications'); } catch {}
  let want = localStorage.getItem(MICK) || ''; if (want && !ds.some(d => d.deviceId === want)) want = ds.some(d => d.label) ? '' : want;
  if (!localStorage.getItem(MICK)) { const y = ds.find(d => /yeti/i.test(d.label)); if (y) { want = y.deviceId; localStorage.setItem(MICK, want); } }
  DEV.innerHTML = '<option value="">system default mic</option>' + ds.map((d, k) => `<option value="${esc(d.deviceId)}">${esc((d.label || 'microphone ' + (k + 1)).replace(/\s*\([0-9a-f]{4}:[0-9a-f]{4}\)$/i, ''))}</option>`).join('');
  DEV.value = ds.some(d => d.deviceId === want) ? want : ''; DEV.title = DEV.selectedOptions[0]?.textContent || ''; }
DEV.onchange = () => { localStorage.setItem(MICK, DEV.value || 'system'); DEV.title = DEV.selectedOptions[0]?.textContent || ''; DEV.blur(); };
if (navigator.mediaDevices) { listMics(); navigator.mediaDevices.addEventListener?.('devicechange', listMics); }
// a desk mic: no echo cancelling (the brain's voice is stopped while it listens), no noise gate and no auto gain (both can swallow a
// quiet voice, and Chrome's auto gain turns the system's mic volume); the server raises a quiet recording instead
const micWant = id => ({ audio: { ...(id && id !== 'system' ? { deviceId: { exact: id } } : {}), channelCount: 1, echoCancellation: false, noiseSuppression: false, autoGainControl: false } });
async function startRec(mode) {
  if (talk === 'listening') return; stopTalk(); const g = ++tgen; recMode = mode; tState('listening', 'opening the microphone…');
  const id = DEV.value; try { mic = await navigator.mediaDevices.getUserMedia(micWant(id)); }
  catch (e) { if (id && e && (e.name === 'OverconstrainedError' || e.name === 'NotFoundError')) { try { mic = await navigator.mediaDevices.getUserMedia(micWant('')); DEV.value = ''; } catch (e2) { e = e2; } }
    if (!mic) { if (g === tgen) tErr(e && e.name === 'NotAllowedError' ? 'the microphone is blocked: allow it for this page' : 'no microphone: ' + (e && e.message || e)); return; } }
  if (g !== tgen) { mic.getTracks().forEach(x => x.stop()); mic = null; return; }
  if (![...DEV.options].some(o => o.value && !o.textContent.startsWith('microphone '))) listMics();   // the names are known now
  const a = audio(); a.resume(); S.micAn = a.createAnalyser(); S.micAn.fftSize = 2048; a.createMediaStreamSource(mic).connect(S.micAn); floor = .2;
  recBits = []; rec = new MediaRecorder(mic, MediaRecorder.isTypeSupported('audio/webm;codecs=opus') ? { mimeType: 'audio/webm;codecs=opus', audioBitsPerSecond: 64000 } : {}); rec.ondataavailable = e => e.data.size && recBits.push(e.data);
  rec.onstop = () => { const type = rec.mimeType || 'audio/webm', send = rec._send, ms = Math.round(performance.now() - recAt); mic && mic.getTracks().forEach(x => x.stop()); mic = null; S.micAn = null; rec = null; LVB.classList.remove('hear'); if (g !== tgen) return;
    if (!send) return tState('idle'); if (ms < 350) return tState('idle', 'too short: hold Space while you talk'); sendAudio(new Blob(recBits, { type }), ms, g); };
  rec.start(250); recAt = performance.now(); heardAt = 0; quietAt = 0; tState('listening'); }
function stopRec(send) { if (rec && rec.state !== 'inactive') { rec._send = send; rec.stop(); } }
// a transcript with no real words (empty, only punctuation, one letter, only "um"/"hmm"): nothing heard, never a question (the server checks too)
const FILLER = new Set('um umm uh uhh uhm erm er ah ahh oh eh hm hmm hmmm mm mmm mhm huh uh-huh mm-hmm hm-hmm'.split(' '));
function saidNothing(t) { const w = String(t || '').toLowerCase().match(/[\p{L}\p{N}]+(?:-[\p{L}\p{N}]+)*/gu) || []; return w.join('').length <= 1 || w.every(x => FILLER.has(x)); }
function sendAudio(blob, ms, g) { tState('thinking', 'turning your words into text…'); tAbort = new AbortController();
  fetch('/talk/stt', { method: 'POST', headers: { 'Content-Type': 'audio/webm', 'X-Deck': '1' }, body: blob, signal: tAbort.signal })
    .then(x => x.json()).then(j => { if (g !== tgen) return; if (j.error) return tErr(j.error);
      if (j.heard === false || saidNothing(j.text)) return tState('unheard', j.why === 'silent' ? 'the mic sent silence · pick your mic below' : 'speak closer or louder · check the mic below');
      askBrain(j.text, 'voice', { ms_record: ms, ms_convert: j.ms_convert, ms_stt: j.ms_stt, engine: j.engine }); })
    .catch(e => { if (g === tgen && e.name !== 'AbortError') tErr('the Deck server did not answer'); }); }
function caption(q, a, typing) { RD('tcap').classList.add('on'); if (q !== undefined) RD('tq').textContent = q; RD('ta').innerHTML = esc(a || '') + (typing ? '<span class="cur"></span>' : ''); }
function askBrain(q, how, stt) { if (saidNothing(q)) return tState('unheard'); const g = ++tgen; tJob = null; tId = ''; RD('tjob').classList.remove('on'); RD('tchips').innerHTML = ''; caption(q, '', true); tState('thinking'); tAbort = new AbortController(); let spoke = '', buf = '';
  post('/talk/ask', { q, how, stt, live: liveNonce() }, tAbort.signal).then(async x => { if (!x.ok) throw new Error('the Deck server said ' + x.status); const rd = x.body.getReader(), dec = new TextDecoder();
    for (;;) { const { value, done } = await rd.read(); if (g !== tgen) return rd.cancel(); if (value) buf += dec.decode(value, { stream: true }); let n;
      while ((n = buf.indexOf('\n')) >= 0) { const line = buf.slice(0, n); buf = buf.slice(n + 1); let ev; try { ev = JSON.parse(line); } catch { continue; }
        if (ev.event === 'first' && !spoke) { spoke = ev.text; caption(undefined, spoke, true); speak(spoke, true); }
        else if (ev.event === 'done') showAnswer(ev, spoke, g); }
      if (done) break; } })
    .catch(e => { if (g === tgen && e.name !== 'AbortError') tErr(String(e.message || e)); }); }
function showAnswer(r, spoke, g) { tId = r.id || ''; caption(undefined, r.answer || '(no answer)');
  const list = (r.sources || []).map(x => ({ x, i: x.c ? byPath.get(x.c + ':' + pk(x.p)) : undefined }));
  RD('tchips').innerHTML = list.map(({ x, i }, n) => `<button ${i === undefined ? 'disabled title="not in the Deck\'s snapshot"' : `data-i="${i}" title="${esc(x.c + '/' + x.p)}  ·  click to open"`} style="--k:${i === undefined ? 'var(--dim)' : KC(DOCS[i].c)}"><i>${String(n + 1).padStart(2, '0')}</i><span>${esc(i === undefined ? x.title : DOCS[i].t)}</span></button>`).join('');
  RD('tchips').querySelectorAll('button[data-i]').forEach(b => b.onclick = () => lock(+b.dataset.i));
  const lit = list.map(o => o.i).filter(i => i !== undefined); live.release(voiceEv);
  voiceEv = liveOwn({ q: RD('tq').textContent, who: 'Deck voice', kind: 'ask', list: lit, secs: list.filter(o => o.i === undefined && o.x.c).map(o => o.x.c), voice: true, hold: true });   /* held until the voice has said it all (tState releases it) */ if (lit.length && S.sel < 0) { clearLabels(); ask.quiet(); lit.forEach(i => addLabel(i, DOCS[i].t)); }
  if (r.kind === 'job' && r.job) { tJob = r.job; RD('tjl').textContent = r.job.label || r.job.id; RD('tjob').classList.add('on'); RD('tyes').disabled = RD('tno').disabled = false; stopVoice(); if (r.answer) speak(r.answer, false); else tState('job'); return; }
  const rest = spoke ? (r.answer.startsWith(spoke) ? r.answer.slice(spoke.length).trim() : (r.rest || '')) : r.answer; speak(rest || '', false); }
// the voice: sentence by sentence (bin/say's split), each made while the one before plays
function sentences(text) { const raw = text.split(/\s+/).join(' ').split(/(?<=[.!?])\s+/).map(x => x.trim()).filter(Boolean), out = [];
  for (const p of raw) { if (out.length && out[out.length - 1].length < 25) out[out.length - 1] += ' ' + p; else out.push(p); } if (!out.length) out.push(text);
  if (out[0].length > 60) { const m = out[0].match(/^(.{12,60}?\bnotes? says?)\s+(.+)$/) || out[0].match(/^(.{20,70}?,)\s+(.+)$/); if (m) out.splice(0, 1, m[1], m[2]); } return out; }
function speak(text, more) { const g = tgen; sayMore = more; if (!text.trim()) return pumping || sayDone();
  for (const part of sentences(text)) { const prev = sayChain || Promise.resolve(); const got = prev.then(() => g === tgen ? post('/talk/say', { text: part }).then(x => x.ok ? x.arrayBuffer() : x.json().then(j => { throw new Error(j.error); })) : null); sayChain = got.catch(() => null); sayQ.push(got); }
  if (!pumping) { pumping = true; playNext(g); } }
async function playNext(g) { if (g !== tgen) return; const got = sayQ.shift(); if (!got) { pumping = false; return sayMore ? tState('thinking', 'still writing the answer…') : sayDone(); }
  let buf; try { buf = await got; } catch (e) { if (g === tgen) { pumping = false; tErr('the voice failed: ' + (e.message || e)); } return; } if (g !== tgen || !buf) return g === tgen ? playNext(g) : undefined;
  if (talk !== 'speaking') tState('speaking'); if (MUTE) { setTimeout(() => playNext(g), 300); return; }
  const a = audio(); a.resume(); let ab; try { ab = await a.decodeAudioData(buf); } catch { return playNext(g); } if (g !== tgen) return;
  S.outAn = S.outAn || (() => { const n = a.createAnalyser(); n.fftSize = 2048; n.connect(a.destination); return n; })(); S.src = a.createBufferSource(); S.src.buffer = ab; S.src.connect(S.outAn);
  S.src.onended = () => { S.src = null; playNext(g); }; S.src.start(); }
function sayDone() { if (talk === 'error') return; sayMore = false; tJob ? tState('job', 'yes or no below') : tState('idle'); }
function stopVoice() { sayQ = []; sayChain = null; sayMore = pumping = false; if (S.src) { S.src.onended = null; try { S.src.stop(); } catch {} S.src = null; } }
function stopTalk(byUser) { const was = talk; tgen++; if (tAbort) tAbort.abort(); tAbort = null; stopRec(false); stopVoice();
  if (byUser && tId && (was === 'thinking' || was === 'speaking')) post('/talk/outcome', { id: tId, what: 'stopped' }).catch(() => {}); tJob ? tState('job', 'yes or no below') : tState('idle', was === 'idle' || was === 'error' || was === 'unheard' ? undefined : 'stopped'); }
RD('tyes').onclick = () => { if (!tJob) return; const job = tJob, g = ++tgen; RD('tyes').disabled = RD('tno').disabled = true; stopVoice(); tState('thinking', (job.label || 'working on it') + '…');
  post('/talk/job', { job, id: tId, confirmed: true }).then(x => x.json()).then(r => { if (g !== tgen) return; tJob = null; RD('tjob').classList.remove('on'); caption(undefined, r.message || 'Done.'); r.speak && r.message ? speak(r.message, false) : tState(r.ok ? 'idle' : 'error', r.ok ? 'done' : 'the job failed'); })
    .catch(() => { if (g === tgen) { tJob = null; RD('tjob').classList.remove('on'); tErr('the Deck server did not answer'); } }); };
RD('tno').onclick = () => { if (!tJob) return; if (tId) post('/talk/outcome', { id: tId, what: 'declined' }).catch(() => {}); tJob = null; RD('tjob').classList.remove('on'); stopTalk(); caption(undefined, "Okay, I won't."); tState('idle'); };
TB.onclick = () => { if (tFake) return; if (talk === 'listening') stopRec(true); else if (talk === 'thinking' || talk === 'speaking') stopTalk(true); else startRec('click'); };
const typingIn = el => el && el.closest && el.closest('input,textarea,select,[contenteditable=""],[contenteditable="true"]');
addEventListener('keydown', e => { if (e.key === 'Escape' && (talk === 'listening' || talk === 'thinking' || talk === 'speaking')) { e.preventDefault(); e.stopImmediatePropagation(); return stopTalk(true); }
  if (e.code !== 'Space' || e.ctrlKey || e.metaKey || e.altKey || editing || typingIn(e.target) || leftAway) return; e.preventDefault(); e.stopImmediatePropagation(); if (e.repeat) return;
  if (talk === 'thinking' || talk === 'speaking') stopTalk(true); startRec('hold'); }, true);
addEventListener('keyup', e => { if (e.code !== 'Space' || recMode !== 'hold') return; e.preventDefault(); if (rec) stopRec(true); else if (talk === 'listening') { tgen++; tState('idle'); } recMode = ''; }, true);
// test switches (headless): talk=idle|listening|thinking|speaking|error|unheard shows a state with a made-up level; ask=<words> asks the brain in text (add mute); chip=<n> clicks the n-th Ask chip
{ const tm = location.hash.match(/[#&]talk=(\w+)/), am = location.hash.match(/[#&]ask=([^&]+)/);
  if (tm) { tFake = tm[1]; tm[1] === 'error' ? tErr('the microphone is blocked: allow it for this page') : tState(tm[1] in TSUB ? tm[1] : 'idle'); if (tm[1] === 'unheard') caption('', ''), RD('tcap').classList.remove('on'); setTimeout(() => { shell.level(.6); shell.snap(); }, 50); }
  if (am) setTimeout(() => askBrain(decodeURIComponent(am[1]), 'test'), 600);
  const cm = location.hash.match(/[#&]chip=(\d+)/); if (cm) setTimeout(() => { const b = ask.chips()[+cm[1]]; if (b) b.click(); }, 500); }
// frame
let last = performance.now(); renderSection();
function frame(t) {
  const dt = Math.min(50, t - last); last = t;
  if (S.prog < 1) { if (!S.hold) S.prog = Math.min(1, S.prog + dt / 2800); for (let i = 0; i < N; i++) { const e = ease(clamp(S.prog * 1.4 - delay[i])); for (let k = 0; k < 3; k++) cur[i * 3 + k] = S.from[i * 3 + k] + (to[i * 3 + k] - S.from[i * 3 + k]) * e; cur[i * 3 + 1] += Math.sin(Math.PI * e) * .55; } cloud.g.attributes.position.needsUpdate = true; }
  const pe = ease(S.prog); if (Math.abs(S.targetOffX - S.offX) > .3) { S.offX += (S.targetOffX - S.offX) * .12; fitView(); camera.updateProjectionMatrix(); }
  if (!S.drag && S.ty === null && S.hov < 0 && pvDot < 0) S.yaw += dt * (view === 'radar' ? .00003 : .00006);   // the slow turn waits while the mouse rests on a dot or its card, so the dot doesn't slide away from under it
  if (S.ty !== null) { let dy = S.ty - S.yaw; dy = Math.atan2(Math.sin(dy), Math.cos(dy)); S.yaw += dy * .07; if (Math.abs(dy) < .004) S.ty = null; }
  const lookT = view === 'tunnel' ? -.1 : 0;   // during a switch the camera rides the same eased clock as the notes and the ring (starts and lands softly)
  if (S.autoCam && S.prog < 1 && camFrom) { S.pitch = camFrom[0] + (S.pT - camFrom[0]) * pe; S.dist = camFrom[1] + (S.dT - camFrom[1]) * pe; S.lookY = camFrom[2] + (lookT - camFrom[2]) * pe; }
  else { if (S.autoCam) { S.pitch += (S.pT - S.pitch) * .045; S.dist += (S.dT - S.dist) * .045; } S.lookY += (lookT - S.lookY) * .045; }
  tl.tick(dt);
  root.rotation.set(0, S.yaw, 0); camera.position.set(0, Math.sin(S.pitch) * S.dist, Math.cos(S.pitch) * S.dist); camera.lookAt(0, S.lookY, 0); camera.updateMatrixWorld(); root.updateMatrixWorld();   // labels and the reticle are placed with this frame's camera, not the last one
  // structure fade + highlight
  for (const k in vis) vis[k] += ((view === k ? 1 : 0) - vis[k]) * .06; const e = eff();
  for (const m of mats) { const u = m.userData; m.opacity = u.op * vis[u.view] * (u.sec && e ? (u.sec === e ? 1 : .25) : 1); }
  sets.map.visible = vis.map > .02; sets.tunnel.visible = vis.tunnel > .02; sets.radar.visible = vis.radar > .02;
  const sweep = (t * .00045) % TAU; sweepG.rotation.y = -sweep; cloud.m.uniforms.uSweep.value = sweep; cloud.m.uniforms.uSweepOn.value = 0;   // calm (brief 15): the sweep no longer pings notes
  const slY = yOf(S.cutoff); slice.position.y = slY; const cu = cloud.m.uniforms; cu.uScan.value = -2.6 + Math.abs(Math.sin((S.beamT = (S.beamT + dt * .00012) % 1) * Math.PI)) * 5.2; cu.uScanA.value = 0;   /* calm (brief 15): no roaming map beam over the notes */ cu.uScan2.value = slY; cu.uScanB.value = vis.tunnel;
  // scanner ring rides the transition
  scanner.visible = S.prog < 1; scanner.position.y = scanFrom + (yOf(-1) - scanFrom) * ease(S.prog); scanner.material.opacity = S.prog >= 1 ? 0 : .95 * Math.min(clamp(scanOp0 + S.prog * 5), clamp((1 - S.prog) * 4));
  shell.frame(t, ease(S.prog), scanner.position.y, scanner.material.opacity);
  // labels
  const place = [];   // labels are kept inside the free area first, then pushed apart (so the edge can't stack them again)
  const fl = 16 + leftW() + 8, Rr = document.getElementById(readerOpen ? 'reader' : 'right').getBoundingClientRect(), fr = (Rr.width ? Rr.left : W()) - 8;
  COLS.forEach((c, k) => { const a = S.labelFrom[k].clone().lerp(anchors[view][c], pe); labelCur[k].copy(a); tmp.copy(a).applyMatrix4(root.matrixWorld); const [x, y] = project(tmp, camera, W(), H()); const el = labelEls[k];
    const w = el.offsetWidth || 120; place.push({ el, x: clamp(x, fl + w / 2, fr - w / 2), y, y0: y, k, w, h: (el.offsetHeight || 18) + 4, c }); });
  place.sort((p, q) => p.y - q.y);
  for (let it = 0; it < 4; it++) for (let m = 0; m < place.length; m++) for (let n = 0; n < m; n++) { const p = place[m], q = place[n]; if (hidden.has(p.c) || hidden.has(q.c)) continue; if (Math.abs(p.x - q.x) < (p.w + q.w) / 2 + 6 && Math.abs(p.y - q.y) < p.h) p.y = q.y + p.h; }
  for (const p of place) { const o = labelOff[p.k], dy = p.y - p.y0; labelOff[p.k] = o === undefined || STILL ? dy : o + clamp((dy - o) * .18, -3, 3); p.y = p.y0 + labelOff[p.k]; p.el.style.left = p.x + 'px'; p.el.style.top = p.y + 'px'; p.el.style.opacity = hidden.has(p.c) ? 0 : ''; p.el.classList.toggle('dim', !!(e && e !== p.c)); }
  // live searches: lines to the notes, pulses, sections waking (live.js)
  live.frame(t);
  // hover: the nearest dot wins, but stay on the current dot until the mouse is clearly nearer another one (no flicker between neighbours)
  let [best, bd] = S.drag || S.overRd ? [-1, 0] : nearDot(S.mx, S.my); if (S.hov >= 0 && best !== S.hov && !S.drag && !S.overRd && cloud.A[S.hov] >= .5) { const [x, y, z] = dotXY(S.hov), dh = Math.hypot(x - S.mx, y - S.my); if (z <= 1 && dh < PICK + 4 && (best < 0 || bd > dh - 5)) best = S.hov; }
  S.hov = best; renderer.domElement.style.cursor = S.hov >= 0 ? 'pointer' : 'grab'; tip.style.display = 'none'; dotHover(t);
  const taken = place.filter(p => !hidden.has(p.c)).map(p => [p.x - p.w / 2, p.y - p.h / 2, p.x + p.w / 2, p.y + p.h / 2]);   // note labels sit right of their dot (translate 10px, -50%)
  labels.map(l => { tmp.set(cur[l.i * 3], cur[l.i * 3 + 1], cur[l.i * 3 + 2]).applyMatrix4(root.matrixWorld); const [x, y] = project(tmp, camera, W(), H()); return { l, x, y, w: l.el.offsetWidth, h: l.el.offsetHeight + 2 }; }).sort((a, b) => a.y - b.y)
    .forEach(p => { let y = p.y; if (p.w) { for (let it = 0; it < 12; it++) { const r = [p.x + 10, y - p.h / 2, p.x + 10 + p.w, y + p.h / 2], hit = taken.find(b => r[0] < b[2] && r[2] > b[0] && r[1] < b[3] && r[3] > b[1]); if (!hit) break; y = hit[3] + p.h / 2 + 1; } taken.push([p.x + 10, y - p.h / 2, p.x + 10 + p.w, y + p.h / 2]); }
      const o = p.l.oy, dy = y - p.y; p.l.oy = o === undefined || STILL ? dy : o + clamp((dy - o) * .18, -3, 3); p.l.el.style.left = p.x + 'px'; p.l.el.style.top = p.y + p.l.oy + 'px'; });
  if (S.sel >= 0) { const arr = nbLines.geometry.attributes.position.array; DOCS[S.sel].nb.forEach((j, k) => { arr.set([cur[S.sel * 3], cur[S.sel * 3 + 1], cur[S.sel * 3 + 2], cur[j * 3], cur[j * 3 + 1], cur[j * 3 + 2]], k * 6); }); nbLines.geometry.attributes.position.needsUpdate = true; nbLines.visible = true;
    tmp.set(cur[S.sel * 3], cur[S.sel * 3 + 1], cur[S.sel * 3 + 2]).applyMatrix4(root.matrixWorld); const [x, y] = project(tmp, camera, W(), H()); ret.style.display = 'block'; ret.style.left = x + 'px'; ret.style.top = y + 'px'; xh.style.display = xv.style.display = 'block'; xh.style.left = xv.style.left = x + 'px'; xh.style.top = xv.style.top = y + 'px'; lead(x, y, t); } else nbLines.visible = false;
  const sk = skins.tick(t); if (sk) paint(sk); skins.frameTime(dt);
  talkFrame(t); renderer.render(scene, camera); if (!TRACE) requestAnimationFrame(frame);
}
// test switch (headless): trace stops the frame loop; a script steps it with __deck.tick(t) and reads __deck.snap() to look for jumps
const TRACE = location.hash.includes('trace');
if (TRACE) window.__deck = { tick: frame, go, lock, live: () => live.snap(), play: ev => live.play(ev), snap: () => ({ prog: S.prog, w: shell.state && [...shell.obj.children[0].material.uniforms.uW.value.toArray()], scanY: scanner.position.y, scanOp: scanner.material.opacity, cam: camera.position.toArray(), lookY: S.lookY, yaw: S.yaw,
  labels: labelEls.map(e => [parseFloat(e.style.left), parseFloat(e.style.top)]), notes: labels.map(l => [parseFloat(l.el.style.left), parseFloat(l.el.style.top)]), ret: S.sel >= 0 ? [parseFloat(ret.style.left), parseFloat(ret.style.top)] : null,
  lead: S.sel >= 0 ? leadL.getAttribute('points') : '' }),
  // the voice path: talk(state) as the page would, ear(an) puts a fake analyser on the mic and the voice, play(on) says whether a clip plays; voice() reads what the shell is driven by
  talk: st => tState(st), ear: an => { S.micAn = S.outAn = an; }, play: on => { S.src = on ? {} : null; },
  voice: () => { const pick = u => Object.fromEntries(Object.entries(u).filter(([, x]) => typeof x.value === 'number').map(([k, x]) => [k, x.value]));
    const u = shell.obj.children[0].material.uniforms; return { lv: S.voiceLv, ...pick(u), pts: shell.obj.children[1].material.uniforms.uGlow.value, col: u.uCol.value.toArray(), hot: u.uHot.value.toArray(), ...Object.fromEntries(Object.entries(pick(cloud.m.uniforms)).filter(([k]) => /^uV|^uShim/.test(k)).map(([k, x]) => ['dot' + k, x])), pulse: notePulse() }; } };
refresh(); if (!TRACE) requestAnimationFrame(frame);
if (location.hash.includes('probe')) window.__dots = () => { const o = []; for (let i = 0; i < N; i++) { if (cloud.A[i] < .5) continue; const [x, y, z] = dotXY(i); if (z <= 1) o.push([i, Math.round(x), Math.round(y)]); } return { dots: o, sel: S.sel, hov: S.hov, pv: pvI, pvDot, reader: readerOpen }; };   // test switch (headless): where the dots are on screen
if (location.hash.includes('still')) document.head.insertAdjacentHTML('beforeend', '<style>#lockp *,#lockp,#reader,#reader *,#pv,#pv *,.ret2 svg,.ret2 .shock{animation:none!important;transition:none!important}.tg-title{min-height:44px}</style>');
const lm = location.hash.match(/lock=(\d+)/); if (lm) setTimeout(() => lock(+lm[1]), 400);
const hv = location.hash.slice(1).replace(/[!~&].*/, ''); if (hv in VIEW) { if (location.hash.includes('!')) { go(hv); S.prog = 1; cur.set(LAY[hv]); cloud.g.attributes.position.needsUpdate = true; S.pitch = S.pT; S.dist = S.dT; S.labelFrom = COLS.map(c => anchors[hv][c].clone()); for (const k in vis) vis[k] = k === hv ? 1 : 0; } else if (location.hash.includes('~')) { S.from = new Float32Array(Lmap); go(hv); S.prog = +location.hash.split('~')[1]; S.hold = true; } else setTimeout(() => go(hv), 600); }
