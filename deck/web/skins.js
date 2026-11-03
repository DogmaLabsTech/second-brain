// Skins: switch the whole look live. The looks themselves are token blocks in skins.css; this file only names them,
// switches <html data-skin>, cross-fades the three.js side (the CSS side cross-fades by itself, see skins.css) and remembers the
// choice. The scene theme is read from the same CSS tokens (a hidden probe element carries the target skin), so there is one
// source of truth per skin. The deck calls tick(t) every frame and repaints the scene with the returned theme while it changes.
import { THREE } from './hud.js';
import { SKINS } from './skins/index.js';   // the skin list lives in skins/index.js
import { invertCSS } from './invert.js';     // the inverted twin of every skin
export { SKINS };
const KEY = 'deckSkin', INV = 'deckInvert', INV_CSS = 'deckInvCSS', BLUR = 'deckBlur', FADE = 420, ROLES = ['line', 'sweep', 'slice', 'scan', 'nb', 'shell', 'listen', 'speak', 'think', 'hot', 'err'];
// Holo, built in: used only if skins.css can't be loaded at all, so the page is then fully Holo (page and scene), never half a skin.
// A copy of the Holo block in skins.css: keep the two in step (test compares them).
const HOLO_CSS = `:root{--c:#5be7ff;--amber:#ffb454;--ok:#7dffb0;--bad:#ff7a7a;--violet:#c9a2ff; --hi:#fff;--tx-hi:#e8fbff;--tx:#bfeaf5;--tx-read:#d6edf3;--dim:#6a93a0;--dim2:#8fb7c4;--on-c:#02080c;--listen:#c8faff; --bg1:#0a2430;--bg2:#04101a;--bg3:#02060a;--bg-a:#0000;--bg-b:#0000; --glass:#06161fbd;--glass2:#030c12c8;--glass-rd:#05141de8;--glass-pop:#031219f2; --surf:#06202bcc;--surf-hi:#0d3140;--well:#02101799;--track:#0f2a35; --line:#5be7ff30;--edge:#02080c;--inner:#5be7ff1f;--shadow:#000a;--halo:#02080c; --warn-bg:#2a1f0ecc;--warn-tx:#ffe3b8;--err-bg:#2a0e0ecc;--err-tx:#ffc4bc;--em:#ffdcae;--quote:#ead8b8;--link:#ffc477;--code-tx:#9ff0ff;--code-bg:#0b2d3b; --g-agent-os:#ff7a45;--g-business:#ffd23f;--g-chats:#4d9bff;--g-codex:#8b7bff;--g-computer:#19d3c5;--g-content:#ff5fa2; --g-days:#f1ecc8;--g-experiments:#b8f27c;--g-hermes:#8a94a6;--g-memory:#ce9143;--g-plans:#6ee7ff;--g-pm:#ff4d5e;--g-projects:#5cd65c; --glow:1;--corner:1;--scan-op:.5;--vig-op:1;--r:12px;--r-sm:7px;--blur:10px;--sat:1.25; --font-ui:"JetBrainsMono Nerd Font","JetBrains Mono",ui-monospace,monospace;--font-read:Inter,system-ui,sans-serif;--font-mono:"JetBrainsMono Nerd Font","JetBrains Mono",monospace; --s-line:#5be7ff;--s-sweep:#aef6ff;--s-slice:#ffb454;--s-scan:#d8fbff;--s-nb:#8cf0ff;--s-shell:#5be7ff;--s-listen:#b4f7ff;--s-speak:#7beeff;--s-think:#ffb454;--s-hot:#d8fbff;--s-err:#ff6a6a;--s-blend:add;--s-core:.5;--s-dot:1;--s-shell-glow:1;--s-size:1; --sp:1;--skin:holo}`;
const HOLO = Object.fromEntries(HOLO_CSS.slice(6, -1).split(';').filter(Boolean).map(x => { const i = x.indexOf(':'); return [x.slice(0, i).trim(), x.slice(i + 1).trim()]; }));
const ease = t => t < .5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
export function makeSkins(groups) {
  const html = document.documentElement, probe = document.createElement('div'); probe.style.display = 'none'; document.body.append(probe);
  const names = SKINS.map(s => s[0]), hashed = (location.hash.match(/[#&]skin=([\w-]+)/) || [])[1];
  let name = names.includes(html.dataset.skin) ? html.dataset.skin : 'holo';
  if (hashed && names.includes(hashed)) name = hashed;
  // the scene theme of a skin: colours per role and per note group, the blend mode and a few numbers
  function ok() { delete probe.dataset.inv; probe.dataset.skin = 'holo'; return !!getComputedStyle(probe).getPropertyValue('--s-line').trim(); }
  // a skin's own file loaded (its block carries --skin:<name>); if one @import failed, that skin would show as Holo: refuse it
  function has(n) { delete probe.dataset.inv; probe.dataset.skin = n; return getComputedStyle(probe).getPropertyValue('--skin').trim() === n; }
  function read(n, i = inv) { probe.dataset.skin = n; if (i) probe.dataset.inv = ''; else delete probe.dataset.inv; const cs = getComputedStyle(probe), v = k => cs.getPropertyValue(k).trim() || HOLO[k] || '', col = k => new THREE.Color().setStyle(v(k) || '#ffffff');
    const o = { blend: v('--s-blend') === 'normal' ? 'normal' : 'add', core: parseFloat(v('--s-core')) || 0, dot: parseFloat(v('--s-dot')) || 1, shellGlow: parseFloat(v('--s-shell-glow')) || 1, size: parseFloat(v('--s-size')) || 1, g: {} };
    ROLES.forEach(r => o[r] = col('--s-' + r)); groups.forEach(c => o.g[c] = col(v('--g-' + c) ? '--g-' + c : '--dim2')); return o; }   // a group no skin knows yet (a future collection) gets the neutral text colour
  const clone = o => ({ ...o, g: Object.fromEntries(Object.entries(o.g).map(([k, c]) => [k, c.clone()])), ...Object.fromEntries(ROLES.map(r => [r, o[r].clone()])) });
  // (the early script may have put last time's inverted rules in place: take them off while checking, or their tokens would pass for loaded skins)
  const early = html.hasAttribute('data-inv'); delete html.dataset.inv;
  if (ok() && !has(name)) name = 'holo';   // saved or hashed skin whose file did not load: plain Holo
  // inverted palettes: one generated rule per skin, turned on by <html data-inv> (the early script in deck.html sets it from the saved
  // choice and puts last time's rules in place, so the first frame is already right). Rebuilt here from the live tokens; if that fails, the
  // Deck shows the plain skin (never a half-inverted look). Remembered once for all skins (deckInvert '1'); the hash `invert` forces it on unsaved.
  let inv = early || /[#&]invert\b/.test(location.hash), invOk = false;
  function build() { let st = document.getElementById('skin-inv'); try { const css = invertCSS(names); if (!st) { st = document.createElement('style'); st.id = 'skin-inv'; document.head.append(st); } st.textContent = css; invOk = true; try { localStorage.setItem(INV_CSS, css); } catch {} }
    catch (e) { console.warn('inverted palettes failed, plain skins only', e); if (st) st.remove(); invOk = false; } if (!invOk) inv = false; inv ? html.dataset.inv = '' : delete html.dataset.inv; }
  const wantInv = inv; if (ok()) build(); else inv = false;   // (healing below: inverted again once the skins are back)
  let to = read(name), from = clone(to), live = clone(to), t0 = -1, dirty = true, fadeT = 0, broken = false;
  html.dataset.skin = name; window.__skinOk = ok() ? 'ok' : 'healing';
  // fail safe: if the skin tokens are missing (the browser kept an old hud.css from before skins existed), load the
  // stylesheets again past the cache, in their places, then repaint. If that fails too, it is plain Holo (the scene from HOLO below).
  if (!ok()) { const t = Date.now(), old = document.querySelector('link[rel=stylesheet][href^="hud.css"]'), sk = document.createElement('link'); sk.rel = 'stylesheet'; sk.href = 'skins.css?v=' + t;
    let left = old ? 2 : 1; const done = () => { if (--left) return; const good = ok(); if (!good) { name = 'holo'; broken = true; html.dataset.skin = name; document.getElementById('skin-inv')?.remove(); const st = document.createElement('style'); st.id = 'skin-fallback'; st.textContent = HOLO_CSS; document.head.append(st); buttons(); }
      if (good) { inv = wantInv; build(); } to = read(name); from = clone(to); live = clone(to); t0 = -1; dirty = true; window.__skinOk = good ? 'healed' : 'fallback'; };
    sk.onload = sk.onerror = done; if (old) { old.onload = old.onerror = done; old.href = 'hud.css?v=' + t; old.after(sk); } else document.head.append(sk); }
  // (broken: skins.css never loaded, only the built-in Holo is there, so switching would leave half a skin)
  function set(n, animate = true) { if (!names.includes(n) || broken) return; if (!has(n)) { console.warn('skin file missing or not loaded: ' + n); return; } const was = name; name = n; try { localStorage.setItem(KEY, n); } catch {}
    fade(animate && was !== n); html.dataset.skin = n; buttons(); }
  function fade(animate) { from = clone(live); to = read(name); t0 = animate ? -2 : -1; dirty = true;   // -2: starts on the next tick (its clock)
    if (animate) { html.classList.add('skinfade'); clearTimeout(fadeT); fadeT = setTimeout(() => html.classList.remove('skinfade'), FADE + 80); } }
  // invert(on): the current skin's inverted twin, with the same cross-fade as a skin switch
  function invert(on, animate = true) { on = !!on && invOk && !broken; if (on === inv) return; inv = on; try { localStorage.setItem(INV, on ? '1' : '0'); } catch {}
    fade(animate); on ? html.dataset.inv = '' : delete html.dataset.inv; buttons(); }
  // tick(t): the live theme while it changes (null when nothing changed); colours and numbers ease over FADE ms, the blend mode flips half way
  function tick(t) { if (!dirty) return null; if (t0 === -2) t0 = t; const k = t0 < 0 ? 1 : ease(Math.min(1, (t - t0) / FADE));
    ROLES.forEach(r => live[r].copy(from[r]).lerp(to[r], k)); for (const c in to.g) live.g[c].copy(from.g[c]).lerp(to.g[c], k);
    for (const x of ['core', 'dot', 'shellGlow', 'size']) live[x] = from[x] + (to[x] - from[x]) * k; live.blend = k < .5 ? from.blend : to.blend;
    if (k >= 1) { dirty = false; t0 = -1; } return live; }
  // the skin cards in Settings: one card per skin; its swatch strip carries that skin's own tokens (inverted too while inverting is on),
  // so the stripes are its real colours: page, text, main and second accent, four group colours. Tagged dark or light. Plus the switches.
  const boxes = [];
  const dark = (n, i) => { probe.dataset.skin = n; if (i) probe.dataset.inv = ''; else delete probe.dataset.inv; return getComputedStyle(probe).getPropertyValue('--s-blend').trim() !== 'normal'; };
  function buttons() { const label = SKINS.find(s => s[0] === name)[1];
    for (const box of boxes) { box.querySelectorAll('.sk').forEach(b => { const on = b.dataset.s === name; b.classList.toggle('on', on); b.setAttribute('aria-pressed', on);
        const sw = b.querySelector('.sw'); if (inv) sw.dataset.inv = ''; else delete sw.dataset.inv; b.querySelector('.tag').textContent = dark(b.dataset.s, inv) ? 'DARK' : 'LIGHT'; });
      box.querySelectorAll('.skl').forEach(l => l.textContent = label.toUpperCase() + (inv ? '  ·  INVERTED' : ''));
      box.querySelectorAll('[data-sw=inv]').forEach(b => { b.setAttribute('aria-checked', inv); b.disabled = !invOk || broken; });
      box.querySelectorAll('[data-sw=blur]').forEach(b => b.setAttribute('aria-checked', blurOn())); } }
  function picker(el) { boxes.push(el); el.innerHTML = '<div class="skgrid">' + SKINS.map(([n, l]) => `<button class="sk" data-s="${n}" title="${l}" aria-label="${l}"><i class="sw" data-skin="${n}"><s></s><s></s><s></s><s></s><s></s><s></s><s></s><s></s></i><b>${l}</b><em class="tag"></em></button>`).join('') + '</div>';
    el.querySelectorAll('.sk').forEach(b => b.onclick = () => set(b.dataset.s)); buttons(); }
  // any element with data-sw="inv" / "blur" becomes that switch; .skl shows the current skin's name
  function wire(el) { if (!boxes.includes(el)) boxes.push(el); el.querySelectorAll('[data-sw=inv]').forEach(b => b.onclick = () => invert(!inv)); el.querySelectorAll('[data-sw=blur]').forEach(b => b.onclick = () => setBlur(!blurOn())); buttons(); }
  // blur guard: if the page runs slowly with glass blur on, try plain translucency; keep it only if that really helps
  // (frosted glass can also be turned off in Settings, remembered as deckBlur 'off'; then the guard stays out of it)
  const force = location.hash.match(/[#&](noblur|blur)\b/); let blurOff = false; try { blurOff = localStorage.getItem(BLUR) === 'off'; } catch {}
  if (force ? force[1] === 'noblur' : blurOff) html.classList.add('noblur');
  const blurOn = () => !html.classList.contains('noblur');
  function setBlur(on) { html.classList.toggle('noblur', !on); perf.phase = 'off'; try { localStorage.setItem(BLUR, on ? 'on' : 'off'); } catch {} buttons(); }
  const perf = { phase: force || blurOff || location.hash.includes('still') ? 'off' : 'wait', n: 0, sum: 0, at: performance.now() + 4000, withBlur: 0, withoutBlur: 0 };
  function frameTime(dt) { if (perf.phase === 'off' || performance.now() < perf.at || document.hidden) return; perf.sum += dt; if (++perf.n < 120) return;
    const ms = perf.sum / perf.n; perf.n = perf.sum = 0;
    if (perf.phase === 'wait') { perf.withBlur = ms; if (ms > 24) { html.classList.add('noblur'); perf.phase = 'try'; perf.at = performance.now() + 800; } else perf.phase = 'off'; }
    else if (perf.phase === 'try') { perf.withoutBlur = ms; if (ms > perf.withBlur * .85) html.classList.remove('noblur'); perf.phase = 'off'; }
    window.__skinPerf = { ...perf, noblur: html.classList.contains('noblur') }; }
  return { set, tick, picker, wire, invert, setBlur, frameTime, get inv() { return inv; }, get invOk() { return invOk && !broken; }, next(d = 1) { for (let k = 1; k <= names.length; k++) { const n = names[(names.indexOf(name) + d * k + names.length * k) % names.length]; if (broken || has(n)) { set(n); break; } } return name; }, get name() { return name; }, get label() { return SKINS.find(s => s[0] === name)[1]; } };
}
