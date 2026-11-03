import { RD, editing, leaveEdit, readerOpen, say, setOpen, talkBusy, typingIn } from '../deck-main.js';
// ---- a new map: the hourly refresh swaps in a new data.js and the server says so on the live stream (live.js passes it on
// as a `deck-data` event with the file's stamp). The first stamp is the map this page drew; a different one shows the chip
// NEW DATA · RELOAD (a click reloads now). The page reloads by itself only when it is idle: no note open, nothing being edited or
// typed, Settings shut, no voice turn (listening, thinking, speaking or waiting for a yes) and a minute without a key, click or move.
// Test switch: #fresh=<seconds> sets that quiet time and keeps window.__fresh (what the chip and the idle check see).
const FM = location.hash.match(/fresh=(\d+)/), QUIET = (FM ? +FM[1] : 60) * 1000;
let base = null, waiting = false, lastIn = performance.now();
for (const t of ['keydown', 'pointerdown', 'pointermove', 'wheel']) addEventListener(t, () => { lastIn = performance.now(); }, { capture: true, passive: true });
RD('livebtn').insertAdjacentHTML('afterend', '<button id="freshbtn" hidden title="a new map of your notes is ready: click to load it (it loads by itself when you leave the Deck alone for a minute)">NEW DATA · RELOAD</button>');
const FB = RD('freshbtn');
FB.onclick = () => { if (leaveEdit()) location.reload(); };
const busy = () => editing ? 'editing' : readerOpen ? 'a note is open' : setOpen ? 'settings open' : typingIn(document.activeElement) ? 'typing' : talkBusy() ? 'voice turn' : '';
function why() { const b = busy(); return b || (performance.now() - lastIn < QUIET ? 'recent input' : ''); }
addEventListener('deck-data', e => { const v = e.detail && e.detail.v; if (!v) return; if (base === null) { base = v; return; }
  if (v === base || waiting) return; waiting = true; FB.hidden = false; say('NEW DATA  ·  THE MAP RELOADS WHEN YOU ARE IDLE, OR CLICK RELOAD'); });
setInterval(() => { if (waiting && !why()) location.reload(); }, 2000);
if (FM) window.__fresh = () => ({ base, waiting, chip: !FB.hidden, why: why() });
