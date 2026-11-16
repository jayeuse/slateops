#!/bin/bash
# s1.sh - P1 measurement stack (plan slice S1) inside the boot-test distribution. Run as root.
#
# It installs and measures the real Slate Operations production stack, built from the
# repository source in the downloaded ZIP, with throwaway secrets that never leave Linux.
#
#   s1.sh install --host NAME --source TAR [--port 443] [--bind 0.0.0.0] [--gateway-port 58000]
#                 [--app-subnet CIDR]   (only when the product default 172.31.248.0/28 collides)
#   s1.sh stop-test-stack     stop the 8443 boot-test stack (it uses memory during measurements)
#   s1.sh measure-idle LABEL  idle memory (file cache dropped first), docker stats, sizes
#   s1.sh backup              one timed offline backup (RESTORE.md) and the ordered restart
#   s1.sh restore-timing      restic restore of the newest snapshot into a scratch folder
#   s1.sh port80 start|stop   a standalone test page on TCP 80 (F2; the product has no :80 yet)
#   s1.sh avahi start NAME|stop   F1 second-name check with Avahi (optional)
#   s1.sh report              one safe JSON document with every measurement (and the
#                             published ports of the running containers)
#   s1.sh abort               stop a running build or pull and remove the build cache
#   s1.sh remove              remove everything that S1 added to this distribution
#   s1.sh sample | ready-watch    the two boot-time services (systemd units run them)
#
# Output rules (the Windows side copies stdout to its logs): stdout holds step names,
# durations, sizes and exit codes only. Build, Compose, provisioning and backup output goes
# to ROOT/private/log (root only). After a failure, the tail of that log is printed with every
# generated secret value replaced by [REDACTED]. Every run ends with a scan of its own stdout
# transcript for the generated values.
set -euo pipefail
umask 022

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="${S1_ROOT:-/var/lib/slateops-s1}"
PRIV="$ROOT/private"
STATE="$ROOT/state"
MEASURE="$ROOT/measure"
SRC="$ROOT/src"
PROJECT=slateops-s1
SERVER_IMAGE=slateops-s1-server:p1
CADDY_IMAGE=slateops-s1-caddy:p1
PORT80_IMAGE=busybox:1.37.0-musl@sha256:f6a95d611e0a8780fabdb2aec43e31275b2720dfefa3e41b16835bfc42454478
PROVIDERS="db auth storage imgproxy realtime meta studio api-gw"
export DEBIAN_FRONTEND=noninteractive
TRANSCRIPT="$STATE/transcript.log"
CURRENT_LOG=""

now() { date -u +%s; }
stamp() { date -u +%Y-%m-%dT%H:%M:%SZ; }

say() {
    local line
    line="$(stamp) s1: $*"
    printf '%s\n' "$line"
    if [ -d "$STATE" ]; then printf '%s\n' "$line" >> "$TRANSCRIPT"; fi
}

die() {
    say "FAILED: $*"
    if [ -n "$CURRENT_LOG" ] && [ -f "$CURRENT_LOG" ]; then
        say "last lines of $CURRENT_LOG (secret values redacted):"
        python3 "$HERE/s1_env.py" redact "$ROOT" "$CURRENT_LOG" | tail -n 40 | sed 's/^/    | /' | tee -a "$TRANSCRIPT"
    fi
    scan_transcript || true
    exit 1
}

# Runs a command with its output in a root-only log. Usage: logged STEP command...
logged() {
    local step="$1"; shift
    CURRENT_LOG="$PRIV/log/$step.log"
    printf '==== %s %s\n' "$(stamp)" "$*" >> "$CURRENT_LOG"
    local code=0
    "$@" >> "$CURRENT_LOG" 2>&1 || code=$?
    [ "$code" -eq 0 ] || die "step $step (exit code $code)"
    CURRENT_LOG=""
}

timing() { printf '%s %s\n' "$1" "$2" >> "$STATE/install-timings.txt"; }

compose() {
    docker compose --project-name "$PROJECT" --env-file "$PRIV/provider.env" \
        -f "$SRC/infra/supabase/compose.yaml" -f "$SRC/infra/supabase/compose.production.yaml" "$@"
}

load_params() {
    [ -f "$STATE/params.env" ] || die "S1 is not installed (no $STATE/params.env). Run install first."
    # shellcheck disable=SC1091
    . "$STATE/params.env"
}

scan_transcript() {
    if [ -f "$PRIV/keys.env" ] && [ -f "$TRANSCRIPT" ]; then
        python3 "$HERE/s1_env.py" scan "$ROOT" "$TRANSCRIPT"
    fi
}

https_code() {
    curl -sk -o /dev/null -w '%{http_code}' --max-time 5 \
        --resolve "$S1_HOST:$S1_PORT:${S1_PROBE_ADDR:-127.0.0.1}" "https://$S1_HOST:$S1_PORT/api/ready" 2>/dev/null || true
}

