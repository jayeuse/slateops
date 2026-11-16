#!/bin/bash
# setup-docker.sh - installs Docker Engine and starts the boot-test stack (run as root,
# with systemd running). Usage: setup-docker.sh <bridge|host>
#
# 1. Installs curl and gnupg from Debian's own signed repository.
# 2. Downloads Docker's apt signing key and stops unless its primary key fingerprint is
#    9DC8 5822 9FC7 DD38 854A E2D8 8D81 803C 0EBF CD88 (from docs.docker.com and the key itself).
# 3. Adds Docker's apt repository with that key only (Signed-By), installs docker-ce,
#    docker-ce-cli, containerd.io and docker-compose-plugin, and enables Docker under systemd.
#    Docker's convenience script is not used (it warns against WSL and cannot be pinned).
# 4. Creates a random PostgreSQL password inside the distribution (never leaves it),
#    and starts the test stack with "docker compose up --wait".
# 5. Waits for the first heartbeat and prints the status JSON from inside the distribution.
# Safe to run again: every step checks what already exists.
set -euo pipefail

LIB=/usr/local/lib/slateops-boottest
PAYLOAD="$LIB/payload"
DATA=/var/lib/slateops-boottest
SECRETS=/etc/slateops-boottest
PROJECT=slateops-boottest
DOCKER_KEY_URL=https://download.docker.com/linux/debian/gpg
DOCKER_KEY_FINGERPRINT=9DC858229FC7DD38854AE2D88D81803C0EBFCD88
export DEBIAN_FRONTEND=noninteractive

log() { printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"; }

wait_for_systemd() {
    local state=""
    for _ in $(seq 1 90); do
        state="$(systemctl is-system-running 2>/dev/null || true)"
        case "$state" in
            running|degraded) log "systemd state: $state"; return 0 ;;
        esac
        sleep 2
    done
    log "systemd did not reach running or degraded (last state: ${state:-none})."
    return 1
}

install_prerequisites() {
    log "Installing ca-certificates, curl and gnupg from the Debian repository."
    apt-get update
    apt-get install -y --no-install-recommends ca-certificates curl gnupg
}

install_docker_key() {
    # Prints nothing on success; exits non-zero on a fingerprint mismatch.
    local tmp primary pubs
    tmp="$(mktemp -d)"
    mkdir -m 0700 "$tmp/gnupg"
    curl -fsSL "$DOCKER_KEY_URL" -o "$tmp/docker.asc"
    pubs="$(GNUPGHOME="$tmp/gnupg" gpg --batch --show-keys --with-colons "$tmp/docker.asc" | grep -c '^pub:' || true)"
    primary="$(GNUPGHOME="$tmp/gnupg" gpg --batch --show-keys --with-colons "$tmp/docker.asc" \
        | awk -F: '$1 == "fpr" { print $10; exit }')"
    if [ "$pubs" != "1" ] || [ "$primary" != "$DOCKER_KEY_FINGERPRINT" ]; then
        log "Docker key check FAILED: $pubs primary key(s), fingerprint '${primary}'. Expected $DOCKER_KEY_FINGERPRINT."
        rm -rf "$tmp"
        return 1
    fi
    install -m 0755 -d /etc/apt/keyrings
    install -m 0644 "$tmp/docker.asc" /etc/apt/keyrings/docker.asc
    rm -rf "$tmp"
    log "Docker key fingerprint verified: $primary"
}

install_docker_packages() {
    local codename arch
    codename="$(. /etc/os-release && echo "$VERSION_CODENAME")"
    arch="$(dpkg --print-architecture)"
    cat > /etc/apt/sources.list.d/docker.sources <<EOF
Types: deb
URIs: https://download.docker.com/linux/debian
Suites: ${codename}
Components: stable
Architectures: ${arch}
Signed-By: /etc/apt/keyrings/docker.asc
EOF
    apt-get update
    apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
    log "Installed: $(dpkg-query -W -f='${Package} ${Version}, ' docker-ce docker-ce-cli containerd.io docker-compose-plugin)"
}

enable_docker() {
    systemctl enable containerd.service docker.service
    systemctl start docker.service
    systemctl is-active --quiet docker.service
    docker version --format 'Docker Engine {{.Server.Version}} (API {{.Server.APIVersion}})'
    docker compose version
}

prepare_payload_files() {
    install -d -m 0711 "$SECRETS"
    if [ ! -s "$SECRETS/pg_password" ]; then
        ( umask 077; od -An -tx1 -N24 /dev/urandom | tr -d ' \n' > "$SECRETS/pg_password" )
        log "Created a random PostgreSQL password in $SECRETS/pg_password (the value is not shown)."
    fi
    # uid/gid 999 is the postgres user of the postgres image (db and heartbeat containers).
    chown 999:999 "$SECRETS/pg_password"
    chmod 0400 "$SECRETS/pg_password"
    install -d -m 0755 "$DATA" "$DATA/host"
    install -d -m 0755 -o 999 -g 999 "$DATA/status"
    chmod 0755 "$PAYLOAD/www" "$PAYLOAD/www/cgi-bin"
    chmod 0755 "$PAYLOAD/www/cgi-bin/index.cgi"
    chmod 0644 "$PAYLOAD/heartbeat.sh" "$PAYLOAD/compose.yaml"
}

start_stack() {
    local profile="$1" other
    if [ "$profile" = "bridge" ]; then other=web-host; else other=web; fi
    # Remove the web service of the other profile, so only one listener owns port 8443.
    docker compose --project-name "$PROJECT" --file "$PAYLOAD/compose.yaml" --profile bridge --profile host \
        rm --stop --force "$other" || true
    docker compose --project-name "$PROJECT" --file "$PAYLOAD/compose.yaml" --profile "$profile" \
        up --detach --wait --wait-timeout 300
    docker compose --project-name "$PROJECT" --file "$PAYLOAD/compose.yaml" --profile "$profile" ps
}

wait_for_status() {
    local body
    for _ in $(seq 1 60); do
        if body="$(curl -fsS --max-time 5 http://127.0.0.1:8443/ 2>/dev/null)" \
            && printf '%s' "$body" | grep -q '"fresh":true'; then
            log "Inside check passed: http://127.0.0.1:8443/"
            printf '%s\n' "$body"
            return 0
        fi
        sleep 5
    done
    log "Inside check FAILED: no fresh status at http://127.0.0.1:8443/ after 300 s."
    docker compose --project-name "$PROJECT" logs --tail 50 || true
    return 1
}

main() {
    local profile="${1:-bridge}"
    case "$profile" in bridge|host) ;; *) log "Usage: $0 <bridge|host>"; exit 2 ;; esac
    [ "$(id -u)" = "0" ] || { log "Run as root."; exit 2; }
    wait_for_systemd
    install_prerequisites
    install_docker_key
    install_docker_packages
    enable_docker
    prepare_payload_files
    start_stack "$profile"
    wait_for_status
    log "Disk of the distribution:"
    df -h /
}

if [ "${BASH_SOURCE[0]}" = "$0" ]; then
    main "$@"
fi
