import { RD, S, decode, docOf, editing, note, pvCache, renderNote, say } from '../deck-main.js';
// ---- 🔒 this computer only (brief 22): memory notes only. GET /private reads the note's tag; the toggle asks the server to run
// `brain private <note> on|off`, which changes the note (the Deck never edits it); then the note is read again. Turning it off asks first.
let lockSt = null; const BYW = { owner: 'you', filter: 'the names filter' };
export function lockShow(st) { lockSt = st; const on = !!(st && st.local_only), who = st && st.by ? (st.local_only ? 'locked' : 'turned off') + ' by ' + (BYW[st.by] || st.by) + (st.at ? ' on ' + st.at : '') : '';
  RD('reader').classList.toggle('mem', !!st); RD('rdlock').classList.toggle('on', on); RD('rdlockv').textContent = on ? 'ON' : 'OFF'; RD('rdlock').disabled = false;
  RD('rdlock').title = (on ? 'This computer only: online writers never get this note. Click to turn it off.' : 'Click to keep this note on this computer only: online writers will never get it.') + (who ? '\n' + who.replace(/^./, c => c.toUpperCase()) + '.' : '');
  const b = RD('rdlockb'); b.classList.toggle('on', on); b.textContent = on ? '🔒 THIS COMPUTER ONLY' + (st.by ? ' · BY ' + (BYW[st.by] || st.by).toUpperCase() : '') + (st.at ? ' · ' + st.at : '') : ''; b.title = who;
  if (!st) { lockAsk(false); lockMsg(''); } }
function lockMsg(t, cls = '') { const m = RD('rdlockmsg'); m.textContent = t; m.className = 'rd-note' + (t ? ' on ' + cls : ''); }
function lockAsk(on) { RD('rdlockask').classList.toggle('on', on); if (on) { lockMsg(''); RD('rdlockkeep').focus(); } }
export function lockLoad(n) { if (n.collection !== 'memory') return lockShow(null);
  fetch('/private?id=' + n.id, { headers: { 'X-Deck': '1' }, cache: 'no-store' }).then(x => x.json()).then(j => { if (note !== n || !j.memory) return;
    if (j.title) { docOf(n.i).t = j.title; decode(RD('rdt'), j.title, 8); }   // the note's own title (its heading or summary), not the file name
    lockShow(j.ok ? j : { local_only: false }); if (!j.ok) { RD('rdlock').disabled = true; lockMsg("Can't read this note's lock: " + (j.error || 'unknown problem') + '.', 'bad'); } }).catch(() => {}); }
function lockSet(on) { const n = note; if (!n || editing) return; lockAsk(false); RD('rdlock').disabled = true; lockMsg(on ? 'Locking…' : 'Turning the lock off…', 'busy');
  fetch('/private', { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Deck': '1' }, body: JSON.stringify({ id: n.id, on }) })
    .then(x => x.json().catch(() => ({ ok: false, error: 'the server said ' + x.status })))
    .then(j => { if (note !== n) return; RD('rdlock').disabled = false;
      if (!j.ok) return lockMsg('Nothing changed: ' + (j.error || 'unknown problem') + '.', 'bad');
      lockShow(j.state || j); const st = j.state || j, t = '“' + (j.title || docOf(n.i).t) + '”', by = st.by ? ' by ' + (BYW[st.by] || st.by) + (st.at ? ' on ' + st.at : '') : '';
      lockMsg(!j.changed ? `${t} was already ${on ? 'this computer only' : 'not locked'}${by}. Nothing changed.`
        : on ? `Done: ${t} is now this computer only (locked${by}). Online writers will never get it.` : `Done: the lock is off (turned off${by}). Online writers may get ${t} again.`);
      say(on ? 'LOCKED  ·  THIS COMPUTER ONLY' : 'LOCK OFF');
      if (j.changed) fetch('/note?id=' + n.id, { cache: 'no-store' }).then(x => x.ok ? x.json() : null).then(k => { if (!k || note !== n || editing) return; S.pendS = RD('rdb').scrollTop; Object.assign(n, k); pvCache.delete(n.id); renderNote(); }).catch(() => {}); })
    .catch(() => { RD('rdlock').disabled = false; lockMsg('Nothing changed: the Deck server did not answer.', 'bad'); }); }
RD('rdlock').onclick = () => { if (!lockSt || !note) return; if (lockSt.local_only) lockAsk(!RD('rdlockask').classList.contains('on')); else lockSet(true); };
RD('rdlockkeep').onclick = () => lockAsk(false); RD('rdlockoff').onclick = () => lockSet(false);
