#!/usr/bin/env bash
# Monday check-up (second-brain-checkup.timer). It runs the check-up itself: `brain checkup --auto` runs the fair test,
# adds the score row to eval/scores.tsv, saves the report to ~/.local/state/second-brain/checkups/DATE.txt and sends the
# desktop notice with the result and the flags. It never learns online or starts a training round by itself.
# The fixing (reading the 👎, tuning the general way) still happens in Claude Code: /brain-checkup.
# If the run itself breaks, the notice says so (before 2026-10-27 this script only counted, so a missed Monday left no row).
set -uo pipefail
root="$(cd "$(dirname "$(readlink -f "$0")")/.." && pwd)"
"$root/bin/brain" checkup --auto
code=$?
if [[ $code -ne 0 && $code -ne 3 ]]; then
  # exit 3 = checkup.py already sent its own failure notice; anything else is a crash before it could
  notify-send -a "Second brain" -i brain "Brain check-up failed" \
    "The Monday check-up did not finish. Run: brain checkup  (see ~/.local/state/second-brain/checkups/)" || true
fi
exit "$code"
