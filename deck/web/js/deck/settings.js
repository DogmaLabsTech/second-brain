import { THREE, days } from '../../hud.js';
import { KC, Lmap, S, pvHide, say, skins, thM, yOf } from '../deck-main.js';
// ---- Settings: gear in the top bar, the "," key, or the line in 01 View; Esc or a click outside closes. Test switch: #settings
const SETP = document.getElementById('setp'), SETV = document.getElementById('setveil'); skins.picker(document.getElementById('setskins')); skins.wire(SETP);
document.querySelector('#topbar .stat').insertAdjacentHTML('afterend', '<button id="gear" title="Settings  ( , )" aria-label="settings"><svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg></button>');
const GEAR = document.getElementById('gear'); export let setOpen = false;
export function settings(on = !setOpen) { setOpen = on; SETP.classList.toggle('on', on); SETV.classList.toggle('on', on); GEAR.classList.toggle('on', on); GEAR.setAttribute('aria-expanded', on);
  if (on) { if (typeof pvHide === 'function') pvHide(); (SETP.querySelector('.sk.on') || SETP).focus({ preventScroll: true }); } else if (SETP.contains(document.activeElement)) document.activeElement.blur(); }
GEAR.onclick = () => settings(); document.getElementById('skset').onclick = () => settings(true); document.getElementById('setx').onclick = SETV.onclick = () => settings(false);
addEventListener('keydown', e => { if (setOpen && e.key === 'Escape') { e.preventDefault(); e.stopImmediatePropagation(); settings(false); } }, true);   // Esc closes Settings first
export function invertKey() { if (!skins.invOk) return; skins.invert(!skins.inv); say('PALETTE  ›  ' + (skins.inv ? 'INVERTED' : 'NORMAL')); }
if (location.hash.includes('settings')) setTimeout(() => settings(true), 300);   // (after the module has run: the hover card's state is defined further down)
// section labels
export const anchors = { map: {}, tunnel: {}, radar: {} };
COLS.forEach((c, k) => { const m = new THREE.Vector3(); let n = 0; DOCS.forEach((d, i) => { if (d.c === c) { m.x += Lmap[i * 3]; m.y += Lmap[i * 3 + 1]; m.z += Lmap[i * 3 + 2]; n++; } }); anchors.map[c] = m.divideScalar(n).add(new THREE.Vector3(Math.cos(thM(k)) * .9, .55, Math.sin(thM(k)) * .9));
  anchors.tunnel[c] = new THREE.Vector3(Math.cos(thM(k)) * 3.95, yOf(0) + .35, Math.sin(thM(k)) * 3.95); anchors.radar[c] = new THREE.Vector3(Math.cos(thM(k)) * 3.95, .1, Math.sin(thM(k)) * 3.95); });
export const labelEls = COLS.map(c => { const e = document.createElement('div'); e.className = 'sec'; e.style.setProperty('--k', KC(c)); e.innerHTML = `<i></i><b>${NICE[c].toUpperCase()}</b><small>${DOCS.filter(d => d.c === c).length}</small>`; document.body.append(e); return e; });
export let labelCur = COLS.map(c => anchors.map[c].clone()); S.labelFrom = labelCur.map(a => a.clone()); export const labelOff = [];
export const wk = c => DOCS.filter(d => d.c === c && days(d.d) <= 7).length;
