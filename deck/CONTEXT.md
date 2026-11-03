# deck/: the Second Brain Deck

A local app that draws the notes of your second brain as a 3D map. Folders:

| Folder | What |
|---|---|
| app/ | The Electron window (main.js), its permission rules (rules.js), and the launchers (deck, brain-deck, a .desktop file) |
| server/ | server.py: a local server on 127.0.0.1 that serves web/, the map file, note reads, search and the voice and ask panels. Tests sit next to it |
| web/ | The page: deck.html, scripts (js/), skins (skins/, skins.css) and the bundled three.js |
| tools/ | build_data.py and add_sim.py make data.js from the qmd index (vectors.py reads the vectors); refresh.sh runs them and swaps the map in only when it looks sane |
| tests/ | smoke.mjs, an end-to-end check in a hidden window (needs a real map) |

The map file (data.js) is not in git. It is built from your own notes by tools/refresh.sh, so a fresh clone starts with NO MAP YET. See README.md for the steps and the settings.
