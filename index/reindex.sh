#!/usr/bin/env bash
# Re-read changed notes and embed only new or changed ones. Run hourly by second-brain-reindex.timer.
set -euo pipefail
here="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
. "$here/env.sh"
command -v qmd >/dev/null || { echo "second-brain reindex: qmd is not installed (see docs/getting-started.md)" >&2; exit 1; }
mkdir -p "${BRAIN_HOME:-$HOME/brain}/chats"
# One run at a time (the timer and a manual `brain reindex` must not overlap).
lock="${XDG_DATA_HOME:-$HOME/.local/share}/second-brain/reindex.lock"
mkdir -p "$(dirname "$lock")"
exec 9>"$lock"
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
# The nodeterm canvas: new board events, agents' "finished" notes (nodeterm keeps them a few hours) and the node names
# shown now, into ~/brain/days/canvas/ (day/canvas.py; under a second when nothing is new).
if [[ -f "$here/../day/canvas.py" ]]; then
  python3 -I "$here/../day/canvas.py" run --quiet || echo "canvas import failed; indexing the rest anyway" >&2
fi
qmd update
# Embed every collection here except codex: its vectors are made on the test machine (index/codex-testbox.sh, <user> 2026-10-18).
conf="${XDG_CONFIG_HOME:-$HOME/.config}/qmd/index.yml"
# Read the list first: a failure inside `for c in $(...)` would be swallowed and the embed step silently skipped.
cols="$(python3 -I -c 'import sys, yaml; print(" ".join(k for k in yaml.safe_load(open(sys.argv[1]))["collections"] if k != "codex"))' "$conf")" \
  || { echo "second-brain reindex: cannot read $conf (run brain onboard; the python yaml package, PyYAML, must be installed)" >&2; exit 1; }
for c in $cols; do
  env -u QMD_EMBED_PARALLELISM qmd embed -c "$c"
done
# The test-machine step is optional: it only runs when the script is there (it is not part of the public repo).
if [[ -x "$here/codex-testbox.sh" ]]; then
  "$here/codex-testbox.sh" || echo "codex vectors on the test machine failed; trying next run" >&2
fi
# Drop vectors of removed or changed notes and compact the index.
qmd cleanup >/dev/null
echo "second-brain reindex done in $(( $(date +%s) - start ))s"
