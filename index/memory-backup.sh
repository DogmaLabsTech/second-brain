#!/usr/bin/env bash
# Pack the whole agent memory store (notes, unsaved drafts, its git history) into one dated file on the HDD.
# Keeps the 14 newest copies. Run nightly by agent-memory-backup.timer.
# Test overrides: MEMORY_STORE, MEMORY_BACKUP_MOUNT, MEMORY_BACKUP_DIR, MEMORY_BACKUP_KEEP.
set -euo pipefail
store="${MEMORY_STORE:-$HOME/projects/shared}"
mount="${MEMORY_BACKUP_MOUNT:-/mnt/backup}"
dest="${MEMORY_BACKUP_DIR:-~/backups/agent-memory}"
keep="${MEMORY_BACKUP_KEEP:-14}"
# If the drive isn't mounted, stop: copying into the empty mount point would fill the main disk.
mountpoint -q "$mount" || { echo "memory-backup: $mount is not mounted; nothing copied" >&2; exit 1; }
[[ -d "$store" ]] || { echo "memory-backup: the memory store is not there ($store); nothing copied" >&2; exit 1; }
mkdir -p "$dest"
file="$dest/agent-memory-$(date +%F).tar.gz"
# Write to a temp name first, so a half-written copy never looks like a good one.
tar -czf "$file.tmp" -C "$(dirname "$store")" "$(basename "$store")"
mv -f "$file.tmp" "$file"
date '+%F %T' > "$dest/last-copy.txt"
# Dated names sort oldest first; remove all but the newest $keep, only in this folder.
mapfile -t copies < <(find "$dest" -maxdepth 1 -type f -name 'agent-memory-????-??-??.tar.gz' | sort)
for ((i = 0; i < ${#copies[@]} - keep; i++)); do rm -f -- "${copies[i]}"; done
echo "memory-backup: copied $store to $file"
