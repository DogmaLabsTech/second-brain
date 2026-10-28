import { THREE, NOW, chrome, boot, typeInto, makeCloud, lineMat, project, days, hex3, cardInfo } from '../hud.js';
import { makeShell, DOT_GLSL } from '../shell.js';
import { makeSkins } from '../skins.js';
import { movable, replaceAll } from '../movable.js'; import { makeTimeline } from '../timeline.js'; import { makeAsk } from '../ask.js';
import { rings, ringWords, hideRingTip } from '../rings.js'; import { makeLive, makeFeed } from '../live.js';
const KC = c => `var(--g-${c},var(--dim2))`;   // a note group's colour in the page (skin token); the scene takes its colours from the skin theme (paint)
chrome('DECK · MAP ⇄ TUNNEL ⇄ RADAR', 0);
boot(['> SECOND BRAIN // DECK', '> reading index ............ ok', `> ${DOCS.length} notes in ${COLS.length} sections`, '> laying out three views ..... ok', '> tunnel transition armed', '> ready']);
const W = () => innerWidth, H = () => innerHeight, N = DOCS.length, SPAN = Math.PI * 2 / COLS.length, HT = 4.6, TAU = Math.PI * 2;
const secIdx = Object.fromEntries(COLS.map((c, k) => [c, k])), th0 = k => -Math.PI / 2 + k * SPAN, thM = k => th0(k) + SPAN / 2;
const age = d => Math.min(days(d.d), 38), ageR = d => Math.min(days(d.d), 60), yOf = a => (1 - a / 38) * HT - HT / 2;
const radRad = a => a <= 0 ? .05 : Math.min(.96, .07 + .89 * Math.sqrt(a / 60));
const clamp = (v, a = 0, b = 1) => Math.max(a, Math.min(b, v)), ease = t => t < .5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
function rankNorm(sel) { const o = new Float32Array(N); for (const c of COLS) { const idx = []; DOCS.forEach((d, i) => { if (d.c === c) idx.push(i); }); idx.sort((a, b) => sel(a) - sel(b)); idx.forEach((i, r) => o[i] = (r + .5) / idx.length); } return o; }
const r0 = rankNorm(i => DOCS[i].uv[0]), r1 = rankNorm(i => DOCS[i].uv[1]);
// ---- three layouts
const Lmap = new Float32Array(N * 3), Ltun = new Float32Array(N * 3), Lrad = new Float32Array(N * 3), cen = {};
for (const c of COLS) { const a = [0, 0, 0]; let n = 0; DOCS.forEach(d => { if (d.c === c) { a[0] += d.xyz[0]; a[1] += d.xyz[1]; a[2] += d.xyz[2]; n++; } }); cen[c] = a.map(v => v / n * 2.1); }
const ringC = {}; COLS.forEach((c, k) => { const o = cen[c]; ringC[c] = [Math.cos(thM(k)) * 3.4 * .78 + o[0] * .22, o[1] * .7, Math.sin(thM(k)) * 3.4 * .78 + o[2] * .22]; });
DOCS.forEach((d, i) => { const k = secIdx[d.c], c = cen[d.c], rc = ringC[d.c], p = d.xyz.map(v => v * 2.1);
  Lmap.set([rc[0] + (p[0] - c[0]) * .4, rc[1] + (p[1] - c[1]) * .4, rc[2] + (p[2] - c[2]) * .4], i * 3);
  const th = th0(k) + SPAN * (.07 + .86 * r0[i]), rt = 1.0 + 2.0 * r1[i]; Ltun.set([Math.cos(th) * rt, yOf(age(d)), Math.sin(th) * rt], i * 3);
  const rr = 3.15 * radRad(ageR(d)) + (r1[i] - .5) * .1; Lrad.set([Math.cos(th) * rr, (r1[i] - .5) * .1, Math.sin(th) * rr], i * 3); });
const LAY = { map: Lmap, tunnel: Ltun, radar: Lrad };
const VIEW = { map: { pitch: .2, dist: 10.4, desc: 'Notes grouped by what they are about. Each section floats as its own island; notes close together are close in meaning.' },
  tunnel: { pitch: .42, dist: 13.4, desc: 'Height is time. Today is the top ring, older notes sink. Each wedge of the tower is one section.' },
  radar: { pitch: 1.1, dist: 14.6, desc: 'Looking down from above. The centre changed today, the rim is weeks old. Each slice is one section.' } };
// ---- scene
const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true }); renderer.setPixelRatio(Math.min(2, devicePixelRatio)); renderer.setSize(W(), H()); document.getElementById('stage').append(renderer.domElement);
const S = {};   // the state several parts of the page write (move 3 of the split: one shared object)
const scene = new THREE.Scene(), camera = new THREE.PerspectiveCamera(42, W() / H(), .1, 100); S.offX = 30; S.offY = 52; const fitView = () => camera.setViewOffset(W(), H(), S.offX, S.offY, W(), H()); fitView(); const root = new THREE.Group(); scene.add(root);
const cloud = makeCloud(d => d.xyz, 1); cloud.P.set(Lmap); cloud.g.attributes.position.needsUpdate = true; root.add(cloud.pts); const cur = cloud.P;
// the dots: two scan bands that fade with their views (map beam, tunnel date slice) instead of one band that jumps, and the shell's voice rings and shimmer
cloud.g.setAttribute('aGrp', new THREE.BufferAttribute(new Float32Array(DOCS.map(d => COLS.indexOf(d.c))), 1));   // live searches: each note's section, so only searched sections wake up
{ const m = cloud.m, u = m.uniforms; Object.assign(u, { uWake: { value: new Float32Array(COLS.length) }, uLive: { value: 0 }, uScan2: { value: -99 }, uBand2: { value: .22 }, uScanA: { value: 1 }, uScanB: { value: 0 }, uCore: { value: .5 }, uDot: { value: 1 }, uSize: { value: 1 } });
  m.fragmentShader = m.fragmentShader.replace('varying vec3 vC;', 'uniform float uCore; uniform float uDot; varying vec3 vC;').replace('vec3(core*.5), a*a*vA*1.5)', 'vec3(core*uCore), min(1., a*a*vA*1.5*uDot))');
  m.vertexShader = DOT_GLSL + `attribute float aGrp; uniform float uWake[${COLS.length}]; uniform float uLive;\n` + 'uniform float uSize; uniform float uScan2; uniform float uBand2; uniform float uScanA; uniform float uScanB;\n' + m.vertexShader
    .replace('float band=smoothstep(uBand,0.,abs(position.y-uScan));', 'float band=smoothstep(uBand,0.,abs(position.y-uScan))*uScanA+smoothstep(uBand2,0.,abs(position.y-uScan2))*uScanB;')
    .replace('gl_PointSize=aSize*(1.', 'float vg=max(voiceGlow(position),0.); vA+=vg*.9*aAlpha; vA*=mix(1.,.32+.93*uWake[int(aGrp+.5)],uLive); gl_PointSize=uSize*aSize*(1.+vg*.7'); }
