# Handoff: finish router upgrade 2 (for a Pi agent, 2026-10-16)

Context: `docs/router-upgrades-plan.md`. Upgrades 1 and 3 are done; upgrade 2 is built and committed
(commits 718f82c and later) and only needs round 5's result. <user> is not technical: plain words, short.

## Where things stand

- the local decider round 4 (`brain-intent-v4`) was switched on at 00:05 (84.5% right on the 110-text fair test; round 3 was
  75.5%, sure and wrong 20/110). It was run by the older side-train script, so it has **no sure-bars**.
- Round 5 (`brain-intent-v5`, the 417 "unsure" practice texts) is being trained and scored by the user service
  `brain-side-train-v5` (`deciders/tools/side-train.sh`). Log: `~/.local/share/second-brain/deciders/side-train.log`.
  This brief runs after that service has ended.
- The new switch rule (in side-train.sh): v5 switches on only if it is right at least as often as v4, sure and
  wrong (`deciders/bars.py score --flat`) no more often, better at one of the two. When it switches, the script
  writes `deciders/brain-intent/bars.json` and `deciders/results/brain-intent-v5.bars.json` and commits.

## Your steps (repo: ~/projects/second-brain)

1. Read the log's last lines and `deciders/results/brain-intent-v5.json`, `.preds.jsonl`, `.current.json`,
   `.current.preds.jsonl` (current = round 4). If v5 failed or was never scored, skip to step 5 and say so.
2. Numbers, all on the same 110-text fair test (`python3 -I deciders/bars.py score <preds> --flat` and
   `python3 -I deciders/bars.py split <preds>`): round 3 (`results/brain-intent-v3-newtest.preds.jsonl`), round 4
   (`results/brain-intent-v5.current.preds.jsonl`), round 5. For each: right, sure and wrong (one 0.6 bar), and the
   split numbers (sure and wrong %, acted % with per-answer bars). Also `unsure` recall and how many questions
   became unsure (per_label in the json).
3. **Bars for the model in use:** if v5 was switched on, bars.json is already made; check it names v5's checkpoint.
   If v5 was kept off, make bars for round 4: `python3 -I deciders/bars.py pick
   deciders/results/brain-intent-v5.current.preds.jsonl <round 4 checkpoint path from
   ~/projects/decider/tasks/brain-intent.yaml>`; commit bars.json. Then check they are in use:
   `brain-decide intent "hmm hold on"` and a private one, `brain-decide intent "send mom's invoice to the uh"`
   (expect unsure or a below-bar reason where the model is under its bar).
4. Run `brain checkup --no-learn --no-train` with `CHECKUP_NOTE="upgrade 2 done: round N in use with sure-bars"`;
   it prints the local decider's "sure and wrong" with the bars in use.
5. Write it down: a "Round 5 and sure-bars (2026-10-16)" section in `deciders/RESULTS.md` (table: round, right,
   sure and wrong, split numbers); in `~/OMARCHY-BRAIN/system/second-brain.md` update the "Deciders" bullets (which
   round is on, the bars, "Sorry, say that again?", learning from real use, details from the local writer,
   the remember-list reminder 9/12/18) and "Weekly check-up" (the router step 4b: sure and wrong, likely misses,
   3 questions a week for <user>, the 30-example retrain trigger). Short, plain words, match the file's style.
6. Commit in this repo (end the message with `Co-Authored-By: Pi agent`). Don't touch `jobs/` rules, the island,
   or the bar; another session works there.
7. Tell <user>: `notify-send -a "Second brain" "Upgrade 2 done" "<one plain sentence: before → after>"`, and write
   the full plain-words report (3-6 short lines: what changed, before/after numbers, anything he must decide) to
   `docs/upgrade2-report.md` and commit it.

Rules: never send private text to the second decider; tests run on the test machine with `crabbox run -- …` (or `CRABBOX_LOCAL=1` if it
can't connect, and say so). Don't start new training rounds.
