// Shared bits for the Deck (a classic script: globals the modules use). Everything stays on this computer.
const COL = {
  'agent-os': '#ff7a45', business: '#ffd23f', chats: '#4d9bff', codex: '#8b7bff', computer: '#19d3c5',
  content: '#ff5fa2', days: '#f1ecc8', experiments: '#b8f27c', hermes: '#8a94a6', memory: '#ce9143', plans: '#6ee7ff',
  pm: '#ff4d5e', projects: '#5cd65c'
};
const NICE = {
  'agent-os': 'Agent OS', business: 'Business', chats: 'Old chats', codex: 'Codex chats', computer: 'Computer',
  content: 'Content', days: 'Day pages', experiments: 'Experiments', hermes: 'Hermes', plans: 'Plans',
  pm: 'Project manager', projects: 'Projects', memory: 'Agent memory'
};
const DOCS = BRAIN.docs;
// a collection this file does not know yet (data.js is rebuilt by the desk) still gets a neutral colour, a name and a place in every view
for (const d of DOCS) if (!COL[d.c]) { COL[d.c] = '#9aa6b2'; NICE[d.c] = d.c.replace(/[-_]+/g, ' ').replace(/^./, m => m.toUpperCase()); }
const COLS = Object.keys(COL).filter(c => DOCS.some(d => d.c === c))
  .sort((a, b) => DOCS.filter(d => d.c === b).length - DOCS.filter(d => d.c === a).length);
function ago(d) {
  const t = new Date(), days = Math.round((Date.UTC(t.getFullYear(), t.getMonth(), t.getDate(), 12) - new Date(d + 'T12:00:00Z')) / 864e5);
  return days <= 0 ? 'today' : days === 1 ? 'yesterday' : days < 60 ? days + ' days ago' : Math.round(days / 30) + ' months ago';
}
const esc = s => String(s).replace(/[&<>"]/g, m => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[m]));
function fit(cv) {
  const dpr = Math.min(2, devicePixelRatio || 1), r = cv.getBoundingClientRect();
  cv.width = r.width * dpr; cv.height = r.height * dpr; cv.getContext('2d').setTransform(dpr, 0, 0, dpr, 0, 0);
  return [r.width, r.height];
}
