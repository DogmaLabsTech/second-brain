# viz: what is here

The Deck, the 3D map of the second brain (three.js page + a small loopback server). Moved in from the prototype folder
`~/Downloads/agent-notes/brain-prototypes/` on 2026-10-28 (brief 25). The plan it follows: that folder's
`briefs/24-electron-plan-report.md` (nine steps; 1 and 2 done in brief 25, 3 and 4, the Electron window, in brief 26; 5-7, the
hourly refresh, the launcher and the NEW DATA chip, in brief 28).
When you add, move or retire a file here, update this file in the same commit.

## Current (use these)
- `README.md`: the plain guide for <user>.
- `app/main.js`: the Electron window (start: `app/deck`, after `npm ci` once). One window, no menu, one copy
  (`requestSingleInstanceLock`). Starts `python3 -I server/server.py` with `DECK_PARENT_WATCH=1` and waits for `/health`, or reuses a
  Deck server that already answers; another program on the port: it asks, never kills. Stops its server on close. Only
  `http://127.0.0.1:<port>` in the window, web links to the browser, all other requests blocked, mic-only permissions, `F11`,
  window size in `~/.config/second-brain-deck/window.json`, window class `second-brain-deck` (from `desktopName` in `package.json`).
  Env: `DECK_PORT`, `DECK_DEBUG=1` (dev tools, F12), `DECK_USER_DATA`, `DECK_TEST_HIDDEN=1` (tests only).
- `app/brain-deck`: the launcher, installed as a copy in `~/.local/bin/brain-deck`. Starts `app/deck` from the main repo's `viz/`
  (`DECK_VIZ` overrides); when the Electron program is missing it runs `npm ci` and `node node_modules/electron/install.js` once
  (npm 11 skips Electron's own download step) and says so.
- `app/second-brain-deck.desktop`: the app-menu entry "Second Brain Deck" (runs `~/.local/bin/brain-deck`, window class
  `second-brain-deck`), installed as a copy in `~/.local/share/applications/`. Check: `desktop-file-validate`.
- `app/rules.js`: what the window lets through (links, requests, permissions, safe window size); tests `app/test/rules.test.js`:
  `crabbox run -- node --test viz/app/test/rules.test.js`.
- `app/deck`: starts Electron with `--ozone-platform-hint=auto`; extra switches pass on (`--disable-gpu`).
- `tests/smoke.mjs`: the app with a hidden window on test port 8797 (page, WebGL, sections, notes, links, permissions, one copy,
  server stopped after close and after kill -9, reuse, busy port). Needs this computer's data.js: `CRABBOX_LOCAL=1 node tests/smoke.mjs`.
  `DECK_TEST_PORT` changes the port; `DECK_SMOKE_NOTES` must be the map's note count (the default, 2385, was the count on
  2026-10-28 morning); `DECK_SMOKE_OUT` (an existing folder) keeps the results. In a fresh worktree run `npm ci` and
  `node node_modules/electron/install.js` first.
- `package.json`, `package-lock.json`: Electron pinned to 45.1.0. `node_modules/` (about 290 MB) is git-ignored.
- `server/server.py`: the server. Serves `web/` (the Deck is `/deck.html`), `/data.js` from
  `~/.local/share/second-brain/viz/data.js`, `/note`, `/search`, `/live`, `/private`, `/talk/*`. Loopback only, Host check,
  `X-Deck` header on every POST, `/health` for the app. Env: `DECK_PORT` (8765), `DECK_DATA`, `DECK_TALK_LOG`, `DECK_TEST_MAP`,
  `DECK_PARENT_WATCH=1` (exit when the app's stdin pipe closes). `/live` also sends `data` {v}: the data.js stamp at connect and again
  when a new map is swapped in (checked every `DECK_DATA_POLL` seconds, 3; announced once the file stays the same).
- `server/test_server.py`: `crabbox run -- python3 -I viz/server/test_server.py` (the `/note` check needs `CRABBOX_LOCAL=1`).
- `server/test_talk.py`: the voice gate and talk helpers with a stand-in brain (no real job runs), test port 8799:
  `crabbox run -- python3 -I viz/server/test_talk.py` (the pre-roll test needs ffmpeg: `CRABBOX_LOCAL=1`).
- `web/deck.html`: the page markup only. Its live-token meta line (`<meta name="deck-live" content="">`) must stay exactly as it
  is: the server fills it in. The small inline script at the top sets the skin before anything draws (no flash); keep it inline.
- `web/css/deck.css`: the Deck's own styles (were the `<style>` block of `deck.html`).
- `web/js/deck-main.js`: the start of the page script. It imports the pieces below **in this order** (they run in that
  order, as when it was one file), then runs the frame loop and the test hash switches. Pieces import shared names back from it.
- `web/js/deck/`: the pieces, one per section: `scene.js` (layouts, scene, drawings, skin painting, the state), `settings.js`
  (Settings, section labels), `panels.js`, `links.js` (note links, markdown), `reader.js`, `lock-tag.js` (🔒), `hover.js`
  (previews, dot hover, lock/unlock), `timeline-ask.js`, `live.js` (08 Live), `input.js` (mouse, keys, left column, size),
  `voice.js` (07 Voice), `fresh.js` (the NEW DATA · RELOAD chip and the reload when idle; test switch `#fresh=<seconds>`). `S` (in `scene.js`) holds the names more than one piece changes (`S.sel`, `S.prog`, ...); a piece
  can't assign another file's variable, so a new shared changing value goes into `S` too.
- `web/*.js`, `web/*.css`: the shared parts (top bar and point cloud `hud.js`, the shell, skins, panels, timeline, ask, rings, live feed).
- `web/skins/`: one file per colour skin plus `index.js` (the list). `web/vendor/`: three.js.
- `tools/build_data.py`, `tools/add_sim.py`: make `data.js` (read the search index read-only, `VIZ_INDEX` overrides it; output
  folder defaults to `~/.local/share/second-brain/viz/`). Both read the notes' fingerprints through `tools/vectors.py`.
- `tools/refresh.sh`: the hourly refresh (lock, nice 10, temp folder, check, atomic swap, skips an unchanged index; one log line per run
  in `~/.local/state/second-brain/viz-refresh.log`; `refresh.sig` beside data.js). Run by `index/second-brain-viz-refresh.service`, which
  the reindex starts when it is done (`index/second-brain-reindex.service.d/viz.conf`). Env: `VIZ_OUT`, `VIZ_INDEX`, `VIZ_MIN_NOTES`.

## Private, never in git
`data.js` (note titles and paths) and the talk log (what <user> asked). `.gitignore` lists both as a second lock.

## Not moved in (stay in the prototype folder as history)
The early concept pages (`holo.html`, `radar.html`, `tunnel.html`, `1-nebula.html`...), `head-lab/`, the Blender renders and their tools,
the briefs and reports. The top bar's small nav in `hud.js` still links the three concept pages (DECK, HOLO-CORE, RADAR, TUNNEL);
here only DECK leads somewhere. Removing that nav is a later tidy (it changes the picture, so not in the file split).
