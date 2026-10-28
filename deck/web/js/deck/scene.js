import { chrome, boot, days, THREE, makeCloud, lineMat } from '../../hud.js';
import { DOT_GLSL, makeShell } from '../../shell.js';
import { makeSkins } from '../../skins.js';
import { Z, labelCur, leftW } from '../deck-main.js';
export const KC = c => `var(--g-${c},var(--dim2))`;   // a note group's colour in the page (skin token); the scene takes its colours from the skin theme (paint)
chrome('DECK · MAP ⇄ TUNNEL ⇄ RADAR', 0);
boot(['> SECOND BRAIN // DECK', '> reading index ............ ok', `> ${DOCS.length} notes in ${COLS.length} sections`, '> laying out three views ..... ok', '> tunnel transition armed', '> ready']);
export const W = () => innerWidth, H = () => innerHeight, N = DOCS.length, SPAN = Math.PI * 2 / COLS.length, HT = 4.6, TAU = Math.PI * 2;
export const secIdx = Object.fromEntries(COLS.map((c, k) => [c, k])), th0 = k => -Math.PI / 2 + k * SPAN, thM = k => th0(k) + SPAN / 2;
export const age = d => Math.min(days(d.d), 38), ageR = d => Math.min(days(d.d), 60), yOf = a => (1 - a / 38) * HT - HT / 2;
const radRad = a => a <= 0 ? .05 : Math.min(.96, .07 + .89 * Math.sqrt(a / 60));
export const clamp = (v, a = 0, b = 1) => Math.max(a, Math.min(b, v)), ease = t => t < .5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
function rankNorm(sel) { const o = new Float32Array(N); for (const c of COLS) { const idx = []; DOCS.forEach((d, i) => { if (d.c === c) idx.push(i); }); idx.sort((a, b) => sel(a) - sel(b)); idx.forEach((i, r) => o[i] = (r + .5) / idx.length); } return o; }
const r0 = rankNorm(i => DOCS[i].uv[0]), r1 = rankNorm(i => DOCS[i].uv[1]);
// ---- three layouts
export const Lmap = new Float32Array(N * 3), Ltun = new Float32Array(N * 3), Lrad = new Float32Array(N * 3), cen = {};
for (const c of COLS) { const a = [0, 0, 0]; let n = 0; DOCS.forEach(d => { if (d.c === c) { a[0] += d.xyz[0]; a[1] += d.xyz[1]; a[2] += d.xyz[2]; n++; } }); cen[c] = a.map(v => v / n * 2.1); }
const ringC = {}; COLS.forEach((c, k) => { const o = cen[c]; ringC[c] = [Math.cos(thM(k)) * 3.4 * .78 + o[0] * .22, o[1] * .7, Math.sin(thM(k)) * 3.4 * .78 + o[2] * .22]; });
DOCS.forEach((d, i) => { const k = secIdx[d.c], c = cen[d.c], rc = ringC[d.c], p = d.xyz.map(v => v * 2.1);
  Lmap.set([rc[0] + (p[0] - c[0]) * .4, rc[1] + (p[1] - c[1]) * .4, rc[2] + (p[2] - c[2]) * .4], i * 3);
  const th = th0(k) + SPAN * (.07 + .86 * r0[i]), rt = 1.0 + 2.0 * r1[i]; Ltun.set([Math.cos(th) * rt, yOf(age(d)), Math.sin(th) * rt], i * 3);
  const rr = 3.15 * radRad(ageR(d)) + (r1[i] - .5) * .1; Lrad.set([Math.cos(th) * rr, (r1[i] - .5) * .1, Math.sin(th) * rr], i * 3); });
export const LAY = { map: Lmap, tunnel: Ltun, radar: Lrad };
export const VIEW = { map: { pitch: .2, dist: 10.4, desc: 'Notes grouped by what they are about. Each section floats as its own island; notes close together are close in meaning.' },
  tunnel: { pitch: .42, dist: 13.4, desc: 'Height is time. Today is the top ring, older notes sink. Each wedge of the tower is one section.' },
  radar: { pitch: 1.1, dist: 14.6, desc: 'Looking down from above. The centre changed today, the rim is weeks old. Each slice is one section.' } };
