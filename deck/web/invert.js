// Inverted palettes (brief 14): every skin gets an inverted twin, made from its own tokens by one function (invert), so new skins get one too.
// Dark skins become light and light skins dark. Not a colour negative: in OKLCH the backgrounds and the text swap lightness (hue and tint kept),
// the accents, the group colours and the scene colours keep their hue and chroma and move only as far in lightness as they must to read on
// the new background (text: WCAG AA 4.5 even over the worst backdrop the glass can blur; accents and dots: 3), then the group colours are pushed
// apart until every pair is easy to tell (CIE76 delta-E 16+). The scene switches drawing mode (glow on dark, ink on light).
// The result is one rule per skin, `[data-skin=<name>]:where([data-inv])`, low enough in specificity that a skin file can override any token
// by hand with `[data-skin=<name>][data-inv]{--tx:...}`. Inverting is turned on by `<html data-inv>` (skins.js). No imports: the probe page uses it too.
const SURF = ['bg1', 'bg2', 'bg3', 'bg-a', 'bg-b', 'glass', 'glass2', 'glass-rd', 'glass-pop', 'surf', 'surf-hi', 'well', 'track', 'halo', 'code-bg', 'warn-bg', 'err-bg'];
const TEXT = ['hi', 'tx-hi', 'tx', 'tx-read', 'dim', 'dim2', 'listen', 'warn-tx', 'err-tx', 'em', 'quote', 'link', 'code-tx', 'line'];
const ACC = ['c', 'amber', 'ok', 'bad', 'violet'], SCENE = ['line', 'sweep', 'slice', 'scan', 'nb', 'shell', 'listen', 'speak', 'think', 'hot', 'err'].map(r => 's-' + r);
export const GROUPS = ['agent-os', 'business', 'chats', 'codex', 'computer', 'content', 'days', 'experiments', 'hermes', 'memory', 'plans', 'pm', 'projects'];
export const TOKENS = [...SURF, ...TEXT, ...ACC, 'on-c', 'shadow', 'inner', 'edge', ...GROUPS.map(g => 'g-' + g), ...SCENE];
// ---- colour maths: sRGB 0..255 (+ alpha 0..1) <-> OKLab / OKLCH, WCAG contrast, CIE76 delta-E (the same measures as t13/contrast.mjs)
const lin = v => { v /= 255; return v <= .04045 ? v / 12.92 : ((v + .055) / 1.055) ** 2.4; }, gam = v => 255 * (v <= .0031308 ? 12.92 * v : 1.055 * v ** (1 / 2.4) - .055);
function toLch([r, g, b]) { r = lin(r); g = lin(g); b = lin(b);
  const l = Math.cbrt(.4122214708 * r + .5363325363 * g + .0514459929 * b), m = Math.cbrt(.2119034982 * r + .6806995451 * g + .1073969566 * b), s = Math.cbrt(.0883024619 * r + .2817188376 * g + .6299787005 * b);
  const L = .2104542553 * l + .793617785 * m - .0040720468 * s, A = 1.9779984951 * l - 2.428592205 * m + .4505937099 * s, B = .0259040371 * l + .7827717662 * m - .808675766 * s;
  return [L, Math.hypot(A, B), Math.atan2(B, A)]; }
function fromLch(L, C, h) { const A = C * Math.cos(h), B = C * Math.sin(h), l = (L + .3963377774 * A + .2158037573 * B) ** 3, m = (L - .1055613458 * A - .0638541728 * B) ** 3, s = (L - .0894841775 * A - 1.291485548 * B) ** 3;
  return [4.0767416621 * l - 3.3077115913 * m + .2309699292 * s, -1.2684380046 * l + 2.6097574011 * m - .3413193965 * s, -.0041960863 * l - .7034186147 * m + 1.707614701 * s]; }
// OKLCH -> sRGB, lowering chroma until the colour fits the screen's gamut (keeps lightness and hue)
function lch(L, C, h) { L = Math.min(1, Math.max(0, L)); let lo = 0, hi = C, rgb = fromLch(L, C, h); const fits = v => v.every(x => x >= -1e-4 && x <= 1.0001);
  if (!fits(rgb)) { for (let k = 0; k < 18; k++) { const mid = (lo + hi) / 2; if (fits(fromLch(L, mid, h))) lo = mid; else hi = mid; } rgb = fromLch(L, lo, h); }
  return rgb.map(x => Math.round(gam(Math.min(1, Math.max(0, x))))); }