// the brain's shell: fitted to the real extent of the notes in each layout (globe / tall tube / low dome)
function extent(L) { let y0 = 1e9, y1 = -1e9, x0 = 1e9, x1 = -1e9, z0 = 1e9, z1 = -1e9; for (let i = 0; i < N; i++) { const x = L[i * 3], y = L[i * 3 + 1], z = L[i * 3 + 2]; x0 = Math.min(x0, x); x1 = Math.max(x1, x); y0 = Math.min(y0, y); y1 = Math.max(y1, y); z0 = Math.min(z0, z); z1 = Math.max(z1, z); } return { x0, x1, y0, y1, z0, z1 }; }
const radial = (L, cx, cz) => { let r = 0; for (let i = 0; i < N; i++) r = Math.max(r, Math.hypot(L[i * 3] - cx, L[i * 3 + 2] - cz)); return r; };
const FITS = (() => { const m = extent(Lmap), t = extent(Ltun), r = extent(Lrad), mc = [(m.x0 + m.x1) / 2, (m.y0 + m.y1) / 2, (m.z0 + m.z1) / 2], mR = radial(Lmap, mc[0], mc[2]) * 1.04;
  const tR = radial(Ltun, 0, 0) * 1.12, rR = radial(Lrad, 0, 0) * 1.12;
  return { map: { c: mc, r: [mR, Math.max((m.y1 - m.y0) / 2 * 1.5, mR * .7)] }, tunnel: { c: [0, (t.y0 + t.y1) / 2, 0], r: [tR, (t.y1 - t.y0) / 2 + .55] }, radar: { c: [0, r.y0 - .06, 0], r: [rR, rR * .52] } }; })();
const shell = makeShell(FITS); root.add(shell.obj); shell.dots(cloud.m.uniforms);
// ---- structure drawings (each view has its own set; they fade in and out)
const sets = { map: new THREE.Group(), tunnel: new THREE.Group(), radar: new THREE.Group() }, mats = []; Object.values(sets).forEach(g => root.add(g));
function ln(set, pts, op, sec) { const m = lineMat(0xffffff, op); m.userData = { op, sec, view: set, role: 'line' }; mats.push(m); const l = new THREE.Line(new THREE.BufferGeometry().setFromPoints(pts), m); sets[set].add(l); return l; }
const circ = (r, y, n = 128) => Array.from({ length: n + 1 }, (_, i) => new THREE.Vector3(Math.cos(i / n * TAU) * r, y, Math.sin(i / n * TAU) * r));
const arc = (r, y, a0, a1, n = 24) => Array.from({ length: n + 1 }, (_, i) => { const a = a0 + (a1 - a0) * i / n; return new THREE.Vector3(Math.cos(a) * r, y, Math.sin(a) * r); });
// map: holo base
[[3, .22], [5.8, .14]].forEach(([r, o]) => ln('map', circ(r, -3.6), o));
for (let i = 0; i < 24; i++) { const a = i / 24 * TAU, r1_ = 5.45; ln('map', [new THREE.Vector3(Math.cos(a) * r1_, -3.6, Math.sin(a) * r1_), new THREE.Vector3(Math.cos(a) * 5.8, -3.6, Math.sin(a) * 5.8)], .35); }
// tunnel: layer rings, wedge walls, section arcs
[0, 7, 14, 21, 28, 38].forEach(a => ln('tunnel', circ(3.3, yOf(a)), a === 0 ? .8 : .26));
ln('tunnel', [new THREE.Vector3(0, yOf(38), 0), new THREE.Vector3(0, yOf(0) + .3, 0)], .4);
COLS.forEach((c, k) => { const a = th0(k); ln('tunnel', [new THREE.Vector3(Math.cos(a) * 3.3, yOf(38), Math.sin(a) * 3.3), new THREE.Vector3(Math.cos(a) * 3.3, yOf(0), Math.sin(a) * 3.3)], .14);
  ln('tunnel', arc(3.45, yOf(0), a + .03, a + SPAN - .03), .9, c); ln('tunnel', arc(3.45, yOf(38), a + .03, a + SPAN - .03), .5, c); });
// radar: range rings, spokes, section arcs
[0, 7, 30, 60].forEach(a => ln('radar', circ(3.15 * radRad(a), 0, 128), a === 60 ? .55 : .3));
COLS.forEach((c, k) => { const a = th0(k); ln('radar', [new THREE.Vector3(0, 0, 0), new THREE.Vector3(Math.cos(a) * 3.3, 0, Math.sin(a) * 3.3)], .22);
  ln('radar', arc(3.38, 0, a + .03, a + SPAN - .03), .95, c); });
for (let i = 0; i < 72; i++) { const a = i / 72 * TAU, l = i % 6 ? .06 : .14; ln('radar', [new THREE.Vector3(Math.cos(a) * 3.3, 0, Math.sin(a) * 3.3), new THREE.Vector3(Math.cos(a) * (3.3 - l), 0, Math.sin(a) * (3.3 - l))], .4); }
const sweepG = new THREE.Group(); sets.radar.add(sweepG); const swl = new THREE.Line(new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(0, 0, 0), new THREE.Vector3(3.3, 0, 0)]), lineMat(0xffffff, .95)); swl.material.userData = { op: .95, view: 'radar', role: 'sweep' }; mats.push(swl.material); sweepG.add(swl);
const wedge = new THREE.Mesh(new THREE.CircleGeometry(3.3, 40, 0, .9).rotateX(-Math.PI / 2), new THREE.MeshBasicMaterial({ transparent: true, opacity: .09, blending: THREE.AdditiveBlending, depthWrite: false, side: THREE.DoubleSide })); wedge.material.userData = { op: .09, view: 'radar', role: 'sweep' }; mats.push(wedge.material); sweepG.add(wedge);
// date slice (amber) + transition scanner ring
const slice = new THREE.Line(new THREE.BufferGeometry().setFromPoints(circ(3.3, 0)), lineMat(0xffffff, .95)); slice.material.userData = { op: .95, view: 'tunnel', role: 'slice' }; mats.push(slice.material); sets.tunnel.add(slice);
const scanner = new THREE.Line(new THREE.BufferGeometry().setFromPoints(circ(3.7, 0)), lineMat(0xffffff, 0)); root.add(scanner);
const nbLines = new THREE.LineSegments(new THREE.BufferGeometry().setAttribute('position', new THREE.BufferAttribute(new Float32Array(12 * 3), 3)), lineMat(0xffffff, .45)); nbLines.frustumCulled = false; root.add(nbLines);
// ---- skins: paint the scene with the skin's theme (dot colours per group, lines by role, the shell, add or normal blending); runs while a switch fades
const skins = makeSkins(COLS), dotC = cloud.g.attributes.color.array, gIdx = DOCS.map(d => d.c);
function paint(T) { const B = T.blend === 'normal' ? THREE.NormalBlending : THREE.AdditiveBlending, setB = m => { if (m.blending !== B) { m.blending = B; m.needsUpdate = true; } };
  for (let i = 0; i < N; i++) { const c = T.g[gIdx[i]]; dotC[i * 3] = c.r; dotC[i * 3 + 1] = c.g; dotC[i * 3 + 2] = c.b; } cloud.g.attributes.color.needsUpdate = true;
  for (const m of mats) { m.color.copy(m.userData.sec ? T.g[m.userData.sec] : T[m.userData.role]); setB(m); }
  scanner.material.color.copy(T.scan); nbLines.material.color.copy(T.nb); [scanner.material, nbLines.material, cloud.m].forEach(setB);
  cloud.m.uniforms.uCore.value = T.core; cloud.m.uniforms.uDot.value = T.dot; cloud.m.uniforms.uSize.value = T.size; shell.theme(T); }
