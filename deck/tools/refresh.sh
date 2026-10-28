#!/usr/bin/env bash
# Make a new map (data.js) after the hourly reindex (plan: brief 24 part 3). Run by second-brain-viz-refresh.service, which the
# reindex starts when it is done; by hand: viz/tools/refresh.sh (--force: build even if the index did not change).
# - one run at a time (a lock); low priority (nice 10)
# - skips the work when the index did not change since the last good map (note count, newest change, number of note pieces)
# - builds into a temporary folder, checks the result (enough notes, every note's neighbours scored: `ns`), and only then
#   swaps it in (an atomic rename, so the Deck never reads half a file). A failed run keeps the old data.js.
# - one line per run in ~/.local/state/second-brain/viz-refresh.log
# Env: VIZ_OUT (the map's folder, ~/.local/share/second-brain/viz), VIZ_INDEX (the search index, read-only),
# VIZ_MIN_NOTES (100: fewer notes than this, or under half of the old map's, counts as broken).
set -uo pipefail
here="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
out="${VIZ_OUT:-$HOME/.local/share/second-brain/viz}"; index="${VIZ_INDEX:-$HOME/.cache/qmd/index.sqlite}"; min="${VIZ_MIN_NOTES:-100}"
logf="$HOME/.local/state/second-brain/viz-refresh.log"
mkdir -p "$out" "$(dirname "$logf")"
log() { printf '%s %s\n' "$(date -Iseconds)" "$*" | tee -a "$logf"; }
exec 9>"$out/refresh.lock"
flock -n 9 || { log "skipped: another refresh is running"; exit 0; }
start=$(date +%s)

# what the map is made from: changes when a note is added, changed or removed (or its pieces are embedded again)
sig=$(python3 -I - "$index" <<'EOF'
import sqlite3, sys
c = sqlite3.connect("file:" + sys.argv[1] + "?mode=ro", uri=True)
print(*c.execute("select count(*), max(modified_at) from documents where active=1").fetchone(), c.execute("select count(*) from vectors_vec_rowids").fetchone()[0])
EOF
) || { log "FAILED: could not read the search index $index; old data.js kept"; exit 1; }
if [[ ${1:-} != --force && -f $out/data.js && "$(cat "$out/refresh.sig" 2>/dev/null)" == "$sig" ]]; then
  log "skipped: index unchanged ($sig)"; exit 0
fi

tmp=$(mktemp -d "$out/.refresh-XXXXXX"); trap 'rm -rf "$tmp"' EXIT
if ! { VIZ_INDEX="$index" nice -n 10 python3 -I "$here/build_data.py" "$tmp" && VIZ_INDEX="$index" nice -n 10 python3 -I "$here/add_sim.py" "$tmp"; } >"$tmp/run.log" 2>&1; then
  log "FAILED: the map makers stopped ($(grep -v '^\s*$' "$tmp/run.log" | tail -1 | cut -c1-200)); old data.js kept"; exit 1
fi
# the check: the file reads back, enough notes, positions and neighbour scores filled in for every note
if ! n=$(python3 -I - "$tmp/data.js" "$out/data.js" "$min" 2>"$tmp/check.log" <<'EOF'
import json, sys
def load(p):
    raw = open(p).read(); return json.loads(raw[raw.index("=") + 1:].rstrip().rstrip(";"))
docs = load(sys.argv[1])["docs"]
try: old = len(load(sys.argv[2])["docs"])
except Exception: old = 0
bad = [d.get("id") for d in docs if not (isinstance(d.get("ns"), list) and len(d["ns"]) == len(d.get("nb") or []) > 0 and len(d.get("xyz") or []) == 3 and len(d.get("uv") or []) == 2)]
if len(docs) < int(sys.argv[3]) or len(docs) < old / 2: sys.exit(f"only {len(docs)} notes (old map: {old}, at least {sys.argv[3]})")
if bad: sys.exit(f"{len(bad)} notes without neighbour scores or a place, e.g. {bad[:3]}")
print(len(docs))
EOF
); then
  log "FAILED: the new map did not pass the check ($(tail -1 "$tmp/check.log" | cut -c1-200)); old data.js kept"; exit 1
fi
mv -f "$tmp/data.js" "$out/data.js" && printf '%s\n' "$sig" >"$out/refresh.sig"
log "ok: new data.js with $n notes in $(( $(date +%s) - start ))s"
