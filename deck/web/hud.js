// Shared HUD parts for the three concepts. COL, NICE, DOCS, COLS, ago, esc come from common.js; BRAIN from data.js (the server serves it from ~/.local/share/second-brain/viz/).
import * as THREE from 'three';
export { THREE };
const _t = new Date(); export const NOW = Date.UTC(_t.getFullYear(), _t.getMonth(), _t.getDate(), 12);
export const days = d => Math.round((NOW - new Date(d + 'T12:00:00Z')) / 864e5);
export const hex3 = h => [1, 3, 5].map(i => parseInt(h.slice(i, i + 2), 16) / 255);

export function chrome(sub, active) {
  document.body.insertAdjacentHTML('afterbegin', `<div class="vig"></div><div class="scan"></div>
  <div id="topbar"><span class="t">SECOND<i>·</i>BRAIN</span><span class="s">${sub}</span>
  <div class="nav2"><a href="deck.html" class="${active === 0 ? 'on' : ''}">DECK</a><a href="holo.html" class="${active === 1 ? 'on' : ''}">HOLO-CORE</a><a href="radar.html" class="${active === 2 ? 'on' : ''}">RADAR</a><a href="tunnel.html" class="${active === 3 ? 'on' : ''}">TUNNEL</a></div>
  <div class="stat"><span>NOTES <b>${DOCS.length.toLocaleString()}</b></span><span>GROUPS <b>${COLS.length}</b></span><span>CHECK-UP <b>${BRAIN.scores.at(-1).top3}/${BRAIN.scores.at(-1).of}</b></span><span id="clock"></span></div></div>
  <div id="tip"></div>`);
  const clk = document.getElementById('clock'); const tick = () => clk.textContent = new Date().toTimeString().slice(0, 8); tick(); setInterval(tick, 1000);
}
// big slow turning rings behind the scene (pure decoration, 1 element)
export function rings(size = 760) {
  const arc = (r, n, w, dash) => `<circle cx="${size / 2}" cy="${size / 2}" r="${r}" fill="none" stroke="#5be7ff" stroke-width="${w}" stroke-dasharray="${dash}" opacity=".5"/>`;
  const tick = r => Array.from({ length: 72 }, (_, i) => { const a = i * Math.PI / 36, l = i % 6 ? 6 : 14; return `<line x1="${size / 2 + Math.cos(a) * r}" y1="${size / 2 + Math.sin(a) * r}" x2="${size / 2 + Math.cos(a) * (r - l)}" y2="${size / 2 + Math.sin(a) * (r - l)}" stroke="#5be7ff" stroke-width="1" opacity=".5"/>`; }).join('');
  document.body.insertAdjacentHTML('beforeend', `<div class="rg"><svg class="spin" width="${size}" height="${size}">${arc(size / 2 - 4, 0, 1, '2 10')}${tick(size / 2 - 22)}</svg>
  <svg class="spin2" width="${size}" height="${size}">${arc(size / 2 - 50, 0, 2, '90 40 14 40')}${arc(size / 2 - 70, 0, 1, '4 6')}</svg></div>`);
}
export async function boot(lines) {
  const el = document.createElement('div'); el.id = 'boot'; document.body.append(el);
  for (const l of lines) { el.textContent += l + '\n'; await new Promise(r => setTimeout(r, 140)); }
  await new Promise(r => setTimeout(r, 250)); el.classList.add('go'); setTimeout(() => el.remove(), 900);
}
export function typeInto(el, text, ms = 12) {
  el.textContent = ''; el.classList.add('cur'); let i = 0; clearInterval(el._t);
  el._t = setInterval(() => { el.textContent = text.slice(0, ++i); if (i >= text.length) { clearInterval(el._t); el.classList.remove('cur'); } }, ms);
}
export function cardInfo(i) { const d = DOCS[i]; return { title: d.t, meta: `${NICE[d.c]}  ·  changed ${ago(d.d)}  ·  ${d.n} piece${d.n > 1 ? 's' : ''}`, path: d.p }; }

// glowing point cloud with a "scan band" uniform
export function makeCloud(pos, scale = 1) {
  const n = DOCS.length, P = new Float32Array(n * 3), C = new Float32Array(n * 3), S = new Float32Array(n), A = new Float32Array(n).fill(1), F = new Float32Array(n);
  DOCS.forEach((d, i) => { P.set(pos(d, i).map(v => v * scale), i * 3); C.set(hex3(COL[d.c]), i * 3); S[i] = 6.5 + Math.min(3.5, d.n * .3); });
  const g = new THREE.BufferGeometry(); g.setAttribute('position', new THREE.BufferAttribute(P, 3)); g.setAttribute('color', new THREE.BufferAttribute(C, 3));
  g.setAttribute('aSize', new THREE.BufferAttribute(S, 1)); g.setAttribute('aAlpha', new THREE.BufferAttribute(A, 1)); g.setAttribute('aFlash', new THREE.BufferAttribute(F, 1));
  const m = new THREE.ShaderMaterial({
    transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, vertexColors: true,
    uniforms: { uScale: { value: innerHeight * .5 }, uScan: { value: -99 }, uBand: { value: .35 }, uSweep: { value: 0 }, uSweepOn: { value: 0 } },
    vertexShader: `attribute float aSize; attribute float aAlpha; attribute float aFlash; varying vec3 vC; varying float vA; uniform float uScale; uniform float uScan; uniform float uBand; uniform float uSweep; uniform float uSweepOn;
      void main(){ vC=color; vec4 mv=modelViewMatrix*vec4(position,1.); float band=smoothstep(uBand,0.,abs(position.y-uScan)); float ping=exp(-mod(uSweep-atan(position.z,position.x),6.2831853)*2.6)*uSweepOn; vA=aAlpha*(.75+band*1.3+ping*1.1)+aFlash;
      gl_PointSize=aSize*(1.+band*1.5+ping*1.6+aFlash*2.2)*uScale/-mv.z*.016; gl_Position=projectionMatrix*mv; }`,
    fragmentShader: `varying vec3 vC; varying float vA; void main(){ float d=length(gl_PointCoord-.5); float a=smoothstep(.5,.0,d); float core=smoothstep(.14,.0,d); gl_FragColor=vec4(vC*1.05+vec3(core*.5), a*a*vA*1.5); }`
  });
  const pts = new THREE.Points(g, m); pts.frustumCulled = false;
  return { pts, g, m, A, F, P, setAlpha(i, v) { A[i] = v; g.attributes.aAlpha.needsUpdate = true; }, flush() { g.attributes.aAlpha.needsUpdate = g.attributes.aFlash.needsUpdate = true; } };
}
export function lineMat(color = 0x5be7ff, op = .6) { return new THREE.LineBasicMaterial({ color, transparent: true, opacity: op, blending: THREE.AdditiveBlending, depthWrite: false }); }
export function project(v, camera, w, h) { const p = v.clone().project(camera); return [(p.x * .5 + .5) * w, (-p.y * .5 + .5) * h, p.z]; }
