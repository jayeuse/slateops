#!/usr/bin/env bash
# build-rootfs.sh - runs inside the build container that build.sh starts (as root).
#
# 1. Points the container's apt at snapshot.debian.org ($SNAPSHOT) and installs mmdebstrap,
#    gpg, curl and ca-certificates from it.
# 2. Checks the three Debian 13 archive keys by fingerprint (W4-1) and Docker's apt key by
#    fingerprint (W4-2). Only these keys can sign what the image installs.
# 3. Runs mmdebstrap (variant "important", the base of the Debian WSL image that REQ-0022
#    ran) with the exact Docker versions; hooks.sh adds our files, cosign and the cleanup.
# 4. Writes /out/slateops-linux-<version>-<arch>.tar.gz with gzip -n.
# Every pin and every download is logged (plan section 10).
set -euo pipefail

# /build is this folder, mounted read-only by build.sh.
# shellcheck source=pins.env
. /build/pins.env
: "${ARCH:?}" "${VERSION:?}"
export DEBIAN_FRONTEND=noninteractive
SOURCE_DATE_EPOCH="$(date -u -d "${SNAPSHOT:0:4}-${SNAPSHOT:4:2}-${SNAPSHOT:6:2}T${SNAPSHOT:9:2}:${SNAPSHOT:11:2}:${SNAPSHOT:13:2}Z" +%s)"
export SOURCE_DATE_EPOCH
name="slateops-linux-$VERSION-$ARCH.tar.gz"
work=/var/tmp/slateops-linux
keys="$work/keys"

log() { printf '%s build %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"; }
fail() { log "FAILED: $*"; exit 1; }

log "pins: snapshot $SNAPSHOT (SOURCE_DATE_EPOCH $SOURCE_DATE_EPOCH), arch $ARCH, version $VERSION"
log "pins: docker-ce $DOCKER_CE_VERSION, docker-ce-cli $DOCKER_CE_CLI_VERSION, containerd.io $CONTAINERD_IO_VERSION, docker-compose-plugin $DOCKER_COMPOSE_PLUGIN_VERSION, cosign $COSIGN_VERSION"
mkdir -p "$keys"

# 1. Build tools from the same snapshot. The snapshot's Release files are older than their
# Valid-Until date; the signature check stays on. This setting is in the build container
# only and never in the image (scripts/release_linux_image.py check refuses it).
rm -f /etc/apt/sources.list.d/debian.sources
cat > /etc/apt/sources.list.d/snapshot.sources <<EOF
Types: deb
URIs: http://snapshot.debian.org/archive/debian/$SNAPSHOT
Suites: trixie trixie-updates
Components: main
Signed-By: /usr/share/keyrings/debian-archive-keyring.pgp

Types: deb
URIs: http://snapshot.debian.org/archive/debian-security/$SNAPSHOT
Suites: trixie-security
Components: main
Signed-By: /usr/share/keyrings/debian-archive-keyring.pgp
EOF
printf 'Acquire::Check-Valid-Until "false";\nAcquire::Retries "5";\n' > /etc/apt/apt.conf.d/90snapshot
log "fetch: build tools from http://snapshot.debian.org/archive/debian/$SNAPSHOT"
apt-get update -qq
apt-get install -y -qq --no-install-recommends mmdebstrap gpg ca-certificates curl >/dev/null
log "build tools: $(dpkg-query -W -f '${Package} ${Version}, ' mmdebstrap gpg curl)"

fingerprints() {
    gpg --batch --show-keys --with-colons "$1" \
        | awk -F: '$1 == "pub" { primary = 1; next } $1 == "fpr" && primary { print $10; primary = 0 }'
}

# 2. The Debian 13 keys, one file each, checked by fingerprint, joined into one keyring.
check_debian_key() {
    local file="/usr/share/keyrings/$1" expected="$2" found
    found="$(fingerprints "$file")"
    [ "$found" = "$expected" ] || fail "$file has key(s) '$found', expected $expected"
    log "key checked: $1 = $expected"
    cat "$file" >> "$keys/debian.pgp"
}
check_debian_key debian-archive-trixie-automatic.pgp "$DEBIAN_KEY_ARCHIVE"
check_debian_key debian-archive-trixie-security-automatic.pgp "$DEBIAN_KEY_SECURITY"
check_debian_key debian-archive-trixie-stable.pgp "$DEBIAN_KEY_RELEASE"

log "fetch: $DOCKER_KEY_URL"
curl --fail --silent --show-error --location --retry 5 --output "$keys/docker.asc" "$DOCKER_KEY_URL"
found="$(fingerprints "$keys/docker.asc")"
[ "$found" = "$DOCKER_KEY_FINGERPRINT" ] \
    || fail "Docker's key has primary key(s) '$found', expected only $DOCKER_KEY_FINGERPRINT"
log "key checked: Docker apt key = $DOCKER_KEY_FINGERPRINT"

# 3. The root file system. "important" is Debian's standard base (systemd, apt, iproute2,
# logrotate, ...); the list names every package that the image needs, so a change of
# priorities in Debian cannot drop one.
packages=(
    systemd systemd-sysv dbus libpam-systemd ca-certificates iproute2 kmod procps
    logrotate nftables iptables apparmor pigz xz-utils curl python3 restic chrony
    "docker-ce=$DOCKER_CE_VERSION" "docker-ce-cli=$DOCKER_CE_CLI_VERSION"
    "containerd.io=$CONTAINERD_IO_VERSION" "docker-compose-plugin=$DOCKER_COMPOSE_PLUGIN_VERSION"
)
include="$(IFS=,; echo "${packages[*]}")"
debian="http://snapshot.debian.org/archive/debian/$SNAPSHOT"
security="http://snapshot.debian.org/archive/debian-security/$SNAPSHOT"
log "fetch: Debian packages from $debian and $security; Docker packages from $DOCKER_REPOSITORY"
# The hooks get the root folder as "$1" from mmdebstrap, so the quotes stay single.
# shellcheck disable=SC2016
mmdebstrap \
    --mode=root --variant=important --arch="$ARCH" --format=tar \
    --aptopt='Acquire::Check-Valid-Until "false"' --aptopt='Acquire::Retries "5"' \
    --include="$include" \
    --setup-hook='bash /build/hooks.sh setup "$1"' \
    --customize-hook='bash /build/hooks.sh customize "$1"' \
    trixie "$work/rootfs.tar" \
    "deb [signed-by=$keys/debian.pgp] $debian trixie main" \
    "deb [signed-by=$keys/debian.pgp] $debian trixie-updates main" \
    "deb [signed-by=$keys/debian.pgp] $security trixie-security main" \
    "deb [signed-by=$keys/docker.asc] $DOCKER_REPOSITORY trixie stable"

# 4. gzip -n stores no name and no time, so the same tar gives the same .tar.gz.
gzip -n -6 -c "$work/rootfs.tar" > "/out/$name"
log "wrote $name: $(stat -c %s "/out/$name") bytes, sha256 $(sha256sum "/out/$name" | cut -d' ' -f1)"
