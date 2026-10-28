import { ringWords } from '../../rings.js';
import { KC, S, W, Z, clamp, decode, leftW, lock, lockLoad, lockShow, mdRender, nh, pvCache, pvHide, pvShow, say } from '../deck-main.js';
// notes that are not dots in the scene (notes newer than data.js; the memory store used to be one, since brief 23 its notes are dots) still open in the reader (brief 22): they are
// kept in LOOSE and numbered from LOOSE0 up, so the reader's history works the same; docOf(i) is the note for either kind
export const LOOSE0 = 1e6, LOOSE = [], docOf = i => i >= LOOSE0 ? LOOSE[i - LOOSE0] : DOCS[i];
export function loose(h) { let k = LOOSE.findIndex(d => d.id === h.id); if (k < 0) k = LOOSE.push({ id: h.id, c: h.c, p: h.p || '', t: h.t || (h.p || '').split('/').pop(), d: '' }) - 1; return LOOSE0 + k; }
export let readerOpen = false, readerReq = 0, readerW = 0; S.baseOffX = 30; S.targetOffX = 30; export let note = null, editing = false, dirty = false, asking = false;
export const RD = id => document.getElementById(id), NARROW = 1700, STILL = location.hash.includes('still');
// narrow windows: while the reader is open the 04 lock panel steps aside (it comes back when the window is wide or the reader closes)
export function layoutReader() { const r = RD('reader'), wide = readerOpen && W() < NARROW; document.body.classList.toggle('rdwide', wide);
  const B = RD('bottom').getBoundingClientRect(), Lx = 16 + leftW() + 14, right = wide ? W() - 16 : RD('right').getBoundingClientRect().left - 14, top = 50 + 8 * Z;
  readerW = clamp((right - Lx) * (wide ? .62 : .6), 460, 640 * Z); r.style.left = (right - readerW) + 'px'; r.style.width = readerW + 'px'; r.style.top = top + 'px'; r.style.height = Math.max(300, B.top - 14 - top) + 'px';
  S.targetOffX = readerOpen ? W() / 2 - (Lx + right - readerW) / 2 : S.baseOffX; }
function setPct() { const b = RD('rdb'), max = b.scrollHeight - b.clientHeight, p = max > 0 ? b.scrollTop / max : 1; RD('rdbar').style.width = (editing ? 0 : p * 100) + '%'; RD('rdpct').textContent = editing ? '' : Math.round(p * 100) + '% READ'; }
function hint() { const h = RD('rdhint'); if (editing) h.innerHTML = `<span class="dirty">${dirty ? '● UNSAVED CHANGES' : 'NO CHANGES YET'}</span><span>CTRL+S SAVE</span><span>ESC CANCEL</span>`;
  else h.innerHTML = `<span>ESC CLOSE</span><span>${note && !note.editable ? 'READ-ONLY' : 'E EDIT'}</span><span>CLICK A LINK TO JUMP</span><span>ALT ← → BACK / FORWARD</span>`; }
function showErr(t) { const e = RD('rderr'); e.textContent = t || ''; e.classList.toggle('on', !!t); }
// if the note's first heading is an H1 with the same words as its title (also after a status line, a quote or front matter), hide the repeat
export function dropTitle(b, ts) { const h1 = b.querySelector(':scope>h1,:scope>h2,:scope>h3'), nt = x => x.toLowerCase().replace(/[^\p{L}\p{N}]+/gu, ''), a = h1 && nt(h1.textContent);
  if (h1 && h1.tagName === 'H1' && a && ts.some(t => { const n = t && nt(t); return n && (n === a || (Math.min(n.length, a.length) >= 12 && (n.startsWith(a) || a.startsWith(n)))); })) h1.remove(); }
// [[Note#Heading]]: scroll the heading to the top of the box and flash it
export function jumpTo(box, h) { const n = nh(h), hs = [...box.querySelectorAll('h1,h2,h3,h4,h5,h6')], el = hs.find(x => nh(x.textContent) === n) || hs.find(x => n && nh(x.textContent).startsWith(n)); if (!el) return false;
  box.scrollTop += el.getBoundingClientRect().top - box.getBoundingClientRect().top - 10; el.classList.remove('hit'); void el.offsetWidth; el.classList.add('hit'); return true; }
