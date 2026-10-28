// Movable panels (brief 10): drag a panel by its title bar anywhere on screen. It snaps gently to the screen edges and to the
// other movable panels, never leaves the screen (re-clamped on resize), and its place is remembered (localStorage deckPanel.<key>).
// Double-click the title bar, or its RESET control, to put it back. The panel stays in its docked slot and is only shifted with a
// transform, so the slot keeps its space and nothing else on the page moves.
// Use: movable(panel, { key: 'timeline' }); handle defaults to the panel's .h title bar. Works inside a CSS-zoomed column.
const all = [], M = 12, SNAP = 14, GAP = 10;
const store = { get: k => { try { return JSON.parse(localStorage.getItem('deckPanel.' + k)); } catch { return null; } },
  set: (k, v) => { try { v ? localStorage.setItem('deckPanel.' + k, JSON.stringify(v)) : localStorage.removeItem('deckPanel.' + k); } catch {} } };
const topMin = () => { const t = document.getElementById('topbar'); return (t ? t.getBoundingClientRect().bottom : 0) + 6; };
const clamp = (v, a, b) => Math.max(a, Math.min(Math.max(a, b), v));
export function movable(el, { key, handle = el.querySelector('.h'), onMove } = {}) {
  let pos = store.get(key), off = [0, 0], dragging = null;   // pos: {x, y} of the top-left corner on screen (px); off: the current shift
  const zoom = () => el.currentCSSZoom || 1;
  const dock = () => { const r = el.getBoundingClientRect(); return { x: r.left - off[0], y: r.top - off[1], w: r.width, h: r.height }; };
  const fit = (x, y, d) => [clamp(x, M, innerWidth - M - d.w), clamp(y, topMin(), innerHeight - M - d.h)];
  function put(x, y, anim) { const d = dock(); [x, y] = fit(x, y, d); off = [x - d.x, y - d.y]; const z = zoom();
    el.classList.toggle('anim', !!anim); el.style.transform = off[0] || off[1] ? `translate(${off[0] / z}px,${off[1] / z}px)` : '';
    el.classList.toggle('moved', !!pos); onMove && onMove(); }
  // snapping: each edge pulls toward the screen margins and the other panels' edges (side by side or lined up) when close
  function snap(x, y, d) { const xs = [M, innerWidth - M - d.w], ys = [topMin(), innerHeight - M - d.h];
    for (const o of all) { if (o.el === el || !o.el.offsetParent) continue; const r = o.el.getBoundingClientRect();
      xs.push(r.left, r.right - d.w, r.right + GAP, r.left - GAP - d.w); ys.push(r.top, r.bottom - d.h, r.bottom + GAP, r.top - GAP - d.h); }
    const near = (v, c) => { let b = v, bd = SNAP; for (const t of c) { const dd = Math.abs(t - v); if (dd < bd) { bd = dd; b = t; } } return b; };
    return [near(x, xs), near(y, ys)]; }
  function save() { if (!pos) return store.set(key, null); const d = dock(), x = d.x + off[0], y = d.y + off[1];
    // remembered from the nearer edges, so a panel parked on the right stays on the right when the window changes size
    pos = { x, y, r: innerWidth - x - d.w, b: innerHeight - y - d.h, ax: x + d.w / 2 > innerWidth / 2 ? 'r' : 'l', ay: y + d.h / 2 > innerHeight / 2 ? 'b' : 't' }; store.set(key, pos); }
  function place(anim) { if (!pos) return put(dock().x, dock().y, anim); const d = dock();
    put(pos.ax === 'r' ? innerWidth - pos.r - d.w : pos.x, pos.ay === 'b' ? innerHeight - pos.b - d.h : pos.y, anim); }
  function reset() { pos = null; store.set(key, null); el.classList.add('anim'); off = [0, 0]; el.style.transform = ''; el.classList.remove('moved'); onMove && onMove(); }
  handle.addEventListener('pointerdown', e => { if (e.button !== 0 || e.target.closest('button,input,a,select,.hdbtn,.pm-reset')) return;
    e.preventDefault(); const d = dock(); dragging = { sx: e.clientX, sy: e.clientY, x0: d.x + off[0], y0: d.y + off[1], d, moved: false };
    handle.setPointerCapture(e.pointerId); });
  handle.addEventListener('pointermove', e => { if (!dragging) return; const g = dragging, dx = e.clientX - g.sx, dy = e.clientY - g.sy;
    if (!g.moved && Math.hypot(dx, dy) < 4) return; if (!g.moved) { g.moved = true; el.classList.add('dragging'); document.body.classList.add('pdrag'); }
    pos = pos || {}; const [x, y] = snap(...fit(g.x0 + dx, g.y0 + dy, g.d), g.d); put(x, y, false); });
  const end = () => { if (!dragging) return; const g = dragging; dragging = null; el.classList.remove('dragging'); document.body.classList.remove('pdrag'); if (g.moved) save(); };
  handle.addEventListener('pointerup', end); handle.addEventListener('pointercancel', end); handle.addEventListener('lostpointercapture', end);
  handle.addEventListener('dblclick', e => { if (!e.target.closest('button,input,a,select')) reset(); });
  const rb = document.createElement('button'); rb.className = 'pm-reset'; rb.title = 'put back  (or double-click the title bar)'; rb.textContent = 'reset'; rb.onclick = reset;
  (handle.querySelector('b') || handle).append(rb); handle.classList.add('pm-handle'); el.classList.add('mov');
  const me = { el, place, reset, get moved() { return !!pos; } }; all.push(me);
  requestAnimationFrame(() => place(false)); return me;
}
// after a window resize or a panel-size change: every moved panel is placed again from its remembered edges, inside the screen
let rz; addEventListener('resize', () => { clearTimeout(rz); rz = setTimeout(() => all.forEach(o => o.place(false)), 160); });
export const replaceAll = () => all.forEach(o => o.place(false));