api_ready_inside() {
    local id
    id="$(compose ps -q api 2>/dev/null || true)"
    [ -n "$id" ] || return 1
    docker exec "$id" python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/ready', timeout=3).status == 200 else 1)" >/dev/null 2>&1
}

wait_for() {
    # wait_for SECONDS DESCRIPTION command...
    local limit="$1" what="$2"; shift 2
    local start; start="$(now)"
    while [ $(( $(now) - start )) -lt "$limit" ]; do
        if "$@"; then return 0; fi
        sleep 2
    done
    die "$what not reached in $limit s"
}

https_ready() { [ "$(https_code)" = "200" ]; }

# ---------------------------------------------------------------------------
# install
# ---------------------------------------------------------------------------

install_prerequisites() {
    local missing=""
    for tool in python3 restic curl; do command -v "$tool" >/dev/null 2>&1 || missing="$missing $tool"; done
    if [ -n "$missing" ]; then
        say "installing from the Debian repository:$missing"
        logged apt apt-get update
        # shellcheck disable=SC2086
        logged apt apt-get install -y --no-install-recommends ca-certificates $missing
    fi
    command -v docker >/dev/null 2>&1 || die "docker is not installed (run the boot-test setup first)"
}

make_directories() {
    install -d -m 0755 "$ROOT" "$STATE" "$MEASURE"
    install -d -m 0700 "$PRIV" "$PRIV/log" "$PRIV/tls" "$ROOT/backup" \
        "$ROOT/backup/restic-repository" "$ROOT/backup/staging" "$ROOT/backup/markers"
    # The API writes its logs here (UID 10001); Compose never creates the host path.
    install -d -m 0700 -o 10001 -g 10001 "$ROOT/logs"
    # RESTORE.md: the backup-exports sibling of the repository, operator-owned, group 10001.
    install -d -m 0750 -o 0 -g 10001 "$ROOT/backup/backup-exports"
}

extract_source() {
    local tar_file="$1" tmp="$ROOT/src.tmp" sentinel
    if [ -f "$STATE/source.done" ] && [ -d "$SRC" ]; then say "source: already extracted"; return; fi
    [ -f "$tar_file" ] || die "source archive $tar_file is missing"
    rm -rf "$tmp" "$SRC"
    install -d -m 0755 "$tmp"
    CURRENT_LOG="$PRIV/log/source.log"
    tar -xf "$tar_file" -C "$tmp" --no-same-owner --no-same-permissions >> "$CURRENT_LOG" 2>&1 || die "source extraction"
    CURRENT_LOG=""
    # macOS archivers add AppleDouble "._*" files; Alembic would load "._<revision>.py".
    find "$tmp" -name '._*' -type f -delete
    # Windows extraction and tar.exe do not keep Unix modes; no tracked file needs an exec bit.
    find "$tmp" -type d -exec chmod 0755 {} +
    find "$tmp" -type f -exec chmod 0644 {} +
    for sentinel in .dockerignore backend/pyproject.toml backend/uv.lock frontend/package-lock.json \
        contracts infra/docker/backend.Dockerfile infra/docker/caddy.Dockerfile \
        infra/supabase/compose.yaml infra/supabase/compose.production.yaml \
        infra/caddy/generate_config.py packaging/backup/backup_installation.py; do
        [ -e "$tmp/$sentinel" ] || die "the source archive lacks $sentinel (incomplete download or extraction)"
    done
    if grep -q $'\r' "$tmp/infra/supabase/compose.yaml"; then
        die "the source has Windows line ends (CR); extract the ZIP with Windows Explorer, not another tool"
    fi
    mv "$tmp" "$SRC"
    touch "$STATE/source.done"
    say "source: extracted ($(du -sm "$SRC" | cut -f1) MB)"
}

build_images() {
    local t0
    if [ -f "$STATE/build.done" ] && docker image inspect "$SERVER_IMAGE" >/dev/null 2>&1 \
        && docker image inspect "$CADDY_IMAGE" >/dev/null 2>&1; then
        say "images: already built"; return
    fi
    say "building the server image (frontend and backend; this can take 10 to 30 minutes)"
    t0="$(now)"
    logged build-server docker build --progress=plain -f "$SRC/infra/docker/backend.Dockerfile" -t "$SERVER_IMAGE" "$SRC"
    timing build_server_seconds $(( $(now) - t0 ))
    say "server image built in $(( $(now) - t0 )) s"
    t0="$(now)"
    logged build-caddy docker build --progress=plain -f "$SRC/infra/docker/caddy.Dockerfile" -t "$CADDY_IMAGE" "$SRC"
    timing build_caddy_seconds $(( $(now) - t0 ))
    say "Caddy image built in $(( $(now) - t0 )) s"
    touch "$STATE/build.done"
}

