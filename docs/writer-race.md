# Writer race (2026-10-15)

Who should write `brain ask`'s short answer? Each writer got the **same notes and the same prompt**
(`ask/ask.py` `SYSTEM` + the top 4 search hits, about 650 characters each) for 21 questions: the 10 from
`search-test.md`, 8 more with a known answer, and 3 the notes can't answer. The facts a right answer must
contain were written down first (`ask/race-questions.tsv`); the answers are in `ask/race-results.jsonl`.

Run again: `CRABBOX_LOCAL=1 python3 -I ask/race.py local:qwen2.5 local:granite4.2 haiku`
(needs `second-brain-ollama.service`; each local model gets an unscored warm-up first).

## Result

| Writer | Right (of 18) | Honest when not found (of 3) | Right overall (of 21) | Wrong or made up | First words, median | Whole answer, median | Slowest |
|---|---|---|---|---|---|---|---|
| local qwen2.5 3B | 9 | 3 | 12 (57%) | 7 | 5.2 s | 6.6 s | 10.2 s |
| local granite4.2 3B (thinking off) | 6 | 3 | 9 (43%) | 3 (+9 "not found" though the note was there) | 5.8 s | 7.8 s | 13.7 s |
| **Haiku** (`claude -p`, tools and MCP off) | **13** | **3** | **16 (76%)** | 3 | 3.4 s | 3.6 s | 6.1 s |
| gpt-oss | skipped | | | | | | |
| **`auto` (the default, run after the race)** | **13** | **3** | **16 (76%)** | 3 | 3.3 s | 4.0 s | 7.1 s |

- Scores were checked by hand after the regex check: two "right" became "wrong" (qwen2.5 said 0 founding
  spots are *left*, it's 0 *used*; Haiku's "why does the bar get killed" only described the one crash that
  wasn't memory).
- **gpt-oss** isn't on this computer: the only copy is `gpt-oss:120b-cloud`, which runs on Ollama's servers,
  not here, so it can't be a local writer (and the notes are private). The local `gpt-oss:20b` is a 13 GB
  download and would run on the processor here, far past the 60 s limit; not tried.
- **Speed:** both 3B models run mostly on the processor (an i7-8700 shared with everything else): CUDA 13 has no
  kernels for the GTX 1060, and Vulkan gets only the card's free memory (0.6 GB when the deciders and qmd are
  loaded, so 3%–44% of the layers). Reading the ~800-token prompt alone takes 4–9 s. Cold load from the big
  drive: 15–30 s.
- **Where they fail:** qwen2.5 picks the first note even when another one answers it and makes up numbers
  ("every 10 seconds"). granite4.2 is careful but says "I couldn't find that" for 9 answerable questions.
- The 2–3 misses all writers share are search misses (the right note wasn't in the top 4: Roku IP, website
  price, "how often") or a passage that starts too far from the fact (Pit Wall's local port, the island key).
- All three always said "I couldn't find that in your notes" for the 3 questions the notes can't answer.

## The default: `--writer auto`

The rule was: the best local writer if it's right at least 80% of the time and finishes within 4 s; otherwise
`auto` = local with a 4 s limit, then Haiku. No local writer came close (57% and 6.6 s at best), so **`auto`**
is the default:

- The local writer (qwen2.5, the better of the two) and Haiku start together. If the local answer is complete
  within 4 s (`BRAIN_LOCAL_SECONDS`), it is used and Haiku is stopped; otherwise Haiku's answer is used.
  Starting Haiku at once instead of after the 4 s saves those 4 s.
- A light check on the local answer (`local_ok`): "not found", fewer than 5 words, or file paths in it go to
  Haiku instead (Haiku is already running). Added after qwen2.5 answered "Why does the bar get killed:
  search/computer/system/memory-crashes.md".
- The local writer is skipped when its model isn't loaded (a cold load is 15–30 s) or when
  `BRAIN_LOCAL_SECONDS=0`.
- On this computer it means **Haiku writes most answers**, about 4–4.5 s from question to answer (the 4 s wait
  for the local writer is the floor). Later in the day qwen2.5 got faster (0.9–2.8 s: with the card less busy and
  Ollama reusing the prompt's start) and wrote some answers itself. The `auto` row above is the real default:
  as right as Haiku alone (`ask/race-results-auto.jsonl`). `--writer haiku` is about 1 s faster; `BRAIN_LOCAL_SECONDS=0`
  makes `auto` the same. Every answer says who wrote it (`writer`), so the test phase can count.
- Privacy: Haiku sees the question and the top 4 notes (business notes and chat notes too). That is the plan's
  documented backup; the second decider never sees them.

When the local writer could win: a graphics card with room for a 3B model (it would read the prompt in well
under a second), or a better small model. Re-run the race then.
