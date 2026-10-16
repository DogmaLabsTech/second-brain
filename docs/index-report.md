# Index report (2026-10-15)

First build of the second-brain index with qmd 2.8.3 on desktop (GTX 1060 6 GB, 12 threads,
31 GB RAM). The computer was busy with other agents the whole time (load average 15 to 28), so
these times are on the slow side.

## What is indexed (after tuning)

| Collection | Folder | Files |
|---|---|---|
| `computer` | `~/OMARCHY-BRAIN` (no `example/muse-screens`, no Paperclip copies in `paperclip/*/`) | 121 |
| `business` | `~/user-labs-business` | 341 |
| `projects` | `README.md`, `CLAUDE.md`, `AGENTS.md`, `docs/**/*.md` of each `~/projects/*` | 177 |
| `chats` | `~/.local/share/second-brain/chats` (made by `chats/convert.py`) | 386 |
| **all** | | **1,025 files, about 4,000 chunks** |

No staging folder was needed for `projects`: qmd takes several masks at once
(`*/README.md,*/CLAUDE.md,*/AGENTS.md,*/docs/**/*.md`). qmd always skips `node_modules`, `.git`,
`.cache`, `vendor`, `dist` and `build`; `.venv`, `.secrets` and `.env*` are in the ignore lists.

## Time taken

| Step | Time |
|---|---|
| `npm install -g @tobilu/qmd@2.8.3` | 21 s |
| Downloading the three models (`qmd pull`, 2.2 GB, about 1.6 MB/s) | 22 min 43 s |
| Embedding `computer` (199 notes then, 853 chunks), Vulkan | 3 min 26 s |
| Embedding `business` + `projects` (498 notes, 2,179 chunks), Vulkan | 9 min 40 s |
| Embedding `chats` on the processor | stopped: about 90 notes in 25 min |
| Embedding the rest of `chats` (296 notes, 1,027 chunks), Vulkan | 4 min 58 s |
| First hourly run of the timer (13 changed notes, 100 chunks) | 40 s |

So a full rebuild is about 18 minutes of embedding on the graphics card; hourly runs take
under a minute.

## Size on disk

| What | Where | Size |
|---|---|---|
| The index (words, vectors, cache) | `~/.cache/qmd/index.sqlite` | 38 MB |
| Models | `~/.cache/qmd/models/` | 2.2 GB (embed 334 MB, re-ranker 639 MB, query writer 1.28 GB) |
| qmd itself | mise node 26.7.0 global `node_modules/@tobilu/qmd` | 854 MB |
| Settings | `~/.config/qmd/index.yml` (copy of `index/index.yml`) | 3 KB |

## Graphics card notes

- qmd's prebuilt **CUDA** build crashes on the GTX 1060 (Pascal):
  `CUDA error: no kernel image is available for execution on the device`, then a core dump.
  `QMD_LLAMA_GPU=vulkan` works (`qmd doctor`: "GPU vulkan; offloading enabled").
- On the **processor**, searches and the shared server stalled for 2 to 5 minutes whenever the
  computer was busy (llama.cpp threads fighting other work), and the server then failed with
  `DisposedError: Object is disposed` when qmd's 5-minute idle timer fired mid-request. On Vulkan,
  with `QMD_EMBED_PARALLELISM=1`, a cold search takes about 6 s and a warm one 0.3 s.
- The re-ranker is slow here even on Vulkan: about 65 s per new question (40 candidates). That's
  why searches skip it (see `search-test.md`).
- qmd frees its models after 5 idle minutes, so the card's memory comes back when nobody searches.
