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
import { dotHover, lock, pvDot, pvHide, pvI, unlock } from './deck/hover.js'; export * from './deck/hover.js';
import { ask, tl } from './deck/timeline-ask.js'; export * from './deck/timeline-ask.js';
import { live, liveNonce, liveOwn } from './deck/live.js'; export * from './deck/live.js';
import { PICK, dotXY, leftAway, leftW, nearDot } from './deck/input.js'; export * from './deck/input.js';
import { notePulse, tState, talkFrame } from './deck/voice.js'; export * from './deck/voice.js';
import './deck/fresh.js';
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
  const sweep = (t * .00045) % TAU; sweepG.rotation.y = -sweep; cloud.m.uniforms.uSweep.value = sweep; cloud.m.uniforms.uSweepOn.value = 0;   // calm: the sweep no longer pings notes
  const slY = yOf(S.cutoff); slice.position.y = slY; const cu = cloud.m.uniforms; cu.uScan.value = -2.6 + Math.abs(Math.sin((S.beamT = (S.beamT + dt * .00012) % 1) * Math.PI)) * 5.2; cu.uScanA.value = 0;   /* calm: no roaming map beam over the notes */ cu.uScan2.value = slY; cu.uScanB.value = vis.tunnel;
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
