// The Deck's own window (plan: brief 24 part 2). One window, no menu, one copy at a time. It starts the Deck's server
// (server/server.py) as its child, or uses one that already answers /health, and stops its own server when the window closes.
// Loopback only: the window shows only http://127.0.0.1:<port>, web links open in the normal browser, new windows are refused.
// Env: DECK_PORT (8765), DECK_DEBUG=1 (dev tools), DECK_USER_DATA (the app's folder, ~/.config/second-brain-deck),
// F11 full screen. The window's size and place are kept in window.json in the app's folder. The window class (Wayland app_id)
// is second-brain-deck, for a Hyprland rule later. Only the microphone may be used, only by the Deck's own page.
// DECK_TEST_HIDDEN=1 (tests: a window that is never shown, fixed size, web links only logged, errors printed instead of asked).
// Privacy: no crash reporter and no auto-updater are started (Electron sends neither by itself), spell-check is off (it would
// download dictionaries), and every request that is not the Deck's own server is blocked.
'use strict';
const { app, BrowserWindow, Menu, dialog, screen, session, shell } = require('electron');
const { spawn } = require('child_process'), fs = require('fs'), http = require('http'), path = require('path');
const { allowPermission, fitBounds, linkAction, mayLoad } = require('./rules');

const VIZ = path.resolve(__dirname, '..'), PORT = Number(process.env.DECK_PORT || 8765), ORIGIN = `http://127.0.0.1:${PORT}`;
const HIDDEN = process.env.DECK_TEST_HIDDEN === '1', DEBUG = process.env.DECK_DEBUG === '1', TITLE = 'Second Brain Deck';
const say = m => console.error('deck: ' + m);

app.setName('second-brain-deck');
app.setDesktopName('second-brain-deck.desktop');   // the window class / Wayland app_id: second-brain-deck
app.setPath('userData', process.env.DECK_USER_DATA || path.join(app.getPath('appData'), 'second-brain-deck'));
app.commandLine.appendSwitch('ozone-platform-hint', 'auto');
app.enableSandbox();
Menu.setApplicationMenu(null);
if (!app.requestSingleInstanceLock()) { say('already open: brought that window to the front'); app.exit(0); return; }

let win = null, child = null, childErr = '';

// GET /health: 'deck' (the Deck's server, with its pid), 'other' (something else answers on the port), 'free' (nobody)
const health = () => new Promise(done => {
  const r = http.get({ host: '127.0.0.1', port: PORT, path: '/health', timeout: 1500 }, res => {
    let b = ''; res.setEncoding('utf8'); res.on('data', d => { b += d; });
    res.on('end', () => { try { const h = JSON.parse(b); done(h.app === 'second-brain-deck' && h.ready ? { state: 'deck', pid: h.pid } : { state: 'other' }); } catch { done({ state: 'other' }); } });
  });
  r.on('timeout', () => r.destroy(new Error('timeout')));
  r.on('error', e => done({ state: e.code === 'ECONNREFUSED' ? 'free' : 'other' }));
});
const wait = ms => new Promise(r => setTimeout(r, ms));

function fail(msg) {
  if (HIDDEN) say(msg); else dialog.showErrorBox(TITLE, msg);
  stopServer(); app.exit(1);
}

async function startServer() {
  child = spawn('python3', ['-I', path.join(VIZ, 'server', 'server.py')], { cwd: VIZ, env: { ...process.env, DECK_PORT: String(PORT), DECK_PARENT_WATCH: '1' },
    stdio: ['pipe', 'ignore', 'pipe'] });   // its stdin is our pipe: when this app is gone, the server sees it close and exits
  child.stderr.setEncoding('utf8'); child.stderr.on('data', d => { childErr = (childErr + d).slice(-2000); });
  child.on('error', e => { childErr += String(e); });
  for (let i = 0; i < 150; i++) {   // up to ~20 s
    if (child.exitCode !== null || child.signalCode) throw new Error(`the Deck's server stopped while starting:\n${childErr.trim().split('\n').slice(-6).join('\n')}`);
    const h = await health();
    if (h.state === 'deck' && h.pid === child.pid) return;
    await wait(130);
  }
  throw new Error("the Deck's server did not answer within 20 seconds");
}

function stopServer() {
  if (!child || child.exitCode !== null) return;
  try { child.stdin.end(); } catch {}
  child.kill('SIGTERM');
}

// the port: reuse a Deck server that already answers; if another program has it, ask (it is never stopped from here)
async function server() {
  for (;;) {
    const h = await health();
    if (h.state === 'deck') { say(`using the Deck server already running on ${PORT} (pid ${h.pid})`); return; }
    if (h.state === 'free') return startServer();
    const msg = `Port ${PORT} is used by another program (perhaps the old Deck prototype). The Deck will not stop it.\n\nStop that program, then press Try again.`;
    if (HIDDEN) throw new Error(`port ${PORT} is used by another program; not starting`);
    const { response } = await dialog.showMessageBox({ type: 'warning', title: TITLE, message: msg, buttons: ['Try again', 'Quit'], defaultId: 0, cancelId: 1 });
    if (response === 1) { app.exit(0); return new Promise(() => {}); }
  }
}