// ---- scene
export const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true }); renderer.setPixelRatio(Math.min(2, devicePixelRatio)); renderer.setSize(W(), H()); document.getElementById('stage').append(renderer.domElement);
export const S = {};   // the state several parts of the page write (move 3 of the split: one shared object)
export const scene = new THREE.Scene(), camera = new THREE.PerspectiveCamera(42, W() / H(), .1, 100); S.offX = 30; S.offY = 52; export const fitView = () => camera.setViewOffset(W(), H(), S.offX, S.offY, W(), H()); fitView(); export const root = new THREE.Group(); scene.add(root);
export const cloud = makeCloud(d => d.xyz, 1); cloud.P.set(Lmap); cloud.g.attributes.position.needsUpdate = true; root.add(cloud.pts); export const cur = cloud.P;
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
export const shell = makeShell(FITS); root.add(shell.obj); shell.dots(cloud.m.uniforms);
// ---- structure drawings (each view has its own set; they fade in and out)
export const sets = { map: new THREE.Group(), tunnel: new THREE.Group(), radar: new THREE.Group() }, mats = []; Object.values(sets).forEach(g => root.add(g));
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
export const sweepG = new THREE.Group(); sets.radar.add(sweepG); const swl = new THREE.Line(new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(0, 0, 0), new THREE.Vector3(3.3, 0, 0)]), lineMat(0xffffff, .95)); swl.material.userData = { op: .95, view: 'radar', role: 'sweep' }; mats.push(swl.material); sweepG.add(swl);
const wedge = new THREE.Mesh(new THREE.CircleGeometry(3.3, 40, 0, .9).rotateX(-Math.PI / 2), new THREE.MeshBasicMaterial({ transparent: true, opacity: .09, blending: THREE.AdditiveBlending, depthWrite: false, side: THREE.DoubleSide })); wedge.material.userData = { op: .09, view: 'radar', role: 'sweep' }; mats.push(wedge.material); sweepG.add(wedge);
// date slice (amber) + transition scanner ring
export const slice = new THREE.Line(new THREE.BufferGeometry().setFromPoints(circ(3.3, 0)), lineMat(0xffffff, .95)); slice.material.userData = { op: .95, view: 'tunnel', role: 'slice' }; mats.push(slice.material); sets.tunnel.add(slice);
export const scanner = new THREE.Line(new THREE.BufferGeometry().setFromPoints(circ(3.7, 0)), lineMat(0xffffff, 0)); root.add(scanner);
export const nbLines = new THREE.LineSegments(new THREE.BufferGeometry().setAttribute('position', new THREE.BufferAttribute(new Float32Array(12 * 3), 3)), lineMat(0xffffff, .45)); nbLines.frustumCulled = false; root.add(nbLines);
// ---- skins: paint the scene with the skin's theme (dot colours per group, lines by role, the shell, add or normal blending); runs while a switch fades
export const skins = makeSkins(COLS), dotC = cloud.g.attributes.color.array, gIdx = DOCS.map(d => d.c);
export function paint(T) { const B = T.blend === 'normal' ? THREE.NormalBlending : THREE.AdditiveBlending, setB = m => { if (m.blending !== B) { m.blending = B; m.needsUpdate = true; } };
  for (let i = 0; i < N; i++) { const c = T.g[gIdx[i]]; dotC[i * 3] = c.r; dotC[i * 3 + 1] = c.g; dotC[i * 3 + 2] = c.b; } cloud.g.attributes.color.needsUpdate = true;
  for (const m of mats) { m.color.copy(m.userData.sec ? T.g[m.userData.sec] : T[m.userData.role]); setB(m); }
  scanner.material.color.copy(T.scan); nbLines.material.color.copy(T.nb); [scanner.material, nbLines.material, cloud.m].forEach(setB);
  cloud.m.uniforms.uCore.value = T.core; cloud.m.uniforms.uDot.value = T.dot; cloud.m.uniforms.uSize.value = T.size; shell.theme(T); }
paint(skins.tick(performance.now()));
// ---- state
S.hold = false; export let view = 'map'; S.prog = 1; S.from = new Float32Array(Lmap); export let to = Lmap, delay = new Float32Array(N); S.yaw = .4; S.pitch = VIEW.map.pitch; S.dist = VIEW.map.dist; S.pT = S.pitch; S.dT = S.dist; S.autoCam = true; S.ty = null;
export let scanFrom = yOf(38), scanOp0 = 0; S.lookY = 0; S.voiceLv = 0; export let camFrom = null;
S.overRd = false; S.drag = null; S.moved = 0; S.mx = 0; S.my = 0; S.sel = -1; S.hov = -1; export let q = '', hidden = new Set(); S.focus = null; S.hoverG = null; S.cutoff = 0; let playing = false; S.beamT = 0;
export const vis = { map: 1, tunnel: 0, radar: 0 };
const toast = document.getElementById('toast'); let toastT;
export function say(t) { toast.textContent = t; toast.classList.add('on'); clearTimeout(toastT); toastT = setTimeout(() => toast.classList.remove('on'), 2400); }
export function viewDist(v) { const B = document.getElementById('bottom').getBoundingClientRect(), fw = W() - (32 + leftW() + 332 * Z + 28), fh = H() - 62 - B.height - 14, sc = clamp(Math.min(fw / 1480, fh / 920), .55, 1.5); return VIEW[v].dist / sc; }
export function go(v) {
  if (v === view) return; view = v; shell.go(v); scanFrom = S.prog < 1 ? scanner.position.y : yOf(38); scanOp0 = S.prog < 1 ? scanner.material.opacity / .95 : 0;   // mid-flight: the ring and shell carry on from where they are
  S.from = new Float32Array(cur); to = LAY[v]; S.prog = 0; camFrom = [S.pitch, S.dist, S.lookY]; S.autoCam = true; S.pT = VIEW[v].pitch; S.dT = viewDist(v); S.ty = null;
  const up = v === 'tunnel'; DOCS.forEach((d, i) => delay[i] = (up ? 1 - age(d) / 38 : age(d) / 38) * .4);
  document.querySelectorAll('.tab').forEach(b => b.classList.toggle('on', b.dataset.v === v)); document.getElementById('vdesc').textContent = VIEW[v].desc;
  say('REALIGNING  ›  ' + v.toUpperCase() + ' VIEW'); S.labelFrom = labelCur.map(a => a.clone());
}
document.querySelectorAll('.tab').forEach(b => b.onclick = () => go(b.dataset.v));
document.getElementById('vdesc').textContent = VIEW.map.desc; skins.wire(document.getElementById('skins'));
