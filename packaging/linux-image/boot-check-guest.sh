#!/bin/bash
# boot-check-guest.sh - runs inside the booted throwaway copy of the image (W4-5, W4-6).
# boot-check.sh installs it as a service, reads the result file, and decides.
#
# It waits until systemd finishes the start, then records the system state, the failed
# units, the state of containerd, Docker and chrony, Docker's image store, and every
# listening TCP and UDP socket. Then it powers the container off.
set -u
result=/var/tmp/slateops-boot-check/result.txt
mkdir -p "$(dirname "$result")"

{
    echo "system_state=$(timeout 240 systemctl is-system-running --wait 2>&1)"
    echo "failed_units=$(systemctl list-units --failed --plain --no-legend 2>&1 | awk '{print $1}' | paste -sd, -)"
    for unit in containerd docker chrony; do
        echo "active_$unit=$(systemctl is-active "$unit" 2>&1)"
    done
    for _ in $(seq 1 30); do
        docker info >/dev/null 2>&1 && break
        sleep 2
    done
    echo "docker_store=$(docker info --format '{{.Driver}} {{json .DriverStatus}}' 2>&1)"
    # W5b: the engine of the image runs with the image's Python (status changes nothing
    # but report.json in this throwaway copy).
    echo "engine_status=$(printf '%s' '{"run_id":"boot-20260101T000000Z-check1","windows_part_version":"0.0.1","wsl_version":"2.6.1.0"}' \
        | slateops-engine status 2>&1 | head -c 400)"
    echo "listen_tcp=$(ss -H -ltn 2>&1 | paste -sd'|' -)"
    echo "listen_udp=$(ss -H -lun 2>&1 | paste -sd'|' -)"
    echo "done=yes"
} > "$result.tmp" 2>&1
mv "$result.tmp" "$result"
systemctl poweroff
