#!/usr/bin/env bash
# Check that this computer has what second-brain needs. It installs nothing and needs no sudo.
#   ./install.sh          check and print the next steps
#   ./install.sh --json   the same check for scripts and AI agents: {"ok": true|false, "missing": [...], "optional_missing": [...]}
set -uo pipefail
root="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
json=0; [[ "${1:-}" == "--json" ]] && json=1
missing=(); optional=()
say() { [[ $json == 1 ]] || echo "$@"; }
check() { timeout 20 bash -c "$1" >/dev/null 2>&1; }
need() { if check "$2"; then say "ok        $1"; else say "MISSING   $1  ($3)"; missing+=("$1"); fi; }
want() { if check "$2"; then say "ok        $1"; else say "optional  $1  ($3)"; optional+=("$1"); fi; }
need "python 3.12+" "python3 -c 'import sys; sys.exit(sys.version_info < (3, 12))'" "install Python 3.12 or newer"
need "git" "git --version" "install git"
need "pyyaml" "python3 -c 'import yaml'" "pip install pyyaml"
need "qmd" "qmd --version" "the local notes search: npm i -g @tobilu/qmd (needs Node 22.12+)"
want "numpy" "python3 -c 'import numpy'" "only the Deck map needs it: pip install numpy"
want "node 22.12+" "node --version | python3 -c 'import sys; v = tuple(int(x) for x in sys.stdin.read().strip().lstrip(\"v\").split(\".\")[:2]); sys.exit(v < (22, 12))'" "only the Deck needs it"
want "ollama" "ollama --version" "optional local models for brain ask"
want "claude" "claude --version" "optional: Claude Code, if you want your chats turned into notes"
if [[ $json == 1 ]]; then
  # names hold spaces ("python 3.12+"), so they go in one per line, never joined by spaces
  python3 - "$((${#missing[@]}==0))" "$(printf '%s\n' ${missing[@]+"${missing[@]}"})" "$(printf '%s\n' ${optional[@]+"${optional[@]}"})" <<'PY'
import json, sys
print(json.dumps({"ok": sys.argv[1] == "1", "missing": [m for m in sys.argv[2].splitlines() if m], "optional_missing": [m for m in sys.argv[3].splitlines() if m]}))
PY
  exit $(( ${#missing[@]} == 0 ? 0 : 1 ))
fi
echo
if [[ ${#missing[@]} -eq 0 ]]; then
  echo "Ready. Next: bin/brain onboard   (you choose which notes and AI chats go into the brain)"
else
  echo "Fix the MISSING items above, then run ./install.sh again."; exit 1
fi