paint(skins.tick(performance.now()));
// ---- state
S.hold = false; let view = 'map'; S.prog = 1; S.from = new Float32Array(Lmap); let to = Lmap, delay = new Float32Array(N); S.yaw = .4; S.pitch = VIEW.map.pitch; S.dist = VIEW.map.dist; S.pT = S.pitch; S.dT = S.dist; S.autoCam = true; S.ty = null;
let scanFrom = yOf(38), scanOp0 = 0; S.lookY = 0; S.voiceLv = 0; let camFrom = null;
S.overRd = false; S.drag = null; S.moved = 0; S.mx = 0; S.my = 0; S.sel = -1; S.hov = -1; let q = '', hidden = new Set(); S.focus = null; S.hoverG = null; S.cutoff = 0; let playing = false; S.beamT = 0;
const vis = { map: 1, tunnel: 0, radar: 0 };
const toast = document.getElementById('toast'); let toastT;
function say(t) { toast.textContent = t; toast.classList.add('on'); clearTimeout(toastT); toastT = setTimeout(() => toast.classList.remove('on'), 2400); }
function viewDist(v) { const B = document.getElementById('bottom').getBoundingClientRect(), fw = W() - (32 + leftW() + 332 * Z + 28), fh = H() - 62 - B.height - 14, sc = clamp(Math.min(fw / 1480, fh / 920), .55, 1.5); return VIEW[v].dist / sc; }
function go(v) {
  if (v === view) return; view = v; shell.go(v); scanFrom = S.prog < 1 ? scanner.position.y : yOf(38); scanOp0 = S.prog < 1 ? scanner.material.opacity / .95 : 0;   // mid-flight: the ring and shell carry on from where they are
  S.from = new Float32Array(cur); to = LAY[v]; S.prog = 0; camFrom = [S.pitch, S.dist, S.lookY]; S.autoCam = true; S.pT = VIEW[v].pitch; S.dT = viewDist(v); S.ty = null;
  const up = v === 'tunnel'; DOCS.forEach((d, i) => delay[i] = (up ? 1 - age(d) / 38 : age(d) / 38) * .4);
  document.querySelectorAll('.tab').forEach(b => b.classList.toggle('on', b.dataset.v === v)); document.getElementById('vdesc').textContent = VIEW[v].desc;
  say('REALIGNING  ›  ' + v.toUpperCase() + ' VIEW'); S.labelFrom = labelCur.map(a => a.clone());
}
document.querySelectorAll('.tab').forEach(b => b.onclick = () => go(b.dataset.v));
document.getElementById('vdesc').textContent = VIEW.map.desc; skins.wire(document.getElementById('skins'));
// ---- Settings (brief 14): gear in the top bar, the "," key, or the line in 01 View; Esc or a click outside closes. Test switch: #settings
const SETP = document.getElementById('setp'), SETV = document.getElementById('setveil'); skins.picker(document.getElementById('setskins')); skins.wire(SETP);
document.querySelector('#topbar .stat').insertAdjacentHTML('afterend', '<button id="gear" title="Settings  ( , )" aria-label="settings"><svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg></button>');
const GEAR = document.getElementById('gear'); let setOpen = false;
function settings(on = !setOpen) { setOpen = on; SETP.classList.toggle('on', on); SETV.classList.toggle('on', on); GEAR.classList.toggle('on', on); GEAR.setAttribute('aria-expanded', on);
  if (on) { if (typeof pvHide === 'function') pvHide(); (SETP.querySelector('.sk.on') || SETP).focus({ preventScroll: true }); } else if (SETP.contains(document.activeElement)) document.activeElement.blur(); }
GEAR.onclick = () => settings(); document.getElementById('skset').onclick = () => settings(true); document.getElementById('setx').onclick = SETV.onclick = () => settings(false);
addEventListener('keydown', e => { if (setOpen && e.key === 'Escape') { e.preventDefault(); e.stopImmediatePropagation(); settings(false); } }, true);   // Esc closes Settings first
function invertKey() { if (!skins.invOk) return; skins.invert(!skins.inv); say('PALETTE  ›  ' + (skins.inv ? 'INVERTED' : 'NORMAL')); }
if (location.hash.includes('settings')) setTimeout(() => settings(true), 300);   // (after the module has run: the hover card's state is defined further down)
// section labels
const anchors = { map: {}, tunnel: {}, radar: {} };
COLS.forEach((c, k) => { const m = new THREE.Vector3(); let n = 0; DOCS.forEach((d, i) => { if (d.c === c) { m.x += Lmap[i * 3]; m.y += Lmap[i * 3 + 1]; m.z += Lmap[i * 3 + 2]; n++; } }); anchors.map[c] = m.divideScalar(n).add(new THREE.Vector3(Math.cos(thM(k)) * .9, .55, Math.sin(thM(k)) * .9));
  anchors.tunnel[c] = new THREE.Vector3(Math.cos(thM(k)) * 3.95, yOf(0) + .35, Math.sin(thM(k)) * 3.95); anchors.radar[c] = new THREE.Vector3(Math.cos(thM(k)) * 3.95, .1, Math.sin(thM(k)) * 3.95); });
const labelEls = COLS.map(c => { const e = document.createElement('div'); e.className = 'sec'; e.style.setProperty('--k', KC(c)); e.innerHTML = `<i></i><b>${NICE[c].toUpperCase()}</b><small>${DOCS.filter(d => d.c === c).length}</small>`; document.body.append(e); return e; });
let labelCur = COLS.map(c => anchors.map[c].clone()); S.labelFrom = labelCur.map(a => a.clone()); const labelOff = [];
const wk = c => DOCS.filter(d => d.c === c && days(d.d) <= 7).length;
// ---- panels
const eff = () => S.focus || S.hoverG, mx2 = Math.max(...COLS.map(c => DOCS.filter(d => d.c === c).length));
document.getElementById('groups').innerHTML = COLS.map(c => { const n = DOCS.filter(d => d.c === c).length; return `<div class="row" data-c="${c}" style="--k:${KC(c)};--w:${Math.max(4, n / mx2 * 100)}%"><i></i><span>${NICE[c]}</span><u></u><em>${n}</em><b class="eye" title="hide">◉</b></div>`; }).join('');
document.querySelectorAll('#groups .row').forEach(r => { const c = r.dataset.c;
  r.onclick = () => { S.focus = S.focus === c ? null : c; document.querySelectorAll('#groups .row').forEach(x => x.classList.toggle('on', x.dataset.c === S.focus)); refresh(); renderSection(); };
  r.onmouseenter = () => { S.hoverG = c; refresh(); renderSection(); }; r.onmouseleave = () => { S.hoverG = null; refresh(); renderSection(); };
  r.querySelector('.eye').onclick = e => { e.stopPropagation(); hidden.has(c) ? hidden.delete(c) : hidden.add(c); r.classList.toggle('off', hidden.has(c)); refresh(); }; });
