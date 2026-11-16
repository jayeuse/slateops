#!/usr/bin/env bash
# build.sh - builds the Slate Operations Linux image: our Debian 13 root file system for
# WSL (docs/plans/windows-installer.md 3.1 and 5.2, slice W4).
#
# Usage: packaging/linux-image/build.sh --arch amd64|arm64 --version <version> --output <dir>
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
# The engine (W5b) is not part of the image yet. The image holds an empty
# /opt/slateops/engine/. W5b adds an option here that copies the engine bundle into
# hooks.sh, which unpacks it to /opt/slateops/engine/<version>/ and links
# /usr/local/bin/slateops-engine to it.
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
arch=""
version=""
output=""

usage() {
    echo "Usage: $0 --arch amd64|arm64 --version <version> --output <dir>" >&2
    exit 2
}

while [ "$#" -gt 0 ]; do
    case "$1" in
        --arch) arch="${2:-}"; shift 2 ;;
        --version) version="${2:-}"; shift 2 ;;
        --output) output="${2:-}"; shift 2 ;;
        *) usage ;;
    esac
done
case "$arch" in amd64|arm64) ;; *) usage ;; esac
[[ "$version" =~ ^[0-9]+\.[0-9]+\.[0-9]+(-rc\.[0-9]+|-dev)?$ ]] || usage
[ -n "$output" ] || usage

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

docker run --rm --privileged --platform "linux/$arch" \
    --volume "$here:/build:ro" \
    --volume "$output:/out" \
    --env "ARCH=$arch" \
    --env "VERSION=$version" \
    "$BUILD_IMAGE" \
    bash /build/build-rootfs.sh