generate_keys() {
    if [ -f "$PRIV/keys.env" ]; then say "keys: exist (never regenerated)"; return; fi
    rm -rf "$PRIV/gen"
    install -d -m 0700 -o 10001 -g 10001 "$PRIV/gen"
    # backend/operations/supabase_keys.py needs the backend environment, so it runs in a
    # one-shot container of the server image with no network. It prints no values.
    logged keys docker run --rm --network none --read-only --user 10001:10001 \
        --tmpfs /tmp:rw,noexec,nosuid,nodev,size=16m,uid=10001,gid=10001 \
        --cap-drop ALL --security-opt no-new-privileges --no-healthcheck \
        --volume "$PRIV/gen:/out" --entrypoint python "$SERVER_IMAGE" \
        operations/supabase_keys.py --output /out/keys.env
    install -m 0600 -o 0 -g 0 "$PRIV/gen/keys.env" "$PRIV/keys.env"
    rm -rf "$PRIV/gen"
    say "keys: generated inside Linux (values not shown)"
}

write_caddyfile() {
    if [ -f "$PRIV/Caddyfile" ]; then return; fi
    logged caddyfile python3 "$SRC/infra/caddy/generate_config.py" --public-host "$S1_HOST" \
        --output "$PRIV/Caddyfile.new" --upstream-host api --backend-port 8000 --health-port 3449 \
        --https-port "$S1_PORT" --tls-mode internal
    caddyfile_for_caddy "$PRIV/Caddyfile.new"
    mv "$PRIV/Caddyfile.new" "$PRIV/Caddyfile"
}

# The Caddyfile holds no secret. Caddy runs as UID 1000 and must read it. The backup tool
# (packaging/backup) accepts only a file owned by root or the operator with no group or
# other bits. The two rules conflict on a Linux file system, so S1 gives the file to UID 1000
# while Caddy runs and back to root for the backup (a P1 finding, reported in the results).
caddyfile_for_caddy() { chown 1000:1000 "$1"; chmod 0400 "$1"; }
caddyfile_for_backup() { chown 0:0 "$1"; chmod 0600 "$1"; }

start_stack() {
    local t0
    t0="$(now)"
    say "pulling the pinned provider images"
    # shellcheck disable=SC2086
    logged pull compose pull --quiet $PROVIDERS
    timing pull_providers_seconds $(( $(now) - t0 ))
    say "provider images pulled in $(( $(now) - t0 )) s"
    t0="$(now)"
    # shellcheck disable=SC2086
    logged providers compose up -d --wait --wait-timeout 900 $PROVIDERS
    timing providers_healthy_seconds $(( $(now) - t0 ))
    say "provider services healthy in $(( $(now) - t0 )) s"
    if [ ! -f "$STATE/provision.done" ]; then
        t0="$(now)"
        logged provision docker run --rm --pull=never --network "${PROJECT}_provider" \
            --env-file "$PRIV/provision.env" --user 10001:10001 --read-only \
            --tmpfs /tmp:rw,noexec,nosuid,nodev,size=64m,uid=10001,gid=10001 \
            --cap-drop ALL --security-opt no-new-privileges --no-healthcheck \
            --entrypoint /bin/sh "$SERVER_IMAGE" -ec '
                python operations/provision_database_role.py --confirm
                python -m alembic upgrade head
                python -m alembic check
                python operations/provision_storage.py --confirm
            '
        touch "$STATE/provision.done"
        timing provisioning_seconds $(( $(now) - t0 ))
        say "provisioning (roles, migrations, Storage) done in $(( $(now) - t0 )) s"
    fi
    t0="$(now)"
    logged api compose up -d --wait --wait-timeout 300 api
    wait_for 300 "API /api/ready (internal)" api_ready_inside
    timing api_ready_seconds $(( $(now) - t0 ))
    say "API ready (internal path) in $(( $(now) - t0 )) s"
    t0="$(now)"
    logged caddy compose up -d --wait --wait-timeout 300 caddy
    wait_for 300 "HTTPS /api/ready through Caddy" https_ready
    timing caddy_ready_seconds $(( $(now) - t0 ))
    say "HTTPS https://$S1_HOST:$S1_PORT/api/ready answers 200 through Caddy in $(( $(now) - t0 )) s"
}

install_units() {
    if [ "$(ps -p 1 -o comm= 2>/dev/null)" != "systemd" ]; then
        say "systemd is not PID 1 here; boot-time sampler and readiness watcher not installed"
        return
    fi
    local script="$HERE/s1.sh"
    cat > /etc/systemd/system/slateops-s1-sampler.service <<EOF
[Unit]
Description=Slate Operations P1: memory sampler (every 5 s)
After=local-fs.target

[Service]
ExecStart=/bin/bash $script sample
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
    cat > /etc/systemd/system/slateops-s1-ready.service <<EOF
[Unit]
Description=Slate Operations P1: first HTTPS /api/ready after each Linux boot
After=docker.service
Wants=docker.service

[Service]
Type=simple
ExecStart=/bin/bash $script ready-watch
Restart=no

[Install]
WantedBy=multi-user.target
EOF
    logged units systemctl daemon-reload
    logged units systemctl enable --now slateops-s1-sampler.service
    logged units systemctl enable slateops-s1-ready.service
    say "boot-time sampler and readiness watcher installed"
}

