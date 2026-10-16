#!/usr/bin/env bash
# Install the second-brain qmd config and build the index.
# Undo: index/uninstall.sh
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
env -u QMD_EMBED_PARALLELISM qmd embed
qmd status