const lum = c => .2126 * lin(c[0]) + .7152 * lin(c[1]) + .0722 * lin(c[2]);
export const ratio = (a, b) => { const x = lum(a), y = lum(b); return (Math.max(x, y) + .05) / (Math.min(x, y) + .05); };
export const over = (f, bg) => [0, 1, 2].map(i => f[i] * f[3] + bg[i] * (1 - f[3]));
const lab = c => { const [r, g, b] = c.map(lin), X = (.4124 * r + .3576 * g + .1805 * b) / .95047, Y = .2126 * r + .7152 * g + .0722 * b, Z = (.0193 * r + .1192 * g + .9505 * b) / 1.08883, f = t => t > .008856 ? Math.cbrt(t) : 7.787 * t + 16 / 116; return [116 * f(Y) - 16, 500 * (f(X) - f(Y)), 200 * (f(Y) - f(Z))]; };
export const dE = (a, b) => { const p = lab(a), q = lab(b); return Math.hypot(p[0] - q[0], p[1] - q[1], p[2] - q[2]); };
const hex = c => '#' + [...c.slice(0, 3).map(v => Math.round(v)), Math.round((c[3] ?? 1) * 255)].map(v => v.toString(16).padStart(2, '0')).join('').replace(/ff$/, '');
// lightness swap, separately for "was dark" and "was light" (piecewise linear in OKLab L): page and glass go to the far end, text to the near end
const curve = pts => L => { for (let i = 1; i < pts.length; i++) if (L <= pts[i][0]) { const [a, x] = pts[i - 1], [b, y] = pts[i]; return x + (y - x) * (L - a) / (b - a); } return pts.at(-1)[1]; };
const TO_LIGHT = curve([[0, .99], [.2, .968], [.35, .91], [.6, .56], [.8, .42], [1, .26]]), TO_DARK = curve([[0, .97], [.35, .86], [.55, .68], [.8, .3], [.9, .22], [1, .15]]);
// move a colour's lightness (hue and chroma kept) the least it takes to reach `min` contrast against every backdrop; `dir` -1 darker, +1 lighter
function reach(c, backs, min, dir) { const [L, C, h] = toLch(c), a = c[3] ?? 1, at = x => [...lch(x, C, h), a], worst = x => Math.min(...backs.map(b => ratio(a < 1 ? over(at(x), b) : at(x), b)));
  if (worst(L) >= min) return c; const end = dir < 0 ? 0 : 1; if (worst(end) < min) return at(end);
  let lo = L, hi = end; for (let k = 0; k < 22; k++) { const mid = (lo + hi) / 2; if (worst(mid) >= min) hi = mid; else lo = mid; } return at(hi); }
