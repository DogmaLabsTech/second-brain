# second-brain

**Your notes and your AI chats, in one searchable brain that stays on your computer.**

Ask it a question in plain words and get a short answer with the notes it used. Your Claude Code and Codex chats become notes too, with keys, tokens and emails removed first. Nothing is sent anywhere unless you set up an online writer yourself.

## What you get

- **Search and ask.** brain search finds the best notes. brain ask answers in one to three sentences and names its sources.
- **Your chats as notes.** Past Claude Code and Codex chats turn into notes you can search, with secrets removed.
- **A first-run you control.** brain onboard shows what it found and puts in only what you choose. The default is nothing.
- **Day pages and reminders.** What moved today, a morning standup, and reminders by voice or command.
- **A privacy list.** Words you put in a private list keep a question or note away from any online model.
- **The Deck.** A 3D map of your notes in its own window. See deck/README.md.

## What you need

- Python 3.12 or newer, git, and the Python package pyyaml
- qmd, the local notes search (npm i -g @tobilu/qmd, needs Node 22.12 or newer)
- Optional: Ollama with a small model for brain ask, numpy and Node for the Deck, Claude Code if you want your chats turned into notes

## Install (about five minutes)

An AI agent can follow these steps from a fresh clone. Each step says what you should see.

1. Get the code: git clone https://github.com/DogmaLabsTech/second-brain.git, then go into the folder.
2. Check the computer: run ./install.sh. You should see "ok" for each needed tool and a line that says Ready. Fix anything marked MISSING and run it again. (./install.sh --json gives the same answer for scripts.)
3. Choose what goes in: run bin/brain onboard. It lists the notes folders and AI chat histories it found and asks about each one. Say no to anything you do not want. Or, without questions: bin/brain onboard --yes --notes ~/notes --sessions claude
4. Try it: run bin/brain search "something from your notes". You should see paths and snippets.
5. Optional: put bin/brain on your PATH, for example ln -s "$PWD/bin/brain" ~/.local/bin/brain

More detail and a checklist for a brand-new machine: docs/getting-started.md.

## Everyday commands

| Command | What it does |
|---|---|
| brain search "words" | The best five notes, as path and snippet |
| brain ask "question" | A short answer with the notes it used (needs a model, see above) |
| brain onboard | Choose what goes into the brain, any time you like |
| brain status | Is the search index keeping up? |
| brain reindex | Read changed notes now (a timer can do it every hour) |
| brain day | What moved today, yesterday or overnight |
| brain alarm list | Your reminders |
| brain drafts | Draft lessons and test questions waiting for you to keep or drop |

Run bin/brain with no words for the full list.

## Where things live

| Folder | What |
|---|---|
| bin/ | The brain command and small wrappers |
| ask/ | Search and ask: the answer writers, the chat proxy, the memory store |
| chats/ | Turns Claude Code and Codex chats into notes and removes secrets |
| index/ | The qmd search config, onboarding, the reindex scripts and optional systemd units |
| day/ | Day pages, standups and the canvas page |
| jobs/ | Small voice jobs: remember, remind, open a note, start a Claude |
| media/ | Notes for pictures and videos your agents make |
| eval/ | A weekly check-up that scores the search on questions you give it |
| deciders/ | The privacy list guard (decider tools are optional and not part of this repo) |
| deck/ | The Deck: a 3D map of your notes |

## Your notes stay yours

- The brain is a plain folder on your computer (default ~/brain). It never lives inside a repository and is never pushed.
- Chats are redacted before they become notes. Redaction cannot be turned off; to skip it, skip the source.
- Put words in deciders/private.json (copy private.example.json) and any ask that contains them is kept away from online models. An empty or broken list stops anything being sent.
- Folders you choose stay where they are. The search reads them in place and never changes them.

## Optional extras

- Run things on a timer: index/install-units.sh copies the systemd user units into place with your real path filled in. It enables nothing. Turn on only the timers you want.
- The Deck: see deck/README.md.
- Local models: install Ollama and pull a small model, for example ollama pull qwen2.5:3b. Set BRAIN_LOCAL_MODEL to use another.

## Tests

Run bin/test. It runs every folder in a throwaway home, so it never touches your real notes. Tests that need your own data or services skip themselves.

## Using it with agent-os

agent-os is the desk that talks to your AI team. It looks for the brain folder in its settings (paths.notes). Run bin/brain onboard first, then follow the agent-os setup.

## Licence

The code is MIT licensed (LICENSE). Third-party notices are in NOTICE.