// reader history (◂ ▸ buttons, Alt+← / Alt+→): every note opened in the reader, with where you were in it
let rdHist = [], rdPos = -1, rdScroll = [], navHist = false, pendH = ''; S.pendS = 0;
function updNav() { RD('rdback').disabled = rdPos <= 0; RD('rdfwd').disabled = rdPos >= rdHist.length - 1; }
export function histGo(k) { const p = rdPos + k; if (p < 0 || p >= rdHist.length || !leaveEdit()) return; if (readerOpen) rdScroll[rdPos] = RD('rdb').scrollTop; navHist = true; pendH = ''; S.pendS = rdScroll[p] || 0; rdPos = p; rdHist[p] >= LOOSE0 ? openReader(rdHist[p]) : lock(rdHist[p]); }
export function follow(i, h) { pvHide(); if (i === S.sel && readerOpen) { if (!h || !jumpTo(RD('rdb'), h)) RD('rdb').scrollTop = 0; return; } pendH = h || ''; S.pendS = 0; lock(i); }
export function renderNote(quiet) { const b = RD('rdb'), j = note, d = docOf(j.i), w = (j.text.match(/\S+/g) || []).length;
  b.innerHTML = mdRender(j.text, true, { i: j.i >= LOOSE0 ? -1 : j.i, c: d.c, p: d.p }) + (j.truncated ? '<p class="k">… the note continues (cut here for display)</p>' : ''); dropTitle(b, [d.t, j.title]); b.style.opacity = ''; b.scrollTop = 0; [...b.children].forEach((e, k) => e.style.setProperty('--n', k));
  if (pendH) jumpTo(b, pendH); else if (S.pendS) b.scrollTop = S.pendS; pendH = ''; S.pendS = 0;
  RD('rds').textContent = j.path; RD('rdst').textContent = `${w.toLocaleString()} WORDS · ${Math.max(1, Math.round(w / 220))} MIN READ`; ringWords(j.i, w);
  RD('rdd').textContent = 'CHANGED ' + (j.source === 'file' && j.modified ? ago(j.modified.slice(0, 10)).toUpperCase() + ' · ' + j.modified.replace('T', ' ').slice(0, 16) : d.d ? ago(d.d).toUpperCase() + ' · ' + d.d : '');
  const s = RD('rdsrc'); s.textContent = j.source === 'file' ? 'LIVE FILE' : 'INDEX COPY · READ-ONLY'; s.classList.toggle('idx', j.source !== 'file'); s.title = j.why || '';
  RD('rdedit').disabled = !j.editable; RD('rdedit').title = j.editable ? 'edit this note (E)' : "can't edit: " + j.why; hint(); setPct(); }
