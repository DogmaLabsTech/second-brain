// The brain's shell: the talking presence of the Deck (it replaced the hologram head). A see-through net of thin glowing
// lines and points that wraps all the notes of the current view: a globe around the Map's islands, a tall tube around the
// Tunnel's timeline, a low dome over the Radar's disc. Every point of the net has a (u, v) place (u around, v bottom to top);
// the vertex shader builds all three shapes from it and mixes them by three weights, so a view switch is one eased number
// per frame (no CPU loop over vertices) and a switch mid-flight starts from the shape on screen, so nothing pops.
// Additive, no depth writes, rim-lit (the middle stays faint), so it never hides the dots or labels; it is never picked.
// States: idle (slow breathing), listening (brighter, follows the mic, ripples run in toward the centre), thinking (amber scan
// sweeps up through it, the dots shimmer), speaking (ripples run out over the shell and through the dots with the voice),
// error (a brief red flicker). Colours and blending come from the skin through theme(T). The deck calls go(view) when a switch starts, frame(t, e, scanY, scanOn) every frame with
// e = the switch's eased progress (the scanner ring's), level(0..1, gap) and set(state). dots(uniforms) drives the note cloud.
// Calm motion: the voice goes through an envelope (rises in ~80 ms, falls in ~400 ms, two stages so it has no corners, in real
// time so the frame rate doesn't matter); between the brain's sentences (gap) it is held and eases down instead of dropping to
// zero; a short wait for the rest of the answer stays 'speaking'; the states crossfade on springs (ease in and out, ~0.5 s).
import { THREE } from './hud.js';
const SHAPE = `uniform vec3 uW, uC0, uC1, uC2; uniform vec2 uR0, uR1, uR2;
vec3 shapeN; float shapeQ;   // the normal and the ripple coordinate (0 = the shape's centre line, 1 = its ends)
vec3 shape(vec2 uv) { float th = uv.x * 6.2831853; vec2 cs = vec2(cos(th), sin(th));
  float ph = uv.y * 3.1415927, sp = sin(ph);                        // globe: bottom pole to top pole
  vec3 s = uC0 + vec3(cs.x * sp * uR0.x, -cos(ph) * uR0.y, cs.y * sp * uR0.x), ns = normalize(vec3(cs.x * sp / uR0.x, -cos(ph) / uR0.y, cs.y * sp / uR0.x) + 1e-5);
  float tv = uv.y * 2. - 1., lip = 1. - .14 * pow(abs(tv), 12.);   // tube: the ends turn in a little
  vec3 t = uC1 + vec3(cs.x * uR1.x * lip, tv * uR1.y, cs.y * uR1.x * lip), nt = vec3(cs.x, 0., cs.y);
  float a = uv.y * 1.5707963, ca = cos(a);                            // dome: rim (v 0) to the top (v 1)
  vec3 d = uC2 + vec3(cs.x * ca * uR2.x, sin(a) * uR2.y, cs.y * ca * uR2.x), nd = normalize(vec3(cs.x * ca / uR2.x, sin(a) / uR2.y, cs.y * ca / uR2.x));
  shapeN = normalize(ns * uW.x + nt * uW.y + nd * uW.z + 1e-5); shapeQ = abs(tv) * (uW.x + uW.y) + (1. - uv.y) * uW.z;
  return s * uW.x + t * uW.y + d * uW.z; }
float converge(float v) { return uW.x * sin(v * 3.1415927) + uW.y + uW.z * cos(v * 1.5707963); }`;   // where meridians bunch up (poles, dome top)
const RIP = `uniform float uRipA, uRipP, uRipB, uRipQ, uRipK;   // two trains of rings: out (speaking, A at phase P) and in (listening, B at Q)
float ripple(float q) { return pow(.5 + .5 * cos((q * uRipK - uRipP) * 6.2831853), 5.) * uRipA + pow(.5 + .5 * cos((q * uRipK - uRipQ) * 6.2831853), 5.) * uRipB; }`;
// live searches: a soft ring runs out over the shell from the spot nearest a searched note (spot(x, y, z)); w = its age in s, < 0 = off
const SPOT = `uniform vec4 uSpot[6];
float spots(vec3 p) { float o = 0.; for (int i = 0; i < 6; i++) { vec4 s = uSpot[i]; if (s.w < 0.) continue; float d = length(p - s.xyz) - s.w * 1.1;
  o += exp(-d * d / .05) * exp(-s.w * 1.3) * smoothstep(0., .2, s.w); } return o; }`;
