# second-brain: what is here

The code, settings and guides for <user>'s second brain: search, short answers, jobs, the day page,
speech to text and the weekly check-up. Start with `README.md` (the plain guide for <user>).
`AGENTS.md` has the folder map and the rules for helpers. The notes themselves are not in this folder.

When you add, move or retire a file here, update this file in the same commit.

## Current (use these)

- `README.md`: the plain guide. Keep it true when behaviour changes.
- `AGENTS.md`: rules and the folder map.
- `index/index.yml`: which folders are searched, and the search advice that the search server shows
  Claude. The live copy is `~/.config/qmd/index.yml`; it changes only when `index/setup.sh` runs.
- `eval/drafts.py` (`brain drafts`): the check-up's drafts for <user> to keep or drop (test questions for the tuning set,
  lore stories for agent-os `lore/drafts/`). Tests: `eval/test_drafts.py`.
- `eval/memory_keep.py` (`brain drafts keep <draft> --to projects/<repo>/lessons`): `keep` for agent-memory drafts: moves a draft into the store
  `~/projects/shared/` (its own git, no remote; the `memory` collection in `index/index.yml`), fills the front matter, makes the
  summary with the local model after the names filter, commits there; a hand choice from `brain private` in the draft wins over the
  filter. Tests: `eval/test_memory_keep.py`.
- `index/memory-backup.sh`: the nightly copy of the agent memory store to the HDD (`agent-memory-backup.timer`, 21:15;
  `~/backups/agent-memory/`, 14 newest kept; stops if the HDD is not mounted). Tests: `index/test_memory_backup.py`.
- `ask/searchlog.py`: the search record (2026-10-28): one private line per chat search or read and per `brain search`,
  in `~/.local/state/second-brain/searches.jsonl` (the Deck shows it). Written by the chats' door `ask/chat_proxy.py`
  and `ask/search_cli.py`. `caller()` names who ran a `brain search` or `brain ask` (walks up the parent processes to
  the first known agent; also used by `ask/asklog.py`). Tests: `ask/test_searchlog.py`, `ask/test_caller.py`.
- `ask/memory.py` (`brain memory <repo> ["task"]`, 2026-10-28): the agent memory store's notes for a project and a task
  (scope, pinned first, summaries word for word, 2,000-token ceiling). The chats' door `ask/chat_proxy.py` serves the
  same as its `memory` tool. Tests: `ask/test_memory.py`, `ask/test_memory_tool.py`.
- `ask/private_tag.py` (`brain private <note> on|off`, `brain private list`, `--json` for the Deck; 2026-10-28): mark a memory note
  local-only by hand (`local-only-by: owner`) or unmark it; only those front matter lines change, backup first. Tests:
  `ask/test_private_tag.py`.
- `eval/memory_score.py` (2026-10-28): the agent memory score: runs `ask/memory.py` find on the agent test set and prints top-3
  hits and mean place of the right note (both rules, both rank kinds). Sets: `eval/memory-tuning.jsonl` (tune on it),
  `eval/memory-heldout.jsonl` (real run-spec prompts, git-ignored, measure only; `memory-heldout.example.jsonl` is its
  name-free part), `eval/memory-spotcheck.md` (<user>'s 10 questions), log `eval/memory-scores.tsv`. Tests: `eval/test_memory_score.py`.
- `deciders/private_guard.py`: the one check of `private.json` before anything goes to an online model (empty, broken or
  unreadable = send nothing). Tests: `deciders/test_private_fail_closed.py`, `ask/test_private_fail_closed.py`.
- `eval/README.md`: the fair test rules. `eval/scores.tsv`: the score log (add a row, newest last).
  `eval/heldout.example.jsonl` shows the format; the real `eval/heldout.jsonl` stays on this computer.
  `eval/seen.jsonl` is the tuning set (kept drafts land here, never in heldout).
- `docs/checkup.md`: the weekly check-up routine.
- `docs/writer-race.md`: the writer race (2026-10-15). The numbers in the README come from it.

## History (dated; kept for the record, may be out of date)

Moved into `docs/history/` on 2026-10-27. Do not use these for current numbers.

- `docs/history/search-test.md` (2026-10-15): the old 10-question search test. Replaced by `eval/heldout.jsonl`.
  Its questions are `index/search-questions.tsv`.
- `docs/history/index-report.md` (2026-10-15): numbers from the first index build.
- `docs/history/router-upgrades-plan.md`, `docs/history/handoff-upgrade2-finish.md`, `docs/history/upgrade2-report.md`
  (2026-10-15 and 16): the router upgrades plan, its handoff and its report. Finished.
- `docs/history/plan-day-journal.md` (2026-10-16): the plan for the day page, goodnight and the standup.
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
| `docs/` | results, plans and reports (see the lists above) |