record_sizes() {
    CURRENT_LOG="$PRIV/log/sizes.log"
    python3 - "$STATE/sizes.json" "$PROJECT" "$SERVER_IMAGE" "$CADDY_IMAGE" "$1" >> "$CURRENT_LOG" 2>&1 <<'PY' || die "size measurement"
import json, os, subprocess, sys
out, project, server, caddy, phase = sys.argv[1:6]
def run(*args):
    return subprocess.run(args, check=True, capture_output=True, text=True).stdout
refs = sorted(set(run("docker", "compose", "--project-name", project, "--env-file",
    os.environ["S1_PROVIDER_ENV"], "-f", os.environ["S1_COMPOSE"], "-f", os.environ["S1_OVERLAY"],
    "config", "--images").split()))
images = {}
for ref in refs:
    try:
        images[ref.split("@")[0]] = int(run("docker", "image", "inspect", "-f", "{{.Size}}", ref).strip())
    except subprocess.CalledProcessError:
        images[ref.split("@")[0]] = None
volumes = {}
for line in run("docker", "system", "df", "-v", "--format", "{{json .}}").splitlines():
    data = json.loads(line)
    for volume in data.get("Volumes") or []:
        if volume.get("Name", "").startswith(project + "_"):
            volumes[volume["Name"]] = volume.get("Size")
df = run("df", "-B1", "--output=size,used,avail", "/").splitlines()[-1].split()
build_cache = None
for line in run("docker", "system", "df", "--format", "{{json .}}").splitlines():
    data = json.loads(line)
    if data.get("Type") == "Build Cache":
        build_cache = data.get("Size")
try:
    existing = json.load(open(out))
except (OSError, ValueError):
    existing = {}
existing[phase] = {
    "images_bytes": images,
    "images_total_bytes": sum(v for v in images.values() if v),
    "volumes": volumes,
    "build_cache": build_cache,
    "root_fs": {"size_bytes": int(df[0]), "used_bytes": int(df[1]), "avail_bytes": int(df[2])},
}
json.dump(existing, open(out, "w"), indent=1, sort_keys=True)
PY
    CURRENT_LOG=""
}

cmd_install() {
    local host="" source="" port=443 bind=0.0.0.0 gateway=58000 subnet="" t_all
    while [ $# -gt 0 ]; do
        case "$1" in
            --host) host="$2"; shift 2 ;;
            --source) source="$2"; shift 2 ;;
            --port) port="$2"; shift 2 ;;
            --bind) bind="$2"; shift 2 ;;
            --gateway-port) gateway="$2"; shift 2 ;;
            --app-subnet) subnet="$2"; shift 2 ;;
            *) die "unknown option $1" ;;
        esac
    done
    [[ "$host" =~ ^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.local$ ]] || die "--host must be <name>.local in lower case (got '$host')"
    [[ "$port" =~ ^[0-9]+$ && "$gateway" =~ ^[0-9]+$ ]] || die "ports must be numbers"
    t_all="$(now)"
    make_directories
    if [ -f "$STATE/params.env" ]; then
        load_params
        [ "$S1_HOST" = "$host" ] || die "S1 was installed for $S1_HOST; run 'remove' before a new name"
    else
        [[ -z "$subnet" || "$subnet" =~ ^[0-9.]+/[0-9]+$ ]] || die "--app-subnet must be an IPv4 CIDR"
        printf 'S1_HOST=%s\nS1_PORT=%s\nS1_BIND=%s\nS1_GATEWAY_PORT=%s\nS1_APP_SUBNET=%s\n' "$host" "$port" "$bind" "$gateway" "$subnet" > "$STATE/params.env"
        load_params
    fi
    : > "$STATE/install-timings.txt"
    say "install started: host $S1_HOST, HTTPS port $S1_PORT, bind $S1_BIND"
    install_prerequisites
    extract_source "$source"
    build_images
    generate_keys
    logged env python3 "$HERE/s1_env.py" write-env "$ROOT" "$S1_HOST" "$S1_PORT" "$S1_BIND" "$S1_GATEWAY_PORT" "${S1_APP_SUBNET:-}"
    write_caddyfile
    logged compose-config compose config --quiet
    record_sizes after_build
    if [ -z "$(ls -A "$ROOT/backup/restic-repository")" ]; then
        RESTIC_REPOSITORY="$ROOT/backup/restic-repository" RESTIC_PASSWORD_FILE="$PRIV/restic-password" \
            logged restic-init restic init
        say "Restic repository initialized"
    fi
    start_stack
    install_units
    say "removing the build cache (the real installer pulls images and never builds)"
    logged prune docker builder prune -af
    record_sizes after_install
    timing install_total_seconds $(( $(now) - t_all ))
    python3 - "$STATE/install-timings.txt" "$STATE/install-timings.json" <<'PY'
