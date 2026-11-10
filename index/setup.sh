#!/usr/bin/env bash
# Install the second-brain qmd config by hand and build the index. (brain onboard does this for you and adds
# the notes folders you choose; use this script only to reset the config to the shipped sections.)
set -euo pipefail
. "$(cd "$(dirname "$0")" && pwd)/env.sh"
here="$(cd "$(dirname "$0")" && pwd)"
conf="${XDG_CONFIG_HOME:-$HOME/.config}/qmd/index.yml"
mkdir -p "$(dirname "$conf")" "${BRAIN_HOME:-$HOME/brain}/chats"
# qmd does not expand a ~ in a collection path, so write the full path of this home folder
want="$(mktemp)"; trap 'rm -f "$want"' EXIT
sed "s#^\([[:space:]]*path:[[:space:]]*\)~/#\1${HOME%/}/#" "$here/index.yml" > "$want"
if [[ -f "$conf" ]] && ! cmp -s "$want" "$conf"; then
  cp "$conf" "$conf.bak-$(date +%Y%m%d-%H%M%S)"
fi
cp "$want" "$conf"
command -v qmd >/dev/null || { echo "setup: qmd is not installed (see docs/getting-started.md)" >&2; exit 1; }
qmd update
# Read the list first: a failure inside `for c in $(...)` would be swallowed and the embed step silently skipped.
cols="$(python3 -I -c 'import sys, yaml; print(" ".join(yaml.safe_load(open(sys.argv[1]))["collections"]))' "$conf")" \
  || { echo "setup: cannot read $conf (the python yaml package, PyYAML, must be installed)" >&2; exit 1; }
for c in $cols; do
  env -u QMD_EMBED_PARALLELISM qmd embed -c "$c"
done
qmd status
