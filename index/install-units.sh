#!/usr/bin/env bash
# Copy the optional systemd user units (hourly reindex, deck refresh, day page, reminders, backups, ...) into
# ~/.config/systemd/user with this clone's real path filled in. It enables nothing: you decide which to turn on.
#   index/install-units.sh [--dry-run]
set -euo pipefail
root="$(cd "$(dirname "$(readlink -f "$0")")/.." && pwd)"
dest="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
dry=0; [[ "${1:-}" == "--dry-run" ]] && dry=1
[[ $dry == 1 ]] || mkdir -p "$dest"
find "$root" -path "$root/.git" -prune -o \( -name '*.service' -o -name '*.timer' \) -print | sort | while read -r unit; do
  name="$(basename "$unit")"
  echo "$name"
  [[ $dry == 1 ]] || sed "s#%h/projects/second-brain#$root#g" "$unit" > "$dest/$name"
done
if [[ $dry == 0 && -d "$root/index/second-brain-reindex.service.d" ]]; then
  mkdir -p "$dest/second-brain-reindex.service.d"
  for f in "$root"/index/second-brain-reindex.service.d/*.conf; do
    sed "s#%h/projects/second-brain#$root#g" "$f" > "$dest/second-brain-reindex.service.d/$(basename "$f")"
  done
fi
echo "Next: systemctl --user daemon-reload, then enable the timers you want, for example: systemctl --user enable --now second-brain-reindex.timer"
