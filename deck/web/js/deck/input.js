import { project } from '../../hud.js';
import { replaceAll } from '../../movable.js';
import { H, N, S, W, camera, clamp, cloud, cur, editing, fitView, layoutReader, lock, readerOpen, readerW, renderer, root, say, tmp, view, viewDist } from '../deck-main.js';
// input
// picking: the nearest shown dot within PICK px of the mouse (screen space, this frame's camera and layout) wins
export const PICK = 16, dotXY = i => { tmp.set(cur[i * 3], cur[i * 3 + 1], cur[i * 3 + 2]).applyMatrix4(root.matrixWorld); return project(tmp, camera, W(), H()); };
export function nearDot(x0, y0, r = PICK) { let best = -1, bd = r; for (let i = 0; i < N; i++) { if (cloud.A[i] < .5) continue; const [x, y, z] = dotXY(i); if (z > 1) continue; const d = Math.hypot(x - x0, y - y0); if (d < bd) { bd = d; best = i; } } return [best, bd]; }
let downDot = -1;   // the dot is chosen when the button goes down (the hover is paused while the button is held, so it can't be read at mouseup)
renderer.domElement.onmousedown = e => { S.drag = [e.clientX, e.clientY]; S.moved = 0; downDot = S.hov >= 0 ? S.hov : nearDot(e.clientX, e.clientY)[0]; S.ty = null; S.autoCam = false; };
addEventListener('mouseup', () => { if (S.drag && S.moved < 5 && downDot >= 0) { S.pickQuiet = [S.mx, S.my]; lock(downDot); } S.drag = null; downDot = -1; });
addEventListener('mousemove', e => { S.mx = e.clientX; S.my = e.clientY; if (S.pickQuiet && Math.hypot(S.mx - S.pickQuiet[0], S.my - S.pickQuiet[1]) > 4) S.pickQuiet = null; S.overRd = !!(e.target.closest && e.target.closest('#reader,#pv,.mov,#setp,#setveil')); if (S.drag) { S.yaw += (e.clientX - S.drag[0]) * .006; S.pT = S.pitch = clamp(S.pitch + (e.clientY - S.drag[1]) * .006, -.2, 1.5); S.moved += Math.abs(e.clientX - S.drag[0]) + Math.abs(e.clientY - S.drag[1]); S.drag = [e.clientX, e.clientY]; } });
renderer.domElement.onwheel = e => { e.preventDefault(); S.dT = S.dist = clamp(S.dist * Math.exp(e.deltaY * .001), 4, 22); };
addEventListener('resize', () => { clearTimeout(window._rz); window._rz = setTimeout(() => { applyZ(false); S.dT = viewDist(view); S.autoCam = true; }, 120); if (readerOpen) layoutReader(); renderer.setSize(W(), H()); camera.aspect = W() / H(); fitView(); camera.updateProjectionMatrix(); cloud.m.uniforms.uScale.value = H() * .5; });
// left column (View + Sections): slide away / bring back (key T, the ◂ buttons, the tab)
export let leftAway = location.hash.includes('leftaway') || localStorage.getItem('deckLeftAway') === '1';
export const leftW = () => 272 * Z;   // the left column's space stays reserved, so nothing else moves when it is hidden
function applyLeft(anim) { const ps = [document.getElementById('viewp'), document.getElementById('sections'), document.getElementById('voicep')], t = document.getElementById('secTab'), L = document.getElementById('left');
  if (leftAway) { ps.forEach(p => p.classList.add('away')); setTimeout(() => { if (leftAway) { ps.forEach(p => p.style.display = 'none'); L.classList.add('hidden'); } }, anim ? 270 : 0); t.style.display = 'block'; }
  else { L.classList.remove('hidden'); ps.forEach(p => { p.style.display = ''; void p.offsetWidth; p.classList.remove('away'); }); t.style.display = 'none'; }
  if (anim) { applyZ(false); S.dT = viewDist(view); S.autoCam = true; } }
export function toggleLeft() { leftAway = !leftAway; localStorage.setItem('deckLeftAway', leftAway ? '1' : '0'); applyLeft(true); say(leftAway ? 'PANELS HIDDEN  ·  PRESS T TO SHOW' : 'PANELS SHOWN'); }
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
