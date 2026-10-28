#!/usr/bin/env bash
# Install the second-brain qmd config and build the index.
# Undo: README.md, "How to undo".
set -euo pipefail
. "$(cd "$(dirname "$0")" && pwd)/env.sh"
here="$(cd "$(dirname "$0")" && pwd)"
conf="${XDG_CONFIG_HOME:-$HOME/.config}/qmd/index.yml"
mkdir -p "$(dirname "$conf")" "$HOME/.local/share/second-brain/chats"
if [[ -f "$conf" ]] && ! cmp -s "$here/index.yml" "$conf"; then
  cp "$conf" "$conf.bak-$(date +%Y%m%d-%H%M%S)"
fi
cp "$here/index.yml" "$conf"
qmd update
# Every collection but codex here; codex's vectors are made on the test machine (index/codex-testbox.sh).
for c in $(python3 -I -c 'import os, yaml; print(" ".join(k for k in yaml.safe_load(open(os.path.expanduser("~/.config/qmd/index.yml")))["collections"] if k != "codex"))'); do
  env -u QMD_EMBED_PARALLELISM qmd embed -c "$c"
done
"$here/codex-testbox.sh" || echo "codex vectors on the test machine failed; the hourly run tries again" >&2
qmd status
