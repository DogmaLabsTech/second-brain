# The Deck (the brain's map)

The Deck is a picture of your second brain: every note is a glowing dot, notes about the same thing sit together, and
you can fly between three views (1 Map, 2 Tunnel, 3 Radar), click a dot to read the note, and talk to the brain.
It used to live in `~/Downloads/agent-notes/brain-prototypes/` as a test; this folder is the real home.

## How to start it
The Deck has its own window now (an Electron app). Once, after getting this folder, install the window part (about 290 MB,
stays in `node_modules/`, never in git):
```
cd ~/projects/second-brain/viz && npm ci
```
Then start it:
```
~/projects/second-brain/viz/app/deck
```
- It starts the Deck's server by itself and stops it when you close the window. If a Deck server already runs, it uses that one.
- If another program holds the port (for example the old prototype on 8765), it asks you to stop that program; it never stops it itself.
- Starting it a second time just brings the open window to the front.
- `F11` full screen. It remembers its size (on Hyprland, where the window goes is decided by Hyprland).
- Only the microphone is allowed (for the voice panel). Camera, screen sharing, notifications and location are refused.
- Web links in a note open in your normal browser. Nothing else leaves this computer.
- If the graphics card misbehaves: `app/deck --disable-gpu`. For dev tools: `DECK_DEBUG=1 app/deck`.
- A short `brain-deck` command and an app-menu entry come in a later step.

The page alone still works in a browser too: `python3 -I server/server.py`, then http://127.0.0.1:8765/deck.html.
(The old prototype also uses 8765. Only one can run at a time. To try this one next to it, add `DECK_PORT=8796` in front, for the app too.)

## Your notes stay private
- It only listens on this computer (127.0.0.1). Nothing is put on the tailnet or the internet.
- The map's data (`data.js`: every note's title and where it lives) is **not** in this folder and never goes into git.
  It lives in `~/.local/share/second-brain/viz/data.js`. What you say to the voice panel is logged in
  `~/.local/state/second-brain/talk-log.jsonl`, also outside git.

## How to refresh the map
The map is a snapshot. To make a new one (about 4 minutes; it only reads the search index):
```
python3 -I tools/build_data.py && python3 -I tools/add_sim.py
```
Both write to `~/.local/share/second-brain/viz/`. Reload the page afterwards. (An automatic hourly refresh is a later step.)

## What is in here
| Folder | What |
|---|---|
| `web/` | the page itself: `deck.html`, its styles and scripts, the colour skins, three.js (`vendor/`) |
| `app/` | the window: `main.js` (Electron), `rules.js` (what the window lets through), `deck` (start it) |
| `server/` | the small local server (`server.py`) and its tests |
| `tests/` | `smoke.mjs`: the app tested with a hidden window |
| `tools/` | the two map makers: `build_data.py` (positions) and `add_sim.py` (how alike the neighbours are) |
