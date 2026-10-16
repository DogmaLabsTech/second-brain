#!/usr/bin/env bash
# Monday reminder for the brain check-up (second-brain-checkup.timer). It only counts; the
# check-up itself runs in Claude Code (/brain-checkup), so nothing changes without <user>.
set -euo pipefail
read -r asks down < <(python3 -I - <<'PY'
import json, os, time
st = os.path.expanduser("~/.local/state/second-brain")
since = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(time.time() - 7 * 86400))
def rows(n):
    try:
        return [json.loads(l) for l in open(os.path.join(st, n)) if l.strip()]
    except OSError:
        return []
a = [r for r in rows("asks.jsonl") if r.get("at", "") >= since]
ids = {r["id"] for r in a}
d = sum(1 for r in rows("ratings.jsonl") if r.get("id") in ids and r.get("verdict") == "down")
print(len(a), d)
PY
)
notify-send -a "Second brain" -i brain "Brain check-up time" \
  "This week you asked ${asks} things and gave ${down} 👎. Type /brain-checkup in Claude and I'll look at them."
