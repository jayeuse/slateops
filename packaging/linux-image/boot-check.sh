#!/usr/bin/env bash
# boot-check.sh - boots a throwaway copy of the Linux image with systemd-nspawn and checks
# that systemd starts, that containerd, Docker and chrony run, that Docker uses the
# containerd image store, and that nothing listens on a TCP or UDP port
# (docs/plans/windows-installer.md W4-5, W4-6, AC-W4-8).
#
# Usage: packaging/linux-image/boot-check.sh --arch amd64|arm64 --tarball <file>
#
# The tarball is mounted read-only and never changes: the copy lives in a tmpfs of a
# privileged, digest-pinned Debian container (pins.env) and is gone after the run.
# The copy gets two test-only additions: the guest check service, and a chrony drop-in
# that runs chronyd with -x. -x keeps chronyd from setting the clock, so the container
# needs no clock right and cannot change the host's time; chronyd still opens every
# socket that it opens in WSL, so the listening check is real. --register=no and
# --keep-unit let nspawn run in a container that has no systemd and no D-Bus.
#
# What this cannot prove: WSL's own init, the WSL kernel, mirrored networking, the
# Windows side and a real time sync. The engine's `prepare` self-check proves those on
# Windows (plan 10.3, W5b and W14).
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
arch=""
tarball=""
while [ "$#" -gt 0 ]; do
    case "$1" in
        --arch) arch="${2:-}"; shift 2 ;;
        --tarball) tarball="${2:-}"; shift 2 ;;
        *) echo "Usage: $0 --arch amd64|arm64 --tarball <file>" >&2; exit 2 ;;
    esac
done
case "$arch" in amd64|arm64) ;; *) echo "boot-check.sh: --arch amd64|arm64" >&2; exit 2 ;; esac
[ -f "$tarball" ] || { echo "boot-check.sh: no tarball $tarball" >&2; exit 2; }
tarball="$(cd "$(dirname "$tarball")" && pwd)/$(basename "$tarball")"

# shellcheck source=pins.env
. "$here/pins.env"
docker run --rm --privileged --platform "linux/$arch" \
    --tmpfs /check:rw,exec,dev,suid,size=3g --tmpfs /run:rw,exec \
    --volume "$here:/build:ro" \
    --volume "$tarball:/image.tar.gz:ro" \
    "$BUILD_IMAGE" \
    bash -euo pipefail -c '
log() { printf "%s boot-check %s\n" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"; }
. /build/pins.env
bash /build/snapshot-apt.sh systemd-container
log "systemd-nspawn $(dpkg-query -W -f "\${Version}" systemd-container)"

root=/check/root
mkdir "$root"
# A tmpfs holds no POSIX ACLs; systemd sets the journal ACLs again at boot.
tar --numeric-owner --xattrs --xattrs-include="*" --xattrs-exclude="system.posix_acl_*" -xzpf /image.tar.gz -C "$root"
install -D -m 0755 /build/boot-check-guest.sh "$root/usr/local/sbin/slateops-boot-check"
cat > "$root/etc/systemd/system/slateops-boot-check.service" <<EOF
[Unit]
Description=Slate Operations image boot check (test only)
After=containerd.service docker.service chrony.service
[Service]
Type=simple
ExecStart=/usr/local/sbin/slateops-boot-check
[Install]
WantedBy=multi-user.target
EOF
ln -s /etc/systemd/system/slateops-boot-check.service \
    "$root/etc/systemd/system/multi-user.target.wants/slateops-boot-check.service"
mkdir -p "$root/etc/systemd/system/chrony.service.d"
cat > "$root/etc/systemd/system/chrony.service.d/boot-check.conf" <<EOF
[Unit]
ConditionCapability=
[Service]
ExecStart=
ExecStart=!/usr/sbin/chronyd -x \$DAEMON_OPTS
EOF

log "booting the copy with systemd-nspawn (private network, no registration)"
status=0
timeout 420 systemd-nspawn --quiet --boot --directory="$root" --machine=slateops-check \
    --register=no --keep-unit --private-network --resolv-conf=off --timezone=off --link-journal=no \
    --console=pipe > /check/console.log 2>&1 || status=$?
log "systemd-nspawn exit $status"

result="$root/var/tmp/slateops-boot-check/result.txt"
if [ ! -f "$result" ]; then
    log "FAILED: the guest wrote no result; console tail:"
    tail -n 80 /check/console.log
    exit 1
fi
cat "$result"
value() { sed -n "s/^$1=//p" "$result"; }
problems=()
case "$(value system_state)" in
    running) ;;
    *) problems+=("W4-5: systemd state is $(value system_state), failed units: $(value failed_units)") ;;
esac
for unit in containerd docker chrony; do
    [ "$(value "active_$unit")" = active ] || problems+=("W4-5: $unit is $(value "active_$unit")")
done
case "$(value docker_store)" in
    *io.containerd.snapshotter.v1*) ;;
    *) problems+=("AC-W4-8: Docker does not use the containerd image store: $(value docker_store)") ;;
esac
case "$(value engine_status)" in
    *\"code\":\"ok\"*) ;;
    *) problems+=("W5b: slateops-engine status did not answer ok: $(value engine_status)") ;;
esac
[ -z "$(value listen_tcp)" ] || problems+=("W4-6: TCP listeners: $(value listen_tcp)")
[ -z "$(value listen_udp)" ] || problems+=("W4-6: UDP listeners: $(value listen_udp)")
if [ "${#problems[@]}" -gt 0 ]; then
    for problem in "${problems[@]}"; do log "FAILED: $problem"; done
    log "console tail:"
    tail -n 80 /check/console.log
    exit 1
fi
log "passed: systemd running; containerd, Docker and chrony active; containerd image store; engine status ok; no listener"
'
