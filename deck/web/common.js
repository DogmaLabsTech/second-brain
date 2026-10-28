// Shared bits for the brain prototypes. Everything stays on this computer.
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
// a collection this file does not know yet (data.js is rebuilt by the desk) still gets a neutral colour, a name and a place in every view (brief 23)
for (const d of DOCS) if (!COL[d.c]) { COL[d.c] = '#9aa6b2'; NICE[d.c] = d.c.replace(/[-_]+/g, ' ').replace(/^./, m => m.toUpperCase()); }
const COLS = Object.keys(COL).filter(c => DOCS.some(d => d.c === c))
  .sort((a, b) => DOCS.filter(d => d.c === b).length - DOCS.filter(d => d.c === a).length);
const hexRGB = h => [1, 3, 5].map(i => parseInt(h.slice(i, i + 2), 16));
const sprites = {};
function sprite(col, size = 64) {
  const key = col + size; if (sprites[key]) return sprites[key];
  const c = document.createElement('canvas'); c.width = c.height = size; const x = c.getContext('2d');
  const [r, g, b] = hexRGB(COL[col] || '#ffffff');
  const gr = x.createRadialGradient(size / 2, size / 2, 0, size / 2, size / 2, size / 2);
  gr.addColorStop(0, `rgba(255,255,255,1)`); gr.addColorStop(.18, `rgba(${r},${g},${b},.95)`);
  gr.addColorStop(.5, `rgba(${r},${g},${b},.28)`); gr.addColorStop(1, `rgba(${r},${g},${b},0)`);
  x.fillStyle = gr; x.fillRect(0, 0, size, size); return sprites[key] = c;
}
function ago(d) {
  const t = new Date(), days = Math.round((Date.UTC(t.getFullYear(), t.getMonth(), t.getDate(), 12) - new Date(d + 'T12:00:00Z')) / 864e5);
  return days <= 0 ? 'today' : days === 1 ? 'yesterday' : days < 60 ? days + ' days ago' : Math.round(days / 30) + ' months ago';
}
const esc = s => String(s).replace(/[&<>"]/g, m => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[m]));
function cardHTML(i, onNb = 'pick') {
  const d = DOCS[i];
  return `<div class="chip" style="--c:${COL[d.c]}">${NICE[d.c]}</div>
  <h3>${esc(d.t)}</h3><div class="path">${esc(d.p)}</div>
  <div class="meta">changed ${ago(d.d)} (${d.d}) · ${d.n} piece${d.n > 1 ? 's' : ''}</div>
  <h4>Closest in meaning</h4>` +
    d.nb.map(j => `<a href="#" class="nb" data-i="${j}" style="--c:${COL[DOCS[j].c]}">${esc(DOCS[j].t)}</a>`).join('');
}
function legendHTML() {
  return COLS.map(c => `<button class="leg" data-c="${c}" style="--c:${COL[c]}"><i></i>${NICE[c]} <b>${DOCS.filter(d => d.c === c).length}</b></button>`).join('');
}
function fit(cv) {
  const dpr = Math.min(2, devicePixelRatio || 1), r = cv.getBoundingClientRect();
  cv.width = r.width * dpr; cv.height = r.height * dpr; cv.getContext('2d').setTransform(dpr, 0, 0, dpr, 0, 0);
  return [r.width, r.height];
}
