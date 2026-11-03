# The Deck

A 3D map of your notes. Every note is a dot, grouped by topic. Click a dot to read the note, and use the ask panel to talk to your second brain.

It runs only on your computer: a small Python server on 127.0.0.1 plus an Electron window (or any browser).

## What you need

- Node 22.12 or newer (it comes with npm)
- Python 3.12 or newer with the packages in requirements.txt (pyyaml and numpy)
- qmd, the local notes search that second-brain uses (index/setup.sh sets it up)

## Install and start

1. In this folder run: npm ci
2. Then run: node node_modules/electron/install.js (npm 11 does not download Electron by itself)
3. Make the map: tools/refresh.sh --force
4. Open the window: app/deck. Or run: python3 -I server/server.py and open http://127.0.0.1:8765/deck.html in a browser.

With no map yet the page says NO MAP YET and reloads by itself when the map exists. The first map needs your notes in the search index, so run the onboarding first (brain onboard, from the second-brain folder).

Optional launcher: ln -s "$PWD/app/brain-deck" ~/.local/bin/brain-deck, then copy app/second-brain-deck.desktop into ~/.local/share/applications.

## Settings

All settings are environment variables with working defaults.

| Variable | Default | What |
|---|---|---|
| DECK_PORT | 8765 | The server port |
| DECK_DIR | this folder | Where the app lives |
| DECK_DATA | ~/.local/share/second-brain/deck/data.js | The map file |
| DECK_OUT | ~/.local/share/second-brain/deck | Where tools/refresh.sh writes the map |
| DECK_INDEX | ~/.cache/qmd/index.sqlite | The qmd index the map is built from |
| DECK_MIN_NOTES | 10 | A map with fewer notes counts as broken |
| DECK_SCORES | none | Optional check-up history (tab-separated) shown in the top bar |
| DECK_BRAIN | brain | The brain command the ask panel calls |

## Tests

- npm test (needs no notes)
- python3 -I server/test_server.py and python3 -I server/test_talk.py
- npm run smoke needs a real map and is skipped on a fresh clone

## Keys

F11 full screen. The window remembers its size and place.
