# viz: what is here

The Deck, the 3D map of the second brain (three.js page + a small loopback server). Moved in from the prototype folder
`~/Downloads/agent-notes/brain-prototypes/` on 2026-10-28 (brief 25). The plan it follows: that folder's
`briefs/24-electron-plan-report.md` (nine steps; 1 and 2 done in brief 25, 3 and 4, the Electron window, in brief 26).
When you add, move or retire a file here, update this file in the same commit.

## Current (use these)
- `README.md`: the plain guide for <user>.
- `app/main.js`: the Electron window (start: `app/deck`, after `npm ci` once). One window, no menu, one copy
  (`requestSingleInstanceLock`). Starts `python3 -I server/server.py` with `DECK_PARENT_WATCH=1` and waits for `/health`, or reuses a
  Deck server that already answers; another program on the port: it asks, never kills. Stops its server on close. Only
  `http://127.0.0.1:<port>` in the window, web links to the browser, all other requests blocked, mic-only permissions, `F11`,
  window size in `~/.config/second-brain-deck/window.json`, window class `second-brain-deck` (from `desktopName` in `package.json`).
  Env: `DECK_PORT`, `DECK_DEBUG=1` (dev tools, F12), `DECK_USER_DATA`, `DECK_TEST_HIDDEN=1` (tests only).
- `app/rules.js`: what the window lets through (links, requests, permissions, safe window size); tests `app/test/rules.test.js`:
  `crabbox run -- node --test viz/app/test/rules.test.js`.
- `app/deck`: starts Electron with `--ozone-platform-hint=auto`; extra switches pass on (`--disable-gpu`).
- `tests/smoke.mjs`: the app with a hidden window on test port 8797 (page, WebGL, sections, notes, links, permissions, one copy,
  server stopped after close and after kill -9, reuse, busy port). Needs this computer's data.js: `CRABBOX_LOCAL=1 node tests/smoke.mjs`.
- `package.json`, `package-lock.json`: Electron pinned to 45.1.0. `node_modules/` (about 290 MB) is git-ignored.
- `server/server.py`: the server. Serves `web/` (the Deck is `/deck.html`), `/data.js` from
  `~/.local/share/second-brain/viz/data.js`, `/note`, `/search`, `/live`, `/private`, `/talk/*`. Loopback only, Host check,
  `X-Deck` header on every POST, `/health` for the app. Env: `DECK_PORT` (8765), `DECK_DATA`, `DECK_TALK_LOG`, `DECK_TEST_MAP`,
  `DECK_PARENT_WATCH=1` (exit when the app's stdin pipe closes).
- `server/test_server.py`: `crabbox run -- python3 -I viz/server/test_server.py` (the `/note` check needs `CRABBOX_LOCAL=1`).
- `web/deck.html`: the page markup only. Its live-token meta line (`<meta name="deck-live" content="">`) must stay exactly as it
  is: the server fills it in. The small inline script at the top sets the skin before anything draws (no flash); keep it inline.
- `web/css/deck.css`: the Deck's own styles (were the `<style>` block of `deck.html`).
- `web/js/deck-main.js`: the start of the page script. It imports the pieces below **in this order** (they run in that
  order, as when it was one file), then runs the frame loop and the test hash switches. Pieces import shared names back from it.
- `web/js/deck/`: the pieces, one per section: `scene.js` (layouts, scene, drawings, skin painting, the state), `settings.js`
  (Settings, section labels), `panels.js`, `links.js` (note links, markdown), `reader.js`, `lock-tag.js` (🔒), `hover.js`
  (previews, dot hover, lock/unlock), `timeline-ask.js`, `live.js` (08 Live), `input.js` (mouse, keys, left column, size),
  `voice.js` (07 Voice). `S` (in `scene.js`) holds the names more than one piece changes (`S.sel`, `S.prog`, ...); a piece
  can't assign another file's variable, so a new shared changing value goes into `S` too.
- `web/*.js`, `web/*.css`: the shared parts (top bar and point cloud `hud.js`, the shell, skins, panels, timeline, ask, rings, live feed).
- `web/skins/`: one file per colour skin plus `index.js` (the list). `web/vendor/`: three.js.
- `tools/build_data.py`, `tools/add_sim.py`: make `data.js` (read the search index read-only; output folder defaults to
  `~/.local/share/second-brain/viz/`).

## Private, never in git
`data.js` (note titles and paths) and the talk log (what <user> asked). `.gitignore` lists both as a second lock.

## Not moved in (stay in the prototype folder as history)
The early concept pages (`holo.html`, `radar.html`, `tunnel.html`, `1-nebula.html`...), `head-lab/`, the Blender renders and their tools,
the briefs and reports. The top bar's small nav in `hud.js` still links the three concept pages (DECK, HOLO-CORE, RADAR, TUNNEL);
here only DECK leads somewhere. Removing that nav is a later tidy (it changes the picture, so not in the file split).
