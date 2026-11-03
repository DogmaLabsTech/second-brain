// Smoke test of the Deck app (app/main.js) with a window that is never shown. It starts Electron on the test port 8797
// (DECK_TEST_PORT; never the real 8765), with fake media devices (no real mic), muted sound and a fresh app folder, and drives the page
// over the DevTools protocol. It needs this computer's data.js (the private map), so run it here: CRABBOX_LOCAL=1 node tests/smoke.mjs
// Checks: page, WebGL, 13 sections, all notes, no page errors; links and requests; start twice = one window; server gone after close;
// no orphan after a forced kill; an already running Deck server is reused and left running; another program on the port is not touched.
import { spawn } from 'node:child_process';
import fs from 'node:fs';
import net from 'node:net';
import os from 'node:os';
import path from 'node:path';

const DECK_DIR = path.resolve(import.meta.dirname, '..'), PORT = Number(process.env.DECK_TEST_PORT || 8797), CDP = PORT + 1000;
const ELECTRON = path.join(DECK_DIR, 'node_modules/electron/dist/electron');
const OUT = process.env.DECK_SMOKE_OUT || fs.mkdtempSync(path.join(os.tmpdir(), 'deck-smoke-'));
const NOTES = Number(process.env.DECK_SMOKE_NOTES || 2385), SECTIONS = 13;
const sleep = ms => new Promise(r => setTimeout(r, ms));
const results = [];
const check = (name, ok, info) => { results.push({ name, ok: !!ok, info }); console.log(`${ok ? 'ok  ' : 'FAIL'} ${name}${info === undefined ? '' : '  ' + JSON.stringify(info)}`); };
const until = async (fn, ms, step = 200) => { const end = Date.now() + ms; for (;;) { const v = await fn(); if (v) return v; if (Date.now() > end) return null; await sleep(step); } };
const alive = pid => { try { process.kill(pid, 0); return true; } catch { return false; } };
const health = () => fetch(`http://127.0.0.1:${PORT}/health`).then(r => r.json()).catch(() => null);
const portFree = p => new Promise(done => { const s = net.connect(p, '127.0.0.1'); s.on('connect', () => { s.destroy(); done(false); }); s.on('error', () => done(true)); });

function launch(userData, { cdp = true } = {}) {
  const args = [DECK_DIR, '--ozone-platform=headless', '--use-fake-device-for-media-stream', '--mute-audio',
    ...(cdp ? [`--remote-debugging-port=${CDP}`, '--remote-debugging-address=127.0.0.1'] : [])];
  const p = spawn(ELECTRON, args, { env: { ...process.env, DECK_PORT: String(PORT), DECK_TEST_HIDDEN: '1', DECK_USER_DATA: userData }, stdio: ['ignore', 'pipe', 'pipe'] });
  p.log = ''; for (const s of [p.stdout, p.stderr]) s.on('data', d => { p.log += d; });
  p.done = new Promise(r => p.on('exit', (code, sig) => r({ code, sig })));
  return p;
}
const ended = (p, ms) => Promise.race([p.done, sleep(ms).then(() => null)]);
const pages = () => fetch(`http://127.0.0.1:${CDP}/json/list`).then(r => r.json()).then(l => l.filter(t => t.type === 'page')).catch(() => null);

async function devtools(ws) {   // a tiny DevTools-protocol client
  const sock = new WebSocket(ws), wait = new Map(), events = []; let n = 0;
  await new Promise((ok, bad) => { sock.onopen = ok; sock.onerror = bad; });
  sock.onclose = e => { if (process.env.DECK_SMOKE_DEBUG) console.log("devtools closed", e.code, e.reason); for (const r of wait.values()) r({ error: "closed" }); wait.clear(); };
  sock.onmessage = m => { const o = JSON.parse(m.data); if (o.id && wait.has(o.id)) { wait.get(o.id)(o); wait.delete(o.id); } else events.push(o); };
  const send = (method, params = {}) => new Promise(r => { const id = ++n; wait.set(id, r); sock.send(JSON.stringify({ id, method, params })); });
  const run = async expr => { const r = await send('Runtime.evaluate', { expression: expr, awaitPromise: true, returnByValue: true }); return r.result?.result?.value ?? r.result?.exceptionDetails?.text; };
  return { send, run, events, close: () => sock.close() };
}

