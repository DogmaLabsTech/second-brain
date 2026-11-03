// Live searches: the scene stays calm until someone searches the brain (a chat, the voice island, the terminal, the
// Deck's own Ask box or voice). Then, per search: only the sections holding its notes wake up (the rest dims), a query point
// with the question and who asked appears above the notes, and a line grows to each note one by one in rank order with a spark
// riding its tip; the note pulses, gets its number, and the shell ripples at that spot. After ~8 s it all fades back to calm.
// Several searches stack (at most CAP on screen, the oldest fades first). Positions are read from the notes' live positions
// every frame, so it follows view switches and the camera. Colours are skin tokens only (CSS vars; dots via the cloud shader).
// Reads (a chat opening a note) are lighter: one thin line, a soft pulse, no number, gone after ~3 s. Notes newer than data.js
// can't be placed, so their line goes to the middle of their section instead and the section wakes.
// One owner for when lines fade: this file. An event fades HOLD after it lands, or, if it was played with hold (the Deck's voice
// answer), only after release(e) (when the voice has finished speaking), then calmly. A held event is never pushed out by the cap.
// makeLive(...) returns { play(ev), release(e), frame(t), snap() }; makeFeed(...) is the 08 Live panel (the list of recent searches).
const CAP = 4, IN = 300, STEP = 300, GROW = 480, HOLD = 7600, LIGHT = 3000, FADE = 1600, QUICK = 700, AFTER = 1200, MAXHITS = 8;
const clamp = (v, a = 0, b = 1) => Math.max(a, Math.min(b, v)), ease = t => t < .5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2, out3 = t => 1 - Math.pow(1 - t, 3);
const NS = 'http://www.w3.org/2000/svg', svgEl = (tag, cls, p) => { const e = document.createElementNS(NS, tag); if (cls) e.setAttribute('class', cls); p.append(e); return e; };
export function makeLive({ cur, root, camera, project, V, cloud, docs, kc, cols, esc, shell, seen, pulse, W, H }) {
  const svg = svgEl('svg', '', document.body); svg.id = 'livesvg';
  const evs = [], F = cloud.F, gi = Object.fromEntries(cols.map((c, k) => [c, k])), wake = cloud.m.uniforms.uWake.value, touched = new Set();
  let now = 0;
  const xy = (i, v = V) => { v.set(cur[i * 3], cur[i * 3 + 1], cur[i * 3 + 2]).applyMatrix4(root.matrixWorld); return project(v, camera, W(), H()); };
  const bySec = {}; docs.forEach((d, i) => (bySec[d.c] = bySec[d.c] || []).push(i));
  for (const c in bySec) { const l = bySec[c], k = Math.max(1, Math.floor(l.length / 24)); bySec[c] = l.filter((_, n) => n % k === 0).slice(0, 24); }   // a few notes per section stand for its middle
  // where a hit is on screen: its note, or the middle of its section's visible notes (a note newer than data.js); null = not visible
  const at = h => { if (h.i !== undefined) return seen(h.i) ? xy(h.i) : null; let x = 0, y = 0, n = 0;
    for (const i of bySec[h.sec] || []) if (seen(i)) { const p = xy(i); if (p[2] <= 1) { x += p[0]; y += p[1]; n++; } } return n ? [x / n, y / n, 0] : null; };
  // play(ev): ev = { q, who, list: [note index, in rank order], secs: [sections of found notes not in data.js], own (the Deck already
  // labels these notes), voice (pulse with the voice), hold (stay until release), light (a read: one soft line) }
  function play(ev) {
    const list = [...new Set(ev.list)].slice(0, MAXHITS), secs = [...new Set(ev.secs || [])].filter(c => c in gi && !list.some(i => docs[i].c === c)).slice(0, Math.max(0, MAXHITS - list.length));
    if (!list.length && !secs.length) return null;
    const live = evs.filter(e => !e.gone && e.fadeAt > now), o = live.find(e => !e.held) || live[0];
    if (live.length >= CAP && o) { o.fadeAt = Math.min(o.fadeAt, now); o.fd = QUICK; o.held = false; }   // the oldest (not the voice's) makes room
    const g = svgEl('g', 'lv-ev' + (ev.light ? ' light' : ''), svg), q = document.createElement('div'); q.className = 'lv-q' + (ev.light ? ' light' : ''); document.body.append(q);
    q.innerHTML = `<i></i><span class="t">${esc(ev.q.length > 54 ? ev.q.slice(0, 52) + '…' : ev.q)}</span><span class="w">${esc(ev.who || '')}</span>`;
    const qd = svgEl('circle', 'lv-qd', g), qr = svgEl('circle', 'lv-qr', g); qd.setAttribute('r', 3.5);
    const hits = [...list.map(i => ({ i, c: docs[i].c })), ...secs.map(c => ({ sec: c, c }))].map((h, k) => { const k2 = kc(h.c), ln = svgEl('line', 'lv-ln' + (h.sec ? ' sec' : ''), g), ring = svgEl('circle', 'lv-ring', g), sp = svgEl('circle', 'lv-sp', g); sp.setAttribute('r', 2.6);
      [ln, ring].forEach(e => e.style.setProperty('--k', k2)); let tag = null;
      if (!ev.own && !ev.light && !h.sec) { tag = document.createElement('div'); tag.className = 'lbl tag lv-tag'; tag.style.setProperty('--k', k2); tag.innerHTML = `<i>${String(k + 1).padStart(2, '0')}</i>`; document.body.append(tag); }
      return { ...h, k, ln, ring, sp, tag, at: -1 }; });
    const e = { ...ev, list, t0: now, fadeAt: ev.hold ? Infinity : now + (ev.light ? LIGHT : HOLD), held: !!ev.hold, fd: FADE, g, q, qd, qr, hits, a: 0, gone: false }; evs.push(e); return e;
  }
  // release(e): the answer has finished (the voice stopped): the lines stay a moment more (and at least until all have landed), then fade calmly
  function release(e, after = AFTER) { if (!e || e.gone || !e.held) return; e.held = false; e.fadeAt = Math.max(now + after, e.t0 + IN + e.hits.length * STEP + GROW + after); }
  function drop(e) { e.gone = true; e.g.remove(); e.q.remove(); e.hits.forEach(h => h.tag && h.tag.remove()); evs.splice(evs.indexOf(e), 1); }
  function frame(t) {
    now = t; for (const i of touched) F[i] = 0; const had = touched.size > 0; touched.clear(); wake.fill(0); let any = 0;
    const qs = [];
    for (const e of [...evs]) {   // pass 1: fade, where the notes are, the query point above the middle of them (on screen, inside the window)
      const age = t - e.t0, a = out3(clamp(age / 400)) * (1 - ease(clamp((t - e.fadeAt) / e.fd)));
      if (t >= e.fadeAt + e.fd) { drop(e); continue; }
      e.a = a; any = Math.max(any, a);
      let sx = 0, sy = 0, n = 0; e.P = e.hits.map(h => { const p = at(h); if (p && p[2] <= 1) { sx += p[0]; sy += p[1]; n++; return p; } return null; });
      if (!n) { e.g.style.opacity = 0; e.q.style.opacity = 0; e.hits.forEach(h => h.tag && (h.tag.style.opacity = 0)); continue; }
      qs.push({ e, x: clamp(sx / n, 60, W() - 60), y: clamp(sy / n - (e.light ? 70 : 120) * Math.min(1.4, H() / 1100), 80, H() - 60), w: e.q.offsetWidth, h: e.q.offsetHeight + 6 });
    }
    // several searches on screen: their questions (and query points) step upward, away from the notes, so no label covers another
    qs.sort((p, q) => q.y - p.y); for (let m = 0; m < qs.length; m++) for (let n = 0; n < m; n++) { const p = qs[m], q = qs[n]; if (Math.abs(p.x - q.x) < (p.w + q.w) / 2 + 8 && q.y - p.y < p.h) p.y = q.y - p.h; }
    for (const { e, x: qx, y: qy } of qs) {   // pass 2: draw
      const age = t - e.t0, a = e.a, P = e.P; e.q.style.left = qx + 'px'; e.q.style.top = qy + 'px'; e.q.style.opacity = a;
      e.g.style.opacity = a; e.qd.setAttribute('cx', qx); e.qd.setAttribute('cy', qy); e.qr.setAttribute('cx', qx); e.qr.setAttribute('cy', qy); e.qr.setAttribute('r', 6 + 10 * ((age / 1600) % 1)); e.qr.style.opacity = 1 - ((age / 1600) % 1);
      e.hits.forEach((h, k) => { const p = P[k], s0 = IN + k * STEP, gr = ease(clamp((age - s0) / GROW));
        if (p && gr > 0 && !e.drew) e.drew = Date.now();   // when the first line started (the live test reads it)
        if (!p || gr <= 0) { h.ln.style.opacity = h.sp.style.opacity = h.ring.style.opacity = 0; if (h.tag) h.tag.style.opacity = 0; return; }
        const x = qx + (p[0] - qx) * gr, y = qy + (p[1] - qy) * gr; h.ln.setAttribute('x1', qx); h.ln.setAttribute('y1', qy); h.ln.setAttribute('x2', x); h.ln.setAttribute('y2', y); h.ln.style.opacity = (gr < 1 ? .9 : .55) * (e.light ? .7 : 1);
        h.sp.setAttribute('cx', x); h.sp.setAttribute('cy', y); h.sp.style.opacity = gr < 1 ? 1 : Math.max(0, 1 - (age - s0 - GROW) / 300);
        if (gr >= 1 && h.at < 0) { h.at = t; if (h.i !== undefined && !e.light) { const j = h.i * 3; shell.spot(cur[j], cur[j + 1], cur[j + 2]); } }   // arrived: the note pulses, gets its number, the shell ripples there (not for a read)
        const since = h.at < 0 ? -1 : t - h.at;
        if (since >= 0) { const r = clamp(since / 900); h.ring.setAttribute('cx', p[0]); h.ring.setAttribute('cy', p[1]); h.ring.setAttribute('r', (5 + 20 * out3(r)) * (h.sec ? 1.6 : e.light ? .6 : 1)); h.ring.style.opacity = 1 - r;
          if (h.i !== undefined) { const v = (1.4 * Math.exp(-since / 520) + .5 + .12 * Math.sin(since / 380)) * a * (e.light ? .55 : 1) + (e.voice ? pulse() : 0); F[h.i] = Math.max(F[h.i], v); touched.add(h.i); } }
        else h.ring.style.opacity = 0;
        if (h.tag) { h.tag.style.opacity = since < 0 ? 0 : a * clamp(since / 200); h.tag.style.left = p[0] + 'px'; h.tag.style.top = p[1] + 'px'; }
        wake[gi[h.c]] = Math.max(wake[gi[h.c]], a * clamp((age - s0) / GROW * 2)); });
    }
    cloud.m.uniforms.uLive.value = any; if (had || touched.size) cloud.g.attributes.aFlash.needsUpdate = true;
  }
  const snap = () => evs.map(e => ({ q: e.q.textContent, a: +e.a.toFixed(3), held: e.held, key: e.key, light: !!e.light, lines: e.hits.map(h => [+h.ln.getAttribute('x1'), +h.ln.getAttribute('y1'), +h.ln.getAttribute('x2'), +h.ln.getAttribute('y2'), h.at >= 0 ? 1 : 0]) }));
  return { play, release, frame, snap, clear() { [...evs].forEach(drop); }, get count() { return evs.length; } };
}
// 08 Live: the recent searches, newest on top: time, who, the question, how many notes. Click = play it again; hover = its notes,
// and a click on one of those opens it in the reader (also a note that is no dot in the scene, e.g. one newer than the snapshot: ).
export function makeFeed(el, { docs, kc, nice, esc, onReplay, onHide, onOpen }) {
  el.innerHTML = `<div class="h"><span><i class="num">08</i>Live</span><b><em class="lf-st" data-r="st">connecting</em><span class="hdbtn" data-r="hide" title="hide  (L)">✕</span></b></div>
    <div class="lf-list" data-r="list"><div class="lf-empty">Calm. Searches show up here as they happen.</div></div><div class="lf-pop" data-r="pop"></div>`;
  const R = n => el.querySelector(`[data-r=${n}]`), rows = new Map(); let n = 0, popT = 0, popRows = [];
  R('hide').onclick = onHide;
  const unpop = () => { clearTimeout(popT); popT = setTimeout(() => R('pop').classList.remove('on'), 260); };   // time to move the mouse over to the pop
  R('pop').onmouseenter = () => clearTimeout(popT); R('pop').onmouseleave = unpop;
  R('pop').onclick = e => { const d = e.target.closest('[data-n]'), o = d && popRows[+d.dataset.n]; if (o && onOpen) { R('pop').classList.remove('on'); onOpen(o.i, o.h); } };
  const time = at => (at || '').slice(11, 19) || new Date().toTimeString().slice(0, 8);
  function add(ev) {
    const key = ev.key || 'r' + ++n; if (rows.has(key)) return; const all = ev.hits ? ev.hits.length : ev.list.length, shown = ev.list.length + (ev.secs || []).length;
    const b = document.createElement('button'); b.className = 'lf-row' + (ev.past ? ' past' : ''); b.dataset.k = key;
    b.innerHTML = `<span class="lf-l1"><time>${esc(time(ev.at))}</time><span class="lf-who">${esc(ev.who || '?')}</span><em>${all ? all + (all === 1 ? ' note' : ' notes') : 'no notes'}</em></span><span class="lf-q">${ev.kind === 'read' ? '<i>opened</i> ' : ''}${esc(ev.q)}</span>`;
    b.title = shown ? 'click to play it again' : all ? 'its notes are not in the Deck’s snapshot' : 'nothing found';   // shown: notes (or sections) it can draw
    rows.set(key, ev); R('list').querySelector('.lf-empty')?.remove(); R('list').prepend(b);
    while (R('list').children.length > 30) { const x = R('list').lastElementChild; rows.delete(x.dataset.k); x.remove(); }
    b.onclick = () => shown && onReplay(ev); b.onmouseenter = () => pop(b, ev); b.onmouseleave = unpop;
  }
  // the pop lists every note found, in rank order; one newer than the Deck's snapshot shows its title and section, marked new
  function pop(b, ev) { clearTimeout(popT); const p = R('pop'), rowsOf = ev.idx ? ev.hits.map((h, k) => ({ i: ev.idx[k], h })) : ev.list.map(i => ({ i })), miss = rowsOf.filter(o => o.i === undefined && o.h).length; popRows = rowsOf;
    p.innerHTML = `<b>${esc(ev.q)}</b>` + rowsOf.map(({ i, h }, k) => { const c = i !== undefined ? docs[i].c : h.c;
      return `<div data-n="${k}" style="--k:${c ? kc(c) : 'var(--dim)'}" class="${i === undefined ? 'new' : ''}${i !== undefined || h.id ? ' go' : ''}" title="${i !== undefined || h.id ? 'click to open' : ''}"><i>${String(k + 1).padStart(2, '0')}</i><span>${esc(i !== undefined ? docs[i].t : h.t || h.path || '?')}</span><em>${i === undefined ? 'new · ' : ''}${esc(c ? (nice[c] || c).toUpperCase() : '?')}</em></div>`; }).join('')
      + (miss > 0 ? `<p>${miss === 1 ? 'one note is' : miss + ' notes are'} newer than the Deck’s snapshot</p>` : '') + (!rowsOf.length ? '<p>nothing found</p>' : '');
    const r = el.getBoundingClientRect(), z = el.currentCSSZoom || 1, right = r.right + 300 * z < innerWidth; p.classList.toggle('left', !right);
    p.style.top = (b.getBoundingClientRect().top - r.top) / z + 'px'; p.classList.add('on'); }
  return { add, status(t, cls = '') { const s = R('st'); s.textContent = t; s.className = 'lf-st ' + cls; } };
}
