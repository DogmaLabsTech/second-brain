#!/usr/bin/env bash
# Install the second-brain qmd config by hand and build the index. (brain onboard does this for you and adds
# the notes folders you choose; use this script only to reset the config to the shipped sections.)
set -euo pipefail
. "$(cd "$(dirname "$0")" && pwd)/env.sh"
here="$(cd "$(dirname "$0")" && pwd)"
conf="${XDG_CONFIG_HOME:-$HOME/.config}/qmd/index.yml"
mkdir -p "$(dirname "$conf")" "${BRAIN_HOME:-$HOME/brain}/chats"
if [[ -f "$conf" ]] && ! cmp -s "$here/index.yml" "$conf"; then
  cp "$conf" "$conf.bak-$(date +%Y%m%d-%H%M%S)"
fi
cp "$here/index.yml" "$conf"
qmd update
for c in $(python3 -I -c 'import os, yaml; print(" ".join(yaml.safe_load(open(os.path.expanduser("~/.config/qmd/index.yml")))["collections"]))'); do
  env -u QMD_EMBED_PARALLELISM qmd embed -c "$c"
done
qmd status
