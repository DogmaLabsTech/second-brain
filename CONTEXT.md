# second-brain: what is current

A local notes search and a chat-to-notes converter, with a small set of helpers around them. Everything runs on your computer.

- bin/brain is the one command. Its first lines list every subcommand.
- index/onboard.py is the first-run flow: scan, choose, then write only what was chosen (the receipt is ~/.config/second-brain/onboard.json).
- index/index.yml is the shipped search config (one collection per brain section); onboarding adds one collection per notes folder.
- chats/ converts Claude Code and Codex chats to notes (convert.py, codex.py) and removes secrets (redact.py).
- ask/ answers questions from the top notes (ask.py), keeps the agent memory store (memory*.py) and guards private text.
- day/, jobs/, media/, eval/ hold the day pages, voice jobs, media notes and the weekly check-up.
- deciders/private_guard.py is the privacy list guard. Local decider tools are optional and live outside this repo.
- docs/media/readme/ holds the README pictures (animated SVG). make_art.py draws them (the hero brain is a Codex image in source/); edit that script, not the SVGs. LICENSE-ART covers them.
- deck/ is the Second Brain Deck (Electron app, local server and web page). See deck/CONTEXT.md.

Tests: bin/test runs everything in a throwaway home. Each folder also runs alone: python3 -m unittest discover -s <folder> -p 'test_*.py'.
