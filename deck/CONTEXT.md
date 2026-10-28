# viz: what is here

The Deck, the 3D map of the second brain (three.js page + a small loopback server). Moved in from the prototype folder
`~/Downloads/agent-notes/brain-prototypes/` on 2026-10-28 (brief 25). The plan it follows: that folder's
`briefs/24-electron-plan-report.md` (nine steps; steps 1 and 2 are done here, Electron comes in step 3).
When you add, move or retire a file here, update this file in the same commit.

## Current (use these)
- `README.md`: the plain guide for <user>.
- `server/server.py`: the server. Serves `web/` (the Deck is `/deck.html`), `/data.js` from
  `~/.local/share/second-brain/viz/data.js`, `/note`, `/search`, `/live`, `/private`, `/talk/*`. Loopback only, Host check,
  `X-Deck` header on every POST. Env: `DECK_PORT` (8765), `DECK_DATA`, `DECK_TALK_LOG`, `DECK_TEST_MAP`.
- `server/test_server.py`: `crabbox run -- python3 -I viz/server/test_server.py` (the `/note` check needs `CRABBOX_LOCAL=1`).
- `web/deck.html`: the page. Its live-token meta line (`<meta name="deck-live" content="">`) must stay exactly as it is: the server fills it in.
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