const VS = `attribute vec2 aUV; attribute float aMer; uniform float uBreath, uPt; ${SHAPE} ${RIP} ${SPOT}
varying float vB, vV, vY, vQ, vM, vBack, vSp;
void main() { vec3 p = shape(aUV); float rip = ripple(shapeQ); vQ = shapeQ; vSp = spots(p);
  p += shapeN * (uBreath + rip * .07 + vSp * .04); vec4 wp = modelMatrix * vec4(p, 1.);
  vec3 n = normalize(mat3(modelMatrix) * shapeN), vd = normalize(cameraPosition - wp.xyz); float f = dot(n, vd);
  vB = pow(1. - abs(f), 2.2); vBack = step(f, 0.); vV = aUV.y; vY = p.y;
  vM = aMer > .5 ? smoothstep(.04, .3, converge(aUV.y)) : 1.; vB *= vM;
  gl_Position = projectionMatrix * viewMatrix * wp; gl_PointSize = uPt * (1. + rip * vM * .8); }`;
const FS = `uniform vec3 uCol, uHot; uniform float uGlow, uScanV, uScanVA, uScanY, uScanYA, uPts, uNorm; varying float vB, vV, vY, vQ, vM, vBack, vSp; ${RIP}
void main() { if (uPts > .5 && length(gl_PointCoord - .5) > .5) discard; float vRip = ripple(vQ) * vM;   // per pixel: the bands glide along a line instead of stepping from point to point
  float scan = exp(-pow((vV - uScanV) / .06, 2.)) * uScanVA * 1.6 + exp(-pow((vY - uScanY) / .16, 2.)) * uScanYA;
  float b = uGlow * (.24 + .76 * vB) * mix(1., .45, vBack);
  vec3 h = uHot * (scan * (.35 + .5 * vB) + vRip * (.3 + .7 * vB) + min(vSp, 1.2) * (.45 + .55 * vB) * .8) * uGlow;
  if (uNorm > .5) { float hm = max(max(uHot.r, uHot.g), max(uHot.b, .05)), hl = clamp(max(max(h.r, h.g), h.b) / hm, 0., 1.), al = clamp(b * 1.15 + hl * .8, 0., 1.);   // light skins: ink lines with real alpha
    gl_FragColor = vec4(mix(uCol, uHot, clamp(hl / max(al, .01), 0., 1.)), al); }
  else gl_FragColor = vec4(uCol * b + h, 1.); }`;
// the notes: a ring of light running out from (speaking) or in to (listening) the shell's centre, and a shimmer while thinking
export const DOT_GLSL = `uniform vec3 uVC; uniform vec2 uVR; uniform float uVA, uVP, uShim, uVT;
float voiceGlow(vec3 p) { float q = length(vec2(length((p - uVC).xz) / uVR.x, (p.y - uVC.y) / uVR.y)), w = pow(.5 + .5 * cos((q * 2.2 - uVP) * 6.2831853), 8.) * uVA;
  float h = fract(sin(dot(p, vec3(12.9898, 78.233, 37.719))) * 43758.5453); return w + uShim * (.5 + .5 * sin(uVT * 4.5 + h * 60.)) * .7 - uShim * .25; }`;
