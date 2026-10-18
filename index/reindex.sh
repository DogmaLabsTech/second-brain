#!/usr/bin/env bash
# Re-read changed notes and embed only new or changed ones. Run hourly by second-brain-reindex.timer.
set -euo pipefail
here="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
. "$here/env.sh"
mkdir -p "$HOME/.local/share/second-brain/chats"
# One run at a time (the timer and a manual `brain reindex` must not overlap).
exec 9>"$HOME/.local/share/second-brain/reindex.lock"
flock -n 9 || { echo "second-brain reindex already running, skipping"; exit 0; }
start=$(date +%s)
# Turn new or changed Claude chats into notes first (chats/convert.py, only changed ones).
if [[ -f "$here/../chats/convert.py" ]]; then
  python3 -I "$here/../chats/convert.py" --quiet || echo "chat converter failed; indexing the rest anyway" >&2
fi
# The same for Codex chats (chats/codex.py), into chats/codex/.
if [[ -f "$here/../chats/codex.py" ]]; then
  python3 -I "$here/../chats/codex.py" --quiet || echo "codex chat converter failed; indexing the rest anyway" >&2
fi
qmd update
env -u QMD_EMBED_PARALLELISM qmd embed
# Drop vectors of removed or changed notes and compact the index.
qmd cleanup >/dev/null
echo "second-brain reindex done in $(( $(date +%s) - start ))s"