import json, sys
rows = dict(line.split() for line in open(sys.argv[1]) if line.strip())
json.dump({key: int(value) for key, value in rows.items()}, open(sys.argv[2], "w"), indent=1, sort_keys=True)
PY
    say "install complete in $(( $(now) - t_all )) s"
    scan_transcript || die "the stdout transcript holds a generated secret value"
}

# ---------------------------------------------------------------------------
# measurements
# ---------------------------------------------------------------------------

cmd_sample() {
    install -d -m 0755 "$MEASURE"
    local boot file
    boot="$(cat /proc/sys/kernel/random/boot_id)"
    file="$MEASURE/mem-$boot.csv"
    # Keep the six newest sample files.
    # shellcheck disable=SC2012
    ls -1t "$MEASURE"/mem-*.csv 2>/dev/null | tail -n +7 | xargs -r rm -f || true
    [ -f "$file" ] || echo "epoch,mem_total_kib,mem_available_kib" > "$file"
    while true; do
        awk -v t="$(date +%s)" '/^MemTotal:/ {total=$2} /^MemAvailable:/ {avail=$2} END {printf "%s,%s,%s\n", t, total, avail}' /proc/meminfo >> "$file"
        sleep 5
    done
}

cmd_ready_watch() {
    load_params
    # A backup that a power cut or a stop interrupted leaves the Caddyfile with root. Give it
    # back to Caddy; Docker restarts Caddy by itself and then reads it.
    if [ -f "$PRIV/Caddyfile" ] && [ "$(stat -c %u "$PRIV/Caddyfile")" != "1000" ]; then caddyfile_for_caddy "$PRIV/Caddyfile"; fi
    local boot out btime start code tries=0
    boot="$(cat /proc/sys/kernel/random/boot_id)"
    out="$MEASURE/ready-$boot.json"
    [ -f "$out" ] && exit 0
    btime="$(awk '/^btime/ {print $2}' /proc/stat)"
    start="$(now)"
    while [ $(( $(now) - start )) -lt 1800 ]; do
        tries=$((tries + 1))
        code="$(https_code)"
        if [ "$code" = "200" ]; then
            [ -f /var/lib/slateops-boottest/host/windows.json ] && cp /var/lib/slateops-boottest/host/windows.json "$MEASURE/ready-$boot-windows.json"
            printf '{"boot_id":"%s","linux_boot_epoch":%s,"watch_started_epoch":%s,"ready_epoch":%s,"ready_utc":"%s","probes":%s}\n' \
                "$boot" "$btime" "$start" "$(now)" "$(stamp)" "$tries" > "$out"
            exit 0
        fi
        sleep 2
    done
    printf '{"boot_id":"%s","linux_boot_epoch":%s,"watch_started_epoch":%s,"ready_epoch":null,"timed_out_seconds":1800}\n' \
        "$boot" "$btime" "$start" > "$out"
}

cmd_measure_idle() {
    load_params
    local label="${1:-install}" i used=() line total avail max=0 sum=0 dropped=false
    [[ "$label" =~ ^[a-z_]{1,20}$ ]] || die "measure-idle needs a label of lower-case letters"
    # Drop the clean file cache first, so the number shows what the stack holds, not old reads.
    sync
    if (echo 3 > /proc/sys/vm/drop_caches) 2>/dev/null; then dropped=true; fi
    sleep 5
    say "idle memory ($label): 60 s of samples; file cache dropped first: $dropped"
    for i in $(seq 1 30); do
        line="$(awk '/^MemTotal:/ {t=$2} /^MemAvailable:/ {a=$2} END {print t, a}' /proc/meminfo)"
        total="${line% *}"; avail="${line#* }"
        used+=( $(( (total - avail) / 1024 )) )
        sleep 2
    done
    for i in "${used[@]}"; do sum=$((sum + i)); [ "$i" -gt "$max" ] && max="$i"; done
    docker stats --no-stream --format '{{.Name}} {{.MemUsage}}' > "$STATE/docker-stats-$label.txt" 2>/dev/null || true
    python3 - "$STATE/idle-$label.json" "$(( total / 1024 ))" "$(( sum / ${#used[@]} ))" "$max" "$STATE/docker-stats-$label.txt" "$dropped" <<'PY'
import json, sys
out, total, mean, peak, stats, dropped = sys.argv[1:7]
containers = {}
for line in open(stats):
    name, _, usage = line.strip().partition(" ")
    if name:
        containers[name] = usage.split(" / ")[0]
json.dump({"mem_total_mib": int(total), "used_mib_mean": int(mean), "used_mib_max": int(peak),
           "file_cache_dropped": dropped == "true", "containers": containers}, open(out, "w"), indent=1, sort_keys=True)
PY
    record_sizes "idle_$label"
    say "idle memory ($label): used mean $(( sum / ${#used[@]} )) MiB, max $max MiB, of $(( total / 1024 )) MiB"
    scan_transcript || die "the stdout transcript holds a generated secret value"
}