export function openReader(i) { const r = RD('reader'), d = docOf(i), req = ++readerReq, b = RD('rdb'); r.style.setProperty('--k', KC(d.c)); lockShow(null);
  const was = readerOpen; pvHide();
  if (!navHist && rdHist[rdPos] !== i) { if (was && rdPos >= 0) rdScroll[rdPos] = b.scrollTop; rdHist = rdHist.slice(0, rdPos + 1); rdHist.push(i); rdPos = rdHist.length - 1; rdScroll[rdPos] = 0; }
  navHist = false; updNav(); readerOpen = true; note = null; layoutReader(); r.style.display = 'flex'; r.classList.toggle('quiet', was); if (!was) { r.classList.remove('open'); void r.offsetWidth; r.classList.add('open'); }
  decode(RD('rdt'), d.t, was ? 8 : 22); RD('rdg').textContent = (NICE[d.c] || d.c || '?').toUpperCase(); RD('rdd').textContent = d.d ? 'CHANGED ' + ago(d.d).toUpperCase() + ' · ' + d.d : ''; RD('rds').textContent = d.p; RD('rdst').textContent = ''; RD('rdsrc').textContent = '';
  RD('rdedit').disabled = true; showErr(''); hint(); if (was) b.style.opacity = '.3'; else b.innerHTML = '<div class="load">DECRYPTING NOTE <span class="cur"></span></div>'; b.scrollTop = 0; b.onscroll = setPct; setPct();
  fetch('/note?id=' + d.id, { cache: 'no-store' }).then(x => { if (!x.ok) throw x.status; return x.json(); }).then(j => { if (req !== readerReq) return; note = { ...j, i, id: d.id }; renderNote(); lockLoad(note);
    const tg = location.hash.match(/[#&]go=(\d+)/), th = location.hash.match(/[#&]hover=(\d+)/), tl = k => b.querySelectorAll('a.nl')[k];   // test switches: follow / peek the n-th note link
    if (tg && !S.testGone) { S.testGone = true; if (tl(+tg[1])) setTimeout(() => tl(+tg[1]).click(), 50); }
    else if (location.hash.includes('&miss') && b.querySelector('.nl.miss')) b.querySelector('.nl.miss').scrollIntoView({ block: 'center' });
    else if (th && tl(+th[1])) { tl(+th[1]).scrollIntoView({ block: 'center' }); setTimeout(() => pvShow(tl(+th[1])), 150); }
    if (location.hash.includes('&edit') || (j.test && location.hash.includes('testsave'))) startEdit();
    if (j.test && location.hash.includes('testsave')) { RD('rde').value += '\n\n- [x] Test edit from the Deck (' + new Date().toISOString().slice(0, 19) + ')\n'; RD('rde').oninput(); saveEdit(); } })
    .catch(() => { if (req === readerReq) { b.style.opacity = ''; b.innerHTML = '<p class="am">Could not read this note.</p>'; } }); }
// leaving the editor: fine when nothing changed, otherwise ask first (returns false = stay)
export function leaveEdit() { if (!editing) return true; if (!dirty) { exitEdit(); return true; } askDiscard(); say('SAVE OR THROW AWAY YOUR CHANGES FIRST'); return false; }
export function closeReader() { if (!leaveEdit()) return false; pvHide(); readerOpen = false; readerReq++; note = null; RD('reader').style.display = 'none'; layoutReader(); }
export function startEdit() { if (!readerOpen) return; if (!note) return say('NOTE STILL LOADING'); if (!note.editable) return say("CAN'T EDIT THIS NOTE: " + (note.why || '').toUpperCase());
  pvHide(); const t = RD('rde'); editing = true; dirty = false; asking = false; t.value = note.text; RD('reader').classList.add('editing'); RD('rdmode').textContent = 'EDITING'; showErr(''); hint(); setPct(); t.focus(); t.setSelectionRange(0, 0); t.scrollTop = 0; }
export function exitEdit() { editing = dirty = asking = false; RD('reader').classList.remove('editing'); RD('rdask').classList.remove('on'); RD('rdmode').textContent = 'NOTE OPEN'; showErr(''); hint(); setPct(); }
function askDiscard() { asking = true; RD('rdask').classList.add('on'); RD('rdkeep').focus(); }
export function keepEditing() { asking = false; RD('rdask').classList.remove('on'); RD('rde').focus(); }
export function cancelEdit() { if (dirty) askDiscard(); else exitEdit(); }
export function saveEdit() { if (!editing) return; if (!dirty) { exitEdit(); return say('NO CHANGES TO SAVE'); } const t = RD('rde'), sv = RD('rdsave'), text = t.value, n = note; sv.disabled = true; showErr('');
  fetch('/note?id=' + n.id, { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Deck': '1' }, body: JSON.stringify({ text, hash: n.hash }) })
    .then(x => x.json().catch(() => ({ error: 'the server said ' + x.status })).then(j => ({ ok: x.ok, code: x.status, j })))
    .then(({ ok, code, j }) => { sv.disabled = false; if (note !== n) return;
      if (!ok) return showErr('NOT SAVED: ' + (j.error || 'unknown problem') + (code === 409 ? '. Your text is still here: copy it, cancel, and open the note again.' : '.'));
      n.text = text; n.hash = j.hash; n.modified = j.modified; pvCache.delete(n.id); exitEdit(); renderNote(); const s = RD('rdsaved'); s.classList.add('on'); clearTimeout(s._t); if (!STILL) s._t = setTimeout(() => s.classList.remove('on'), 2600); say('NOTE SAVED  ·  OLD COPY BACKED UP'); })
    .catch(() => { sv.disabled = false; showErr('NOT SAVED: the Deck server did not answer. Your text is still here.'); }); }
RD('rdx').onclick = closeReader; RD('rdedit').onclick = startEdit; RD('rdsave').onclick = saveEdit; RD('rdcancel').onclick = cancelEdit; RD('rdkeep').onclick = keepEditing; RD('rddrop').onclick = exitEdit;
RD('rde').oninput = () => { const was = dirty; dirty = RD('rde').value !== note.text.replace(/\r\n?/g, '\n'); if (was !== dirty) hint(); };
RD('rde').onkeydown = e => { if (e.key === 'Tab' && !e.ctrlKey && !e.altKey) { e.preventDefault(); e.target.setRangeText('  ', e.target.selectionStart, e.target.selectionEnd, 'end'); e.target.oninput(); } };
addEventListener('beforeunload', e => { if (editing && dirty) e.preventDefault(); });
RD('rdback').onclick = () => histGo(-1); RD('rdfwd').onclick = () => histGo(1);