function renderSection() {
  const c = eff(), a = DOCS.map((d, i) => i).filter(i => !c || DOCS[i].c === c), dd = i => days(DOCS[i].d);
  const w = a.filter(i => dd(i) <= 7).length, m = a.filter(i => dd(i) > 7 && dd(i) <= 30).length, o = a.length - w - m, pc = x => (x / a.length * 100).toFixed(1) + '%';
  document.getElementById('secn').textContent = c ? NICE[c].toUpperCase() : 'ALL SECTIONS';
  let h = `<div class="stat2"><div><b data-to="${a.length}">0</b><span>notes</span></div><div><b class="am" data-to="${w}">0</b><span>this week</span></div><div><b data-to="${Math.round(o / a.length * 100)}" data-sfx="%">0</b><span>older than 30d</span></div></div>
   <div class="fresh"><i style="width:0" data-w="${pc(w)}" style2=""></i><i style="width:0" data-w="${pc(m)}"></i><i style="width:0" data-w="${pc(o)}"></i></div><div class="k" style="font-size:10px;letter-spacing:.1em">■ <span style="color:var(--c)">WEEK</span> &nbsp;■ <span class="am">MONTH</span> &nbsp;■ OLDER</div>`;
  if (c) { const nw = [...a].sort((x, y) => DOCS[x].d < DOCS[y].d ? 1 : DOCS[x].d > DOCS[y].d ? -1 : 0).slice(0, 5);
    h += '<div class="h" style="margin-top:12px"><span>Newest here</span></div>' + nw.map(i => `<a class="nb" data-i="${i}" style="--k:${KC(c)}">${esc(DOCS[i].t.slice(0, 40))} <span class="k">· ${ago(DOCS[i].d)}</span></a>`).join(''); }
  else h += '<div class="h" style="margin-top:12px"><span>Busiest this week</span></div>' + [...COLS].sort((x, y) => wk(y) - wk(x)).slice(0, 6).map(k => { const t = DOCS.filter(d => d.c === k).length, ww = wk(k); return `<div class="mini" style="--k:${KC(k)}"><span style="color:${KC(k)}">${NICE[k]}</span><div class="fresh"><i style="width:0;background:${KC(k)}" data-w="${ww / t * 100}%"></i></div><b>${ww}</b></div>`; }).join('');
  document.getElementById('secbody').innerHTML = h; const fi = document.querySelectorAll('#secbody .fresh')[0]; if (fi) { const [i1, i2, i3] = fi.children; i1.style.background = 'var(--c)'; i2.style.background = 'var(--amber)'; i3.style.background = 'var(--dim)'; } animateIn(document.getElementById('secbody')); document.querySelectorAll('#secbody .nb').forEach(x => x.onclick = () => lock(+x.dataset.i)); }
const tip = document.getElementById('tip'), tmp = new THREE.Vector3(), labels = [];
const visible = i => !hidden.has(DOCS[i].c), match = i => !hits || hits.has(i), shown = i => tl.alpha(age(DOCS[i]));   // hits: the 06 Ask search's notes (null = no search)
function refresh() { const e = eff(); DOCS.forEach((d, i) => { const b = shown(i); cloud.A[i] = !visible(i) || !b ? 0 : ((e && d.c !== e) ? .1 : match(i) ? 1 : .06) * b; }); cloud.flush(); }
function mk(cls = 'lbl') { const e = document.createElement('div'); e.className = cls; document.body.append(e); return e; }
function clearLabels() { labels.forEach(l => l.el.remove()); labels.length = 0; }
function addLabel(i, txt, tag) { const el = mk(); el.style.setProperty('--k', KC(DOCS[i].c)); const t = tag || String(labels.length + 1).padStart(2, '0'); if (tag === '◎' || S.sel >= 0) { el.classList.add('tag'); el.innerHTML = `<i>${tag === '◎' ? '' : t}</i>`; if (tag === '◎') el.style.display = 'none'; } else el.innerHTML = `<i>${t}</i>${esc(txt.slice(0, 28))}`; labels.push({ i, el }); }
const ret = mk('ret2'); ret.style.display = 'none';
const tickSvg = Array.from({ length: 36 }, (_, i) => { const a = i / 36 * Math.PI * 2, l = i % 3 ? 4 : 9; return `<line x1="${66 + Math.cos(a) * 62}" y1="${66 + Math.sin(a) * 62}" x2="${66 + Math.cos(a) * (62 - l)}" y2="${66 + Math.sin(a) * (62 - l)}"/>`; }).join('');
ret.innerHTML = `<svg viewBox="0 0 132 132" fill="none" style="stroke:var(--c)"><g class="g3" stroke-width="1" opacity=".8">${tickSvg}</g><g class="g1" stroke-width="2"><path d="M66 12a54 54 0 0 1 46 26" /><path d="M120 66a54 54 0 0 1-26 46"/><path d="M66 120a54 54 0 0 1-46-26"/><path d="M12 66a54 54 0 0 1 26-46"/></g>
  <g class="g2" stroke-width="1.5" stroke-dasharray="3 5" opacity=".85"><circle cx="66" cy="66" r="40"/></g><circle cx="66" cy="66" r="22" style="stroke:var(--amber)" stroke-width="1.5"/>
  <path d="M66 36v14M66 82v14M36 66h14M82 66h14" style="stroke:var(--hi)" stroke-width="1.5"/><circle cx="66" cy="66" r="2.5" style="fill:var(--amber);stroke:none"/>
  <path d="M4 20V4h16M112 4h16v16M128 112v16h-16M20 128H4v-16" stroke-width="2" style="opacity:var(--corner)"/></svg><div class="shock"></div>`;
const xh = mk('xh'), xv = mk('xv'); xh.style.display = xv.style.display = 'none';
document.body.insertAdjacentHTML('beforeend', '<svg id="lead" style="display:none"><polyline id="leadl" points=""/><circle id="leadn" r="4" style="fill:var(--amber)"/><circle id="leadp" r="2.5" style="fill:var(--hi)"/></svg>');
const leadSvg = document.getElementById('lead'), leadL = document.getElementById('leadl'), leadN = document.getElementById('leadn'), leadP = document.getElementById('leadp');
function lead(x, y, t) { const pr = document.getElementById(readerOpen ? 'reader' : 'lockp').getBoundingClientRect(); if (!pr.width) return; const tx = pr.left, ex = tx - 34;
  const yE = clamp(y, pr.top + 26, pr.bottom - 36), dy = clamp(yE - y, -34, 34), P = [[x, y], [x + Math.abs(dy), y + dy], [ex, y + dy], [ex, yE], [tx, yE]], seg = P.slice(1).map((p, i) => Math.hypot(p[0] - P[i][0], p[1] - P[i][1])), tot = seg.reduce((a, b) => a + b, 0);
  S.leadT = location.hash.includes('still') ? 1 : Math.min(1, (t - lockAt - 250) / 650); const lim = Math.max(0, S.leadT) * tot; let acc = 0, pts = [P[0]];
  for (let k = 0; k < seg.length; k++) { if (acc + seg[k] <= lim) { pts.push(P[k + 1]); acc += seg[k]; } else { const f = (lim - acc) / seg[k]; pts.push([P[k][0] + (P[k + 1][0] - P[k][0]) * f, P[k][1] + (P[k + 1][1] - P[k][1]) * f]); break; } }
  leadSvg.style.display = 'block'; leadL.setAttribute('points', pts.map(p => p.join(',')).join(' ')); const e = pts[pts.length - 1]; leadN.setAttribute('cx', e[0]); leadN.setAttribute('cy', e[1]); leadN.style.opacity = S.leadT > 0 ? 1 : 0;
  const pk = ((t * .0007) % 1) * tot; let a2 = 0, px = x, py = y; for (let k = 0; k < seg.length; k++) { if (a2 + seg[k] >= pk) { const f = (pk - a2) / (seg[k] || 1); px = P[k][0] + (P[k + 1][0] - P[k][0]) * f; py = P[k][1] + (P[k + 1][1] - P[k][1]) * f; break; } a2 += seg[k]; }
  leadP.setAttribute('cx', px); leadP.setAttribute('cy', py); leadP.style.opacity = S.leadT >= 1 ? 1 : 0; }
