#!/usr/bin/env bash
# hooks.sh - mmdebstrap hooks of build-rootfs.sh. Usage: hooks.sh setup|customize <root>
#
# setup:     before apt resolves anything: the apt preferences that allow only the four
#            Docker Engine packages from Docker's repository (plan 7.4).
# customize: after all packages are installed: our files (rootfs/), cosign, the final
#            apt sources, the enabled units, the engine bundle ($ENGINE_BUNDLE, W5b),
#            the empty folders that later slices fill, the image record, and the
#            cleanup (no machine ID, no build-host files, no apt lists or logs).
#            scripts/release_linux_image.py check verifies the result.
set -euo pipefail

# /build is this folder, mounted read-only by build.sh.
# shellcheck source=pins.env
. /build/pins.env
stage="$1"
root="$2"
keys=/var/tmp/slateops-linux/keys

log() { printf '%s build %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"; }
fail() { log "FAILED: $*"; exit 1; }

install_file() {
    install -D -o 0 -g 0 -m "$3" "$1" "$root/$2"
}

setup() {
    install_file /build/rootfs/etc/apt/preferences.d/slateops-docker \
        etc/apt/preferences.d/slateops-docker 0644
}

install_cosign() {
    local sha url tmp
    case "$ARCH" in
        amd64) sha="$COSIGN_SHA256_AMD64" ;;
        arm64) sha="$COSIGN_SHA256_ARM64" ;;
        *) fail "no cosign pin for $ARCH" ;;
    esac
    tmp="$(mktemp -d)"
    url="https://github.com/sigstore/cosign/releases/download/v$COSIGN_VERSION/cosign-linux-$ARCH"
    log "fetch: $url"
    curl --fail --silent --show-error --location --retry 5 --output "$tmp/cosign" "$url"
    echo "$sha  $tmp/cosign" | sha256sum --check --strict --status - \
        || fail "cosign-linux-$ARCH v$COSIGN_VERSION does not match its pinned SHA-256"
    url="https://raw.githubusercontent.com/sigstore/cosign/v$COSIGN_VERSION/LICENSE"
    log "fetch: $url"
    curl --fail --silent --show-error --location --retry 5 --output "$tmp/LICENSE" "$url"
    echo "$COSIGN_LICENSE_SHA256  $tmp/LICENSE" | sha256sum --check --strict --status - \
        || fail "the cosign v$COSIGN_VERSION LICENSE does not match its pinned SHA-256"
    install_file "$tmp/cosign" usr/local/bin/cosign 0755
    install_file "$tmp/LICENSE" usr/share/doc/cosign/LICENSE 0644
    rm -rf "$tmp"
    log "installed: cosign $COSIGN_VERSION (sha256 $sha)"
}

install_engine() {
    # W5b: the bundle of this release, unpacked under its version; the link is the command.
    local target="$root/opt/slateops/engine/$VERSION"
    [ -f "$ENGINE_BUNDLE" ] || fail "no engine bundle at $ENGINE_BUNDLE"
    ENGINE_SHA256="$(sha256sum "$ENGINE_BUNDLE" | cut -d' ' -f1)"
    install -d -o 0 -g 0 -m 0755 "$root/opt/slateops/engine" "$target"
    tar -xzf "$ENGINE_BUNDLE" -C "$target" --no-same-owner
    [ -f "$target/slateops-engine" ] || fail "the engine bundle has no launcher"
    [ "$(cat "$target/engine/VERSION")" = "$VERSION" ] \
        || fail "the engine bundle is not version $VERSION"
    ln -s "/opt/slateops/engine/$VERSION/slateops-engine" "$root/usr/local/bin/slateops-engine"
    log "installed: engine bundle $(basename "$ENGINE_BUNDLE") (sha256 $ENGINE_SHA256)"
}

write_record() {
    # A safe record of what the image is, for status and Save report (plan 10.4).
    install -d -o 0 -g 0 -m 0755 "$root/usr/share/slateops"
    cat > "$root/usr/share/slateops/linux-image.json" <<EOF
{
  "version": "$VERSION",
  "architecture": "$ARCH",
  "debian_snapshot": "$SNAPSHOT",
  "build_image": "$BUILD_IMAGE",
  "docker_packages": {
    "docker-ce": "$DOCKER_CE_VERSION",
    "docker-ce-cli": "$DOCKER_CE_CLI_VERSION",
    "containerd.io": "$CONTAINERD_IO_VERSION",
    "docker-compose-plugin": "$DOCKER_COMPOSE_PLUGIN_VERSION"
  },
  "cosign": "$COSIGN_VERSION",
  "engine_bundle": {
    "archive": "$(basename "$ENGINE_BUNDLE")",
    "sha256": "$ENGINE_SHA256"
  }
}
EOF
    chmod 0644 "$root/usr/share/slateops/linux-image.json"
}

customize() {
    local file
    # Our files. They replace the package defaults of chrony.conf.
    while IFS= read -r file; do
        install_file "/build/rootfs/$file" "$file" 0644
    done < <(cd /build/rootfs && find . -type f -printf '%P\n' | LC_ALL=C sort)
    install_file "$keys/docker.asc" etc/apt/keyrings/docker.asc 0644
    install_cosign

    # The image's apt sources are deb.debian.org and Docker's repository (debian.sources
    # and docker.sources from rootfs/); the build's snapshot list and apt options go.
    rm -f "$root/etc/apt/sources.list" "$root/etc/apt/apt.conf.d/99mmdebstrap"

    chroot "$root" systemctl enable containerd.service docker.service chrony.service \
        slateops-interop-off.service
    log "enabled: containerd.service docker.service chrony.service slateops-interop-off.service"

    # The engine (W5b), and the folders that later slices fill: secrets, state and logs.
    install_engine
    install -d -o 0 -g 0 -m 0700 "$root/etc/slateops" "$root/var/lib/slateops" "$root/var/log/slateops"
    write_record

    # No identity and no build-host state: WSL and systemd make these at the first start.
    : > "$root/etc/machine-id"
    if [ -e "$root/var/lib/dbus/machine-id" ] && [ ! -L "$root/var/lib/dbus/machine-id" ]; then
        rm -f "$root/var/lib/dbus/machine-id"
    fi
    rm -f "$root/etc/hostname" "$root/etc/resolv.conf" \
        "$root/var/lib/systemd/random-seed" "$root/var/lib/systemd/credential.secret"
    rm -rf "$root/var/lib/apt/lists/"* "$root/var/cache/apt/"*.bin "$root/var/cache/apt/archives/"*.deb \
        "$root/var/log/apt/"* "$root/root/.bash_history"
    rm -f "$root/var/log/dpkg.log" "$root/var/log/alternatives.log" "$root/var/log/bootstrap.log"
    log "customized the root file system"
}

case "$stage" in
    setup) setup ;;
    customize) customize ;;
    *) fail "unknown stage $stage" ;;
esac