export function makeShell(fits) {
  // the net: 15 rings (latitude / height) + 36 meridians, as segments, plus 1,400 loose points (golden-angle spread)
  const uv = [], mer = [], RINGS = 15, MER = 36, SEG = 144, MSEG = 72, seg = (a, b, m) => { uv.push(...a, ...b); mer.push(m, m); };
  for (let r = 1; r <= RINGS; r++) { const v = r / (RINGS + 1); for (let k = 0; k < SEG; k++) seg([k / SEG, v], [(k + 1) / SEG, v], 0); }
  for (let m = 0; m < MER; m++) for (let k = 0; k < MSEG; k++) seg([m / MER, k / MSEG], [m / MER, (k + 1) / MSEG], 1);
  const net = new THREE.BufferGeometry(); net.setAttribute('aUV', new THREE.Float32BufferAttribute(uv, 2)); net.setAttribute('aMer', new THREE.Float32BufferAttribute(mer, 1));
  net.setAttribute('position', new THREE.Float32BufferAttribute(new Float32Array(mer.length * 3), 3));
  const NP = 1400, puv = new Float32Array(NP * 2); for (let i = 0; i < NP; i++) { puv[i * 2] = (i * .6180339887) % 1; puv[i * 2 + 1] = .5 - .5 * Math.cos(Math.acos(1 - 2 * (i + .5) / NP)); }
  const dots = new THREE.BufferGeometry(); dots.setAttribute('aUV', new THREE.BufferAttribute(puv, 2)); dots.setAttribute('aMer', new THREE.BufferAttribute(new Float32Array(NP).fill(1), 1)); dots.setAttribute('position', new THREE.BufferAttribute(new Float32Array(NP * 3), 3));
  const V = n => new THREE.Vector3(...n), U = { uW: { value: new THREE.Vector3(1, 0, 0) }, uC0: { value: V(fits.map.c) }, uC1: { value: V(fits.tunnel.c) }, uC2: { value: V(fits.radar.c) },
    uR0: { value: new THREE.Vector2(...fits.map.r) }, uR1: { value: new THREE.Vector2(...fits.tunnel.r) }, uR2: { value: new THREE.Vector2(...fits.radar.r) },
    uBreath: { value: 0 }, uRipA: { value: 0 }, uRipP: { value: 0 }, uRipB: { value: 0 }, uRipQ: { value: 0 }, uRipK: { value: 3 }, uGlow: { value: .5 }, uCol: { value: new THREE.Color() }, uHot: { value: new THREE.Color() }, uNorm: { value: 0 },
    uScanV: { value: -9 }, uScanVA: { value: 0 }, uScanY: { value: -99 }, uScanYA: { value: 0 }, uSpot: { value: Array.from({ length: 6 }, () => new THREE.Vector4(0, 0, 0, -1)) } };
  const mat = (pts, op) => new THREE.ShaderMaterial({ uniforms: { ...U, uPts: { value: pts }, uPt: { value: pts ? 2.2 * Math.min(2, devicePixelRatio) : 1 }, uGlow: { value: op } }, vertexShader: VS, fragmentShader: FS, transparent: true, depthWrite: false, depthTest: false, blending: THREE.AdditiveBlending });
  const lines = new THREE.LineSegments(net, mat(0, .5)), points = new THREE.Points(dots, mat(1, .5)), obj = new THREE.Group(); lines.frustumCulled = points.frustumCulled = false; obj.add(lines, points);
  lines.renderOrder = points.renderOrder = -1; obj.raycast = lines.raycast = points.raycast = () => {};   // drawn under the dots, never picked
  const ONE = { map: [1, 0, 0], tunnel: [0, 1, 0], radar: [0, 0, 1] }, wFrom = new THREE.Vector3(1, 0, 0), wTo = new THREE.Vector3(1, 0, 0), W = U.uW.value;
  // the state colours come from the skin (theme(), see skins.js): idle, listening, speaking, the thinking tint, the hot ripple/scan colour, error
  const STATES = ['idle', 'listening', 'thinking', 'speaking', 'error'], amber = new THREE.Color(), white = new THREE.Color(), red = new THREE.Color(), cIdle = new THREE.Color(), cListen = new THREE.Color(), cSpeak = new THREE.Color();
  const col = new THREE.Color(), hot = new THREE.Color(), C = new THREE.Vector3(), R = new THREE.Vector2(), CS = [U.uC0, U.uC1, U.uC2], RS = [U.uR0, U.uR1, U.uR2];
  // follow(): one stage of the voice envelope (time constants in seconds); spring(): a critically damped spring, eases in and out, settles in ~0.5 s
  const follow = (x, to, dt, up, down) => x + (to - x) * (1 - Math.exp(-dt / (to > x ? up : down))), spring = (s, to, dt) => { s.v += (81 * (to - s.x) - 18 * s.v) * dt; s.x += s.v * dt; return Math.max(0, Math.min(1, s.x)); };
  const think = { x: 0, v: 0 }, listen = { x: 0, v: 0 }, talkA = { x: 0, v: 0 }, errS = { x: 0, v: 0 };
  const spotAt = [-1, -1, -1, -1, -1, -1]; let spotN = 0;
  let gain = 1, state = 'idle', next = null, nextAt = -1, lv = 0, gap = false, lvT = 0, env1 = 0, env = 0, last = 0, glow = .5, ripP = 0, ripQ = 0, scanV = 0, errAt = -1e9, dotP = 0, th = 0, li = 0, ta = 0;
  function frame(t, e, scanY, scanOn) {
    const dt = Math.min(.05, last ? (t - last) / 1000 : .016), s = t / 1000; last = t;
    if (next && nextAt < 0) nextAt = t + 900; if (next && t >= nextAt) { state = next; next = null; }   // the wait for the rest of the answer, if it lasts
    W.copy(wFrom).lerp(wTo, e);   // the shape on screen (also where a new switch starts from)
    const voice = state === 'listening' || state === 'speaking';   // the envelope's target: the level, or held and easing down over a gap
    lvT = !voice ? 0 : (gap || next) && state === 'speaking' ? lvT + (.2 - lvT) * (1 - Math.exp(-dt / .9)) : lv;
    env1 = follow(env1, lvT, dt, .025, .12); env = follow(env, env1, dt, .025, .12);
    th = spring(think, state === 'thinking' ? 1 : 0, dt); li = spring(listen, state === 'listening' ? 1 : 0, dt); ta = spring(talkA, state === 'speaking' ? 1 : 0, dt); const er = spring(errS, state === 'error' ? 1 : 0, dt);
    const breathe = .5 + .5 * Math.sin(s * 1.1), err = Math.max(0, 1 - (t - errAt) / 900);
    const gT = .42 + .1 * breathe + li * (.3 + .5 * env) + th * (.25 + .08 * Math.sin(s * 5)) + ta * (.12 + .45 * env);
    glow = follow(glow, gT, dt, .12, .2);
    ripP += dt * ta * (.4 + .6 * env); ripQ -= dt * li * (.35 + .5 * env); scanV = (scanV + dt * .55 * Math.max(th, .001)) % 1.15;   // the rings' speed only leans on the voice; their strength follows it
    col.copy(cIdle).lerp(cListen, li).lerp(cSpeak, ta).lerp(amber, th * .55).lerp(red, er);
    if (err > 0) col.copy(cIdle).lerp(red, err * (Math.sin(s * 47) > -.2 ? 1 : .25));   // the flicker
    hot.copy(white).lerp(amber, th * .9);
    C.set(0, 0, 0); R.set(0, 0); for (let i = 0; i < 3; i++) { const w = i ? i > 1 ? W.z : W.y : W.x; C.addScaledVector(CS[i].value, w); R.addScaledVector(RS[i].value, w); }
    for (const m of [lines.material, points.material]) { const u = m.uniforms; u.uW.value = W; u.uCol.value.copy(col); u.uHot.value.copy(hot); u.uBreath.value = R.x * (.006 * Math.sin(s * 1.1) + .012 * env * (li + ta));
      u.uRipA.value = ta * (.15 + 1.05 * env); u.uRipP.value = ripP; u.uRipB.value = li * (.3 + .8 * env); u.uRipQ.value = ripQ; u.uScanV.value = scanV - .05; u.uScanVA.value = th; u.uScanY.value = scanY; u.uScanYA.value = scanOn; }
    for (let i = 0; i < 6; i++) { const w = spotAt[i] < 0 ? -1 : (t - spotAt[i]) / 1000; U.uSpot.value[i].w = w > 2.6 ? -1 : w; if (w > 2.6) spotAt[i] = -1; }
    lines.material.uniforms.uGlow.value = glow * gain * (1 + err); points.material.uniforms.uGlow.value = glow * gain * 1.3 * (1 + err);
    dotP += dt * (ta * (.35 + .7 * env) - li * (.3 + .45 * env)); dotU.uVA.value = 0; dotU.uVP.value = dotP; dotU.uShim.value = 0;   // calm: no voice wave or shimmer over all the notes; only searched notes light up (live.js) dotU.uVT.value = s; dotU.uVC.value.copy(C); dotU.uVR.value.copy(R);
  }
  const dotU = { uVC: { value: new THREE.Vector3() }, uVR: { value: new THREE.Vector2(1, 1) }, uVA: { value: 0 }, uVP: { value: 0 }, uShim: { value: 0 }, uVT: { value: 0 } };
  // theme(T): the skin's scene theme (skins.js): state colours, glow strength, and add (glow on dark) or normal (ink on light) blending
  function theme(T) { cIdle.copy(T.shell); cListen.copy(T.listen); cSpeak.copy(T.speak); amber.copy(T.think); white.copy(T.hot); red.copy(T.err); gain = T.shellGlow; U.uNorm.value = T.blend === 'normal' ? 1 : 0;
    for (const m of [lines.material, points.material]) { const b = T.blend === 'normal' ? THREE.NormalBlending : THREE.AdditiveBlending; if (m.blending !== b) { m.blending = b; m.needsUpdate = true; } } }
  return { obj, frame, theme, dots: u => Object.assign(u, dotU),
    go(v) { wFrom.copy(W); wTo.set(...ONE[v]); },   // start from the shape on screen, even mid-flight
    snap() { const on = x => state === x ? 1 : 0; [[think, 'thinking'], [listen, 'listening'], [talkA, 'speaking'], [errS, 'error']].forEach(([w, x]) => { w.x = on(x); w.v = 0; }); lvT = env1 = env = lv; glow = .42 + on('listening') * .6 + on('thinking') * .25 + on('speaking') * .5; },   // for still test shots
    set(st) { st = STATES.includes(st) ? st : 'idle'; if (st === 'error' && state !== 'error') errAt = performance.now();
      if (state === 'speaking' && st === 'thinking') { next = st; nextAt = -1; return; }   // a short wait for the rest of the answer stays a quiet 'speaking' (see frame)
      next = null; state = st; },
    level(v, between) { lv = Math.max(0, Math.min(1, v || 0)); gap = !!between; },   // between: the brain's voice is between two sentences
    get voice() { return env * ta; },
    // spot(x, y, z): a searched note at (x, y, z) (the notes' space): the ring starts where the shell on screen is nearest to it
    spot(x, y, z) { const dx = x - C.x, dy = y - C.y, dz = z - C.z, k = 1 / Math.max(.05, Math.hypot(dx / R.x, dy / R.y, dz / R.x)), j = spotN++ % 6;
      U.uSpot.value[j].set(C.x + dx * k, C.y + dy * k, C.z + dz * k, 0); spotAt[j] = last || performance.now(); },   // the smoothed voice while speaking (the answer's notes pulse with it)
    get state() { return next || state; } };
}
