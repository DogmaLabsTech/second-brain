# Chat notes

This turns your old Claude Code chats into short notes the second brain can search.

- **Reads:** `~/.claude/projects/` (one `.jsonl` file per chat). It only reads; it never changes them.
- **Writes:** `~/.local/share/second-brain/chats/`, one note per chat, named
  `<date>-<project>-<first 8 letters of the chat id>.md`. Only you can open the folder.

## What a note holds

- A header: title, date, start time, project folder, chat id, how many messages, how long it ran,
  and which source file it came from.
- A title line: the chat's name if it has one (your own name for it, then Claude's automatic
  title), otherwise your first message cut to about 80 letters.
- The conversation: what you typed and what Claude wrote back, with the time of each message.
  Your messages are cut at about 1,000 letters and Claude's at about 2,000. If a note gets bigger
  than about 40 KB, the start and the end are kept and the middle is replaced by a line saying
  how many messages were cut.

## What is left out

- Everything Claude did with tools: commands, file reads, edits, search results, tool output.
- Claude's hidden thinking.
- Machine messages: system reminders, hook and plugin messages ("run-watch", "Stop hook
  feedback", burn-gauge), skill instructions, task notifications, `/clear`-style commands with
  nothing after them, command output, "request interrupted" lines, the summaries written when a
  chat was compacted, and pasted-image placeholders.
- Helper agents (subagents). Their chats are only used when a chat has nothing else in it.
- Chats with nothing left after this (57 of them, mostly tests) get no note.

## How redaction works

Before a note is written, every message (and the title) goes through `redact.py`, and the finished
note gets one more pass. Anything that looks like a secret becomes `[redacted]`, and your email
address becomes `[email]`. It blanks out:

- Known key shapes: `sk-…` (OpenAI, Anthropic), `ghp_…` and `github_pat_…` (GitHub), `AKIA…`
  (Amazon), `xoxb-…` (Slack), `tskey-…` (Tailscale), Google, Hugging Face, npm, Stripe and
  Telegram keys, JWTs (`eyJ…`), private key blocks, Slack and Discord webhook links.
- `Bearer …` / `Token …` / `Basic …` followed by something with a digit in it (or any `Bearer`
  value of 20+ letters).
- Passwords inside links, like `postgres://user:PASSWORD@host`.
- A value after a name that mentions key, token, secret, password, passwd, auth, cookie and
  similar, written with `=` (`api_key=…`). With `:` (`"token": "…"`) only when the value has a digit
  in it, so a sentence like "Key: the bar restarts" is kept.
- `.env`-style lines: `UPPER_SNAKE=value` where the value is longer than 8 letters. Values that
  are clearly folders (`/…`, `~…`, `$VAR`) are kept.
- Pairing codes: 6 to 8 digits within a short distance of the word "pair" or "pairing".
- Long hex strings (32 or more characters).
- Long random-looking strings (32 or more letters, digits, `+/_-`) that mix digits and letters
  and look random. Folder paths and names-with-dashes are checked piece by piece, so normal
  paths stay readable.

**Git ids are kept.** A 40-character git commit id would hit the hex rule, so a hex string of 7
to 40 characters is kept when it comes right after a git word: `commit`, `sha`, `hash`, `rev`,
`HEAD`, `merge`, `cherry-pick`, `revert`, `blob`, `tree`, or `git <something>`. Short git ids
(under 32 characters) never match anything in the first place. Chat ids (with dashes) are kept too.

The rules err on the side of blanking too much. The tests in `test_redaction.py` show what
must go (23 cases) and what must stay (11 cases).

## Run it

```bash
python3 -I ~/projects/second-brain/chats/convert.py            # only new or changed chats
python3 -I ~/projects/second-brain/chats/convert.py --all      # redo every chat
python3 -I ~/projects/second-brain/chats/convert.py --dry-run  # just say what it would do
python3 -I ~/projects/second-brain/chats/convert.py --sample 20 # 20 random chats into a temp folder, to look at
python3 -I ~/projects/second-brain/chats/convert.py --quiet    # one summary line (for the reindex timer)
```

It remembers each source file's time and size in `~/.local/share/second-brain/chats/.state.json`
and only redoes chats that changed. If a chat file disappears, its note is deleted. Two runs at
the same time can't happen: the second one sees the lock and quietly stops.

Tests (from the project folder):

```bash
CRABBOX_LOCAL=1 python3 -I -m unittest discover -s chats -p 'test_*.py'
```

## Undo

Delete the notes and the memory file; nothing else is touched:

```bash
rm -rf ~/.local/share/second-brain/chats
```

Then, if qmd already indexed them, run the reindex (or remove the `chats` collection) so search
forgets them too.