async function main() {
  check(`ports ${PORT} and ${CDP} are free (nothing else would answer instead)`, await portFree(PORT) && await portFree(CDP));
  if (results.some(r => !r.ok)) return;
  const home = fs.mkdtempSync(path.join(os.tmpdir(), 'deck-app-'));

  // 1. the page in the app
  const app = launch(home);
  const page = await until(async () => (await pages())?.find(t => t.url.endsWith('/deck.html')), 30000);
  check('the window shows the Deck page', page, page?.url);
  if (process.env.DECK_SMOKE_DEBUG) app.done.then(x => console.log("app ended", x, app.log));
  if (!page) { console.log(app.log); app.kill('SIGKILL'); return; }
  const h = await health();
  check('the app started its own server (answers /health)', h?.app === 'second-brain-deck' && alive(h.pid), h);
  const t = await devtools(page.webSocketDebuggerUrl);
  await t.send('Runtime.enable'); await t.send('Log.enable'); await t.send('Page.enable');
  await t.send('Page.reload', { ignoreCache: true });   // again, now that errors are being listened to
  await sleep(10000);
  const info = await t.run(`(() => { const c = document.createElement('canvas'), gl = c.getContext('webgl2') || c.getContext('webgl');
    return { title: document.title, webgl: !!gl, stage: !!document.querySelector('#stage canvas'), sections: document.querySelectorAll('#groups > *').length,
      notes: window.BRAIN && window.BRAIN.docs ? window.BRAIN.docs.length : null, voice: !!document.getElementById('voicep'), secure: isSecureContext, size: [innerWidth, innerHeight] }; })()`);
  check('page loads (title)', info?.title === 'Brain · Deck', info?.title);
  check('WebGL works and the scene draws', info?.webgl && info?.stage);
  check(`${SECTIONS} sections listed`, info?.sections === SECTIONS, info?.sections);
  check(`${NOTES} notes loaded`, info?.notes === NOTES, info?.notes);
  check('voice panel there, secure page (mic allowed by the browser)', info?.voice && info?.secure);
  const shot = await t.send('Page.captureScreenshot', { format: 'png' });
  if (shot.result?.data) fs.writeFileSync(path.join(OUT, 'smoke-deck.png'), Buffer.from(shot.result.data, 'base64'));
  const errors = t.events.filter(e => e.method === 'Runtime.exceptionThrown' || (e.method === 'Runtime.consoleAPICalled' && e.params.type === 'error')
    || (e.method === 'Log.entryAdded' && e.params.entry.level === 'error'))
    .map(e => e.params.exceptionDetails?.exception?.description || e.params.exceptionDetails?.text || e.params.entry?.text || JSON.stringify(e.params.args?.map(a => a.value ?? a.description)));
  check('no page errors', errors.length === 0, errors.slice(0, 5));

  // 2. links and requests
  check('a web link in a new window: refused here, handed to the browser',
    await t.run(`window.open('https://example.com/smoke') === null`) === true && /would open in the browser: https:\/\/example\.com\/smoke/.test(app.log));
  check('a file: or mailto: link: refused, not opened anywhere (web links only)',   // Chromium already stops file: before the app sees it
    await t.run(`[window.open('file:///etc/hostname'), window.open('mailto:x@example.com')].every(w => w === null)`) === true
      && /refused: mailto:x@example\.com/.test(app.log) && !/browser: (file|mailto):/.test(app.log));
  await t.run(`location.href = 'https://example.org/nav'; 1`); await sleep(1500);
  check('leaving the page for a web address: stays on the Deck, the browser gets the link',
    String(await t.run('location.href')).endsWith('/deck.html') && /would open in the browser: https:\/\/example\.org\/nav/.test(app.log));
  check('a request to the internet is blocked (nothing leaves the computer)',
    await t.run(`fetch('https://example.net/x').then(() => 'loaded', () => 'blocked')`) === 'blocked' && /blocked a request: https:\/\/example\.net\/x/.test(app.log));

  // 2b. permissions (fake media devices: no real mic is opened)
  const gum = c => `navigator.mediaDevices.getUserMedia(${c}).then(s => { s.getTracks().forEach(x => x.stop()); return 'allowed'; }, e => e.name)`;
  check('microphone: allowed for the Deck', await t.run(gum('{ audio: true }')) === 'allowed');
  check('mic names readable after that (the permission check)', await t.run(`navigator.mediaDevices.enumerateDevices().then(l => l.filter(d => d.kind === 'audioinput').every(d => d.label))`) === true);
  check('camera: refused', await t.run(gum('{ video: true }')) === 'NotAllowedError');
  check('microphone + camera together: refused', await t.run(gum('{ audio: true, video: true }')) === 'NotAllowedError');
  check('screen sharing: refused', /NotAllowed|NotSupported/.test(await t.run(`navigator.mediaDevices.getDisplayMedia({ video: true }).then(() => 'allowed', e => e.name)`)));
  check('notifications: refused', await t.run(`Notification.requestPermission()`) === 'denied');
  check('location: refused', await t.run(`new Promise(r => navigator.geolocation.getCurrentPosition(() => r('allowed'), e => r(e.code)))`) === 1);
  // F11 is not checked here: keys sent over the DevTools protocol skip the app's key hook (before-input-event). <user>'s check.

  // 3. start twice = one window
  const two = launch(home, { cdp: false }), twoEnd = await ended(two, 15000);
  check('a second start ends at once by itself', twoEnd && twoEnd.code === 0, twoEnd);
  check('the first window was brought forward', /second start: focused the open window/.test(app.log));
  check('still exactly one window', (await pages())?.length === 1);

  // 4. closing the window stops the server
  await t.send('Page.close').catch(() => {}); t.close();
  const end = await ended(app, 15000);
  check('closing the window quits the app', end && end.code === 0, end);
  check("the app's server is gone after close", await until(() => !alive(h.pid), 5000), h?.pid);
  check('the port is free again', await portFree(PORT));
  let ws = null; try { ws = JSON.parse(fs.readFileSync(path.join(home, 'window.json'), 'utf8')); } catch {}
  check("the window's size is remembered in the app's folder (window.json)", ws && ws.width === 2560 && ws.height === 1380, ws);
  fs.writeFileSync(path.join(OUT, 'app-log-1.txt'), app.log);

  // 5. a forced kill leaves no orphan server
  const k = launch(home, { cdp: false });
  const kh = await until(async () => { const x = await health(); return x && /ready on/.test(k.log) && x; }, 30000);
  check('started again (for the forced kill)', kh, kh?.pid);
  k.kill('SIGKILL'); await ended(k, 5000);
  check('after kill -9 of the app its server exits by itself', kh && await until(() => !alive(kh.pid), 5000), kh?.pid);
  check('the port is free again', await until(() => portFree(PORT), 3000));

  // 6. a Deck server that already runs is used, and left running
  const mine = spawn('python3', ['-I', path.join(DECK_DIR, 'server/server.py')], { env: { ...process.env, DECK_PORT: String(PORT) }, stdio: ['pipe', 'ignore', 'ignore'] });
  await until(health, 15000);
  const r = launch(home);
  const rp = await until(async () => (await pages())?.find(x => x.url.endsWith('/deck.html')), 30000);
  check('an already running Deck server is reused (no second one)', rp && /using the Deck server already running/.test(r.log) && (await health())?.pid === mine.pid);
  if (rp) { const rt = await devtools(rp.webSocketDebuggerUrl); await rt.send('Page.close').catch(() => {}); rt.close(); }
  await ended(r, 15000);
  check('...and is left running after the app closes', alive(mine.pid) && (await health())?.pid === mine.pid);
  mine.kill(); await until(() => portFree(PORT), 5000);

  // 7. another program on the port: the app stops with a message, the program is not touched
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'deck-other-'));
  const other = spawn('python3', ['-I', '-m', 'http.server', String(PORT), '--bind', '127.0.0.1', '--directory', dir], { stdio: 'ignore' });
  await until(async () => !(await portFree(PORT)), 10000);
  const o = launch(home, { cdp: false }), oEnd = await ended(o, 20000);
  check('another program on the port: the app does not start', oEnd && oEnd.code === 1 && /used by another program/.test(o.log), oEnd);
  check('...and that program is left running', alive(other.pid));
  other.kill(); await until(() => portFree(PORT), 5000);
  fs.rmSync(dir, { recursive: true, force: true });
  if (!process.env.DECK_SMOKE_KEEP) fs.rmSync(home, { recursive: true, force: true });
}

await main();
fs.writeFileSync(path.join(OUT, 'smoke.json'), JSON.stringify(results, null, 1));
const bad = results.filter(r => !r.ok).length;
console.log(`${results.length - bad}/${results.length} ok · results and screenshot in ${OUT}`);
process.exit(bad ? 1 : 0);
