# second-brain: what is here

The code, settings and guides for <user>'s second brain: search, short answers, jobs, the day page,
speech to text and the weekly check-up. Start with `README.md` (the plain guide for <user>).
`AGENTS.md` has the folder map; the rules for helpers come from the agent memory store (`brain memory second-brain "<task>"`). The notes themselves are not in this folder.

When you add, move or retire a file here, update this file in the same commit.

## Current (use these)

- `README.md`: the plain guide. Keep it true when behaviour changes.
- `AGENTS.md`: the folder map and the short rules; the full rules come from memory.
- `index/index.yml`: which folders are searched, and the search advice that the search server shows
  Claude. The live copy is `~/.config/qmd/index.yml`; it changes only when `index/setup.sh` runs.
- `eval/drafts.py` (`brain drafts`): the check-up's drafts for <user> to keep or drop (test questions for the tuning set,
  lore stories for agent-os `lore/drafts/`). Tests: `eval/test_drafts.py`.
- `eval/memory_keep.py` (`brain drafts keep <draft> --to projects/<repo>/lessons`): `keep` for agent-memory drafts: moves a draft into the store
  `~/brain/agents/` (the brain's git, no remote; the `memory` collection in `index/index.yml`), fills the front matter, makes the
  summary with the local model after the names filter, commits there; a hand choice from `brain private` in the draft wins over the
  filter. Tests: `eval/test_memory_keep.py`.
- `eval/memory_drafts.py` (`brain memory-drafts add|list|drop|expire`, 2026-10-28): the lesson drafts of the agent memory
  store (what agent-os's librarian step writes after a job): note format with `already-known` and `was-pushed`, the cap
  of 5 a week (`draft-log.jsonl` in the store), 30-day expiry to `history/expired-drafts/`. Haiku writes the draft's summary and body
  after the names filter (`BRAIN_DRAFT_WRITER=haiku|fixed`; fallback = the fixed-rule draft; `written-by:` says which). Tests: `eval/test_memory_drafts.py`.
- `eval/memory_flags.py` (`brain memory-flags [run|list|confirm|retire]`) and `ask/memory_flagfile.py`: which kept notes may
  be out of date (file gone, file changed a lot, a newer note says the opposite), `flags.jsonl` in the store, the 30-day
  lapse out of the push, the 90-day "still true?" for pinned notes, <user>'s confirm and retire. `ask/memory.py` marks
  flagged notes. Tests: `eval/test_memory_flags.py`.
- `ask/memory_decide.py` (agent memory job 9, 2026-10-28): the memory system asks decider (the second decider now, the local decider later) five choices (memory-real-task for
  the start hook, memory-same-note and memory-lesson-worth for `memory_drafts.add`, memory-conflict for the flags, memory-kind a helper) and
  falls back to the old word rule on `sure: false`; `BRAIN_MEMORY_DECIDER=on|off`, default on. Log: `memory-decider.jsonl` in the state
  folder (no text). Tests: `eval/test_memory_decide.py` (a fake decide; the other memory tests set the switch off).
- `eval/memory_labels.py` (`build | ask | report`): the label sets and spot-check files for training the local decider on those five tasks (phase B), in the
  git-ignored `eval/labels/` (private text). `ask` makes real the second decider calls through decider.
- `eval/memory_week.py`: the "Agent memory for <user>" block of `brain checkup` (drafts, flags, pinned due) and its two numbers
  (repeats that got through, second-round rate; both in `scores.tsv`). Tests: `eval/test_memory_week.py`.
- `index/brain-backup.sh`: the nightly copy of all of `~/brain` (every section, private notes, its git) to the HDD
  (`brain-backup.timer`, 21:15; `~/backups/brain/`, 14 newest kept; stops if the HDD is not mounted).
  Tests: `index/test_brain_backup.py`. (Was `memory-backup.sh`, the agent store only, until one brain, 2026-10-28.)
- `ask/chat_proxy.py` private filter (one brain, 2026-10-29): `get`, `multi_get`, `resources/read`, `query` and REST
  /query and /search answers are read whole and every `private/` note is left out before a chat gets them; `brain ask`
  and `brain search` run by an online agent (Claude, Codex, ...) leave them out too (`ask.HIDE_PRIVATE`). Tests:
  `ask/test_chat_proxy_private.py`, `ask/test_ask_units.py` (OnlineAgents).
- `jobs/bin/open-claude`: start-claude's command, a terminal with Claude in the project folder (`desk` = ~/agent-os);
  replaced the retired project manager's `pm open --launch`. Tests: `jobs/test_open_claude.py`.
- `index/test_brain_paths.py`: one brain (2026-10-28): every note writer and reader (agent store, chats, day pages,
  remember list, project pages, the code's folder names) points into `~/brain` by default.
- `ask/searchlog.py`: the search record (2026-10-28): one private line per chat search or read and per `brain search`,
  in `~/.local/state/second-brain/searches.jsonl` (the Deck shows it). Written by the chats' door `ask/chat_proxy.py`
  and `ask/search_cli.py`. `caller()` names who ran a `brain search` or `brain ask` (walks up the parent processes to
  the first known agent; also used by `ask/asklog.py`). Tests: `ask/test_searchlog.py`, `ask/test_caller.py`.
- `ask/memory.py` (`brain memory <repo> ["task"]`, 2026-10-28): the agent memory store's notes for a project and a task
  (scope, pinned first, summaries word for word, 2,000-token ceiling; all-projects notes only when pinned or matched, <user> 2026-10-28). The chats' door `ask/chat_proxy.py` serves the
  same as its `memory` tool. Tests: `ask/test_memory.py`, `ask/test_memory_tool.py`.
- `ask/private_tag.py` (`brain private <note> on|off`, `brain private list`, `--json` for the Deck; 2026-10-28): mark a memory note
  local-only by hand (`local-only-by: owner`) or unmark it; only those front matter lines change, backup first. Tests:
  `ask/test_private_tag.py`.
- `eval/memory_score.py` (2026-10-28): the agent memory score: runs `ask/memory.py` find on the agent test set and prints top-3
  hits and mean place of the right note (both rules, both rank kinds). Sets: `eval/memory-tuning.jsonl` (tune on it),
  `eval/memory-heldout.jsonl` (real run-spec prompts, git-ignored, measure only; `memory-heldout.example.jsonl` is its
  name-free part), `eval/memory-spotcheck.md` (<user>'s 10 questions), log `eval/memory-scores.tsv`. Tests: `eval/test_memory_score.py`.
- `ask/memory_hook.py` (`bin/brain-memory-hook`, 2026-10-28): Claude's start-of-session memory push (a `UserPromptSubmit`
  hook: first prompt per session, project from the folder or worktree, 2.5 s ceiling, silent on any trouble).
  `index/claude-memory-hook.json`: a settings file with only this hook, for `claude --settings` tests. Not in
  `~/.claude/settings.json` until <user> says yes (README, "the memory hook"). Tests: `ask/test_memory_hook.py`.
- `deciders/private_guard.py`: the one check of `private.json` before anything goes to an online model (empty, broken or
  unreadable = send nothing). Tests: `deciders/test_private_fail_closed.py`, `ask/test_private_fail_closed.py`.
- `eval/README.md`: the fair test rules. `eval/scores.tsv`: the score log (add a row, newest last).
  `eval/heldout.example.jsonl` shows the format; the real `eval/heldout.jsonl` stays on this computer.
  `eval/seen.jsonl` is the tuning set (kept drafts land here, never in heldout).
- `day/canvas.py` (`brain canvas`, 2026-10-30): the nodeterm board logs and agents' "finished" notes as one page per
  day in `~/brain/days/canvas/`; archive and node names in `~/.local/share/second-brain/canvas/`; run by the hourly
  reindex and the day page. Tests: `day/test_canvas.py`.
- `day/tests_week.py` (`brain tests-week`, 2026-10-30): agent-os's failure log and flaky lists as one page per week in
  `~/brain/days/tests/`; the 5:00 `day nightly` writes it. Tests: `day/test_tests_week.py`.
- `media/media.py` (`media add|find|public|show|stray`, `bin/media`, 2026-10-30): the media store `~/Media/agents/<project>/`: every
  screenshot, video and GIF an agent makes, with a `.md` sidecar (what, why, project, date, commit, who, `public: false`).
  Private by default; only `media public` (<user>, never an agent) marks public. `media stray` counts untracked png/mp4/gif/webm
  in code folders per project (`--list` for files, `--worktrees` to include worktrees). The `media` collection in `index/index.yml` searches the sidecars. Tests: `media/test_media.py`.
  `media/stray_watch.py` + `media-stray.service/.timer` (22:30, 2026-10-30): tells the deputy one line when a project has new strays;
  counts in `~/.local/state/second-brain/media-stray-counts.json`; tell() counts rc 5 + "saved in" as delivered (systemd). Not installed until <user> says yes (install lines in the README).
- `viz/` (2026-10-28): the Deck, moved in from the prototype folder. `viz/CONTEXT.md` says which file is current;
  its data (`data.js`) and talk log stay outside git (`~/.local/share/second-brain/viz/`, `~/.local/state/second-brain/`).
  Tests: `viz/server/test_server.py`, `viz/server/test_talk.py`, `viz/app/test/rules.test.js`, and the app smoke test `viz/tests/smoke.mjs`.
- `docs/checkup.md`: the weekly check-up routine.
- `docs/writer-race.md`: the writer race (2026-10-15). The numbers in the README come from it.

## History (dated; kept for the record, may be out of date)

Moved into `docs/history/` on 2026-10-27. Do not use these for current numbers.

- `~/brain/projects/second-brain/docs/history/search-test.md` (2026-10-15): the old 10-question search test. Replaced by `eval/heldout.jsonl`.
  Its questions are `index/search-questions.tsv`.
- `~/brain/projects/second-brain/docs/history/index-report.md` (2026-10-15): numbers from the first index build.
- `~/brain/projects/second-brain/docs/history/router-upgrades-plan.md`, `~/brain/projects/second-brain/docs/history/handoff-upgrade2-finish.md`, `~/brain/projects/second-brain/docs/history/upgrade2-report.md`
  (2026-10-15 and 16): the router upgrades plan, its handoff and its report. Finished.
- `~/brain/projects/second-brain/docs/history/plan-day-journal.md` (2026-10-16): the plan for the day page, goodnight and the standup.
  Built; the code is in `day/`.
- `docs/wake-false-wake-test.json`: the output of one wake-word false-wake test. Not moved yet: the wake test
  (`wake/test/false_wake_test.py`) writes this exact path by default.
- `deciders/results/`: result files from past training and test rounds (v1 to v6, testbox and second_decider runs).
  Check the decider files before you treat any one of them as current.

## Folders

| Folder | What |
|---|---|
| `bin/` | `brain` and its helpers |
| `index/` | search setup: collections, reindex script, timers, search test |
| `chats/` | converters for old Claude and Codex chats, with redaction rules and tests |
| `ask/` | the answer helper: search, decide, write, sources |
| `deciders/` | task files and example sets for the decider models |
| `day/` | the per-day page and its timer |
| `eval/` | the fair test, the check-up and its scores |
| `stt/` | the speech-to-text server |
| `obsidian/` | the Obsidian plugin and vault settings copy |
| `wake/` | the wake-word model, training and tests |
| `jobs/` | one small file per job |
| `media/` | the media store command (`media add, find, public, stray`) |
| `viz/` | the Deck (3D map of the notes): page, server, app window, map makers; its own `CONTEXT.md` |
| `docs/` | results, plans and reports (see the lists above) |
