#!/bin/bash
# f5.sh - spike F5 in the throwaway distribution SlateOpsSpike (automount off). Run as root.
#   f5.sh <DRIVE:> <FOLDER>
# 1. Mounts the Windows drive letter with drvfs at /mnt/p1usb (automount is off, so this is the
#    only Windows drive that Linux sees). drvfs uses the rights of the Windows account that
#    runs the distribution (slateops-svc); the administrator side gave it access to FOLDER.
# 2. Makes a small test data set in Linux: 200 files of 1 MiB (random) and 2000 files of 4 KiB.
# 3. Times restic init, backup and check --read-data with the repository in FOLDER on the drive.
# 4. Deletes the repository and the data set, and unmounts the drive.
# The Restic password is a throwaway value made here; it is never printed.
# The last stdout line is one JSON document with the timings.
set -euo pipefail
DRIVE="${1:?drive letter, for example E:}"
FOLDER="${2:?folder name on the drive}"
MOUNT=/mnt/p1usb
WORK=/root/p1-f5
REPO="$MOUNT/$FOLDER/restic-repository"
export DEBIAN_FRONTEND=noninteractive

log() { printf '%s f5: %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"; }
now() { date +%s.%N; }
elapsed() { awk -v a="$1" -v b="$2" 'BEGIN { printf "%.1f", b - a }'; }

cleanup() {
    rm -rf "$WORK" "$WORK.mount-error"
    if mountpoint -q "$MOUNT"; then
        rm -rf "$REPO" 2>/dev/null || true
        umount "$MOUNT" || true
    fi
}
trap cleanup EXIT

[[ "$DRIVE" =~ ^[D-Z]:$ ]] || { log "bad drive letter"; exit 2; }
[[ "$FOLDER" =~ ^SlateOps-F5-[0-9a-f]{8}$ ]] || { log "bad folder name"; exit 2; }
if [ -e /mnt/c/Windows ]; then log "automount is on; this test needs it off"; exit 2; fi

if ! command -v restic >/dev/null 2>&1; then
    log "installing restic from the Debian repository"
    apt-get update >/dev/null && apt-get install -y --no-install-recommends restic ca-certificates >/dev/null
fi
log "restic: $(restic version | head -n 1)"

mkdir -p "$MOUNT"
t0="$(now)"
if ! mount -t drvfs "$DRIVE" "$MOUNT" 2> "$WORK.mount-error"; then
    log "drvfs mount of $DRIVE FAILED: $(tr '\n' ' ' < "$WORK.mount-error")"
    printf '{"mounted":false,"mount_error":"%s"}\n' "$(tr -d '"\\\n' < "$WORK.mount-error" | cut -c1-200)"
    exit 1
fi
log "drvfs mount of $DRIVE at $MOUNT: ok in $(elapsed "$t0" "$(now)") s; $(findmnt -no FSTYPE,OPTIONS "$MOUNT" | cut -c1-120)"
[ -d "$MOUNT/$FOLDER" ] || { log "folder $FOLDER is missing on $DRIVE"; exit 1; }
fs_type="$(findmnt -no FSTYPE "$MOUNT")"

mkdir -p "$WORK/data/big" "$WORK/data/small"
for i in $(seq 1 200); do head -c 1048576 /dev/urandom > "$WORK/data/big/f$i"; done
for i in $(seq 1 2000); do head -c 4096 /dev/urandom > "$WORK/data/small/f$i"; done
data_bytes="$(du -sb "$WORK/data" | cut -f1)"
head -c 32 /dev/urandom | od -An -tx1 | tr -d ' \n' > "$WORK/password"
chmod 0600 "$WORK/password"
export RESTIC_REPOSITORY="$REPO" RESTIC_PASSWORD_FILE="$WORK/password" RESTIC_CACHE_DIR="$WORK/cache"

t0="$(now)"; restic init >/dev/null; t1="$(now)"
restic backup --quiet "$WORK/data" >/dev/null; t2="$(now)"
restic check --read-data >/dev/null 2>&1; t3="$(now)"
repo_bytes="$(du -sb "$REPO" | cut -f1)"
log "data $((data_bytes / 1048576)) MiB: init $(elapsed "$t0" "$t1") s, backup $(elapsed "$t1" "$t2") s, check --read-data $(elapsed "$t2" "$t3") s"
printf '{"mounted":true,"fs_type":"%s","data_bytes":%s,"repository_bytes":%s,"init_seconds":%s,"backup_seconds":%s,"check_read_data_seconds":%s,"backup_mib_per_second":%s}\n' \
    "$fs_type" "$data_bytes" "$repo_bytes" "$(elapsed "$t0" "$t1")" "$(elapsed "$t1" "$t2")" "$(elapsed "$t2" "$t3")" \
    "$(awk -v b="$data_bytes" -v s="$(elapsed "$t1" "$t2")" 'BEGIN { if (s > 0) printf "%.1f", b / 1048576 / s; else print 0 }')"