cmd_backup() {
    load_params
    local ts boot marker config running t_stop t_stopped t_b0 t_b1 t_ready outcome=failed snapshot="" service
    ts="$(date -u +%Y%m%dT%H%M%SZ)"
    boot="$(cat /proc/sys/kernel/random/boot_id)"
    marker="$ROOT/backup/markers/backup-$ts.json"
    running="$(compose ps --services --status running | tr '\n' ' ')"
    say "backup: services running before: $running"
    t_stop="$(now)"
    logged backup-stop compose stop
    t_stopped="$(now)"
    say "backup: all services stopped in $(( t_stopped - t_stop )) s"
    config="$(python3 "$HERE/s1_env.py" backup-config "$ROOT" "$marker")"
    # If this command stops early (a failure or a signal), the Caddyfile goes back to Caddy.
    trap 'caddyfile_for_caddy "$PRIV/Caddyfile"' EXIT
    trap 'exit 143' TERM HUP INT
    caddyfile_for_backup "$PRIV/Caddyfile"
    t_b0="$(now)"
    CURRENT_LOG="$PRIV/log/backup-$ts.log"
    if (cd "$SRC" && PYTHONPATH="$SRC/packaging" python3 -m backup.backup_installation --config "$config") >> "$CURRENT_LOG" 2>&1; then
        outcome=succeeded
        snapshot="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["snapshot_id"])' "$marker" 2>/dev/null || true)"
    else
        say "backup: the backup command failed; last lines (redacted):"
        python3 "$HERE/s1_env.py" redact "$ROOT" "$CURRENT_LOG" | tail -n 25 | sed 's/^/    | /' | tee -a "$TRANSCRIPT"
    fi
    CURRENT_LOG=""
    t_b1="$(now)"
    caddyfile_for_caddy "$PRIV/Caddyfile"
    say "backup: command $outcome in $(( t_b1 - t_b0 )) s"
    # Restart only what ran before, in the RESTORE.md order: db, providers, api (ready), caddy.
    case " $running " in *" db "*) logged backup-restart compose up -d --no-deps --wait --wait-timeout 600 db ;; esac
    local providers=""
    for service in auth storage imgproxy realtime meta studio api-gw; do
        case " $running " in *" $service "*) providers="$providers $service" ;; esac
    done
    # shellcheck disable=SC2086
    [ -n "$providers" ] && logged backup-restart compose up -d --no-deps --wait --wait-timeout 600 $providers
    case " $running " in *" api "*)
        logged backup-restart compose up -d --no-deps --wait --wait-timeout 300 api
        wait_for 300 "API /api/ready (internal) after the backup" api_ready_inside ;;
    esac
    case " $running " in *" caddy "*)
        logged backup-restart compose up -d --no-deps --wait --wait-timeout 300 caddy
        wait_for 300 "HTTPS /api/ready after the backup" https_ready ;;
    esac
    t_ready="$(now)"
    python3 - "$STATE/backup-$ts.json" <<PY
import json, sys
json.dump({"boot_id": "$boot", "outcome": "$outcome", "snapshot_id": "$snapshot",
  "stop_started_epoch": $t_stop, "stopped_epoch": $t_stopped, "backup_started_epoch": $t_b0,
  "backup_ended_epoch": $t_b1, "ingress_ready_epoch": $t_ready,
  "stop_seconds": $(( t_stopped - t_stop )), "backup_command_seconds": $(( t_b1 - t_b0 )),
  "restart_seconds": $(( t_ready - t_b1 )), "outage_seconds": $(( t_ready - t_stop )),
  "repository_bytes": $(du -sb "$ROOT/backup/restic-repository" | cut -f1),
  "config": "$config", "marker": "$marker"}, open(sys.argv[1], "w"), indent=1, sort_keys=True)
PY
    say "backup: outage $(( t_ready - t_stop )) s (stop $(( t_stopped - t_stop )) s, backup $(( t_b1 - t_b0 )) s, restart $(( t_ready - t_b1 )) s); repository $(du -sm "$ROOT/backup/restic-repository" | cut -f1) MB"
    scan_transcript || die "the stdout transcript holds a generated secret value"
    [ "$outcome" = succeeded ] || exit 1
}

