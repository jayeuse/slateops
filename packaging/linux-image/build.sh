#!/usr/bin/env bash
# build.sh - builds the Slate Operations Linux image: our Debian 13 root file system for
# WSL (docs/plans/windows-installer.md 3.1 and 5.2, slice W4).
#
# Usage: packaging/linux-image/build.sh --arch amd64|arm64 --version <version> \
#            --engine-bundle <slateops-engine-<version>.tar.gz> --output <dir>
#
# Writes <dir>/slateops-linux-<version>-<arch>.tar.gz. The release workflow builds amd64.
# arm64 exists only for a local test on an arm64 host: the architecture must be the
# Docker host's, because the script does not emulate another one.
#
# The build runs in a privileged Debian container pinned by digest (pins.env), because
# mmdebstrap mounts /proc and /dev in the root file system it builds. build-rootfs.sh
# does the work; this script only starts it. The container gets the folder of this
# script read-only and writes only the finished tarball to <dir>.
#
# The engine bundle of the same release (W5b, scripts/release_engine_bundle.py) is
# mounted read-only into the build container; hooks.sh unpacks it to
# /opt/slateops/engine/<version>/, links /usr/local/bin/slateops-engine to its launcher,
# and records the bundle's SHA-256 in /usr/share/slateops/linux-image.json. The bundle
# holds no release manifest; the engine's prepare compares this SHA-256 with the signed
# manifest that receive keeps.
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
arch=""
version=""
output=""
engine_bundle=""

usage() {
    echo "Usage: $0 --arch amd64|arm64 --version <version> --engine-bundle <file> --output <dir>" >&2
    exit 2
}

while [ "$#" -gt 0 ]; do
    case "$1" in
        --arch) arch="${2:-}"; shift 2 ;;
        --version) version="${2:-}"; shift 2 ;;
        --output) output="${2:-}"; shift 2 ;;
        --engine-bundle) engine_bundle="${2:-}"; shift 2 ;;
        *) usage ;;
    esac
done
case "$arch" in amd64|arm64) ;; *) usage ;; esac
[[ "$version" =~ ^[0-9]+\.[0-9]+\.[0-9]+(-rc\.[0-9]+|-dev)?$ ]] || usage
[ -n "$output" ] || usage
[ -f "$engine_bundle" ] || usage
if [ "$(basename "$engine_bundle")" != "slateops-engine-$version.tar.gz" ]; then
    echo "build.sh: the engine bundle must be slateops-engine-$version.tar.gz" >&2
    exit 2
fi
engine_bundle="$(cd "$(dirname "$engine_bundle")" && pwd)/$(basename "$engine_bundle")"

case "$(docker info --format '{{.Architecture}}')" in
    x86_64|amd64) host_arch=amd64 ;;
    aarch64|arm64) host_arch=arm64 ;;
    *) host_arch=unknown ;;
esac
if [ "$arch" != "$host_arch" ]; then
    echo "build.sh: the Docker host is $host_arch; this script builds only for the host's architecture." >&2
    exit 2
fi

# shellcheck source=pins.env
. "$here/pins.env"
mkdir -p "$output"
output="$(cd "$output" && pwd)"
echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) build: image $BUILD_IMAGE, arch $arch, version $version"
echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) build: engine bundle $(basename "$engine_bundle")"

docker run --rm --privileged --platform "linux/$arch" \
    --volume "$here:/build:ro" \
    --volume "$output:/out" \
    --volume "$engine_bundle:/engine/slateops-engine-$version.tar.gz:ro" \
    --env "ARCH=$arch" \
    --env "VERSION=$version" \
    --env "ENGINE_BUNDLE=/engine/slateops-engine-$version.tar.gz" \
    "$BUILD_IMAGE" \
    bash /build/build-rootfs.sh
