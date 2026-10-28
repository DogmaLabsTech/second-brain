# Second brain

A search engine for everything you've written down. It reads your computer notes, your business
notes, your project guides and your old Claude chats, and finds the right note by what you
*mean*, not only by the exact words. Everything runs on this computer; nothing is sent anywhere.

## What it reads

| Name | Where |
|---|---|
| `computer` | `~/OMARCHY-BRAIN` (not `example/muse-screens`, not `.secrets`, not Paperclip's old copies in `paperclip/*/`) |
| `business` | `~/user-labs-business` (not `.env`, `.secrets`, `node_modules`, `.git`) |
| `projects` | each project's `README.md`, `CLAUDE.md`, `AGENTS.md` and `docs/` in `~/projects` |
| `chats` | short notes made from old Claude chats, in `~/.local/share/second-brain/chats/`, and from Codex chats in its `codex/` folder |

Your notes are only read, never changed.

## How to search

In a terminal:

```
brain search "why does the bar get killed"
```

You get the 5 best notes, each with a short piece of text, in under a second. (`BRAIN_SEARCH_SCORES=1 brain search …` puts each note's score and a tab in front of its line; agent-os `think` uses that to drop weak hits. The score follows the note's rank, it is not a fit measure.) The first search
after 5 quiet minutes takes about 6 seconds (it wakes the models up).

In any Claude chat: just ask. Claude has the `brain` tool and is told to look there before asking
you about past work.

How good is it? On the fair test (38 questions; 34 of them have a right note, 4 must say "not found"),
the right note was first for 7 of 34 (21%) and in the top 3 for 18 of 34 (53%), last checked 2026-10-18
(`eval/scores.tsv`; the questions stay on this computer, `eval/README.md`).
Before searching, a small list of your words and the notes' words (`ask/synonyms.tsv`: "reload" →
"restart", "lore" → "world bible") adds the notes' words to the question. Add a line there when a
search misses because you and your notes say it differently.

## Agent memory: rules and lessons for a project

The rules and lessons agents should know live in the memory store (`~/projects/shared/`). To see what an agent
gets for a project and a task:

```
brain memory second-brain "fix the chat door on port 8181"
```

You get that project's notes, and the all-projects notes only on a match (<user>, 2026-10-28): pinned notes first (both
scopes), then the best matches (newer notes win close calls, by the note's date), then the rest of the project's own
notes newest first. An all-projects note that is not pinned shows only when the search ranks it for the task; the
header then says how many were left out, so an agent knows to ask again with a task. Without a task, or when the
search ranks nothing: pinned plus the project's newest notes. Each note shows its summary line exactly as stored, rule or lesson,
the project and the path. Notes marked `(local-only)` are shown too, with that mark. It stops at 2,000 tokens
(characters / 4) and says how many notes did not fit. Drafts and retired notes (`history/`) never show. The search is
by meaning; a word search is added only for exact things in the task (a file name, a port, text in quotes, a function
name). If the search server is down or slow (10 s), or matches no note, you get the pinned and the project's newest notes and a
line saying so.

Claude, Codex and Gemini chats get the same answer from the `memory` tool in the brain (the chats' door adds it; it
needs a restart of `second-brain-chat-search.service` to show up). Code: `ask/memory.py`.

**How well does it find the right note?** One command scores it on two sets of agent questions (36 written for the
notes to tune on; 16 real first prompts quoted from past run specs, measured only, never tuned on):

```
python3 -I eval/memory_score.py --floor --log "what changed"
```

It prints top-3 hits and the mean place of the right note, with and without the exact-thing word search, and `--log`
adds the rows to `eval/memory-scores.tsv`. The pilot bar is 8 of 10 held-out questions with the right note in the
top 3. Rules and the way to read it: `eval/README.md`, "The agent test set". You spot-check 10 questions in
`eval/memory-spotcheck.md`.

### "This computer only" notes

A memory note can be marked this computer only. Then Haiku (the online backup writer) never gets it; `brain ask`
answers from it with the local writer only. Claude chats still read it. The names filter marks a note by itself when it
is not sure about a name; you can mark or unmark one by hand:

```
brain private zorbel on          # mark it (a path in the store, part of the file name, or words from its title)
brain private zorbel off         # unmark it
brain private list               # every marked note: title, path, who marked it and when
```

If the name fits several notes, they are listed and nothing changes. Only memory notes can be marked. Only the three
lines `local-only`, `local-only-by` (you or the filter) and `local-only-at` change in the note; the old file is copied to
`~/.local/share/second-brain/backups/private-tag/` first, and the change is committed in the store. Your choice wins:
`brain drafts keep` keeps it even when the names filter is not sure. Add `--json` for a machine answer (the Deck's
lock button). Code: `ask/private_tag.py`.

## Agent memory in every Claude session (the memory hook)

When a Claude session starts work in one of your projects, the memory hook adds that project's notes to it by itself,
matched to the first thing it is asked, so no agent has to remember to look. It runs on the **first prompt of each
session only** (Claude's `UserPromptSubmit` hook, one marker per session in `~/.local/state/second-brain/memory-hook/`,
cleared after 3 days). Code: `ask/memory_hook.py` (shell entry `bin/brain-memory-hook`). Tests: `ask/test_memory_hook.py`.

- **Which project:** the git repo's name, worktrees included (`~/.agent-os/worktrees/second-brain/<branch>` counts as
  second-brain); only names that are folders in `~/projects/`. Anywhere else: nothing.