const shift = (c, f, cmax = 9) => { const [L, C, h] = toLch(c); return [...lch(f(L), Math.min(C, cmax), h), c[3] ?? 1]; };
// invert(t, dark): t = { token: [r,g,b,a] } of one skin (as the browser resolved it), dark = the skin is dark now. Returns { token: css value }.
export function invert(t, dark) {
  const toLight = dark, f = toLight ? TO_LIGHT : TO_DARK, dir = toLight ? -1 : 1, o = {}, n = {};
  for (const k of SURF) n[k] = shift(t[k], f, toLight ? .06 : .07);
  const bg2 = n.bg2.slice(0, 3), glassOn = g => over(n[g], bg2), worstBack = toLight ? [0, 0, 0] : [255, 255, 255];
  const glassAll = ['glass', 'glass2', 'glass-rd', 'glass-pop'], backs = gs => gs.flatMap(g => [glassOn(g), over(n[g], worstBack)]), typ = gs => gs.map(glassOn);
  for (const k of TEXT) n[k] = shift(t[k], f);
  const fix = (k, bs, min) => n[k] = reach(n[k], bs, min, dir);
  for (const k of ['hi', 'tx-hi', 'tx', 'tx-read']) fix(k, backs(glassAll), 4.7);
  fix('dim2', typ(['glass', 'glass2']), 4.7); fix('dim', typ(['glass', 'glass2']), 3.2); fix('listen', typ(['glass', 'glass2']), 4.7);
  for (const k of ['em', 'quote', 'link', 'code-tx']) fix(k, backs(['glass-rd', 'glass-pop']), 4.7);
  if (n['code-bg'][3] < 1) n['code-bg'] = [...over(n['code-bg'], glassOn('glass-rd')), 1];   // a see-through code background (Aurora): made solid, as it looks on the reader
  fix('code-tx', [n['code-bg'].slice(0, 3), over(n['code-bg'], glassOn('glass-rd'))], 4.7);
  for (const [tx, bg] of [['warn-tx', 'warn-bg'], ['err-tx', 'err-bg']]) fix(tx, [n[bg].slice(0, 3), over(n[bg], glassOn('glass-pop'))], 4.7);
  n.line = [...n.line.slice(0, 3), Math.min(1, (t.line[3] ?? 1) * (toLight ? .9 : 1.1))];
  // accents: same hue, only as much lighter/darker as needed: 3.3:1 on the side-panel glass, and text on an accent fill (--on-c) stays 4.5:1
  n['on-c'] = toLight ? [255, 255, 255, 1] : shift(n.bg3, L => Math.min(L, .16));
  for (const k of ACC) n[k] = reach(t[k], [glassOn('glass'), glassOn('glass2'), n['on-c'].slice(0, 3)], k === 'c' ? 4.6 : 3.3, dir);
  n['on-c'] = reach(n['on-c'], [n.c.slice(0, 3)], 4.6, -dir);
  n.shadow = toLight ? [...shift(t.bg2, () => .25).slice(0, 3), .18] : [0, 0, 0, .62];
  n.inner = toLight ? [255, 255, 255, .8] : [...n.c.slice(0, 3), .12];
  n.edge = toLight ? [0, 0, 0, 0] : [...n.bg3.slice(0, 3), 1];
  // the note groups: same hue and chroma, lightness only as far as dots need to read on the page (against all three background stops)
  const page = ['bg1', 'bg2', 'bg3'].map(k => n[k].slice(0, 3)), G = GROUPS.map(g => 'g-' + g);
  const gMin = toLight ? 3.4 : 4.5;   // (on dark the group colours are also label text, and light colours have room to spare)
  for (const k of G) n[k] = reach(t[k], page, gMin, dir);
  // ... then pull close pairs apart: the one with room moves further from the page (darker on light, lighter on dark), or the other way while it still reads
  for (let it = 0; it < 400; it++) { let best = [99]; for (let i = 0; i < G.length; i++) for (let j = i + 1; j < G.length; j++) { const v = dE(n[G[i]], n[G[j]]); if (v < best[0]) best = [v, i, j]; }
    if (best[0] >= 16.5) break; const [, i, j] = best, Li = toLch(n[G[i]])[0], Lj = toLch(n[G[j]])[0], [far, near] = (Li < Lj) === toLight ? [i, j] : [j, i];
    const mv = (k, d) => { const [L, C, h] = toLch(n[k]); const L2 = L + d; if (L2 < .2 || L2 > .97) return false; const c = [...lch(L2, C * (d * dir > 0 ? 1.03 : 1), h), 1]; if (Math.min(...page.map(p => ratio(c, p))) < gMin - .15) return false; n[k] = c; return true; };
    if (!mv(G[far], .012 * dir) && !mv(G[near], -.012 * dir)) { const [L, C, h] = toLch(n[G[it % 2 ? i : j]]); n[G[it % 2 ? i : j]] = [...lch(L, C * 1.06 + .004, h), 1]; } }
  for (const k of SCENE) n[k] = reach(t[k], [bg2], k === 's-line' || k === 's-nb' ? 2.6 : 3, dir);
  for (const k in n) o['--' + k] = hex(n[k]);
  Object.assign(o, toLight ? { '--s-blend': 'normal', '--glow': '0', '--s-core': '-.4', '--s-size': '.72', '--s-shell-glow': '.6', '--scan-op': '0', '--vig-op': '.25' }
    : { '--s-blend': 'add', '--glow': '.9', '--s-core': '.5', '--s-size': '1', '--s-shell-glow': '1', '--scan-op': '0', '--vig-op': '.85' });
  return o; }
// read every skin's tokens through a hidden element (the browser resolves hex, rgb() and color-mix()) and build the stylesheet of all inverted twins
export function invertCSS(names) {
  const box = document.createElement('div'), el = document.createElement('i'), cv = document.createElement('canvas'); box.style.display = 'none'; box.append(el); document.body.append(box);
  cv.width = cv.height = 1; const g = cv.getContext('2d', { willReadFrequently: true }); let css = '/*inv v1*/';
  const rgba = s => { el.style.color = ''; el.style.color = s; const c = getComputedStyle(el).color; g.clearRect(0, 0, 1, 1); g.fillStyle = '#000'; g.fillStyle = c; g.fillRect(0, 0, 1, 1); const d = g.getImageData(0, 0, 1, 1).data; return [d[0], d[1], d[2], d[3] / 255]; };
  try { for (const n of names) { box.dataset.skin = n; const cs = getComputedStyle(box), t = {}; for (const k of TOKENS) t[k] = rgba(cs.getPropertyValue('--' + k).trim() || '#808080');
    const o = invert(t, cs.getPropertyValue('--s-blend').trim() !== 'normal'); css += `[data-skin=${n}]:where([data-inv]){${Object.entries(o).map(([k, v]) => k + ':' + v).join(';')}}\n`; } }
  finally { box.remove(); }
  return css; }
