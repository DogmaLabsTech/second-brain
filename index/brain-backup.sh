#!/usr/bin/env bash
# Pack the whole brain (~/brain: every section, the private notes, unsaved drafts, its git history, and business/
# with its own git) into one dated file on the HDD. Keeps the 14 newest copies. Run nightly by brain-backup.timer.
# Test overrides: BRAIN_DIR, BRAIN_BACKUP_MOUNT, BRAIN_BACKUP_DIR, BRAIN_BACKUP_KEEP.
set -euo pipefail
brain="$(realpath -- "${BRAIN_DIR:-$HOME/brain}")"
# The brain holds private notes: copies are for <user> only.
umask 077
mount="${BRAIN_BACKUP_MOUNT:-/mnt/backup}"
dest="${BRAIN_BACKUP_DIR:-~/backups/brain}"
keep="${BRAIN_BACKUP_KEEP:-14}"
# If the drive isn't mounted, stop: copying into the empty mount point would fill the main disk.
mountpoint -q "$mount" || { echo "brain-backup: $mount is not mounted; nothing copied" >&2; exit 1; }
[[ -d "$brain" ]] || { echo "brain-backup: the brain is not there ($brain); nothing copied" >&2; exit 1; }
mkdir -p "$dest"
file="$dest/brain-$(date +%F).tar.gz"
# Write to a temp name first, so a half-written copy never looks like a good one; a failed run leaves no temp file.
trap 'rm -f -- "$file.tmp"' EXIT
# tar exit 1 = a file changed while it was read (an agent wrote to the brain): the copy is still whole.
rc=0; tar -czf "$file.tmp" -C "$(dirname "$brain")" "$(basename "$brain")" || rc=$?
((rc <= 1)) || { echo "brain-backup: tar failed (exit $rc); nothing copied" >&2; exit 1; }
((rc == 0)) || echo "brain-backup: a file changed during the copy; kept the copy anyway" >&2
mv -f "$file.tmp" "$file"
trap - EXIT
date '+%F %T' > "$dest/last-copy.txt"
# Dated names sort oldest first; remove all but the newest $keep, only in this folder.
mapfile -t copies < <(find "$dest" -maxdepth 1 -type f -name 'brain-????-??-??.tar.gz' | sort)
for ((i = 0; i < ${#copies[@]} - keep; i++)); do rm -f -- "${copies[i]}"; done
echo "brain-backup: copied $brain to $file"