- **What it adds:** the same list as `brain memory <repo> "<first prompt>"` (pinned first, best match, then the project's
  newest; all-projects notes only when pinned or matched; at most 2,000 tokens), under one header line that points to the `memory` tool and `brain memory`. A prompt like
  "Read /…/builder.md and do what it says" also searches with the start of that brief. A prompt with no meaning
  ("continue", "yes", "ok") gets the pinned and the project's newest notes. You see one line: `Memory: 24 notes pushed (1580 tokens)
  for example-game.` Each push is logged in `~/.local/state/second-brain/memory-hook.jsonl`.
- **Never in the way:** the search gets 1.5 s (slower: pinned and the project's newest), the whole answer 2.5 s (slower: nothing).
  Measured: 0.3 to 0.4 s normally, 1.7 s with a hung search. Store missing (the test machine), no notes, bad input or any error:
  no output, and Claude starts as usual.

Where it fires (tested 2026-10-28 with Claude Code 2.1.311, from a temporary example-game worktree):

| Where | Fires? | How it was proved |
|---|---|---|
| `claude -p "…"` | yes | the model quoted the pushed lines |
| nodeterm agent windows (`claude "<first prompt>"`) | yes | same command in tmux: "Memory: 24 notes pushed" shown, lines quoted; the second prompt got no push |
| agent workers | not tested in agent itself | they are the same interactive Claude with your settings; typed prompts fire the hook in the tmux run |
| subagents (Agent tool) | **no** | a probe saw only `SubagentStart`; the helper said it had no memory. Their hand-back reaches the main chat as a new prompt of the same session, so the marker blocks a second push |
| with your agent, agent-projects and nodeterm hooks | yes, side by side | the `claude -p` run with all your settings plus this one |

Subagents get their rules from the main chat or the `memory` tool. Codex and Gemini have no such hook: they use the
`memory` tool and `brain memory`.

**Switch on** (your yes; it touches every Claude session on this computer): in `~/.claude/settings.json`, add this
entry to the `"UserPromptSubmit": [ … ]` list, next to the two that are there:

```json
{
  "hooks": [
    {
      "type": "command",
      "command": "~/projects/second-brain/bin/brain-memory-hook 2>/dev/null || true",
      "timeout": 5
    }
  ]
}
```

To try it first without touching your settings: `claude --settings ~/projects/second-brain/index/claude-memory-hook.json`
(that file holds only this hook).

**Switch off for a while:** `touch ~/.local/state/second-brain/memory-hook.off` (remove the file to switch back on).
**Undo:** take that entry out of `~/.claude/settings.json` again; then `rm -r ~/.local/state/second-brain/memory-hook
~/.local/state/second-brain/memory-hook.jsonl`.

## The librarian: lesson drafts, old-note flags and the weekly list (agent memory job 6)

The memory store learns without you writing notes, and you stay the one who says yes. Nothing here is pushed to an agent
before your keep. Everything is local; no model is called.

- **Lesson drafts.** When a desk job ends and something objectively went wrong (a second build round, a failed check,
  a test alarm, a revert, a blocked tool in its records), the desk's librarian step writes **one** draft into the
  store's inbox with `brain memory-drafts add` (code: agent-os `librarian lesson`, which reads the job's own files, never
  the agent's story). The draft says **already known: yes/no** (a kept note says the same) and **was pushed: yes/no/unknown**
  (that note was in the memory hook's push for that job). "Yes and pushed" means a repeat got through; it is counted in
  the check-up. At most **5 drafts a week** (a sixth is refused in plain words). A draft nobody keeps for **30 days**
  moves to `history/expired-drafts/` (never deleted, never pushed). `brain memory-drafts list` shows what waits; keep
  it with `brain drafts keep <draft> --to projects/<repo>/lessons`, drop it with `brain memory-drafts drop <draft>`.
  Code: `eval/memory_drafts.py`. Tests: `eval/test_memory_drafts.py`.
- **Flags.** A weekly pass flags (never changes) a kept note when a file in its `files:` list is gone, or changed a lot
  since the note's date (20 lines and half the file, by git log), or a newer note of the same project looks like the
  opposite (same words, one with a "never"). The flags live in the store's `flags.jsonl`, not in the notes. A flagged
  note is still pushed, marked "(may be out of date, check first)". A flag nobody confirms for **30 days** takes the note
  out of the push (not out of the store; `brain memory` still shows it). Pinned notes get a "still true?" every **90 days**.
  Answer with `brain memory-flags confirm <note>` (still right), edit the note and confirm, or
  `brain memory-flags retire <note> --why "…"` (moves it to `history/`, committed; only you run it).
  `brain memory-flags` lists them. Code: `eval/memory_flags.py`, `ask/memory_flagfile.py`. Tests: `eval/test_memory_flags.py`.
- **The weekly list.** `brain checkup` ends with "Agent memory for <user>": new drafts (keep/drop), flags
  (keep/edit/retire) and pinned notes due, each with its command, plus two numbers that also go in `scores.tsv`:
  **repeats that got through** (drafts of the week that were already known and pushed) and the **second-round rate**
  (desk jobs finished this week with `fix: 2` or more / all desk jobs finished this week, read from `~/agent-os/jobs`).
  Skip it with `--no-memory`. Code: `eval/memory_week.py`. Tests: `eval/test_memory_week.py`.

## How to ask (a short answer)

```
brain ask "why does the bar get killed"
```

You get 1 to 3 plain sentences that name the note they came from, the 3 notes it used, and who wrote
the answer. If your notes don't say, it answers "I couldn't find that in your notes." It takes about
4 seconds. `--json` gives the island's format; `--writer local|haiku|auto` picks who writes (default `auto`).

What happens inside (`ask/ask.py`):
1. "Is this a question, a job or just chat?" (`brain-decide intent`) and the search run at the same time.
   Its answer also says `"private": true|false` (family, money, clients…; true whenever something goes wrong).
2. A question: the top 5 notes, then "do they answer it?" (`brain-decide grounded`), then a writer.
3. **Who writes (`auto`):** the local writer (qwen2.5 on this computer, through Ollama) starts alone; Haiku
   joins after 2 s (`BRAIN_HAIKU_WAIT`) only if there's no good local answer yet. A good local answer within
   4 s still wins; a finished Haiku doesn't wait. Haiku is pre-started (`second-brain-haiku.service`,
   `ask/haiku_standby.py`), so it answers in about 2 s. In a 21-question
   race the local writers were right 43–57% of the time and took 6–8 s; Haiku 76% in 3.6 s; `auto` 76% in
   4.0 s (`docs/writer-race.md`). Haiku sees the question and the top 4 notes; the second decider never does.
   **Since 2026-10-18 the local writer runs on the processor, not the graphics card** (<user>: the card is for the
   screen and the search model; the local decider runs on the test machine). Measured: a warm answer 2.3 s (card: 1.3 s); the first one after
   5 quiet minutes about 23 s (it loads from the HDD), so Haiku writes more of the answers. Back to the card: delete the
   three `CUDA_VISIBLE_DEVICES` / `OLLAMA_VULKAN` / `GGML_VK_VISIBLE_DEVICES` lines in `ask/second-brain-ollama.service`.
4. A job (below): it builds the job and the island asks Yes / No if it changes something.
5. Chat ("thanks"): a short friendly line, no search.

## Jobs

One small file per job in `jobs/` (what to say, whether it asks first, the command). `brain job list`.

| Job | Say | Asks first? | What it runs |
|---|---|---|---|
| `open-note` | "open my notes on the bar" | no | opens the best matching note (`xdg-open`) |
| `whats-waiting` | "what's waiting on me?" | no | reads the bar's Claude list, agent helpers and PM runs, says who needs you |
| `team-screen` | "show me the team" | no | opens agent-os's Team screen app (`agent-os-team`, look only: every agent at work side by side); since 2026-10-19 |
| `servers` | "turn on the LLC namer", "turn off the pit wall board" | off only | switches one hosted thing on or off, like a click in the bar's servers list (`hostctl on/off`); names come from `~/.config/hosting/*.conf`, only entries with a tailnet link (never voice typing or Ollama); since 2026-10-20 |
| `what-changed` | "what moved today?", "what about yesterday?", "what happened overnight?" | no | `brain day … --say`: two spoken sentences from the day page (below) |
| `goodnight` | "end of day", "goodnight", "I'm going to bed", "close out the day" | yes | `brain eod` (below; `/eod` in the desk is the same) |
| `start-claude` | "start a Claude on Example Game"; with a task, "start a claude on example: tidy the logs" | yes ("Start a Claude on Example Game?"; with a task "Start a team on Example?") | no task: asks "What should the team do on <project>?" (per-project PM chats were retired 2026-10-19; only "the desk" still opens the whole-desk PM). With a task: `jobs/bin/agent-os-boss`, which prepares a team job (below) |
| `remember-fix` | "fix the thing on my remember list tonight" | yes ("Start a fix from your remember list?") | prepares a team job for that item with agent-os (below) |
| `start-job` | "start a job on agent-os: make the report shorter" | yes ("Start a job on Agent Os?") | prepares a team job on that project with agent-os (below) |
| `music` | "pause", "next song" | no | the music app (MPRIS over D-Bus) |
| `tv` | "turn the TV down" | no | the deck's TV remote scripts, volume up / down / mute only |
| `remember` | "remember that …" | yes | adds a dated line to `~/OMARCHY-BRAIN/inbox/remembered.md` |
| `open-app` | "open Spotify", "launch Discord", "open a terminal", "open VS Code on my second monitor" | no | an installed app's `.desktop` entry; focuses it if it's already open (`omarchy-launch-or-focus`); with a screen, waits for its window and moves it there (`jobs/bin/desktop app <id> <screen>`) |
| `open-file` | "open my downloads folder", "open the kingdom map picture" | no | a file or folder in your home (`xdg-open`); no hidden folders, no programs |
| `desktop` | "next theme", "take a screenshot", "remind me at 2pm to …", "remind me in 10 minutes to …", "lock the screen", "move this window to my other screen" | only log out, restart, shut down | one action from `ACTIONS` in `jobs/desktop.py` (Omarchy commands) |
| `send-file` | "send the latest Example Game files to the laptop", "put the pdf on my phone" | yes (the card names every file and the device) | `jobs/bin/send`: the laptop through `~/.local/bin/send-to-laptop` (lands in Downloads, in the From desktop folder), the test machine with `scp`, the iPhone with Taildrop |

"Open X" tries an app, a file or folder, then a note, in the order your words suggest ("folder",
"picture" or "pdf" means file first; "notes" or "guide" means note first). The desktop actions: theme
(next, by name, picker), wallpaper (next, picker), night light (on, off, toggle), screenshot (whole
screen or a part), screen recording (start, stop), computer volume and mute, mic mute, do not disturb,
stay awake, reminders (at a time up to a week ahead, "at 2pm", "tomorrow at 8am", "at 7 on friday", or in 1 minute
to 24 hours; and say them), go to workspace 1-10, keyboard shortcuts,
emoji and clipboard pickers, Bluetooth on / off, lock, log out, restart, shut down, move a window to a screen.
**Reminders are real alarms** (`jobs/bin/alarm`, since 2026-10-18): a systemd user timer each, so they survive a
restart (one missed while the computer was off goes off when it is back). When one is due, every screen dims and a
big card shows the words with a Done button; a chime repeats until Done (the voice island's card,
`AlarmWindow.qml` in omarchy-setup). A bare hour from 1 to 6 means the afternoon ("at 2" is 2 pm); a time that
has gone by today is tomorrow. `brain alarm list`, `brain alarm cancel <id|all>`, and `brain alarm history`: the
last ones that went off and when Done was pressed (button, key or shell). Tests: `python3 -I jobs/test_alarm.py`.
A how/why question ("how do I turn on the night light") is answered from the notes, not run.
Tests: `python3 jobs/test_desktop_jobs.py` and `python3 jobs/test_send_move.py`.

**Handing a job to agent-os (since 2026-10-23).** "Fix the thing on my remember list tonight" and "start a job on
<project>: <what>" show a Yes / No card. Yes prepares an ordinary team job with agent-os (`jobs/bin/agent-os-start`),
the same plan, yes and five steps as any job:
- the remember-list one runs `agent-os boss prepare --remember --how voice -- "<your words>"`: agent-os finds the item
  you mean and says "Prepared the fix from your remember list. It waits for your go." When more than one item fits it
  asks "which one?" in the office first: "More than one thing on your remember list fits. Pick which one in the
  office, then it waits for your go."
- "start a job on example-game: fix the logs" runs `agent-os boss prepare --repo example-game --how voice -- "fix the
  logs"` (the same as a team job below) and says "Prepared the Example Game team job. It waits for your go."
Nothing is built or pushed until you say yes at the desk. No on the card starts nothing. These two only fire when the
sentence starts that way: "what's on my remembered list?", "remember that ..." and "what should I fix on my remember
list?" stay what they were, and a sentence with two asks in it ("fix the thing on my remember list and then open
Spotify") is asked again. If agent-os fails or takes over a minute it says "I couldn't start that job." Tests:
`CRABBOX_LOCAL=1 python3 -I jobs/test_agent_jobs.py` (a fake agent-os; the real one never runs).

**Start a team (since 2026-10-19).** "Start a claude on example: tidy the logs" (the task comes after a colon, a
comma, a dash or an em dash, or "to" / "and" / "then") shows "Start a team on Example?". Yes runs
`agent-os boss prepare --repo example --how voice -- "tidy the logs"` (`jobs/bin/agent-os-boss`): it writes the boss's and the
worker's job folders, both `go: waiting`, and says "Prepared the Example team job. It waits for your go." (spoken).
**It never starts the boss and never writes a go:** the desk shows you the plan and only your yes goes in both
`go.md`. The words are one line of up to 500 characters, never through a shell; bad input, an unknown project
or `desk` is refused before agent-os is called, and a failing or slow (over 30 seconds) agent-os says
"I couldn't prepare that job." No on the card does nothing. Words with no task after the project ("start a claude
on example-game", "open the example-rpg PM", "start working on example") get the question "What should the team do on
Example?" and open nothing (the per-project PM chats were retired 2026-10-19); "start a claude on the desk" still opens
the whole-desk PM. "so I can watch it", "that's all" and a second project name ("... on example and
example-rpg") are not tasks either and get the same question (a missed task is safe, a guessed one is not). "... on example to check in" is a
task on purpose: the card shows the task before you press Yes, and Yes only prepares. After a comma or dash the task
needs two or more words and may not start with so / I / you / we / it or filler ("example, ok", "example - quick",
"example, example-rpg too" are not tasks); after a colon or "to" / "and" / "then" one word is enough. "Start a claude on the desk:
tidy the board" opens the desk PM and the card says the task was not used. "Start a
job on ..." is its own job and still wins for those words. Two Yes presses make two team jobs (nothing runs; delete one).
Spoken or typed is passed on (`--how`), so the job's `ask.md` says how the words came.
Plan: `~/agent-os/jobs/2026-10-18-orchestration-design/start-claude-plan.md`.

**Moving a window.** "Move this window to my other screen", "move Chrome to the left monitor", "open VS Code
on my second monitor". A screen is said as other / second (the next one, left to right, wrapping), left, right,
top, bottom or a name from `hyprctl monitors -j` (LG, KTC, DP-3). It is checked against the live monitors when
the job runs, so nothing said ever reaches the dispatch as text. "This window" is the active window, or, when the
island has taken the focus, the most recently focused real window. A named app that is not open yet is opened
first, then moved, but only when the name is plainly that app ("move the file to the other screen" is answered,
never turned into opening a file manager). A window is found by its window class; a title only counts when it
holds the app's full name (a terminal titled "Claude Code" is not VS Code; the same rule goes to
`omarchy-launch-or-focus`). "Open a terminal / the browser / files / the editor on my other screen" always opens
a new window, so only that new window is moved, never an old one. It answers plainly when you only have one
screen, the window is already there, or no screen has that name. After the move it checks the window really got there. "Main" or "first" screen is refused for now
(it doesn't know which one is main).

**Sending files.** The words pick the device (laptop, test machine / handheld, phone / iPhone, with speech-to-text slips) and
the files. It only counts as a send when the request starts with a send word (send, put, copy, share...)
and names a device, and what it sends isn't a desktop setting: "remind me to put the charger on the laptop",
"put the volume up on the laptop" and "take a screenshot and send it to my phone" stay a reminder, a volume
change and a screenshot (the decider's desktop label is only overruled when no desktop action fits). Then
the files: a project plus "latest" or "files" is the newest shareable files for that project (Downloads folders
and files named after it, then its own folder; extra folders in `jobs/config/send-sources.json`); "latest
screenshot / picture / pdf" is the newest of that kind; otherwise a name search, used only when every word said is in the file's name and it is a document,
picture or video (any file when its whole name is said, a folder only when "folder" is said). "Send it",
"a text", "the call", "the time", an app's name ("put Spotify on the laptop") or a key word ("my ssh key",
"the .env") get a plain answer, not a card. It always asks first, and the
card lists every file. Limits: the laptop 10 files and 300 MB, the test machine and iPhone 5 files and 100 MB, a folder
only when you name it (200 files, nothing hidden, no links (shortcuts) inside; the copy and the zip keep a
link a link anyway). Never sent: hidden folders, programs, keys, passwords,
tokens. Several files for the laptop become one folder "<Project> - <date>" (stage copies in
`~/.local/state/send-to-laptop/files/`, deleted after 14 days). The laptop sends need the laptop on; the card
still queues them and says so when its status file is stale. `jobs/bin/send --dry <device> '<paths json>'`
shows what would run.

**Half-heard asks (since 2026-10-15).** When the intent decider says `unsure` itself (cut off, the TV talking,
two asks at once, something there's no job for), or the local decider is under that answer's own sure-bar
(`deciders/bars.py`), and no word rule fits, the answer is "Sorry, say that again?" with no search.

**Details from the local writer (since 2026-10-15).** The word rules pick out a job's details first (which app,
file, device, action, project), instantly. Only when they come up empty or unsure does qwen2.5 fill in a small
fixed form for that job (`jobs/details.py`, about 2 s). Anything <user> didn't actually say is blanked, the form is
turned back into a plain command, and that goes through the same finding and checking as a typed one, so nothing
the writer says runs as it is. On the details test (`jobs/test/details_test.py`, 103 asks) word rules alone got 72
right, with the writer 91. Switch: `jobs/config/details.json` (or `BRAIN_DETAILS=0|1`).

**The remember list, three times a day (since 2026-10-16).** At 9:00, 12:00 and 18:00
(`second-brain-remind-list.timer`, `jobs/bin/remind-list`) a notification lists what's open on
`~/OMARCHY-BRAIN/inbox/remembered.md` and the island says it (unless muted). Click it, pick the item and the agent
(Claude, Codex, Gemini, opencode, Grok, Copilot) in Omarchy's menu, and that agent opens in a terminal on the task
(in the project's folder when the item names one, else `~/projects`). The line is marked "→ started with …"
so it stops coming back. "What's on my remember list" also works as a question.

**Project tags on the remember list (since 2026-10-16).** Say "(repo: omarchy-setup)" in a remember ask, or
just name a project ("the example-game boss fight needs a pass"), and the line ends with `(repo: example-game)`.
Project names that are also everyday words (example, factory, digest, expedition, bullpen, …) are only tagged
when you say the tag yourself, so "remember to check the example levels" stays untagged. The tag stays when the
item is marked "→ started with …". Lines without a tag work as before.

`brain job run <id> --args-json '<job>'` runs one (the island does this). It rebuilds the command from the
job file and checks every argument (a known project, a note inside your brain's folders, an allowed
action), so a changed job object can't run anything else. No job deletes, sends mail or spends money.
To add a job: a new file in `jobs/`, its `build` and `_check` lines in `jobs/jobs.py`, and examples for the
intent decider (`deciders/README.md`).

## Your day: what moved, end of day and the morning standup

A day runs from **5 in the morning until end of day** (`/eod` in the desk, or "end of day" / "goodnight" to the
island). Without one it ends at 5 the next morning. "Yesterday" always means the day before, cut this way.

- **What moved?** `brain day` (or `yesterday`, `overnight`, a date like `2026-10-15`) shows about 20 lines:
  saved changes in every project (local and pushed branches, so helpers' worktrees count; not stashes or backup copies), grouped per project with the
  newest three; changes logged with `brain changed`; and folders that appeared or went away with no note.
  A script makes it in under a second, with no AI. Ask the island "what moved today?" and it says it.
  Each day's page is kept in `~/.local/share/second-brain/day/pages/` and is searchable (collection `days`).
- **Log a change by hand:** `brain changed move "~/old -> ~/new"`. `move-to-hdd.sh` does this by itself.
- **End of day:** type `/eod` in the desk, say "end of day" or "goodnight" (or type `brain eod`; `brain goodnight`
  is the same). The island says the day's summary. Items you ticked on the remember list move to
  `~/OMARCHY-BRAIN/inbox/done.md`. It names the jobs that finished today, read from agent-os's in-tray
  (`~/agent-os/jobs/in-tray.md`, made fresh with `agent-os intray`) and history files (`~/agent-os/jobs/history/`);
  it never moves a job folder (since 2026-10-23: agent-os packs finished jobs itself). Then it shows the open items; tick what may run tonight, one at a time, then Done.
  Ticked items run one by one through the morning build (Claude in its safe sandbox, never pushes; each gets a PM
  run folder). The rest stay queued. Helpers already working keep going; nothing else starts. The day is marked
  closed. The screen is not locked (since 2026-10-18); the computer won't sleep until the night's work is done
  (until 7 am if helpers were busy).
- **Morning standup:** at 9:00, before the remember list, the island says yesterday in short, how the
  overnight work went, who waits on you and how many new reports wait in your in-tray, and a notification opens the full page
  (`pages/standup-<date>.md`). Once a day; `brain standup --print` shows it any time.

Timers: `second-brain-day.timer` (5:00: keeps the folder list and yesterday's page) and the 9:00
`second-brain-remind-list` (standup first). Code: `day/day.py`, tests `day/test_day.py`.

## Speech to text (for the island)

`second-brain-stt.service` keeps voxtype's parakeet model loaded (`stt/server.py`, about 1 GB of
memory, http://127.0.0.1:8183, this computer only): about 0.3 s a question instead of 4–6 s. The island's
`bin/listen` uses it and falls back to `voxtype transcribe` when it is off.

## Staying fresh

Every hour the computer re-reads notes that changed (only those). To do it right now:
`brain reindex`. To see when it last ran: `systemctl --user list-timers | grep second-brain`.

**Is it keeping up?** `brain status` (add `--json` for a machine reading) lists each group of notes with how many
notes the index has, the newest note on disk against the newest the index has seen, and flags: `BEHIND` (more than
24 hours behind its folder), `without vectors` (older notes with no meaning-search yet), `FOLDER MISSING`, `RETIRE`.
It also says whether the Codex vectors made on the test machine worked: `index/codex-testbox.sh` leaves a one-line record in
`~/.local/share/second-brain/codex-testbox.status` after every run. It only reads; it never re-indexes. The weekly
`brain checkup` prints the same warnings first (lines starting `!!`). `hermes` is named there as a group to retire
(the agent stopped in September 2026); nothing is removed until <user> says so.

## The Deck (the map of your brain)

The 3D map of all your notes (views 1 Map, 2 Tunnel, 3 Radar; click a dot to read it; the voice panel) lives in `viz/`.
How to start it and refresh it: `viz/README.md`. It only runs on this computer.

## How it works (the short version)

The engine is **qmd** (by Tobi Lütke). It mixes word search and meaning search. Its models run on
the graphics card through Vulkan (the card is too old for qmd's CUDA build, and on the processor it
stalled when the computer was busy). It lets go of the card's memory after 5 quiet minutes.
One small server (`second-brain-mcp.service`) answers every Claude chat and `brain search`, so the
models are loaded once, not once per chat.

**Chats search like the island (since 2026-10-18).** Claude, Codex and Gemini chats used to search with only
their own words. A tiny go-between (`second-brain-chat-search.service`, `ask/chat_proxy.py`) now sits where they
connect: it adds your words from `ask/synonyms.tsv` and lets newer notes win close calls, exactly as `brain ask`
does, and passes everything else through untouched. On the fair test a chat-style search went from 17/34 to 18/34
(the island's own score that day); a plain-question search from 40–70 s to 0.1 s
(`eval/chat_search_test.py`). It uses no AI model and nothing leaves this computer.

**Every search is written down (since 2026-10-28).** Each time a chat searches your brain, the same go-between writes
one line in a private list on this computer: what was asked, which notes came back, how long it took, and which chat
asked (its name and the folder it was working in). Opening a note (`get`) gets a shorter line. `brain search` writes
a line too, and so does `brain ask` (in its own question list): since 2026-10-28 both say which chat or program ran
them (for example Claude, working in `second-brain`, with its nodeterm node's title), or "terminal" if you typed it
yourself. The Deck reads this list to show searches as they happen. The list is
`~/.local/state/second-brain/searches.jsonl` (only you can read it); it keeps the last 5,000 searches or 30 days,
whichever is less. If writing a line ever fails, the search still works. Nothing secret is kept (no passwords or keys).
To stop it, see "How to undo" below.

| Thing | Where |
|---|---|
| qmd program | global npm package (`npm ls -g @tobilu/qmd`) |
| Settings (which folders) | `~/.config/qmd/index.yml`, copied from `index/index.yml` here |
| The index and models | `~/.cache/qmd/` |
| Hourly update | `~/.config/systemd/user/second-brain-reindex.timer` |
| Agent memory backup | `~/.config/systemd/user/agent-memory-backup.timer` → `index/memory-backup.sh` (21:15 nightly: the store `~/projects/shared/` to `~/backups/agent-memory/`, 14 newest kept) |
| Search server | `~/.config/systemd/user/second-brain-mcp.service` (qmd, http://localhost:8182, this computer only) |
| Chats' door to it | `~/.config/systemd/user/second-brain-chat-search.service` → `ask/chat_proxy.py` (http://localhost:8181) |
| Search record | `~/.local/state/second-brain/searches.jsonl`, written by the chats' door and `brain search` (`ask/searchlog.py`) |
| `brain` command | `~/.local/bin/brain` → `bin/brain` here |
| Claude's tool | `brain` MCP server in `~/.claude.json` (and Codex, Gemini: points at the chats' door, 8181) |
| Local writer | `~/.config/systemd/user/second-brain-ollama.service` → `ask/` here (Ollama as you, models in `~/.ollama`, port 11434) |
| Haiku | `claude -p --model claude-haiku-5-5`, no tools, no MCP, no settings, nothing saved |
| Warm speech to text | `~/.config/systemd/user/second-brain-stt.service` → `stt/` here, venv `~/.local/share/second-brain/stt-venv` |

Change which folders are read: edit `index/index.yml`, then run `index/setup.sh`.
Numbers from the first build: `docs/history/index-report.md`.

## How to undo

```
systemctl --user disable --now second-brain-day.timer second-brain-reindex.timer second-brain-chat-search.service second-brain-mcp.service second-brain-ollama.service second-brain-stt.service agent-memory-backup.timer
rm ~/.config/systemd/user/agent-memory-backup.{timer,service}
rm ~/.config/systemd/user/second-brain-{day,reindex}.{timer,service} ~/.config/systemd/user/second-brain-{chat-search,mcp,ollama,stt}.service
claude mcp remove --scope user brain
rm ~/.local/bin/brain
npm uninstall -g @tobilu/qmd
rm -rf ~/.cache/qmd ~/.config/qmd ~/.local/share/second-brain
```

Then delete the "The second brain" and "day-journal" sections in `~/.claude/CLAUDE.md` and `~/.pi/agent/AGENTS.md`.

Stop only the search record (keeps everything else): go back to the version before it and restart the chats' door,
then delete the list.

```
git -C ~/projects/second-brain revert --no-edit 0ece549        # the undo-line fix, first
git -C ~/projects/second-brain revert -m 1 --no-edit d8eb3d7   # then the search-record merge
systemctl --user restart second-brain-chat-search.service
rm ~/.local/state/second-brain/searches.jsonl ~/.local/state/second-brain/searches.jsonl.lock
```

Your notes are untouched either way.

## Weekly check-up

Every answer is saved (`brain log`), <user> taps 👍/👎 on the island (or `brain rate last down "why"`), the island
notes when he says No, presses Esc partway or a job fails (`brain outcome`), and `brain checkup` scores the fair
test (`eval/heldout.jsonl`), the local decider's "sure and wrong" on the intent fair test, the week, and the week's likely
misses (`deciders/tools/learn_misses.py`): it learns from them and starts a the local decider training round on the test machine once
30+ new real examples have built up. It also leaves **drafts** for you: a test question for each 👎, likely miss or
question asked again, and a short lore story when the same cause shows up twice. Nothing is a lesson or a test until
you keep it: `brain drafts` lists them, `brain drafts keep <id>` / `brain drafts drop <id>` decides. The routine: `docs/checkup.md`;
in Claude Code: `/brain-checkup`. Unit tests: `python3 ask/test_ask_units.py` (through Crabbox).

Agent memory: rules and lessons for agents live in their own store, `~/projects/shared/` (private git, no remote; searched as the `memory` collection). `brain drafts keep <draft> --to projects/<repo>/lessons` moves a draft note into it, fills the front matter, makes a one-line summary with the local model (names filter first; if it is not sure, no model sees the note and it is marked local-only) and commits there. `brain ask` answers from a local-only note with the local writer only: Haiku never gets it.

## What's not in this repo

This folder is shared on GitHub (a private project) so helpers can work on the code somewhere else.
Only the code that makes the brain work goes up: search setup, the ask and answer code, jobs, the wake
word code, the deciders code, tests and these guides. Your own words stay on this computer. The list
of what is held back is in `.gitignore`; held-back files are **not deleted**, they stay here and keep
working.

| Held back | Why | Where it lives |
|---|---|---|
| Your notes and their copies, the chat notes | your private writing | your note folders, `~/.local/share/second-brain/chats/` |
| The search index and its models | big, and built from your notes | `~/.cache/qmd/` |
| Ask logs, 👍/👎 ratings, check-up answers | your questions and answers | `~/.local/state/second-brain/` |
| The Deck's map data (`data.js`) and its talk log | every note's title and path; what you said to the Deck | `~/.local/share/second-brain/viz/`, `~/.local/state/second-brain/talk-log.jsonl` |
| Wake word training audio and test clips, recordings | big, and recordings stay private | `~/.local/share/second-brain/wake-data/` |
| Virtual environments, model files (except the 400 KB wake word model) | big, rebuilt on each computer | `~/.local/share/second-brain/*-venv`, `~/.local/share/decider/checkpoints/` |
| `deciders/private.json` | the real names (family, clients) the privacy check looks for | here; start one from `deciders/private.example.json` |
| `deciders/brain-grounded/` practice data and tests | they quote your notes: business, clients, leads, prices, family | here |
| `deciders/brain-intent/src/`, `examples.jsonl`, `test.jsonl`, `test-real.jsonl` | they name family, clients and money, and hold your real asks | here |
| `ask/race-questions.tsv`, `ask/race-results*.jsonl` | business facts, a home IP address, answers quoting your notes | here; `ask/race-questions.example.tsv` shows the format |
| `eval/heldout.jsonl` (the fair test) | business facts and family names | here; `eval/heldout.example.jsonl` has 10 plain ones |

The test machine's address is read from the `testbox` entry in `~/.ssh/config`, not written in the code.

On a new computer the code runs, but the deciders can't be retrained and the fair test can't be scored
until those files are copied over by hand (never through GitHub).

History: GitHub gets a fresh start (one first commit, 2026-10-16). The older history named family,
clients and prices in practice data and commit messages, so it stays on this computer only: in
`.git/second-brain-before-github.bundle` and the local ref `refs/local-backup/master-before-github`.
