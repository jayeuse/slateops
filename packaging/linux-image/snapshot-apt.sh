#!/usr/bin/env bash
# snapshot-apt.sh <package>... - installs packages in the build or boot-check container from
# snapshot.debian.org at $SNAPSHOT (pins.env), as root (review finding S83-1).
#
# The slim build image has no CA bundle, so the first fetch cannot use HTTPS:
# 1. Over HTTP, install only ca-certificates at its exact snapshot version. apt checks the
#    signed index and the package hash; a replayed older index does not hold this version,
#    so the step fails instead of installing another bundle.
# 2. Switch the sources to HTTPS and install the requested packages.
# The snapshot's Release files are older than their Valid-Until date, so that check is off;
# the signature check stays on. This setting is in the container only, never in the image.
set -euo pipefail

# /build is this folder, mounted read-only by build.sh and boot-check.sh.
# shellcheck source=pins.env
. /build/pins.env
export DEBIAN_FRONTEND=noninteractive

log() { printf '%s apt %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"; }

write_sources() {
    cat > /etc/apt/sources.list.d/snapshot.sources <<SOURCES
Types: deb
URIs: $1://snapshot.debian.org/archive/debian/$SNAPSHOT
Suites: trixie trixie-updates
Components: main
Signed-By: /usr/share/keyrings/debian-archive-keyring.pgp

Types: deb
URIs: $1://snapshot.debian.org/archive/debian-security/$SNAPSHOT
Suites: trixie-security
Components: main
Signed-By: /usr/share/keyrings/debian-archive-keyring.pgp
SOURCES
}

rm -f /etc/apt/sources.list.d/debian.sources
printf 'Acquire::Check-Valid-Until "false";\nAcquire::Retries "5";\n' > /etc/apt/apt.conf.d/90snapshot

write_sources http
log "fetch: ca-certificates $CA_CERTIFICATES_VERSION from http://snapshot.debian.org/archive/debian/$SNAPSHOT"
apt-get update -qq
apt-get install -y -qq --no-install-recommends "ca-certificates=$CA_CERTIFICATES_VERSION" >/dev/null

write_sources https
log "fetch: $* from https://snapshot.debian.org/archive/debian/$SNAPSHOT"
apt-get update -qq
apt-get install -y -qq --no-install-recommends "$@" >/dev/null
log "installed: $(dpkg-query -W -f '${Package} ${Version}, ' ca-certificates "$@")"
