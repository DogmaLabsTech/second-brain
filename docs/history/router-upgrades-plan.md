# Router upgrades: handoff brief (2026-10-15)

<user> approved three upgrades to how the second brain understands what he says. Build them **in this order:
2, 1, 3**, one at a time. Each one must be measured before and after, committed, and reported in plain words.
<user> is not technical: talk to him in words a 5-year-old could follow, keep him hands-off, verify before
saying done. Ask him only what truly needs him (plain-words AskUserQuestion, recommended option first).

## Read first

- `~/OMARCHY-BRAIN/system/second-brain.md` (the whole system; "Deciders" and "Weekly check-up" sections)
- `README.md` and `deciders/README.md` in this repo, `deciders/RESULTS.md`
- `~/projects/decider/AGENTS.md` (the `decide` tool and task files; don't break its interface)
- `jobs/jobs.py`, `jobs/*.json`, `ask/ask.py`, `ask/asklog.py`, `deciders/brain_decide.py`
- `~/OMARCHY-BRAIN/testbox-handheld/handheld.md`, sections on the local decider training (the test machine trains the local decider; tests run through Crabbox)

## Where things stand (evening of 2026-10-15)

- **the local decider** is a ModernBERT *classifier* (picks a label + confidence; it cannot write text). Task `brain-intent`
  has 13 labels; the local decider round 3 (`checkpoints/brain-intent-intent-testbox-v3-20261015`) is switched on: 88% on the test
  texts it knows. `brain-grounded` (yes/no: do the top 3 notes answer it) has no the local decider switched on yet.
- **Routing (<user>'s pick):** non-private text → the second decider first, the local decider if the second decider is unsure; private text (family, money,
  clients, leads) → the local decider only; grounded → the local decider only. Code: `deciders/brain_decide.py`.
- **Example makers:** `deciders/tools/gen_intent.py` (Haiku writes in many speaking styles, the second decider checks the
  non-private ones; `--labels`, `--out`), `gen_grounded.py` (real searches, Haiku marks with a quote as proof).
  `build_examples.py` reads every `brain-intent/src/train-*.tsv`; the fair test is `src/test.tsv` (never train on it).
- **Training on the side:** `deciders/tools/side-train.sh RUN …` (run it as `systemd-run --user --unit=… bash …`).
  It uploads to the test machine queue, waits, scores (`tools/evaluate.py … --preds`), and switches on only if better.
  **One may be running now** (`systemctl --user status brain-side-train`; log
  `~/.local/share/second-brain/deciders/side-train.log`) for `brain-grounded-v2` then `brain-intent-v4`
  (adds `job:send-file`). Let it finish; don't start a second test machine round while it runs. Read its result first.
- **Real asks** are logged to `~/.local/state/second-brain/asks.jsonl` (question, intent and who decided, job,
  answer, timings). 180 rows so far, but only `from: island` (24) are <user>'s; `cli` rows are test runs by other
  sessions and must be ignored for learning. 👎/👍 go to `ratings.jsonl` (empty so far).
- Another session (the voice/desktop-jobs work) is also changing `brain-intent` labels and `jobs/`. Check
  `git log` before you start and before each commit; never overwrite their work. If labels change, regenerate
  examples for the new label and add test texts for it.

## Upgrade 2: the local decider learns to say "I don't know" (do this first)

Problem: the local decider is sometimes 98% sure and wrong (an "unsure" ask labelled as a desktop job or an app).
1. **Off-topic and half-heard examples:** about 400 new `unsure` training texts: cut-off speech, TV or other
   people in the background, two requests at once, things there is no job for (email someone, buy something,
   book a table, restart the test machine), filler ("I've seen this so like"). Include <user>'s real half-heard island asks
   from `asks.jsonl` (`from: island`). Add ~20 of them to the fair test too (kept apart from training).
2. **Retrain** through `side-train.sh` (after the running round finishes).
3. **Per-answer sure-bars:** from the new model's `--preds` on the fair test, pick for each label the lowest
   confidence bar where the local decider is right ≥95% of the time; ≥98% for jobs that change something (send-file,
   desktop actions like shut down/restart/log out, start-claude). Store them where `brain_decide.py` can read
   them (for example a small JSON next to the task, or per-question thresholds in the task file if `decide`
   supports it; check `decider/AGENTS.md`). Below the bar: non-private → the second decider; private → `unsure`, and the
   island says "Sorry, say that again?".
4. **New check-up number:** "sure and wrong" rate on the fair test, added to `eval/checkup.py` output and
   `eval/scores.tsv`. It should go down.
Done when: sure-and-wrong is lower than round 3/4's, overall accuracy is not lower, and the bars are in use.

## Upgrade 1: learn from real use

1. **Mark likely misses** (only `from` island, bar or obsidian; never `cli`): asked again within ~30 s in
   different words; a job failed or the answer starts "I couldn't find"/"I don't know how"; 👎; Esc or "No"
   partway (check what the island logs; add a small log line in the island plugin
   `~/.config/omarchy/plugins/user.brain-island/` if needed, commit there).
2. **Fill in the right answer** automatically when clear (the ask that worked right after a rephrase gives the
   label; a failed job's text plus what <user> did next). Unclear ones go to a short list for <user>, asked at most
   a few a week through the Monday check-up. Nothing private goes to the second decider.
3. **Real-voice test:** about 1 in 5 confirmed misses go to a new fair test file (real speech-to-text mistakes);
   the rest go to a `brain-intent/src/train-real.tsv`. `side-train.sh` must require "not worse" on this test too.
4. **Retrain when 30+ new examples** have built up: the weekly check-up (`/brain-checkup` skill,
   `docs/checkup.md`, `eval/`) kicks `side-train.sh`. Report misses found and what changed in the check-up.
Done when: a dry run over the current log marks misses sensibly (show <user> 5 examples in plain words), the
check-up shows them, and the retrain trigger is tested.

## Upgrade 3: details pulled out by the local writer

1. Keep the word rules (`jobs/jobs.py`, `jobs/desktop.py`) as the instant first try.
2. When they come up empty or unsure for a job with details (open-app, open-file, send-file, desktop,
   start-claude, tv, music), ask qwen2.5 through Ollama (`second-brain-ollama.service`) with a fixed JSON format
   built from that job's `args` in its job file (Ollama's `format` = JSON schema). Short output only.
3. The job runner still checks every value exactly as now (`_check` and the desktop checks): app installed,
   file exists, device in the list. Never run on an unchecked value; missing → ask <user> for it in one line.
4. **Details test:** ~100 asks with the expected details (include <user>'s real island asks). Switch on only if it
   gets more right than word rules alone. Record speed: word-rule jobs must stay as fast; qwen path ~1–2 s.
Done when: the details test improves, the speed is recorded, and a real island try works for "send that to my
laptop"-style asks.

## Rules

- Tests run on the test machine through Crabbox (`crabbox run -- …` from the repo root), not locally, unless Crabbox
  can't connect (then `CRABBOX_LOCAL=1` and say so). the local decider training uses the test machine's Windows side (the queue).
- Commit each step in the repo it belongs to (this repo; `decider` for task files; the island plugin), with the
  attribution lines from your system reminder. Big files (>1 GB) go on the HDD (`checkpoints` already is).
- Update `~/OMARCHY-BRAIN/system/second-brain.md` ("Deciders", "Weekly check-up") and `deciders/RESULTS.md`.
- Never send private text to the second decider. Haiku may read note bits and ask texts for making/marking examples (<user> OK'd).
- Before each upgrade, tell <user> in one or two plain sentences what you're starting; after it, what changed
  with the before/after numbers.
