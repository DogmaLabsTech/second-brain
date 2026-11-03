<p align="center">
  <img src="docs/media/readme/hero.svg" alt="second-brain: a glowing holographic brain made of linked notes. Agentic memory on your computer." width="100%">
</p>

<p align="center">
  <img alt="Code licence: MIT" src="https://img.shields.io/badge/code-MIT-2f7d6d">
  <img alt="Art licence: CC BY 4.0" src="https://img.shields.io/badge/art-CC%20BY%204.0-c08a3e">
  <img alt="Python 3.12 or newer" src="https://img.shields.io/badge/python-3.12%2B-3b6ea5">
  <img alt="Runs on this computer" src="https://img.shields.io/badge/runs-locally-4a4a5a">
</p>

# second-brain

**Your notes and your AI chats, in one searchable brain that stays on your computer.**

Ask it a question in plain words and get a short answer with the notes it used. Your Claude Code and Codex chats become notes too, with keys and tokens removed first. Nothing is sent anywhere unless you set up an online writer yourself.

Ready to try it? Jump to the [Quickstart](#quickstart-about-five-minutes).

<h2><img src="docs/media/readme/banner-1.svg" alt="1. Meet your brain: one folder of notes, one search, on your own computer" width="100%"></h2>

<table>
<tr>
<td width="40%" valign="middle">
<p><b>One folder. One search. Your computer.</b></p>
<p>The <b>brain</b> is a plain folder of notes (by default <code>~/brain</code>). A search index reads it, and a small command, <code>brain</code>, asks that index questions.</p>
<p>
<img src="docs/media/readme/icons/search.svg" width="22" align="absmiddle"> <b>Search.</b> <code>brain search</code> finds the best notes.<br>
<img src="docs/media/readme/icons/ask.svg" width="22" align="absmiddle"> <b>Ask.</b> <code>brain ask</code> answers in one to three sentences and names its sources.<br>
<img src="docs/media/readme/icons/day.svg" width="22" align="absmiddle"> <b>Days.</b> What moved today, a morning standup, and reminders.<br>
<img src="docs/media/readme/icons/deck.svg" width="22" align="absmiddle"> <b>The Deck.</b> A 3D map of your notes in its own window (<a href="deck/README.md">deck/README.md</a>).
</p>
</td>
<td width="60%" valign="middle">
<img src="docs/media/readme/scene-search.svg" alt="A terminal animation. Two brain search commands run. One finds a note about a kitchen renovation budget, the other finds a past chat about a checkout bug. Both show the file path and a snippet." width="100%">
</td>
</tr>
</table>

<h2><img src="docs/media/readme/banner-2.svg" alt="2. Your chats become notes: Claude Code and Codex history, with secrets removed first" width="100%"></h2>

<p align="center">
  <img src="docs/media/readme/scene-chats.svg" alt="An animation. A glowing chat window sends a stream of light through an amber scanner gate to a note card. The chat held an API key; the note shows the same line as redacted. Under the note sits a small network of linked nodes, the brain." width="100%">
</p>

<p><img src="docs/media/readme/icons/chat.svg" width="22" align="absmiddle"> <b>Past chats turn into notes you can search.</b> Claude Code and Codex are supported today. Gemini, ChatGPT exports and Cursor are not yet.<br>
<img src="docs/media/readme/icons/scrub.svg" width="22" align="absmiddle"> <b>Secrets go first.</b> Keys, tokens, passwords in links and private key blocks become <code>[redacted]</code> before anything is saved. Redaction cannot be turned off; to skip it, skip the source. Your own email address is dropped once you list it (<code>BRAIN_OWN_EMAILS=you@example.com</code>, or one address per line in <code>~/.config/second-brain/own-emails</code>).<br>
<img src="docs/media/readme/icons/folder.svg" width="22" align="absmiddle"> <b>You choose what goes in.</b> <code>brain onboard</code> shows what it found and reads nothing until you say. The default is nothing. This is a real run on a made-up folder:</p>

<p align="center">
  <img src="docs/media/readme/scene-setup.svg" alt="A terminal animation of the first run. brain onboard --plan lists a notes folder with 3 notes and one Claude chat, and says nothing is ingested unless you choose it. A second command ingests exactly that and reports the search index updated." width="100%">
</p>

<h2><img src="docs/media/readme/banner-3.svg" alt="3. Ask it anything: plain words in, the best notes and their sources out" width="100%"></h2>

<table>
<tr>
<td width="46%" valign="middle">
<p><b>Plain words in. Notes and sources out.</b></p>
<p><code>brain search</code> works with keywords as soon as setup is done. <code>brain ask</code> writes a short answer from the notes it found. It needs a model: a small local one through Ollama, or an online writer you set up yourself. It always names its sources.</p>
<p>For meaning-based search (so "restart" finds a note that says "reload"), run <code>qmd embed</code> once. It downloads models. Then set <code>BRAIN_SEMANTIC=1</code>.</p>
</td>
<td width="54%" valign="middle">

| Command | What it does |
|---|---|
| `brain search "words"` | The best five notes, as path and snippet |
| `brain ask "question"` | A short answer with the notes it used |
| `brain onboard` | Choose what goes into the brain, any time |
| `brain status` | Is the search index keeping up? |
| `brain reindex` | Read changed notes now (a timer can do it every hour) |
| `brain day` | What moved today, yesterday or overnight |
| `brain alarm list` | Your reminders |
| `brain drafts` | Draft lessons and test questions waiting for you |

Run `bin/brain` with no words for the full list.

</td>
</tr>
</table>

<h2><img src="docs/media/readme/banner-4.svg" alt="4. Where everything lives: your folder, the index, and the code in this repository" width="100%"></h2>

<p align="center">
  <img src="docs/media/readme/scene-where.svg" alt="A diagram. Your brain folder holds rules, agents, projects, private, chats, days and inbox. A local qmd search index reads it. The brain command talks to the index. Below, the ten code folders of this repository." width="100%">
</p>

| Folder | What |
|---|---|
| `bin/` | The brain command and small wrappers |
| `ask/` | Search and ask: the answer writers, the chat proxy, the memory store |
| `chats/` | Turns Claude Code and Codex chats into notes and removes secrets |
| `index/` | The qmd search config, onboarding, the reindex scripts and optional systemd units |
| `day/` | Day pages, standups and the canvas page |
| `jobs/` | Small jobs: remember, remind, open a note, start a Claude |
| `media/` | Notes for pictures and videos your agents make |
| `eval/` | A weekly check-up that scores the search on questions you give it |
| `deciders/` | The privacy list guard (decider tools are optional and not part of this repo) |
| `deck/` | The Deck: a 3D map of your notes |

<h2><img src="docs/media/readme/banner-5.svg" alt="5. Your notes stay yours: local by default, redacted by default, private on request" width="100%"></h2>

<p align="center">
  <img src="docs/media/readme/scene-private.svg" alt="An illustration. Inside a glowing sealed dome called this computer sit note cards, chat bubbles, a small brain network and the search index. A heavy gate with a padlock, the private list, stands between the dome and a dim cloud called online services. A dashed line from the gate to the cloud stops at the gate." width="100%">
</p>

<p><img src="docs/media/readme/icons/local.svg" width="22" align="absmiddle"> <b>It lives on your computer.</b> The brain is a plain folder. It never lives inside a repository and is never pushed.<br>
<img src="docs/media/readme/icons/shield.svg" width="22" align="absmiddle"> <b>Chats are redacted before they become notes.</b><br>
<img src="docs/media/readme/icons/list.svg" width="22" align="absmiddle"> <b>The private list.</b> Put words in <code>deciders/private.json</code> (copy <code>private.example.json</code>) and any ask that contains them is kept away from online models. An empty or broken list stops anything being sent.<br>
<img src="docs/media/readme/icons/folder.svg" width="22" align="absmiddle"> <b>Folders you choose stay where they are.</b> The search reads them in place and never changes them.</p>

## Quickstart (about five minutes)

You need Python 3.12 or newer, git and the Python package `pyyaml`, plus qmd, the local notes search (`npm i -g @tobilu/qmd`, needs Node 22.12 or newer). Optional: Ollama with a small model for `brain ask`; numpy and Node for the Deck; Claude Code if you want your chats turned into notes.

An AI agent can follow these steps from a fresh clone. Each step says what you should see.

1. **Get the code:** `git clone https://github.com/DogmaLabsTech/second-brain.git`, then go into the folder.
2. **Check the computer:** run `./install.sh`. You should see "ok" for each needed tool and a line that says Ready. Fix anything marked MISSING and run it again. (`./install.sh --json` gives the same answer for scripts.)
3. **Choose what goes in:** run `bin/brain onboard`. It lists the notes folders and AI chat histories it found and asks about each one. Say no to anything you do not want. Or, without questions: `bin/brain onboard --yes --notes ~/notes --sessions claude`
4. **Try it:** run `bin/brain search "something from your notes"`. You should see paths and snippets.
5. **Optional:** put `bin/brain` on your PATH, for example `ln -s "$PWD/bin/brain" ~/.local/bin/brain`

More detail and a checklist for a brand-new machine: [docs/getting-started.md](docs/getting-started.md).

## Optional extras

- **Run things on a timer:** `index/install-units.sh` copies the systemd user units into place with your real path filled in. It enables nothing. Turn on only the timers you want.
- **The Deck:** see [deck/README.md](deck/README.md).
- **Local models:** install Ollama and pull a small model, for example `ollama pull qwen2.5:3b`. Set `BRAIN_LOCAL_MODEL` to use another.

## Tests

Run `bin/test`. It runs every folder in a throwaway home, so it never touches your real notes. Tests that need your own data or services skip themselves.

## Using it with agent-os

[agent-os](https://github.com/DogmaLabsTech/agent-os) is the desk that talks to your AI team. Its `agent-os start` step finds this brain, shows what it could read and ingests only what you choose. The brain works on its own too; agent-os is optional.

## Licence

The code is MIT licensed ([LICENSE](LICENSE)). The pictures in `docs/media/readme/` are CC BY 4.0 ([LICENSE-ART](LICENSE-ART)); `make_art.py` there draws them. Third-party notices are in [NOTICE](NOTICE).
