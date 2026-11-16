#!/bin/sh
# keepalive.sh - the process that the boot task keeps attached to the distribution.
#
# lib/start-distro.ps1 (the "Start" scheduled task, as slateops-svc) runs:
#   wsl.exe -d SlateOpsBootTest -u root --exec /usr/local/lib/slateops-boottest/keepalive.sh <base64 JSON>
# The argument holds Windows boot facts (last boot time, boot ID, boot type, attach number).
# This script stores them for the heartbeat container, then sleeps forever. While this process
# runs, wsl.exe stays attached, so WSL does not stop the distribution.
set -eu

dir=/var/lib/slateops-boottest/host
mkdir -p "$dir"
chmod 0755 "$dir"
if [ "${1:-}" != "" ]; then
    if printf '%s' "$1" | base64 -d > "$dir/windows.json.tmp" 2>/dev/null; then
        chmod 0644 "$dir/windows.json.tmp"
        mv -f "$dir/windows.json.tmp" "$dir/windows.json"
    else
        rm -f "$dir/windows.json.tmp"
        echo "keepalive: the Windows boot facts were not valid base64; kept the previous file." >&2
    fi
fi
echo "keepalive: attached at $(date -u +%Y-%m-%dT%H:%M:%SZ), Linux boot ID $(cat /proc/sys/kernel/random/boot_id)"
exec sleep infinity
