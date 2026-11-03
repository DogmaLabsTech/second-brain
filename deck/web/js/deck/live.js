import { makeLive, makeFeed } from '../../live.js';
import { project, THREE } from '../../hud.js';
import { movable } from '../../movable.js';
import { H, KC, RD, W, byAny, byPath, camera, cloud, cur, editing, lock, loose, notePulse, openReader, pick, pk, root, say, setOpen, shell, shown, typingIn, visible } from '../deck-main.js';
// ---- 08 Live: every search and ask, from anywhere (chats, the voice island, the terminal, this Deck), as it happens.
// GET /live on the Deck server (read-only events; the token comes in this page's html). Each one plays the live animation
// (live.js) and gets a line in the 08 Live panel. The Ask box and the voice play their own results at once (liveOwn) and tag
// their calls with a nonce, so the server's copy of the same search is skipped here. L / the LIVE button / ✕ show or hide the panel.
export const live = makeLive({ cur, root, camera, project, V: new THREE.Vector3(), cloud, docs: DOCS, kc: KC, cols: COLS, esc, shell, seen: i => visible(i) && shown(i) > .05, pulse: () => notePulse(), W, H });
const LIVEP = RD('livep'), mine = new Set(), LTOK = document.querySelector('meta[name=deck-live]')?.content || '';
export function liveNonce() { const n = Math.random().toString(36).slice(2, 10); mine.add(n); return n; }
// a found note -> its dot: collection + path first, then the same path in any collection (qmd lists some files in two); undefined = newer than data.js
const liveIdx = h => !h.p ? undefined : (h.c && byPath.get(h.c + ':' + pk(h.p))) ?? pick(byAny.get(pk(h.p)), h.c);
export function liveOwn(ev) { feed.add(ev); return live.play({ ...ev, own: true }); }
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
  es.addEventListener('data', m => { try { dispatchEvent(new CustomEvent('deck-data', { detail: JSON.parse(m.data) })); } catch {} });   // a new map (fresh.js)
  es.onerror = () => { LB.classList.remove('ok'); feed.status(es.readyState === 2 ? 'server restarted: reload' : 'reconnecting', 'bad'); }; }