const GL = 'ABCDEF0123456789#$%&@<>/\\|', R = 30, CIRC = 2 * Math.PI * R;
function decode(el, text, ms = 22) { clearInterval(el._d); let n = 0; el._d = setInterval(() => { n += 1.3; el.textContent = text.slice(0, Math.floor(n)) + Array.from(text.slice(Math.floor(n), Math.floor(n) + 6), ch => ch === ' ' ? ' ' : GL[Math.random() * GL.length | 0]).join(''); if (n >= text.length) { clearInterval(el._d); el.textContent = text; } }, ms); }
function countUp(el, to, ms = 900, sfx = '') { const t0 = performance.now(); (function f(t) { const k = clamp((t - t0) / ms), v = Math.round(to * (1 - Math.pow(1 - k, 3))); el.textContent = v.toLocaleString() + sfx; if (k < 1) requestAnimationFrame(f); })(t0); }
function gauge(label, v, text, color) { return `<div class="gg"><svg width="76" height="76" viewBox="-38 -38 76 76" style="color:${color}"><circle class="or" r="36"/><circle class="tk" r="${R}"/><circle class="tr" r="${R}"/>
  <circle class="ar" r="${R}" style="stroke:${color}" transform="rotate(-90)" stroke-dasharray="${CIRC}" stroke-dashoffset="${CIRC}" data-off="${CIRC * (1 - clamp(v))}"/><text y="5">${text}</text></svg><span class="lb">${label}</span></div>`; }
function animateIn(root) { requestAnimationFrame(() => requestAnimationFrame(() => { root.querySelectorAll('[data-off]').forEach(e => e.style.strokeDashoffset = e.dataset.off); root.querySelectorAll('[data-w]').forEach(e => { e.style.transition = 'width 1.1s cubic-bezier(.2,.8,.2,1) .3s'; e.style.width = e.dataset.w; }); root.querySelectorAll('[data-to]').forEach(e => countUp(e, +e.dataset.to, 900, e.dataset.sfx || '')); })); }
// ---- note links: find the note a [[wiki link]] or a relative .md link points to (path first, then file name, then title;
// the same collection wins when several match). -1 = not in the brain.
const nk = s => s.toLowerCase().replace(/\.md$/, '').replace(/[^\p{L}\p{N}]+/gu, '-').replace(/^-|-$/g, ''), pk = p => p.split('/').map(nk).join('/');
const nh = s => s.toLowerCase().replace(/[^\p{L}\p{N}]+/gu, ''), un = s => s.replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&quot;/g, '"').replace(/&amp;/g, '&');
const byPath = new Map(), byAny = new Map(), byName = new Map(), byTitle = new Map(), add = (m, k, i) => { if (!m.has(k)) m.set(k, []); m.get(k).push(i); };
DOCS.forEach((d, i) => { byPath.set(d.c + ':' + pk(d.p), i); add(byAny, pk(d.p), i); add(byName, nk(d.p.split('/').pop()), i); add(byTitle, nk(d.t), i); });
const pick = (l, c) => l && (l.find(i => DOCS[i].c === c) ?? [...l].sort((a, b) => DOCS[a].p.length - DOCS[b].p.length)[0]);
function resolve(t, ctx, rel) { t = t.trim(); if (!t) return ctx ? ctx.i : -1; const c = ctx && ctx.c, dir = ctx ? ctx.p.split('/').slice(0, -1) : [];
  const norm = parts => { const o = []; for (const s of parts) { if (s === '..') o.pop(); else if (s && s !== '.') o.push(s); } return o.join('/'); };
  const tries = rel || t.includes('/') ? [...(t.startsWith('/') ? [] : [norm([...dir, ...t.split('/')])]), norm(t.split('/'))] : [];
  for (const p of tries) { const i = byPath.get(c + ':' + pk(p)); if (i !== undefined) return i; const l = pick(byAny.get(pk(p)), c); if (l !== undefined) return l; }
  return pick(byName.get(nk(t.split('/').pop())), c) ?? pick(byTitle.get(nk(t)), c) ?? -1; }
const nlink = (i, txt, h, emb) => i < 0 ? `<span class="nl miss${emb ? ' emb' : ''}">${txt}</span>` : `<a class="nl${emb ? ' emb' : ''}" data-i="${i}" data-h="${esc(h || '')}">${txt}</a>`;
function wiki(a, emb, ctx) { const k = a.indexOf('|'), tg = (k < 0 ? a : a.slice(0, k)).replace(/\\$/, ''), al = k < 0 ? '' : a.slice(k + 1).trim(), [nm, ...hs] = tg.split('#'), h = hs.join('#').replace(/^\^.*/, '').trim();
  return nlink(resolve(nm, ctx), esc(al || (nm.trim() ? nm.trim() + (h ? ' › ' + h : '') : h)), h, emb); }