function outside(url) {   // a link or a new window that is not the Deck's own page
  if (linkAction(url, ORIGIN) !== 'browser') return say('refused: ' + url.slice(0, 200));
  if (HIDDEN) return say('would open in the browser: ' + url);
  shell.openExternal(url).catch(() => {});
}

// window.json: the last size and place (and whether it was maximized), read back made safe for today's screens
const STATE = () => path.join(app.getPath('userData'), 'window.json');
function savedState() { try { return JSON.parse(fs.readFileSync(STATE(), 'utf8')); } catch { return null; } }
function saveState() {
  if (!win || win.isDestroyed()) return;
  const b = win.getNormalBounds(), f = STATE(), tmp = f + '.tmp';
  try { fs.writeFileSync(tmp, JSON.stringify({ x: b.x, y: b.y, width: b.width, height: b.height, maximized: win.isMaximized() }) + '\n'); fs.renameSync(tmp, f); }
  catch (e) { say('could not save the window size: ' + e.message); }
}

function openWindow() {
  const saved = savedState();
  win = new BrowserWindow({ ...fitBounds(saved, screen.getAllDisplays().map(d => d.workArea)), show: false, title: TITLE, backgroundColor: '#05080c', autoHideMenuBar: true,
    webPreferences: { contextIsolation: true, nodeIntegration: false, sandbox: true, spellcheck: false, webviewTag: false, devTools: DEBUG || HIDDEN, ...(HIDDEN ? { offscreen: true } : {}) } });
  const wc = win.webContents;
  wc.setWindowOpenHandler(({ url }) => { outside(url); return { action: 'deny' }; });
  const guard = (e, url) => { if (linkAction(url, ORIGIN) !== 'stay') { e.preventDefault(); outside(url); } };
  wc.on('will-navigate', guard); wc.on('will-redirect', guard);
  wc.on('will-attach-webview', e => e.preventDefault());
  wc.on('render-process-gone', (e, d) => say('page process gone: ' + d.reason));
  wc.on('before-input-event', (e, k) => {
    if (k.type !== 'keyDown') return;
    if (k.key === 'F11') { e.preventDefault(); win.setFullScreen(!win.isFullScreen()); }
    if (k.key === 'F12' && DEBUG) { e.preventDefault(); wc.toggleDevTools(); }
  });
  if (DEBUG) wc.once('did-finish-load', () => wc.openDevTools({ mode: 'detach' }));
  if (!HIDDEN) win.once('ready-to-show', () => { if (saved && saved.maximized) win.maximize(); win.show(); });
  let later = null; const soon = () => { clearTimeout(later); later = setTimeout(saveState, 500); };   // also kept after a crash
  win.on('resize', soon); win.on('move', soon); win.on('close', () => { clearTimeout(later); saveState(); });
  if (HIDDEN) win.setContentSize(2560, 1380);   // a hidden window starts at 1x1
  win.on('closed', () => { win = null; });
  win.loadURL(ORIGIN + '/deck.html').then(() => { if (HIDDEN) win.setContentSize(2560, 1380); },
    e => { if (e.code !== 'ERR_ABORTED') fail("the Deck's page did not load: " + e.message); });   // aborted = a newer load (a reload) took over
}

app.on('second-instance', () => {
  say('second start: focused the open window');
  if (!win) return;
  if (win.isMinimized()) win.restore();
  if (!HIDDEN) win.show();
  win.focus();
});
app.on('window-all-closed', () => app.quit());
app.on('will-quit', stopServer);
process.on('exit', stopServer);

app.whenReady().then(async () => {
  const ses = session.defaultSession;   // the microphone for the Deck's own page; everything else (camera, notifications, ...) refused
  ses.setPermissionRequestHandler((wc, perm, done, d) => { const ok = allowPermission(perm, d.requestingUrl, d, ORIGIN); if (!ok) say('refused permission: ' + perm + (d.mediaTypes ? ' ' + d.mediaTypes.join('+') : '')); done(ok); });
  ses.setPermissionCheckHandler((wc, perm, origin, d) => allowPermission(perm, (d && d.requestingUrl) || origin, d, ORIGIN));
  ses.setDevicePermissionHandler(() => false);   // no USB, serial or HID devices
  ses.webRequest.onBeforeRequest((d, done) => {   // nothing leaves the computer
    const ok = mayLoad(d.url, ORIGIN);
    if (!ok) say('blocked a request: ' + d.url.slice(0, 200));
    done({ cancel: !ok });
  });
  try { await server(); openWindow(); say('ready on ' + ORIGIN); }
  catch (e) { fail(String(e && e.message || e)); }
});
