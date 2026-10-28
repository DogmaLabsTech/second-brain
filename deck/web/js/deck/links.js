
// ---- note links: find the note a [[wiki link]] or a relative .md link points to (path first, then file name, then title;
// the same collection wins when several match). -1 = not in the brain.
export const nk = s => s.toLowerCase().replace(/\.md$/, '').replace(/[^\p{L}\p{N}]+/gu, '-').replace(/^-|-$/g, ''), pk = p => p.split('/').map(nk).join('/');
export const nh = s => s.toLowerCase().replace(/[^\p{L}\p{N}]+/gu, ''), un = s => s.replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&quot;/g, '"').replace(/&amp;/g, '&');
export const byPath = new Map(), byAny = new Map(), byName = new Map(), byTitle = new Map(), add = (m, k, i) => { if (!m.has(k)) m.set(k, []); m.get(k).push(i); };
DOCS.forEach((d, i) => { byPath.set(d.c + ':' + pk(d.p), i); add(byAny, pk(d.p), i); add(byName, nk(d.p.split('/').pop()), i); add(byTitle, nk(d.t), i); });
export const pick = (l, c) => l && (l.find(i => DOCS[i].c === c) ?? [...l].sort((a, b) => DOCS[a].p.length - DOCS[b].p.length)[0]);
function resolve(t, ctx, rel) { t = t.trim(); if (!t) return ctx ? ctx.i : -1; const c = ctx && ctx.c, dir = ctx ? ctx.p.split('/').slice(0, -1) : [];
  const norm = parts => { const o = []; for (const s of parts) { if (s === '..') o.pop(); else if (s && s !== '.') o.push(s); } return o.join('/'); };
  const tries = rel || t.includes('/') ? [...(t.startsWith('/') ? [] : [norm([...dir, ...t.split('/')])]), norm(t.split('/'))] : [];
  for (const p of tries) { const i = byPath.get(c + ':' + pk(p)); if (i !== undefined) return i; const l = pick(byAny.get(pk(p)), c); if (l !== undefined) return l; }
  return pick(byName.get(nk(t.split('/').pop())), c) ?? pick(byTitle.get(nk(t)), c) ?? -1; }
const nlink = (i, txt, h, emb) => i < 0 ? `<span class="nl miss${emb ? ' emb' : ''}">${txt}</span>` : `<a class="nl${emb ? ' emb' : ''}" data-i="${i}" data-h="${esc(h || '')}">${txt}</a>`;
function wiki(a, emb, ctx) { const k = a.indexOf('|'), tg = (k < 0 ? a : a.slice(0, k)).replace(/\\$/, ''), al = k < 0 ? '' : a.slice(k + 1).trim(), [nm, ...hs] = tg.split('#'), h = hs.join('#').replace(/^\^.*/, '').trim();
  return nlink(resolve(nm, ctx), esc(al || (nm.trim() ? nm.trim() + (h ? ' › ' + h : '') : h)), h, emb); }
let mdCtx = null;   // the note being rendered ({ i, c, p }), so links resolve from its folder and collection
export function mdRender(src, top = true, ctx = mdCtx) {
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
