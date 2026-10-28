# The Deck (the brain's map)

The Deck is a picture of your second brain: every note is a glowing dot, notes about the same thing sit together, and
you can fly between three views (1 Map, 2 Tunnel, 3 Radar), click a dot to read the note, and talk to the brain.
It used to live in `~/Downloads/agent-notes/brain-prototypes/` as a test; this folder is the real home.

## How to start it (for now)
Today it still runs as a web page in the browser. A proper app window (Electron) comes in a later step.

```
cd ~/projects/second-brain/viz && python3 -I server/server.py
```
Then open http://127.0.0.1:8765/deck.html in the browser. Stop it with Ctrl+C.
(The old prototype also uses 8765. Only one can run at a time. To try this one next to it, add `DECK_PORT=8796` in front.)

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
| `server/` | the small local server (`server.py`) and its tests |
| `tools/` | the two map makers: `build_data.py` (positions) and `add_sim.py` (how alike the neighbours are) |
