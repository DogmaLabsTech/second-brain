import { makeTimeline } from '../../timeline.js';
import { NOW } from '../../hud.js';
import { makeAsk } from '../../ask.js';
import { movable } from '../../movable.js';
import { KC, RD, S, addLabel, age, asking, byPath, cancelEdit, clearLabels, closeReader, editing, exitEdit, go, histGo, invertKey, keepEditing, liveNonce, liveOwn, lock, loose, openReader, pk, pvHide, pvI, readerOpen, refresh, saveEdit, say, settings, skins, startEdit, toggleLeft, unlock, visible } from '../deck-main.js';
// 05 Timeline and 06 Ask: self-contained panels (timeline.js, ask.js), both movable by their title bar (movable.js)
export let hits = null;
export const tl = makeTimeline(RD('tlp'), { ages: DOCS.map(age), NOW, count: d => DOCS.filter((x, i) => age(x) >= d && visible(i)).length, onChange: c => { S.cutoff = c; refresh(); } });
addEventListener('keydown', e => { if (e.target.id === 'q') { if (e.key === 'Escape') e.target.blur(); return; }
  if (e.key === 'Escape' && pvI >= 0) { e.preventDefault(); S.pickQuiet = [S.mx, S.my]; return pvHide(); }   // stays shut until the mouse moves
  if (editing) { const k = e.key.toLowerCase(); if ((e.ctrlKey || e.metaKey) && k === 's') { e.preventDefault(); saveEdit(); } else if (e.key === 'Escape') { e.preventDefault(); asking ? keepEditing() : cancelEdit(); } else if (asking && k === 'd' && e.target.id !== 'rde') { e.preventDefault(); exitEdit(); } return; }
  if (e.altKey && readerOpen && (e.key === 'ArrowLeft' || e.key === 'ArrowRight')) { e.preventDefault(); return histGo(e.key === 'ArrowLeft' ? -1 : 1); }
  if (e.ctrlKey || e.metaKey || e.altKey) return; if (e.key === '/') { e.preventDefault(); document.getElementById('q').focus(); } else if (e.key === '1') go('map'); else if (e.key === '2') go('tunnel'); else if (e.key === '3') go('radar'); else if (e.key.toLowerCase() === 't') toggleLeft(); else if (e.key.toLowerCase() === 'k') { skins.next(e.shiftKey ? -1 : 1); say('SKIN  ›  ' + skins.label.toUpperCase()); } else if (e.key.toLowerCase() === 'i') invertKey(); else if (e.key === ',') settings(); else if (e.key.toLowerCase() === 'e' && readerOpen) { e.preventDefault(); startEdit(); } else if (e.key === 'Escape') { if (readerOpen) closeReader(); else unlock(); } else if (e.key === 'Enter' && S.sel >= 0 && !readerOpen) openReader(S.sel); });
export const ask = makeAsk(RD('askp'), { chips: Object.keys(BRAIN.asks), docs: DOCS, kc: KC, nice: NICE, esc, find: h => h.c ? byPath.get(h.c + ':' + pk(h.p)) : undefined, onOpen: i => lock(i), onOpenLoose: h => openReader(loose(h)),
  live: () => liveNonce(),
  onResults: (list, q) => { hits = list.length ? new Set(list) : null; refresh(); liveOwn({ q, who: 'Deck', kind: 'search', list }); if (!list.length) return; if (S.sel < 0) { clearLabels(); list.forEach(i => addLabel(i, DOCS[i].t)); } say('FOUND ' + list.length + ' NOTES  ›  “' + q.toUpperCase() + '”'); },
  onClear: () => { hits = null; if (S.sel < 0) clearLabels(); refresh(); } });
const moveTl = movable(RD('tlp'), { key: 'timeline', onMove: () => ask.place() }), moveAsk = movable(RD('askp'), { key: 'ask', onMove: () => ask.place() });