cmd_restore_timing() {
    load_params
    local latest snapshot config scratch ts t0 t1 t2 t3 bytes inspect_code
    # Backup records are named backup-<UTC time>.json, so the last name in sort order is the newest.
    latest="$(find "$STATE" -maxdepth 1 -name 'backup-*.json' | sort | tail -n 1)"
    [ -n "$latest" ] || die "no backup yet; run 'backup' first"
    snapshot="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["snapshot_id"])' "$latest")"
    config="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["config"])' "$latest")"
    [ -n "$snapshot" ] || die "the newest backup has no snapshot (it failed)"
    ts="$(date -u +%Y%m%dT%H%M%SZ)"
    scratch="$ROOT/backup/restore-scratch-$ts"
    install -d -m 0700 "$scratch"
    say "restore timing: restic restore of snapshot ${snapshot:0:12} into a scratch folder"
    t0="$(date +%s.%N)"
    RESTIC_REPOSITORY="$ROOT/backup/restic-repository" RESTIC_PASSWORD_FILE="$PRIV/restic-password" \
        RESTIC_CACHE_DIR="$ROOT/backup/restic-cache" logged "restore-$ts" restic restore "$snapshot" --target "$scratch"
    t1="$(date +%s.%N)"
    bytes="$(du -sb "$scratch" | cut -f1)"
    rm -rf "$scratch" "$ROOT/backup/restic-cache"
    # restore_installation.py inspection: read-only, creates no target. --execute needs an
    # interactive terminal by design, so the kit does not run it (plan W13a, decision H12).
    t2="$(date +%s.%N)"
    inspect_code=0
    (cd "$SRC" && PYTHONPATH="$SRC/packaging" python3 -m backup.restore_installation --config "$config" \
        --snapshot "$snapshot" --target-project slateops-s1r --target-instance-id slateops-s1r \
        --target-directory "$ROOT/backup/restore-target-$ts") >> "$PRIV/log/restore-$ts.log" 2>&1 || inspect_code=$?
    t3="$(date +%s.%N)"
    local restore_s inspect_s
    restore_s="$(awk -v a="$t0" -v b="$t1" 'BEGIN { printf "%.1f", b - a }')"
    inspect_s="$(awk -v a="$t2" -v b="$t3" 'BEGIN { printf "%.1f", b - a }')"
    python3 - "$STATE/restore-timing.json" <<PY
import json, sys
json.dump({"snapshot_id": "$snapshot", "restic_restore_seconds": $restore_s, "restored_bytes": $bytes,
  "inspection_seconds": $inspect_s, "inspection_exit_code": $inspect_code,
  "full_restore": "not measured: restore_installation.py --execute needs an interactive terminal (plan W13a, decision H12)"},
  open(sys.argv[1], "w"), indent=1, sort_keys=True)
PY
    say "restore timing: restic restore $restore_s s for $(( bytes / 1048576 )) MB; inspection $inspect_s s (exit $inspect_code)"
    scan_transcript || die "the stdout transcript holds a generated secret value"
}

cmd_port80() {
    load_params
    case "${1:-}" in
        start)
            install -d -m 0755 "$ROOT/port80"
            install -m 0644 "$HERE/port80.html" "$ROOT/port80/index.html"
            docker rm -f slateops-s1-port80 >/dev/null 2>&1 || true
            logged port80 docker run -d --name slateops-s1-port80 --restart no \
                --publish "$S1_BIND:80:8080" --read-only --user 65534:65534 --cap-drop ALL \
                --security-opt no-new-privileges --volume "$ROOT/port80:/www:ro" \
                "$PORT80_IMAGE" httpd -f -p 8080 -h /www
            say "port 80 test page started" ;;
        stop)
            docker rm -f slateops-s1-port80 >/dev/null 2>&1 || true
            say "port 80 test page stopped" ;;
        *) die "usage: port80 start|stop" ;;
    esac
}

cmd_avahi() {
    case "${1:-}" in
        start)
            local name="${2:-}" address
            [[ "$name" =~ ^[a-z0-9-]{1,40}\.local$ ]] || die "avahi start needs a NAME.local"
            logged avahi apt-get update
            logged avahi apt-get install -y --no-install-recommends avahi-daemon avahi-utils
            # A distinct host name, so Avahi never answers for the Windows computer name.
            sed -i -e 's/^#\?host-name=.*/host-name=slateops-p1-avahi/' -e 's/^#\?use-ipv6=.*/use-ipv6=no/' \
                /etc/avahi/avahi-daemon.conf
            logged avahi systemctl restart avahi-daemon
            address="$(ip -4 route get 1.1.1.1 2>/dev/null | awk '{for (i = 1; i < NF; i++) if ($i == "src") print $(i + 1)}')"
            [ -n "$address" ] || die "no LAN IPv4 address in the distribution"
            nohup avahi-publish -a -R "$name" "$address" > "$PRIV/log/avahi-publish.log" 2>&1 &
            echo $! > "$STATE/avahi-publish.pid"
            sleep 3
            say "avahi: daemon $(systemctl is-active avahi-daemon 2>&1); publishing $name -> $address"
            say "avahi: publisher log: $(tr '\n' ' ' < "$PRIV/log/avahi-publish.log" | cut -c1-200)" ;;
        stop)
            [ -f "$STATE/avahi-publish.pid" ] && kill "$(cat "$STATE/avahi-publish.pid")" 2>/dev/null || true
            rm -f "$STATE/avahi-publish.pid"
            if dpkg -s avahi-daemon >/dev/null 2>&1; then
                logged avahi apt-get purge -y avahi-daemon avahi-utils
                logged avahi apt-get autoremove -y
            fi
            say "avahi: stopped and removed" ;;
        *) die "usage: avahi start NAME.local|stop" ;;
    esac
}