let mdCtx = null;   // the note being rendered ({ i, c, p }), so links resolve from its folder and collection
function mdRender(src, top = true, ctx = mdCtx) {
  src = src.replace(/\r/g, ''); let fm = ''; const m0 = top && src.match(/^---\n([\s\S]*?)\n---\n?/); if (m0) { fm = m0[1]; src = src.slice(m0[0].length); }
  const L = src.split('\n'), out = []; let i = 0;
  const inl = t => { const cs = [], ph = h => '\u0001' + (cs.push(h) - 1) + '\u0002'; t = t.replace(/`([^`]+)`/g, (_, c) => ph('<code>' + esc(c) + '</code>')).replace(/(!?)\[\[([^\]]+)\]\]/g, (_, e, a) => ph(wiki(a, !!e, ctx)));
    return esc(t).replace(/!\[([^\]]*)\]\([^)]*\)/g, '<span class="k">[image: $1]</span>').replace(/\*\*([^*]+)\*\*|__([^_]+)__/g, (_, a, b) => `<b>${a || b}</b>`).replace(/(^|[^*\w])\*([^*\n]+)\*/g, '$1<em>$2</em>').replace(/(^|\W)_([^_\n]+)_(?=\W|$)/g, '$1<em>$2</em>').replace(/~~([^~]+)~~/g, '<s>$1</s>')
      .replace(/\[([^\]]+)\]\(&lt;([^)]*?)&gt;\)|\[([^\]]+)\]\(([^)\s]*)[^)]*\)/g, (_, ta, ua, tb, ub) => { const t2 = ta || tb, u = ua ?? ub, url = un(u);
        if (/^https?:\/\//i.test(url)) return `<a class="lk" href="${u}" target="_blank" rel="noopener noreferrer">${t2}</a>`;
        const m = !/^[a-z][\w+.-]*:/i.test(url) && url.match(/^([^#?]*\.md)?(?:\?[^#]*)?(?:#(.*))?$/i);
        if (m && (m[1] || m[2])) { let p = m[1] || ''; try { p = decodeURIComponent(p); } catch {} return nlink(p ? resolve(p, ctx, true) : ctx ? ctx.i : -1, t2, m[2] || ''); }
        return `<span class="lk" title="${u}">${t2}</span>`; })
      .replace(/\u0001(\d+)\u0002/g, (_, k) => cs[k]); };
  const LI = /^(\s*)([-*+]|\d+[.)])\s+(.*)/, isList = l => LI.test(l), isRow = l => /^\s*\|.*\|\s*$/.test(l), FENCE = /^\s*(```|~~~)/;
  const item = t => { const m = t.match(/^\[([ xX])\]\s+(.*)/); return m ? `<li class="task${m[1] === ' ' ? '' : ' done'}"><span class="cb${m[1] === ' ' ? '' : ' on'}">${m[1] === ' ' ? '' : '✓'}</span><span class="tx">${inl(m[2])}</span>` : '<li>' + inl(t); };
  while (i < L.length) { const l = L[i];
    const f = l.match(/^\s*(```|~~~)\s*([\w+#.-]*)/); if (f) { const b = []; i++; while (i < L.length && !L[i].trim().startsWith(f[1])) b.push(L[i++]); i++; out.push(`<div class="code">${f[2] ? `<div class="code-h">${esc(f[2])}</div>` : ''}<pre>${esc(b.join('\n'))}</pre></div>`); continue; }
    const h = l.match(/^(#{1,6})\s+(.*?)\s*#*\s*$/); if (h) { out.push(`<h${h[1].length}>${inl(h[2])}</h${h[1].length}>`); i++; continue; }
    if (/^\s*(---+|\*\*\*+|___+)\s*$/.test(l)) { out.push('<hr>'); i++; continue; }
    if (/^\s*>/.test(l)) { const b = []; while (i < L.length && /^\s*>/.test(L[i])) b.push(L[i++].replace(/^\s*>\s?/, '')); const a = (b[0] || '').match(/^\[!(\w+)\][-+]?\s*(.*)/);
      if (a) { const k = a[1].toLowerCase(); out.push(`<div class="co ${k}"><div class="co-h">${esc(a[2] || a[1].toUpperCase())}</div><div>${mdRender(b.slice(1).join('\n'), false, ctx)}</div></div>`); }
      else out.push('<blockquote>' + mdRender(b.join('\n'), false, ctx) + '</blockquote>'); continue; }
    if (isRow(l) && /^\s*\|[\s:|-]+\|\s*$/.test(L[i + 1] || '')) { const rows = []; while (i < L.length && isRow(L[i])) rows.push(L[i++]); const cl = r => r.trim().replace(/^\||\|$/g, '').split(/(?<!\\)\|(?![^[]*\]\])/).map(c => c.trim().replace(/\\\|/g, '|'));
      const al = cl(rows[1]).map(c => /^:-+:$/.test(c) ? 'center' : /-+:$/.test(c) ? 'right' : ''), st = k => al[k] ? ` style="text-align:${al[k]}"` : '';
      out.push('<div class="tw"><table><thead><tr>' + cl(rows[0]).map((c, k) => `<th${st(k)}>${inl(c)}</th>`).join('') + '</tr></thead><tbody>' + rows.slice(2).map(r => '<tr>' + cl(r).map((c, k) => `<td${st(k)}>${inl(c)}</td>`).join('') + '</tr>').join('') + '</tbody></table></div>'); continue; }
    if (isList(l)) { const its = [];
      while (i < L.length) { const m = L[i].match(LI); if (m) { its.push({ ind: m[1].replace(/\t/g, '    ').length, ord: /\d/.test(m[2]), n: parseInt(m[2]), t: m[3] }); i++; }
        else if (its.length && L[i].trim() && /^\s{2,}/.test(L[i]) && !FENCE.test(L[i])) { its[its.length - 1].t += ' ' + L[i].trim(); i++; } else break; }
      let html = ''; const st = [];
      for (const it of its) { while (st.length > 1 && it.ind < st[st.length - 1].ind) html += '</li></' + st.pop().tag + '>';
        const tp = st[st.length - 1]; if (!tp || it.ind > tp.ind) { const tag = it.ord ? 'ol' : 'ul'; st.push({ ind: it.ind, tag }); html += it.ord && it.n !== 1 ? `<ol start="${it.n}">` : `<${tag}>`; } else html += '</li>';
        html += item(it.t); }
      while (st.length) html += '</li></' + st.pop().tag + '>'; out.push(html); continue; }
    if (!l.trim()) { i++; continue; }
    const b = [L[i++]]; while (i < L.length && L[i].trim() && !/^(#{1,6}\s|\s*```|\s*~~~|\s*>|\s*---)/.test(L[i]) && !isList(L[i]) && !isRow(L[i])) b.push(L[i++]); out.push('<p>' + inl(b.join(' ')) + '</p>'); }
  let fmh = ''; if (fm) { const kv = fm.split('\n').map(x => x.match(/^([\w .-]+):\s*(.*)$/)); fmh = kv.every(Boolean) ? `<div class="fm">${kv.map(m => `<i>${esc(m[1])}</i><span>${esc(m[2].replace(/^["']|["']$/g, ''))}</span>`).join('')}</div>` : `<pre class="fm">${esc(fm)}</pre>`; }
  return fmh + out.join(''); }
// notes that are not dots in the scene (notes newer than data.js; the memory store used to be one, since brief 23 its notes are dots) still open in the reader (brief 22): they are
// kept in LOOSE and numbered from LOOSE0 up, so the reader's history works the same; docOf(i) is the note for either kind
const LOOSE0 = 1e6, LOOSE = [], docOf = i => i >= LOOSE0 ? LOOSE[i - LOOSE0] : DOCS[i];
function loose(h) { let k = LOOSE.findIndex(d => d.id === h.id); if (k < 0) k = LOOSE.push({ id: h.id, c: h.c, p: h.p || '', t: h.t || (h.p || '').split('/').pop(), d: '' }) - 1; return LOOSE0 + k; }
let readerOpen = false, readerReq = 0, readerW = 0; S.baseOffX = 30; S.targetOffX = 30; let note = null, editing = false, dirty = false, asking = false;
const RD = id => document.getElementById(id), NARROW = 1700, STILL = location.hash.includes('still');
// narrow windows: while the reader is open the 04 lock panel steps aside (it comes back when the window is wide or the reader closes)
function layoutReader() { const r = RD('reader'), wide = readerOpen && W() < NARROW; document.body.classList.toggle('rdwide', wide);
  const B = RD('bottom').getBoundingClientRect(), Lx = 16 + leftW() + 14, right = wide ? W() - 16 : RD('right').getBoundingClientRect().left - 14, top = 50 + 8 * Z;
  readerW = clamp((right - Lx) * (wide ? .62 : .6), 460, 640 * Z); r.style.left = (right - readerW) + 'px'; r.style.width = readerW + 'px'; r.style.top = top + 'px'; r.style.height = Math.max(300, B.top - 14 - top) + 'px';
  S.targetOffX = readerOpen ? W() / 2 - (Lx + right - readerW) / 2 : S.baseOffX; }
function setPct() { const b = RD('rdb'), max = b.scrollHeight - b.clientHeight, p = max > 0 ? b.scrollTop / max : 1; RD('rdbar').style.width = (editing ? 0 : p * 100) + '%'; RD('rdpct').textContent = editing ? '' : Math.round(p * 100) + '% READ'; }
function hint() { const h = RD('rdhint'); if (editing) h.innerHTML = `<span class="dirty">${dirty ? '● UNSAVED CHANGES' : 'NO CHANGES YET'}</span><span>CTRL+S SAVE</span><span>ESC CANCEL</span>`;
  else h.innerHTML = `<span>ESC CLOSE</span><span>${note && !note.editable ? 'READ-ONLY' : 'E EDIT'}</span><span>CLICK A LINK TO JUMP</span><span>ALT ← → BACK / FORWARD</span>`; }
function showErr(t) { const e = RD('rderr'); e.textContent = t || ''; e.classList.toggle('on', !!t); }
// if the note's first heading is an H1 with the same words as its title (also after a status line, a quote or front matter), hide the repeat
function dropTitle(b, ts) { const h1 = b.querySelector(':scope>h1,:scope>h2,:scope>h3'), nt = x => x.toLowerCase().replace(/[^\p{L}\p{N}]+/gu, ''), a = h1 && nt(h1.textContent);
  if (h1 && h1.tagName === 'H1' && a && ts.some(t => { const n = t && nt(t); return n && (n === a || (Math.min(n.length, a.length) >= 12 && (n.startsWith(a) || a.startsWith(n)))); })) h1.remove(); }
// [[Note#Heading]]: scroll the heading to the top of the box and flash it
function jumpTo(box, h) { const n = nh(h), hs = [...box.querySelectorAll('h1,h2,h3,h4,h5,h6')], el = hs.find(x => nh(x.textContent) === n) || hs.find(x => n && nh(x.textContent).startsWith(n)); if (!el) return false;
  box.scrollTop += el.getBoundingClientRect().top - box.getBoundingClientRect().top - 10; el.classList.remove('hit'); void el.offsetWidth; el.classList.add('hit'); return true; }
// reader history (◂ ▸ buttons, Alt+← / Alt+→): every note opened in the reader, with where you were in it
let rdHist = [], rdPos = -1, rdScroll = [], navHist = false, pendH = ''; S.pendS = 0;
function updNav() { RD('rdback').disabled = rdPos <= 0; RD('rdfwd').disabled = rdPos >= rdHist.length - 1; }
function histGo(k) { const p = rdPos + k; if (p < 0 || p >= rdHist.length || !leaveEdit()) return; if (readerOpen) rdScroll[rdPos] = RD('rdb').scrollTop; navHist = true; pendH = ''; S.pendS = rdScroll[p] || 0; rdPos = p; rdHist[p] >= LOOSE0 ? openReader(rdHist[p]) : lock(rdHist[p]); }
function follow(i, h) { pvHide(); if (i === S.sel && readerOpen) { if (!h || !jumpTo(RD('rdb'), h)) RD('rdb').scrollTop = 0; return; } pendH = h || ''; S.pendS = 0; lock(i); }
function renderNote(quiet) { const b = RD('rdb'), j = note, d = docOf(j.i), w = (j.text.match(/\S+/g) || []).length;
  b.innerHTML = mdRender(j.text, true, { i: j.i >= LOOSE0 ? -1 : j.i, c: d.c, p: d.p }) + (j.truncated ? '<p class="k">… the note continues (cut here for display)</p>' : ''); dropTitle(b, [d.t, j.title]); b.style.opacity = ''; b.scrollTop = 0; [...b.children].forEach((e, k) => e.style.setProperty('--n', k));
  if (pendH) jumpTo(b, pendH); else if (S.pendS) b.scrollTop = S.pendS; pendH = ''; S.pendS = 0;
  RD('rds').textContent = j.path; RD('rdst').textContent = `${w.toLocaleString()} WORDS · ${Math.max(1, Math.round(w / 220))} MIN READ`; ringWords(j.i, w);
  RD('rdd').textContent = 'CHANGED ' + (j.source === 'file' && j.modified ? ago(j.modified.slice(0, 10)).toUpperCase() + ' · ' + j.modified.replace('T', ' ').slice(0, 16) : d.d ? ago(d.d).toUpperCase() + ' · ' + d.d : '');
  const s = RD('rdsrc'); s.textContent = j.source === 'file' ? 'LIVE FILE' : 'INDEX COPY · READ-ONLY'; s.classList.toggle('idx', j.source !== 'file'); s.title = j.why || '';
  RD('rdedit').disabled = !j.editable; RD('rdedit').title = j.editable ? 'edit this note (E)' : "can't edit: " + j.why; hint(); setPct(); }
function openReader(i) { const r = RD('reader'), d = docOf(i), req = ++readerReq, b = RD('rdb'); r.style.setProperty('--k', KC(d.c)); lockShow(null);
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
function leaveEdit() { if (!editing) return true; if (!dirty) { exitEdit(); return true; } askDiscard(); say('SAVE OR THROW AWAY YOUR CHANGES FIRST'); return false; }
function closeReader() { if (!leaveEdit()) return false; pvHide(); readerOpen = false; readerReq++; note = null; RD('reader').style.display = 'none'; layoutReader(); }
function startEdit() { if (!readerOpen) return; if (!note) return say('NOTE STILL LOADING'); if (!note.editable) return say("CAN'T EDIT THIS NOTE: " + (note.why || '').toUpperCase());
  pvHide(); const t = RD('rde'); editing = true; dirty = false; asking = false; t.value = note.text; RD('reader').classList.add('editing'); RD('rdmode').textContent = 'EDITING'; showErr(''); hint(); setPct(); t.focus(); t.setSelectionRange(0, 0); t.scrollTop = 0; }
function exitEdit() { editing = dirty = asking = false; RD('reader').classList.remove('editing'); RD('rdask').classList.remove('on'); RD('rdmode').textContent = 'NOTE OPEN'; showErr(''); hint(); setPct(); }
function askDiscard() { asking = true; RD('rdask').classList.add('on'); RD('rdkeep').focus(); }
function keepEditing() { asking = false; RD('rdask').classList.remove('on'); RD('rde').focus(); }
function cancelEdit() { if (dirty) askDiscard(); else exitEdit(); }
function saveEdit() { if (!editing) return; if (!dirty) { exitEdit(); return say('NO CHANGES TO SAVE'); } const t = RD('rde'), sv = RD('rdsave'), text = t.value, n = note; sv.disabled = true; showErr('');
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
// ---- 🔒 this computer only (brief 22): memory notes only. GET /private reads the note's tag; the toggle asks the server to run
// `brain private <note> on|off`, which changes the note (the Deck never edits it); then the note is read again. Turning it off asks first.
let lockSt = null; const BYW = { owner: 'you', filter: 'the names filter' };
function lockShow(st) { lockSt = st; const on = !!(st && st.local_only), who = st && st.by ? (st.local_only ? 'locked' : 'turned off') + ' by ' + (BYW[st.by] || st.by) + (st.at ? ' on ' + st.at : '') : '';
  RD('reader').classList.toggle('mem', !!st); RD('rdlock').classList.toggle('on', on); RD('rdlockv').textContent = on ? 'ON' : 'OFF'; RD('rdlock').disabled = false;
  RD('rdlock').title = (on ? 'This computer only: online writers never get this note. Click to turn it off.' : 'Click to keep this note on this computer only: online writers will never get it.') + (who ? '\n' + who.replace(/^./, c => c.toUpperCase()) + '.' : '');
  const b = RD('rdlockb'); b.classList.toggle('on', on); b.textContent = on ? '🔒 THIS COMPUTER ONLY' + (st.by ? ' · BY ' + (BYW[st.by] || st.by).toUpperCase() : '') + (st.at ? ' · ' + st.at : '') : ''; b.title = who;
  if (!st) { lockAsk(false); lockMsg(''); } }
function lockMsg(t, cls = '') { const m = RD('rdlockmsg'); m.textContent = t; m.className = 'rd-note' + (t ? ' on ' + cls : ''); }
function lockAsk(on) { RD('rdlockask').classList.toggle('on', on); if (on) { lockMsg(''); RD('rdlockkeep').focus(); } }
function lockLoad(n) { if (n.collection !== 'memory') return lockShow(null);
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
// ---- hover preview (like Obsidian's page preview): rest on a note link ~300 ms, a small card shows the start of that note
// the same card shows for a note dot in the scene (pvDot, placed beside the dot at pvXY): path, start of the note and its closest notes
let pvT = 0, pvHideT = 0, pvLink = null, pvI = -1, pvH = '', pvTop = 0; S.testGone = false; let pvDot = -1, pvXY = null, pvOver = false; const pvCache = new Map(), PV = RD('pv');
const pvGet = id => { if (!pvCache.has(id)) pvCache.set(id, fetch('/note?id=' + id, { cache: 'no-store' }).then(x => { if (!x.ok) throw x.status; return x.json(); }).catch(e => { pvCache.delete(id); throw e; })); return pvCache.get(id); };
function pvPlace() { const w = PV.offsetWidth, h = PV.offsetHeight, m = 8;
  if (pvXY) { const [x, y] = pvXY, g = 18; PV.style.left = (x + g + w <= W() - m ? x + g : Math.max(m, x - g - w)) + 'px'; PV.style.top = clamp(y - 30, m, H() - h - m) + 'px'; return; }   // beside the dot, so the way onto the card is short
  if (!pvLink) return; const r = pvLink.getBoundingClientRect();
  let top = r.bottom + m; if (top + h > H() - m) top = r.top - m - h >= m ? r.top - m - h : H() - m - h;
  PV.style.left = clamp(r.left - 12, m, W() - w - m) + 'px'; PV.style.top = Math.max(m, top) + 'px'; }
function pvShow(a, xy) { const i = a ? +a.dataset.i : xy.i, d = DOCS[i]; if (!d) return; clearTimeout(pvHideT); if (pvLink) pvLink.classList.remove('on'); pvLink = a || null; if (a) a.classList.add('on'); pvI = i; pvH = a && a.dataset.h || ''; pvTop = RD('rdb').scrollTop;
  pvDot = a ? -1 : i; pvXY = a ? null : [xy.x, xy.y]; PV.classList.toggle('dot', !a); const cap = a ? 12000 : 1500, ns = d.ns || d.nb.map(() => .5);
  RD('pvp').textContent = d.c + '/' + d.p; RD('pvn').innerHTML = a ? '' : '<b>CLOSEST IN MEANING</b>' + d.nb.slice(0, 3).map((j, n) => `<a data-i="${j}" style="--k:${KC(DOCS[j].c)}"><span>${esc(DOCS[j].t)}</span><em>${Math.round(ns[n] * 100)}%</em></a>`).join('');
  PV.style.setProperty('--k', KC(d.c)); RD('pvg').textContent = NICE[d.c].toUpperCase(); RD('pvd').textContent = ago(d.d).toUpperCase() + ' · ' + d.d; RD('pvt').textContent = d.t;
  const pb = RD('pvb'); pb.innerHTML = '<div class="load">LOADING <span class="cur"></span></div>'; pb.scrollTop = 0; PV.classList.add('on'); pvPlace();
  pvGet(d.id).then(j => { if (pvI !== i) return; const long = j.text.length > cap; pb.innerHTML = mdRender(j.text.slice(0, cap), true, { i, c: d.c, p: d.p }) + (long || j.truncated ? '<p class="k">… click to read the whole note</p>' : ''); dropTitle(pb, [d.t, j.title]); if (pvH) jumpTo(pb, pvH); pvPlace(); })
    .catch(() => { if (pvI === i) pb.innerHTML = '<p class="am">Could not read this note.</p>'; }); }
function pvHide() { clearTimeout(pvT); clearTimeout(pvHideT); PV.classList.remove('on'); if (pvLink) pvLink.classList.remove('on'); pvLink = null; pvI = -1; pvDot = -1; pvXY = null; }
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
S.leadT = 1; let lockAt = 0;
function lock(i) {
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
let hits = null;
const tl = makeTimeline(RD('tlp'), { ages: DOCS.map(age), NOW, count: d => DOCS.filter((x, i) => age(x) >= d && visible(i)).length, onChange: c => { S.cutoff = c; refresh(); } });
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
const leftW = () => 272 * Z;   // the left column's space stays reserved, so nothing else moves when it is hidden
function applyLeft(anim) { const ps = [document.getElementById('viewp'), document.getElementById('sections'), document.getElementById('voicep')], t = document.getElementById('secTab'), L = document.getElementById('left');
  if (leftAway) { ps.forEach(p => p.classList.add('away')); setTimeout(() => { if (leftAway) { ps.forEach(p => p.style.display = 'none'); L.classList.add('hidden'); } }, anim ? 270 : 0); t.style.display = 'block'; }
  else { L.classList.remove('hidden'); ps.forEach(p => { p.style.display = ''; void p.offsetWidth; p.classList.remove('away'); }); t.style.display = 'none'; }
  if (anim) { applyZ(false); S.dT = viewDist(view); S.autoCam = true; } }
function toggleLeft() { leftAway = !leftAway; localStorage.setItem('deckLeftAway', leftAway ? '1' : '0'); applyLeft(true); say(leftAway ? 'PANELS HIDDEN  ·  PRESS T TO SHOW' : 'PANELS SHOWN'); }
document.getElementById('secHide').onclick = toggleLeft; document.getElementById('viewHide').onclick = toggleLeft; document.getElementById('voiceHide').onclick = toggleLeft; document.getElementById('secTab').onclick = toggleLeft;
// panel size: + / - keys
const zh = location.hash.match(/z=([\d.]+)/); let userM = +(localStorage.getItem('deckM') || 1);
function pickZ() { let z = clamp((.6 + W() / 2560) * userM, .9, 1.8); while (W() - (32 + 604 * z + 28) < 600 && z > .9) z -= .05; return Math.round(z * 100) / 100; }
let Z = zh ? +zh[1] : pickZ();
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
