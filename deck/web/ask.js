// 06 Ask (brief 10): a search box on the brain's meaning search (GET /search?q= on the Deck server runs `brain search`, read-only).
// Enter, or a short pause in typing, searches; the results drop out of the panel as a short list (title, group chip, score) and
// light up their notes in the scene; click one = open it in the reader. The quick chips are suggestions: click = search that.
// A found note that is not a dot in the scene (newer than data.js) still opens in the reader when the index knows it (brief 22).
// Each search carries the Deck's live nonce (X-Deck-Live), so the live feed knows it already played this one (brief 15).
// The box keeps the id "q", so the Deck's key handlers still know it is a text field ( / focuses it, Esc clears then leaves).
export function makeAsk(el, { chips, find, docs, kc, nice, esc, onResults, onOpen, onOpenLoose, onClear, live }) {
  el.innerHTML = `<div class="h"><span><i class="num">06</i>Ask</span><b>meaning search</b></div>
    <div class="ak-box"><i class="ak-ic"></i><input id="q" placeholder="search your notes…" autocomplete="off" spellcheck="false"><kbd data-r="kbd">/</kbd><button class="ak-x" data-r="x" title="clear  (Esc)">✕</button></div>
    <div class="ak-chips" data-r="chips">${chips.map(c => `<button class="chip2" data-q="${esc(c)}">${esc(c)}</button>`).join('')}</div>
    <div class="ak-res" data-r="res"><div class="ak-st" data-r="st"></div><div class="ak-list" data-r="list"></div></div>`;
  const R = n => el.querySelector(`[data-r=${n}]`), box = el.querySelector('#q'), res = R('res');
  let gen = 0, ctl = null, timer = 0, last = '';
  const status = (t, cls = '') => { R('st').className = 'ak-st ' + cls; R('st').innerHTML = t; };
  // the list opens above the panel, or below it when the panel was dragged near the top of the screen
  const side = () => { const r = el.getBoundingClientRect(); res.classList.toggle('down', r.top < innerHeight * .45); };
  const show = on => { if (on) side(); res.classList.toggle('on', on); el.classList.toggle('has-res', on); };
  function clear(keepText) { gen++; if (ctl) ctl.abort(); clearTimeout(timer); last = ''; show(false); R('list').innerHTML = '';
    el.querySelectorAll('.ak-chips .chip2').forEach(x => x.classList.remove('on')); el.classList.remove('busy'); if (!keepText) box.value = ''; onClear(); }
  async function search(q) { q = q.split(/\s+/).join(' ').trim(); clearTimeout(timer); if (!q) return clear(); if (q === last && res.classList.contains('on')) return; last = q;
    const g = ++gen; if (ctl) ctl.abort(); ctl = new AbortController(); el.classList.add('busy');
    el.querySelectorAll('.ak-chips .chip2').forEach(x => x.classList.toggle('on', x.dataset.q === q));
    status(`<i class="ak-sp"></i>looking for “${esc(q)}”…`, 'busy'); R('list').innerHTML = ''; show(true);
    let r; try { const x = await fetch('/search?q=' + encodeURIComponent(q), { headers: { 'X-Deck': '1', ...(live ? { 'X-Deck-Live': live() } : {}) }, signal: ctl.signal }); r = await x.json(); if (!x.ok) throw new Error(r.error || 'the Deck server said ' + x.status); }
    catch (e) { if (g !== gen || e.name === 'AbortError') return; el.classList.remove('busy'); last = ''; return status('search failed: ' + esc(e.message || e), 'err'); }
    if (g !== gen) return; el.classList.remove('busy');
    const list = (r.results || []).map(h => ({ h, i: find(h) })), top = Math.max(...list.map(o => o.h.score), 1e-9);
    if (!list.length) { status(`nothing found for “${esc(q)}”`, 'err'); return onResults([], q); }
    status(`<b>${list.length}</b> notes for “${esc(q)}” <span>${(r.ms / 1000).toFixed(1)} s</span>`);
    R('list').innerHTML = list.map(({ h, i }, n) => { const d = i === undefined ? null : docs[i], c = d ? d.c : h.c, k = c ? kc(c) : 'var(--dim)';
      return `<button class="ak-hit${d ? '' : h.id ? ' loose' : ' miss'}" ${d ? `data-i="${i}"` : h.id ? `data-x="${n}"` : 'disabled'} style="--k:${k};--i:${n};--w:${Math.round(h.score / top * 100)}%" title="${esc(h.path)}${d || h.id ? '  ·  click to open' : '  ·  not in the Deck’s snapshot'}${d ? '' : h.id ? '  ·  not a dot in the scene' : ''}">
        <i>${String(n + 1).padStart(2, '0')}</i><span class="t">${esc(d ? d.t : h.t || h.path.split('/').pop())}</span>${c ? `<span class="tg-chip">${esc((nice[c] || c).toUpperCase())}</span>` : ''}<em>${h.score.toFixed(2)}</em><u></u></button>`; }).join('');
    R('list').querySelectorAll('.ak-hit[data-i]').forEach(b => b.onclick = () => onOpen(+b.dataset.i));
    R('list').querySelectorAll('.ak-hit[data-x]').forEach(b => b.onclick = () => onOpenLoose && onOpenLoose(list[+b.dataset.x].h));
    onResults(list.map(o => o.i).filter(i => i !== undefined), q); }
  box.addEventListener('input', () => { clearTimeout(timer); R('kbd').style.display = box.value ? 'none' : ''; el.classList.toggle('typed', !!box.value);
    if (!box.value.trim()) return clear(true); if (box.value.trim().length >= 3) timer = setTimeout(() => search(box.value), 650); });
  box.addEventListener('keydown', e => { if (e.key === 'Enter') { e.preventDefault(); search(box.value); }
    else if (e.key === 'Escape' && box.value) { e.preventDefault(); e.stopPropagation(); clear(); R('kbd').style.display = ''; el.classList.remove('typed'); } });
  R('x').onclick = () => { clear(); R('kbd').style.display = ''; el.classList.remove('typed'); box.focus(); };
  R('chips').querySelectorAll('.chip2').forEach(b => b.onclick = () => { box.value = b.dataset.q; R('kbd').style.display = 'none'; el.classList.add('typed'); search(b.dataset.q); });
  addEventListener('resize', () => res.classList.contains('on') && side());
  return { search, clear, chips: () => [...R('chips').querySelectorAll('.chip2')], focus: () => box.focus(), place: () => res.classList.contains('on') && side(),
    // another part of the Deck lit up notes (the voice's answer): the chips and list step aside
    quiet() { el.querySelectorAll('.ak-chips .chip2').forEach(x => x.classList.remove('on')); } };
}