cmd_stop_test_stack() {
    if docker compose --project-name slateops-boottest ps -q 2>/dev/null | grep -q .; then
        logged test-stack docker compose --project-name slateops-boottest stop
        say "boot-test stack (port 8443) stopped; its data stays"
    else
        say "boot-test stack is not running"
    fi
}

cmd_abort() {
    # Stops an install that 30-p1.ps1 stopped on the Windows side (for example for low disk space).
    pkill -TERM -f 's1.sh install' 2>/dev/null || true
    pkill -TERM -f 'docker build' 2>/dev/null || true
    pkill -TERM -f 'docker compose' 2>/dev/null || true
    sleep 5
    docker builder prune -af >/dev/null 2>&1 || true
    printf '%s s1: abort: install stopped, build cache removed; free %s on /\n' "$(stamp)" "$(df -h --output=avail / | tail -n 1 | tr -d ' ')"
}

cmd_remove() {
    say "remove: the S1 stack, its volumes (throwaway test data), images, units and files"
    if [ -f "$PRIV/provider.env" ] && [ -d "$SRC" ]; then
        compose down --volumes --remove-orphans >> "$PRIV/log/remove.log" 2>&1 || true
        # S1_KEEP_PROVIDER_IMAGES=1 keeps the pinned provider images (a local test on a shared daemon).
        if [ "${S1_KEEP_PROVIDER_IMAGES:-0}" != "1" ]; then
            compose config --images 2>/dev/null | grep -v '^slateops-s1-' | xargs -r docker image rm >> "$PRIV/log/remove.log" 2>&1 || true
        fi
    fi
    docker rm -f slateops-s1-port80 >/dev/null 2>&1 || true
    docker image rm "$SERVER_IMAGE" "$CADDY_IMAGE" "$PORT80_IMAGE" >/dev/null 2>&1 || true
    docker builder prune -af >/dev/null 2>&1 || true
    if [ "$(ps -p 1 -o comm= 2>/dev/null)" = "systemd" ]; then
        systemctl disable --now slateops-s1-sampler.service slateops-s1-ready.service >/dev/null 2>&1 || true
        rm -f /etc/systemd/system/slateops-s1-sampler.service /etc/systemd/system/slateops-s1-ready.service
        systemctl daemon-reload || true
        if dpkg -s avahi-daemon >/dev/null 2>&1; then
            apt-get purge -y avahi-daemon avahi-utils >/dev/null 2>&1 || true
        fi
    fi
    rm -rf "$ROOT"
    printf '%s s1: remove complete\n' "$(stamp)"
}

main() {
    [ "$(id -u)" = "0" ] || { echo "Run as root."; exit 2; }
    export S1_PROVIDER_ENV="$PRIV/provider.env" S1_COMPOSE="$SRC/infra/supabase/compose.yaml" \
        S1_OVERLAY="$SRC/infra/supabase/compose.production.yaml"
    local command="${1:-}"; shift || true
    case "$command" in
        install) cmd_install "$@" ;;
        stop-test-stack) install -d -m 0755 "$ROOT" "$STATE"; install -d -m 0700 "$PRIV" "$PRIV/log"; cmd_stop_test_stack ;;
        measure-idle) cmd_measure_idle "$@" ;;
        abort) cmd_abort ;;
        backup) cmd_backup ;;
        restore-timing) cmd_restore_timing ;;
        port80) cmd_port80 "$@" ;;
        avahi) cmd_avahi "$@" ;;
        report)
            # Container names and published ports prove the bindings (443 on all addresses, the
            # gateway on 127.0.0.1 only). No values, only names and port mappings.
            docker ps --format '{{.Names}}\t{{.Ports}}' > "$STATE/ports.txt" 2>/dev/null || true
            python3 "$HERE/s1_env.py" report "$ROOT" ;;
        remove) cmd_remove ;;
        sample) cmd_sample ;;
        ready-watch) cmd_ready_watch ;;
        *) sed -n '2,20p' "$0"; exit 2 ;;
    esac
}

main "$@"
