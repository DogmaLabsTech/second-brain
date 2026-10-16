# Plan: day journal, goodnight and the morning standup (2026-10-16)

Why: "what moved today?" made Claude read ~150 commit lines and two logs to write 15 lines, and it
re-learned where to look each time. <user> picked all six fixes (chat, 2026-10-16 01:40).

## What gets built (all in `day/`)
1. **Day page** (`brain day [today|yesterday|overnight|DATE]`): a script, no model, gathers the day's
   events and groups them per project. About 20 lines. Saved as
   `~/.local/share/second-brain/day/pages/YYYY-MM-DD.md` and searchable (qmd collection `days`).
2. **One change log** (`brain changed <kind> "<what>"`): one JSON line per change in
   `~/.local/share/second-brain/day/changes.jsonl`. `move-to-hdd.sh` writes to it; agents are told to
   after moving things by hand. Saved changes (git) are read straight from the repos.
3. **Folder check**: a list of the main folders is kept each night; the day page lists folders that
   appeared or went away with no line in the change log ("moved without a note").
4. **Jobs without Claude**: `what-changed` ("what moved today", "what happened overnight") and
   `goodnight` ("I'm going to bed", "close out the day"). The word rule beats the decider's
   "question" for these (it was trained before they existed); add them to the next the local decider round.
5. **Helper rule**: the agent rules say: for "what changed" questions, run `brain day` first.
6. **Day = 5 am to 5 am**, ended early by goodnight.

## Goodnight (<user>'s answers, 2026-10-16)
- Overnight: what is already running keeps going, plus remember-list items <user> ticks at bedtime.
  Nothing else starts. Ticked items run one by one through `morning-build --note` (Claude, its
  allowed-commands sandbox, never pushes, recorded in a PM run folder).
- The screen locks and goes dark; sleep is held off (`systemd-inhibit`) until the queue is done.
- Typed: `brain goodnight`. Said: the island's goodnight job (asks first).

## Morning standup
- At 9:00, before the remember list (same timer, `ExecStartPre`), once a day: spoken by the island,
  plus a page `pages/standup-YYYY-MM-DD.md` (notification click opens it).
- It says: yesterday in short, what ran overnight and how it went, which helpers wait on <user>.
