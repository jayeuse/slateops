#!/usr/bin/env bash
# install-proof.sh - installs Slate Operations from one test build's own artifacts inside
# our Linux image on a Linux host, and checks the result (docs/plans/windows-installer.md
# W5b-1, W5b-2; TASK-0086 AC-P1).
#
# Usage: packaging/linux-image/install-proof.sh --version <X.Y.Z[-rc.N]> --tarball <linux
#        image .tar.gz> --payload <folder> --output <folder>
#
# The payload folder holds what the setup program streams into `receive`: the signed
# manifest, its sigstore bundle, the engine bundle and our two image archives.
#
# How (a host proof of the Linux side; Windows and WSL are W14):
# 1. The root file system becomes a Docker image (docker import) and boots systemd in a
#    privileged container, so our Docker 29, Compose 5.7.1, containerd store, cosign,
#    Python and engine run as in WSL. Test-only changes: chronyd runs with -x (it must not
#    set the runner's clock, as in boot-check.sh), /etc/resolv.conf names the runner's
#    upstream resolvers, and /var is a volume (overlay on overlay cannot hold images).
# 2. Mailpit (the development pin in infra/supabase/compose.dev.yaml) catches the mail.
#    Auth checks TLS against its own image's roots, which stay unmodified (DEC-0034), so
#    the proof uses plain SMTP: after the install the email settings are staged with the
#    engine's own writer, in place of `smtp-test` (unit-proved, TASK-0085), and `set-email`
#    applies them.
# 3. The listener rule and the interop removal of prepare on the booted image (TASK-0097);
#    receive, prefetch (status until done), install with no email settings and the first
#    administrator's password (DEC-0041); an independent HTTPS /api/ready with the
#    installation's CA; sign-in with that password; a password reset refused with
#    email_not_configured; install again (nothing changes); set-email, then a password reset
#    reaches Mailpit.
# 4. Backups (W10b, TASK-0093 AC-13): a test-only /sbin/mount.drvfs stands in for WSL's drvfs
#    and bind-mounts a stand-in drive folder. Install step 12 takes the first backup; the
#    timer runs a tick; then the proof stops the timer and runs ticks by hand: one scheduled
#    backup with the folder present, and one with it missing (backup_failed, the services
#    come back, status backup_target_missing). The drvfs mount itself is proved in W14.
# On a failure it saves the engine's redacted log bundle, the systemd console and the
# journal tail in the output folder.
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo="$(cd "$here/../.." && pwd)"
version="" tarball="" payload="" output=""
while [ "$#" -gt 0 ]; do
    case "$1" in
        --version) version="${2:-}"; shift 2 ;;
        --tarball) tarball="${2:-}"; shift 2 ;;
        --payload) payload="${2:-}"; shift 2 ;;
        --output) output="${2:-}"; shift 2 ;;
        *) echo "Usage: $0 --version V --tarball F --payload D --output D" >&2; exit 2 ;;
    esac
done
[[ "$version" =~ ^[0-9]+\.[0-9]+\.[0-9]+(-rc\.[0-9]+)?$ ]] || { echo "install-proof.sh: --version" >&2; exit 2; }
[ -f "$tarball" ] && [ -d "$payload" ] && [ -n "$output" ] || { echo "install-proof.sh: inputs" >&2; exit 2; }
mkdir -p "$output"
output="$(cd "$output" && pwd)"

machine=slateops-proof
host=slateops-proof.local
admin="admin@proof.test"
admin_password="proof-only-admin-password"  # a test value, not a secret
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
run_id="install-$stamp-proof1"
mail_ip=10.250.0.10
engine=(docker exec -i "$machine" slateops-engine)
log() { printf '%s install-proof %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"; }
fail() { log "FAILED: $*"; exit 1; }

collect() {
    local status=$?
    if [ "$status" -ne 0 ] && docker inspect --format '{{.State.Running}}' "$machine" >/dev/null 2>&1; then
        log "collecting the engine log bundle, the console and the journal"
        printf '{"run_id":"report-%s-proof1"}' "$stamp" | "${engine[@]}" log-bundle \
            > "$output/log-bundle.json" 2>/dev/null || true
        python3 - "$output/log-bundle.json" "$output/log-bundle.tar.gz" <<'PY' || true
import base64, json, sys
result = json.load(open(sys.argv[1]))
open(sys.argv[2], "wb").write(base64.b64decode(result["bundle_base64"]))
print("log bundle:", result.get("files"), "files,", result.get("left_out"), "left out")
PY
        rm -f "$output/log-bundle.json"
        docker logs "$machine" > "$output/console.log" 2>&1 || true
        docker exec "$machine" journalctl --no-pager --lines 400 > "$output/journal.txt" 2>&1 || true
        docker exec "$machine" docker ps --all --format '{{.Names}}\t{{.Status}}' \
            > "$output/containers.txt" 2>&1 || true
    fi
    exit "$status"
}
trap collect EXIT

status_json() {
    printf '{"run_id":"%s","windows_part_version":"%s","wsl_version":"2.6.1.0"}' \
        "$run_id" "${version%%-*}" | "${engine[@]}" status
}
field() { python3 -c 'import json,sys; print(json.loads(sys.stdin.read())[sys.argv[1]])' "$1"; }
mails() {
    curl --fail --silent --show-error http://127.0.0.1:8025/api/v1/messages \
        | python3 -c 'import json,sys
data = json.load(sys.stdin)
print(sum(1 for m in data["messages"] if any(t["Address"] == sys.argv[1] for t in m["To"])))' "$admin"
}

log "free space before the proof"; df -h / /mnt 2>/dev/null || df -h /

# 1. Our image as a systemd machine ------------------------------------------------------
docker import "$tarball" slateops-linux:proof >/dev/null
docker network create --subnet 10.250.0.0/24 slateops-proof >/dev/null
mailpit="$(sed -n 's/^    image: \(axllent\/mailpit:[^ ]*\)$/\1/p' "$repo/infra/supabase/compose.dev.yaml")"
[ -n "$mailpit" ] || fail "no Mailpit pin in compose.dev.yaml"
docker run --detach --name slateops-proof-mail --network slateops-proof --ip "$mail_ip" \
    --publish 127.0.0.1:8025:8025 --env MP_SMTP_BIND_ADDR=0.0.0.0:1025 \
    --env MP_UI_BIND_ADDR=0.0.0.0:8025 "$mailpit" >/dev/null
cat > "$output/chrony-proof.conf" <<'EOF'
[Unit]
ConditionCapability=
[Service]
ExecStart=
ExecStart=!/usr/sbin/chronyd -x $DAEMON_OPTS
EOF
grep '^nameserver' /run/systemd/resolve/resolv.conf > "$output/resolv.conf"
# Test only: the drvfs stand-in. mount -t drvfs runs /sbin/mount.drvfs <source> <dir> -o ...
cat > "$output/mount.drvfs" <<'EOF'
#!/bin/sh
set -eu
case "$1" in
    'E:\SlateOps\Backups') drive=/srv/proof-drives/E/SlateOps/Backups ;;
    *) echo "mount.drvfs stand-in: no drive for $1" >&2; exit 32 ;;
esac
[ -d "$drive" ] || { echo "mount.drvfs stand-in: drive missing" >&2; exit 32; }
exec mount --bind "$drive" "$2"
EOF
chmod 0755 "$output/mount.drvfs"
docker run --detach --name "$machine" --hostname "$machine" --privileged --cgroupns=private \
    --network slateops-proof --ip 10.250.0.20 \
    --tmpfs /run --tmpfs /run/lock --tmpfs /tmp \
    --volume slateops-proof-var:/var --volume /lib/modules:/lib/modules:ro \
    --volume "$output/chrony-proof.conf:/etc/systemd/system/chrony.service.d/proof.conf:ro" \
    --volume "$output/resolv.conf:/etc/resolv.conf:ro" \
    --volume "$output/mount.drvfs:/usr/sbin/mount.drvfs:ro" \
    --env container=docker --stop-signal SIGRTMIN+3 \
    slateops-linux:proof /lib/systemd/systemd >/dev/null
state="$(docker exec "$machine" timeout 240 systemctl is-system-running --wait 2>&1 || true)"
log "systemd: $state; failed units: $(docker exec "$machine" systemctl --failed --plain --no-legend --no-pager | awk '{print $1}' | paste -sd, -)"
for _ in $(seq 1 60); do docker exec "$machine" docker info >/dev/null 2>&1 && break; sleep 2; done
docker exec "$machine" docker version --format 'Docker {{.Server.Version}}'
docker exec "$machine" docker compose version
docker exec "$machine" docker info --format '{{json .DriverStatus}}' | grep -q io.containerd.snapshotter.v1 \
    || fail "the image's Docker does not use the containerd image store"
docker exec "$machine" df -h /var/lib

# 1b. The checks of prepare that run on any Linux (TASK-0097, W14 round 3) -----------------
# prepare itself needs WSL (wslinfo), so the proof calls the engine's own listener rule and
# interop removal on the booted image. Test only: Docker's resolver of this user-defined test
# network listens on 127.0.0.11 in the machine; WSL has no such listener.
log "nothing listens on the fresh image but the test network's resolver (prepare's rule)"
listeners="$(docker exec "$machine" ss -H -ltnup)"
echo "$listeners"
others="$(docker exec "$machine" /usr/bin/python3 -I -c '
import sys
sys.path.insert(0, f"/opt/slateops/engine/{sys.argv[1]}")
from engine import prepare
lines = [line for line in sys.argv[2].splitlines() if " 127.0.0.11:" not in line]
print("\n".join(prepare.unexpected_listeners("\n".join(lines))[1]))' "$version" "$listeners")"
[ -z "$others" ] || fail "the fresh image has an unexpected listener: $others"
log "the interop unit and the engine remove a WSLInterop entry (prepare's interop rule)"
binfmt=/proc/sys/fs/binfmt_misc
docker exec "$machine" sh -c "[ -e $binfmt/status ] || mount -t binfmt_misc binfmt_misc $binfmt"
register() {  # a throwaway entry on this test kernel; the interpreter never runs
    docker exec "$machine" sh -c "echo ':$1:M::MZ::/bin/false:' > $binfmt/register"
    docker exec "$machine" test -e "$binfmt/$1" || fail "could not register the test entry $1"
}
register WSLInterop-proof
docker exec "$machine" systemctl restart slateops-interop-off.service
for _ in $(seq 1 10); do docker exec "$machine" test -e "$binfmt/WSLInterop-proof" || break; sleep 1; done
docker exec "$machine" test ! -e "$binfmt/WSLInterop-proof" \
    || fail "slateops-interop-off.service left the WSLInterop entry"
register WSLInterop-late
removed="$(docker exec "$machine" /usr/bin/python3 -I -c '
import sys
from pathlib import Path
sys.path.insert(0, f"/opt/slateops/engine/{sys.argv[1]}")
from engine import context, prepare
print(prepare.remove_interop(Path("/proc/sys/fs/binfmt_misc"), context.write_binfmt))' "$version")"
echo "$removed"
docker exec "$machine" test ! -e "$binfmt/WSLInterop-late" || fail "the engine left the WSLInterop entry"

# 2. receive and prefetch ------------------------------------------------------------------
staging="$output/payload"
mkdir -p "$staging"
printf '{"run_id":"%s","setup_version":"%s"}' "$run_id" "$version" > "$staging/request.json"
parts=(release-manifest.json release-manifest.json.sigstore.json "slateops-engine-$version.tar.gz"
       "slateops-server-$version-amd64.oci.tar" "slateops-caddy-$version-amd64.oci.tar")
for part in "${parts[@]}"; do ln -sf "$(cd "$payload" && pwd)/$part" "$staging/$part"; done
log "receive"
result="$(tar --dereference --format=ustar -C "$staging" -cf - request.json "${parts[@]}" | "${engine[@]}" receive)"
echo "$result"
[ "$(field code <<<"$result")" = received ] || fail "receive: $result"

log "prefetch"
printf '{"run_id":"%s","version":"%s"}' "$run_id" "$version" | "${engine[@]}" prefetch
for _ in $(seq 1 240); do
    code="$(status_json | python3 -c 'import json,sys; print(json.load(sys.stdin)["prefetch"])')"
    case "$code" in
        prefetch_done) break ;;
        prefetch_starting|prefetch_running|prefetch_retrying) sleep 5 ;;
        *) fail "prefetch: $code" ;;
    esac
done
[ "$code" = prefetch_done ] || fail "prefetch did not finish in 20 minutes"
status_json

# 3. Install with no email settings and the administrator's password (DEC-0041) -----------
docker exec "$machine" install -d -m 0700 /srv/proof-drives/E/SlateOps/Backups
answers="$(printf '{"business_name":"Proof Clinic","slug":"proof-clinic","admin_email":"%s","admin_username":"proofadmin","public_host":"%s","backup_target":"E:\\\\SlateOps\\\\Backups","data_vhd_max_gb":64,"time_zone":"Asia/Manila"}' "$admin" "$host")"
log "install"
started=$SECONDS
result="$(printf '{"run_id":"%s","version":"%s","answers":%s,"admin_password":"%s"}' "$run_id" "$version" "$answers" "$admin_password" | "${engine[@]}" install)" \
    || fail "install: $result"
log "install took $((SECONDS - started)) s"
python3 -c 'import json,sys; r=json.loads(sys.argv[1]); r.pop("ca_certificate_pem"); r.pop("recovery_key", None); print(r)' "$result"
[ "$(field code <<<"$result")" = installed ] || fail "install: $result"
[ "$(field backup_setup <<<"$result")" = ready ] || fail "install step 12 did not set up the backup"
[ "$(field admin <<<"$result")" = created ] || fail "install step 11 did not create the administrator"

log "the runner timer is on and has run a tick (W10b-1); then it stops, and ticks run by hand"
[ "$(docker exec "$machine" systemctl is-enabled slateops-runner.timer)" = enabled ] \
    || fail "slateops-runner.timer is not enabled"
for _ in $(seq 1 75); do docker exec "$machine" test -f /var/lib/slateops/runner-tick.json && break; sleep 2; done
docker exec "$machine" test -f /var/lib/slateops/runner-tick.json || fail "the timer ran no tick"
docker exec "$machine" systemctl stop slateops-runner.timer
for _ in $(seq 1 300); do
    case "$(docker exec "$machine" systemctl is-active slateops-runner.service || true)" in
        active|activating) sleep 2 ;; *) break ;;
    esac
done

# 4. Checks ---------------------------------------------------------------------------------
log "HTTPS /api/ready through loopback, trusting only the installation's CA (W5b-1)"
docker exec "$machine" curl --fail --silent --show-error --max-time 20 \
    --cacert /etc/slateops/ca/current/root.crt --resolve "$host:443:127.0.0.1" \
    "https://$host/api/ready"; echo
owners="$(docker exec "$machine" stat -c '%n %u:%g %a' /etc/slateops/Caddyfile \
    /etc/slateops/tls/server.key /etc/slateops/provider.env /etc/slateops/app.env \
    /etc/slateops/provision.env /etc/slateops/restic-password /etc/slateops /etc/slateops/ca \
    /etc/slateops/tls /etc/slateops/trust /etc/slateops/trust/slateops-ca.sha256 \
    /etc/slateops/trust/slateops-ca.crt /etc/slateops/trust/slateops.mobileconfig \
    /var/log/slateops/app /var/lib/slateops/backup/backup-exports /var/lib/slateops/installation.json)"
echo "$owners"
expected="/etc/slateops/Caddyfile 1000:1000 600
/etc/slateops/tls/server.key 1000:1000 600
/etc/slateops/provider.env 0:0 600
/etc/slateops/app.env 0:0 600
/etc/slateops/provision.env 0:0 600
/etc/slateops/restic-password 0:0 600
/etc/slateops 0:0 700
/etc/slateops/ca 0:0 700
/etc/slateops/tls 0:0 755
/etc/slateops/trust 0:0 755
/etc/slateops/trust/slateops-ca.sha256 0:0 644
/etc/slateops/trust/slateops-ca.crt 0:0 644
/etc/slateops/trust/slateops.mobileconfig 0:0 644
/var/log/slateops/app 10001:10001 700
/var/lib/slateops/backup/backup-exports 0:10001 750
/var/lib/slateops/installation.json 0:0 600"
[ "$owners" = "$expected" ] || fail "owners and modes differ from the installation rules (AC-I7, AC-I8)"

# W6a (TASK-0089): the trust site on :80, the trust routes on :443, Realtime through Caddy.
code="$(field ca_security_code <<<"$result")"
fingerprint="$(field ca_root_sha256 <<<"$result")"
[[ "$code" =~ ^([0-9A-F]{2}:){31}[0-9A-F]{2}$ ]] || fail "the install result has no security code"
in_machine_curl() { docker exec "$machine" curl --silent --max-time 15 "$@"; }
answer() { in_machine_curl -o /dev/null -w '%{http_code} %{content_type} %{redirect_url}' "$@"; }
log "port 80 serves exactly three trust paths for $host (W6a-1)"
for line in "/trust 200 text/html; charset=utf-8" \
    "/trust/slateops-ca.crt 200 application/x-x509-ca-cert" \
    "/trust/slateops.mobileconfig 200 application/x-apple-aspen-config"; do
    path="${line%% *}"
    seen="$(answer --resolve "$host:80:127.0.0.1" "http://$host$path")"
    [ "$seen" = "${line#* } " ] || fail "http $path answered '$seen'"
done
page="$(in_machine_curl --resolve "$host:80:127.0.0.1" "http://$host/trust")"
grep -qF "$code" <<<"$page" || fail "the trust page does not show the engine's security code $code"
crt_hash="$(in_machine_curl --resolve "$host:80:127.0.0.1" "http://$host/trust/slateops-ca.crt" | sha256sum | cut -d' ' -f1)"
[ "$crt_hash" = "$fingerprint" ] || fail "slateops-ca.crt is not the root certificate"
log "every other :80 path and name redirects to HTTPS"
for path in / /trust/ /trust/index.html /trust/slateops-ca.sha256 /trust/ok /api/health; do
    seen="$(answer --resolve "$host:80:127.0.0.1" "http://$host$path")"
    [ "$seen" = "308  https://$host$path" ] || fail "http $path answered '$seen'"
done
seen="$(answer -H "Host: 127.0.0.1" "http://127.0.0.1/trust")"
[ "$seen" = "308  https://$host/trust" ] || fail "http by IP answered '$seen'"
log ":443 serves /trust and /trust/ok with no cookie and no CORS header (W6a-7, R10)"
tls=(--cacert /etc/slateops/ca/current/root.crt --resolve "$host:443:127.0.0.1")
seen="$(answer "${tls[@]}" "https://$host/trust")"
[ "$seen" = "200 text/html; charset=utf-8 " ] || fail "https /trust answered '$seen'"
ok_headers="$(in_machine_curl "${tls[@]}" -D - -o /dev/null -w 'size=%{size_download}' "https://$host/trust/ok")"
echo "$ok_headers"
grep -q '^HTTP/[0-9.]* 204' <<<"$ok_headers" || fail "/trust/ok is not 204"
grep -q 'size=0$' <<<"$ok_headers" || fail "/trust/ok has a body"
if grep -qiE '^(set-cookie|access-control-)' <<<"$ok_headers"; then fail "/trust/ok sets a cookie or CORS header"; fi
log "one WebSocket upgrade to Realtime through Caddy with the matching Origin (TASK-0086 carry)"
ws_key="$(head -c 16 /dev/urandom | base64)"  # the protocol's random nonce (RFC 6455)
upgrade="$(docker exec "$machine" curl --http1.1 --silent --max-time 5 -o /dev/null -w '%{http_code}' \
    "${tls[@]}" -H "Connection: Upgrade" -H "Upgrade: websocket" -H "Sec-WebSocket-Version: 13" \
    -H "Sec-WebSocket-Key: $ws_key" -H "Origin: https://$host" \
    "https://$host/realtime/v1/websocket?vsn=1.0.0" || true)"
[ "$upgrade" = 101 ] || fail "the Realtime WebSocket upgrade answered '$upgrade'"
docker exec "$machine" docker compose ls
api_post() {  # path, JSON body: the body, then the HTTP code as the last 3 characters
    docker exec "$machine" curl --silent --max-time 20 "${tls[@]}" -w '\n%{http_code}' \
        -H "Origin: https://$host" -H "Content-Type: application/json" --data "$2" \
        "https://$host$1"
}
log "the administrator signs in with the password from setup (DEC-0041, AC-B1)"
signin="$(api_post /api/auth/login "$(printf '{"email":"%s","password":"%s"}' "$admin" "$admin_password")")"
[ "${signin: -3}" = 200 ] || fail "sign-in with the setup password answered ${signin: -3}"
log "a password reset before email is set up ends with email_not_configured (AC-B3)"
reset="$(api_post /api/auth/recovery/request "$(printf '{"email":"%s"}' "$admin")")"
[ "${reset: -3}" = 503 ] && grep -q email_not_configured <<<"$reset" \
    || fail "the password reset without email answered '$reset'"
sleep 5
[ "$(mails)" -eq 0 ] || fail "mail was sent before email was set up"

log "install again (W5b-2): every step done, nothing changes, no mail"
before="$(docker exec "$machine" sh -c 'sha256sum /etc/slateops/*.env /etc/slateops/Caddyfile /etc/slateops/ca/current/*')"
again="$(printf '{"run_id":"install-%s-proof2","version":"%s"}' "$(date -u +%Y%m%dT%H%M%SZ)" "$version" | "${engine[@]}" install)"
[ "$(field code <<<"$again")" = installed ] || fail "second install: $again"
after="$(docker exec "$machine" sh -c 'sha256sum /etc/slateops/*.env /etc/slateops/Caddyfile /etc/slateops/ca/current/*')"
[ "$before" = "$after" ] || fail "the second install changed a file"
sleep 5
[ "$(mails)" -eq 0 ] || fail "the second install sent mail"

log "set-email applies the email settings after the install (AC-B4)"
docker exec -i "$machine" /usr/bin/python3 -I - "$version" "$mail_ip" <<'PY'
import sys
sys.path.insert(0, f"/opt/slateops/engine/{sys.argv[1]}")
from engine import smtp_env
from engine.core import Paths, private_dir, write_private
paths = Paths()
private_dir(paths.staged_smtp.parent)
values = {"SMTP_HOST": sys.argv[2], "SMTP_PORT": "1025", "SMTP_ADMIN_EMAIL": "noreply@proof.test",
          "SMTP_USER": "proof-mailer", "SMTP_PASS": "proof-only-mail-password",
          "SMTP_SENDER_NAME": "Slate Operations proof"}
write_private(paths.staged_smtp, smtp_env.render(values).encode())
print("staged the email settings for the proof's Mailpit")
PY
email="$(printf '{"run_id":"maintenance-%s-proof4"}' "$(date -u +%Y%m%dT%H%M%SZ)" | "${engine[@]}" set-email)" \
    || fail "set-email: $email"
[ "$(field code <<<"$email")" = email_set ] || fail "set-email: $email"
reset="$(api_post /api/auth/recovery/request "$(printf '{"email":"%s"}' "$admin")")"
[ "${reset: -3}" = 204 ] || fail "the password reset after set-email answered '$reset'"
for _ in $(seq 1 30); do [ "$(mails)" -ge 1 ] && break; sleep 2; done
[ "$(mails)" -eq 1 ] || fail "expected one password reset email in Mailpit, found $(mails)"
log "the password reset email reached Mailpit"

log "renewal (W6a-4): delete the leaf pair, renew, Caddy reloads, requests keep answering"
served_leaf() {
    docker exec -i "$machine" python3 -I - "$host" <<'PY'
import hashlib, socket, ssl, sys
context = ssl.create_default_context(cafile="/etc/slateops/ca/current/root.crt")
with context.wrap_socket(socket.create_connection(("127.0.0.1", 443), timeout=10),
                         server_hostname=sys.argv[1]) as connection:
    print(hashlib.sha256(connection.getpeercert(binary_form=True)).hexdigest())
PY
}
before_leaf="$(served_leaf)"
docker exec "$machine" rm /etc/slateops/tls/server.crt /etc/slateops/tls/server.key
printf '{"run_id":"renewal-%s-proof4"}' "$(date -u +%Y%m%dT%H%M%SZ)" \
    | "${engine[@]}" renew-certificate > "$output/renewal.json" &
renewal=$!
: > "$output/during-renewal.txt"
probe() {
    printf '%s %s\n' "$(date +%s%3N)" "$(in_machine_curl "${tls[@]}" -o /dev/null \
        -w '%{http_code}' "https://$host/trust/ok" || true)" >> "$output/during-renewal.txt"
}
while kill -0 "$renewal" 2>/dev/null; do probe; done
wait "$renewal" || fail "renew-certificate: $(cat "$output/renewal.json")"
requests="$(wc -l < "$output/during-renewal.txt")"
for _ in 1 2 3 4 5; do probe; done
renewed="$(cat "$output/renewal.json")"
echo "$renewed"; log "$requests requests during the renewal, 5 after it"
cut -d' ' -f2 "$output/during-renewal.txt" | sort | uniq -c
[ "$requests" -ge 3 ] || fail "too few requests ran during the renewal to show an outage"
# W6a-4: a handshake in flight when Caddy switches can fail (seen locally: at most one per
# reload, TLS error or empty reply, on the base image and ours). The outage is the span of
# failed requests; it must stay within a reload (2 s, planning value; a reload took ~0.1 s).
python3 - "$output/during-renewal.txt" "$requests" <<'PY' || fail "the renewal outage was longer than a reload"
import sys
rows = [line.split() for line in open(sys.argv[1]) if line.strip()]
failed = [int(at) for at, code in rows if code != "204"]
after = [code for _, code in rows[int(sys.argv[2]):]]
span = (max(failed) - min(failed)) if failed else 0
print(f"failed requests: {len(failed)}, failure span: {span} ms, after the renewal: {after}")
sys.exit(0 if span <= 2000 and len(failed) <= 3 and after == ["204"] * 5 else 1)
PY
[ "$renewed" = '{"code":"renewed","reloaded":true}' ] || fail "renew-certificate: $renewed"
[ "$(served_leaf)" != "$before_leaf" ] || fail "Caddy still serves the old certificate"
again="$(printf '{"run_id":"renewal-%s-proof5"}' "$(date -u +%Y%m%dT%H%M%SZ)" | "${engine[@]}" renew-certificate)"
[ "$again" = '{"code":"not_due","reloaded":false}' ] || fail "second renew-certificate: $again"
docker exec "$machine" stat -c '%n %u:%g %a' /etc/slateops/tls/server.key | grep -q ' 1000:1000 600$' \
    || fail "the renewed key is not Caddy's"
# 5. Backups by the runner (W10b-1, W10b-2) -------------------------------------------------
project="$(docker exec "$machine" python3 -c 'import json; print(json.load(open("/var/lib/slateops/installation.json"))["project"])')"
db="$(docker exec "$machine" docker ps --filter "label=com.docker.compose.project=$project" \
    --filter label=com.docker.compose.service=db --format '{{.Names}}')"
make_due() {  # test only: the daily schedule falls due now (one statement, as the superuser)
    docker exec "$machine" docker exec "$db" psql -h 127.0.0.1 -U supabase_admin -d postgres \
        -v ON_ERROR_STOP=1 -q -c "update public.backup_policies set next_due_at = now() - interval '1 minute'"
}
tick() { printf '{"run_id":"backup-%s-pr%04d"}' "$(date -u +%Y%m%dT%H%M%SZ)" "$1" | "${engine[@]}" tick || true; }
ready() { docker exec "$machine" curl --fail --silent --max-time 10 "${tls[@]}" -o /dev/null "https://$host/api/ready"; }
backup_status() { status_json | python3 -c 'import json,sys; print(json.load(sys.stdin)["backup"])'; }

log "a scheduled backup with the target folder present"
make_due
ticked="$(tick 6)"; echo "$ticked"
[ "$(field runner <<<"$ticked")" = succeeded ] || fail "the scheduled backup did not succeed: $ticked"
[ "$(backup_status)" = ok ] || fail "status does not report the backup target as ok"
ready || fail "the services are not ready after the scheduled backup"

log "a scheduled backup with the target folder missing (the drive is pulled)"
docker exec "$machine" umount /var/lib/slateops/backup/repository
docker exec "$machine" mv /srv/proof-drives/E /srv/proof-drives/E-pulled
make_due
ticked="$(tick 7)"; echo "$ticked"
[ "$(field runner <<<"$ticked")" = backup_failed ] || fail "a missing target did not give backup_failed: $ticked"
[ "$(backup_status)" = backup_target_missing ] || fail "status does not report backup_target_missing"
for attempt in 8 9 10; do
    ready && break
    sleep 60
    tick "$attempt"
done
ready || fail "the services did not come back after the failed backup (plan 8.1)"
docker exec "$machine" mv /srv/proof-drives/E-pulled /srv/proof-drives/E
ticked="$(tick 11)"; echo "$ticked"
[ "$(backup_status)" = ok ] || fail "the target was not mounted again when it came back"
log "the next scheduled backup succeeds with no person (the drive is back)"
make_due
ticked="$(tick 12)"; echo "$ticked"
[ "$(field runner <<<"$ticked")" = succeeded ] || fail "the backup after the drive came back did not succeed: $ticked"
ready || fail "the services are not ready after the backup"
# 6. Update, rollback and the package night (W13b, TASK-0095) -----------------------------
# The plan proves W13b with two test builds. One build cannot sign a second version (the
# cosign identity names the tag), so after a real `receive` refusal of a changed manifest the
# proof makes the next two versions from this build, test only, and writes them where
# `receive` keeps a verified release: the server image committed with a new version label
# (and, for the first, the old SLATEOPS_VERSION, so step 10 fails after the migration ran),
# the Caddy image tagged again, the engine bundle with a new engine/VERSION, and the manifest
# with those digests and SHA-256 values. It proves the engine's steps, the rollback and the
# resume rule on a real Docker daemon; it does not prove a second signed release, a schema
# change between releases, or low space (unit tests: test_update.py).
[[ "$version" =~ ^([0-9]+\.[0-9]+\.[0-9]+)-rc\.([0-9]+)$ ]] || fail "the update proof needs an rc version"
bad="${BASH_REMATCH[1]}-rc.$((BASH_REMATCH[2] + 1))"
good="${BASH_REMATCH[1]}-rc.$((BASH_REMATCH[2] + 2))"
now() { date -u +%Y%m%dT%H%M%SZ; }
update_to() { printf '{"run_id":"%s","version":"%s"}' "$1" "$2" | "${engine[@]}" update; }
installation() { docker exec "$machine" python3 -c 'import json,sys; print(json.load(open("/var/lib/slateops/installation.json"))[sys.argv[1]])' "$1"; }
service_of() {
    docker exec "$machine" docker ps --filter "label=com.docker.compose.project=$1" \
        --filter "label=com.docker.compose.service=$2" --format '{{.Names}}'
}
admins() {
    docker exec "$machine" docker exec "$(service_of "$1" db)" psql -h 127.0.0.1 -U supabase_admin \
        -d postgres -tA -c "select count(*) from auth.users where email = '$admin'"
}
origin() {  # the origin and name lines (URLs, no secret) of the two env files, as one hash
    docker exec "$machine" sh -c "grep -h -E '^(SITE_URL|API_EXTERNAL_URL|PUBLIC_ORIGIN|SUPABASE_AUTH_ISSUER)=' /etc/slateops/provider.env /etc/slateops/app.env | sha256sum"
}
journal_state() {
    docker exec "$machine" python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["state"])' \
        "/var/lib/slateops/update/$1.json"
}
make_release() {  # test only: version $1 from this build; its api reports version $2
    docker exec -i "$machine" python3 -I - "$version" "$1" "$2" <<'PY'
import gzip, hashlib, io, json, subprocess, sys, tarfile
from pathlib import Path
old, new, reported = sys.argv[1:4]
kept = Path("/var/lib/slateops/release")
manifest = json.loads((kept / old / "release-manifest.json").read_text())
def run(*argv):
    return subprocess.run(argv, check=True, capture_output=True, text=True).stdout.strip()
def name(role):
    return manifest["images"][role]["ref"].split("@")[0].rsplit(":", 1)[0]
container = run("docker", "create", "--pull", "never", f"{name('server')}:{old}")
try:
    run("docker", "commit", "--change", f"ENV SLATEOPS_VERSION={reported}", "--change",
        f"LABEL org.opencontainers.image.version={new}", container, f"{name('server')}:{new}")
finally:
    run("docker", "rm", container)
run("docker", "tag", f"{name('caddy')}:{old}", f"{name('caddy')}:{new}")
for role in ("server", "caddy"):
    found = run("docker", "image", "inspect", "--format", "{{.Id}}", f"{name(role)}:{new}")
    manifest["images"][role]["ref"] = f"{name(role)}:{new}@{found}"
packed = io.BytesIO()
with tarfile.open(kept / old / f"slateops-engine-{old}.tar.gz") as source, \
        tarfile.open(fileobj=packed, mode="w", format=tarfile.PAX_FORMAT) as target:
    for member in source.getmembers():
        data = source.extractfile(member).read() if member.isfile() else None
        if member.name == "engine/VERSION":
            data = f"{new}\n".encode()
            member.size = len(data)
        target.addfile(member, None if data is None else io.BytesIO(data))
bundle = gzip.compress(packed.getvalue(), mtime=0)
folder = kept / new
folder.mkdir(mode=0o700)
archive = f"slateops-engine-{new}.tar.gz"
(folder / archive).write_bytes(bundle)
manifest["version"] = new
manifest["engine_bundle"].update(archive=archive, sha256=hashlib.sha256(bundle).hexdigest(),
                                 size=len(bundle))
(folder / "release-manifest.json").write_text(json.dumps(manifest))
print(f"test-only release {new}: server {manifest['images']['server']['ref']}")
PY
}

log "a manifest changed after signing is refused by receive (W13b-6)"
changed="$output/changed-payload"
mkdir -p "$changed"
for part in "${parts[@]}"; do ln -sf "$(cd "$payload" && pwd)/$part" "$changed/$part"; done
rm "$changed/release-manifest.json"
python3 - "$payload/release-manifest.json" "$changed/release-manifest.json" <<'PY'
import json, sys
manifest = json.load(open(sys.argv[1]))
manifest["migration_notes"] = "changed after signing"
json.dump(manifest, open(sys.argv[2], "w"))
PY
printf '{"run_id":"update-%s-proof6","setup_version":"%s"}' "$(now)" "$version" > "$changed/request.json"
refused="$(tar --dereference --format=ustar -C "$changed" -cf - request.json "${parts[@]}" | "${engine[@]}" receive || true)"
echo "$refused"
[ "$(field code <<<"$refused")" = manifest_signature_invalid ] || fail "a changed manifest was not refused: $refused"

log "an update whose api reports the old version rolls back by restore (W13b-2, W13b-9)"
make_release "$bad" "$version"
origin_before="$(origin)"
[ "$(admins "$project")" = 1 ] || fail "the administrator is missing before the update"
first="update-$(now)-proof7"
rolled="$(update_to "$first" "$bad" || true)"; echo "$rolled"
[ "$(field code <<<"$rolled")" = api_version_mismatch ] && [ "$(field update <<<"$rolled")" = rolled_back ] \
    || fail "the failed update did not roll back: $rolled"
restored="$(installation project)"
[ "$restored" = "$project-r1" ] || fail "the rollback did not start $project-r1: $restored"
[ "$(installation version)" = "$version" ] || fail "the rollback did not keep version $version"
[ -z "$(docker exec "$machine" docker ps --all --quiet --filter "label=com.docker.compose.project=$project")" ] \
    || fail "a container of the failed project remains"
[ -z "$(docker exec "$machine" docker network ls --quiet --filter "label=com.docker.compose.project=$project")" ] \
    || fail "a network of the failed project remains (plan 7.5 step 1)"
[ -n "$(docker exec "$machine" docker volume ls --quiet --filter "label=com.docker.compose.project=$project")" ] \
    || fail "the failed project's volumes are gone"
ready || fail "the restored installation is not ready on the same name and CA"
[ "$(origin)" = "$origin_before" ] || fail "the rollback changed the origin or the name"
[ "$(admins "$restored")" = 1 ] || fail "the data is not intact after the rollback"
[ "$(journal_state "$first")" = rolled_back ] || fail "the update journal is not closed as rolled_back"
db="$(service_of "$restored" db)"
make_due
ticked="$(tick 13)"; echo "$ticked"
[ "$(field code <<<"$ticked")" = ran ] || fail "a tick after the rollback did not run the runner: $ticked"
[ "$(field runner <<<"$ticked")" = succeeded ] || fail "the adopted backup policy did not run: $ticked"

log "a restart during the update's backup closes it with recover at the next tick (W13b-3, W13b-7)"
make_release "$good" "$good"
killed="update-$(now)-proof8"
update_to "$killed" "$good" > "$output/killed-update.json" 2>&1 &
updating=$!
for _ in $(seq 1 300); do
    [ -n "$(docker exec "$machine" docker ps --quiet --filter name=slateops-runner)" ] && break
    sleep 1
done
[ -n "$(docker exec "$machine" docker ps --quiet --filter name=slateops-runner)" ] || fail "the update's backup did not start"
docker exec "$machine" python3 -I -c '
import os, signal
for pid in filter(str.isdigit, os.listdir("/proc")):
    try:
        words = open(f"/proc/{pid}/cmdline", "rb").read().split(b"\0")
    except OSError:
        continue
    if any(word.endswith(b"slateops-engine") for word in words) and b"update" in words:
        os.kill(int(pid), signal.SIGKILL)
        print("killed the update, process", pid)'
wait "$updating" || true
[ "$(status_json | field engine_idle)" = False ] || fail "engine_idle is true while an update is open"
ticked="$(tick 14)"; echo "$ticked"
[ "$(field code <<<"$ticked")" = update_closed ] && [ "$(field update <<<"$ticked")" = failed ] \
    || fail "the interrupted update was not closed by recover: $ticked"
[ "$(journal_state "$killed")" = failed ] || fail "the interrupted update's journal is not failed"
ready || fail "the services are not ready after recover"
[ "$(installation project)" = "$restored" ] || fail "recover changed the project (a restore ran)"
[ "$(docker exec "$machine" docker exec "$(service_of "$restored" api)" printenv SLATEOPS_VERSION)" = "$version" ] \
    || fail "after recover the api does not run version $version"

log "the update to $good runs every step; the api reports $good and the data stays (W13b-1)"
updated="$(update_to "update-$(now)-proof9" "$good")" || fail "update: $updated"
echo "$updated"
[ "$(field code <<<"$updated")" = updated ] || fail "update: $updated"
[ "$(installation version)" = "$good" ] && [ "$(installation project)" = "$restored" ] \
    || fail "installation.json does not name $good on $restored"
[ "$(docker exec "$machine" docker exec "$(service_of "$restored" api)" printenv SLATEOPS_VERSION)" = "$good" ] \
    || fail "the api does not report $good"
[ "$(admins "$restored")" = 1 ] || fail "the data did not stay"
ready || fail "the updated installation is not ready"
[ "$(docker exec "$machine" readlink /usr/local/bin/slateops-engine)" = "/opt/slateops/engine/$good/slateops-engine" ] \
    || fail "the engine command does not run the $good bundle"
db="$(service_of "$restored" db)"
make_due
ticked="$(tick 15)"; echo "$ticked"
[ "$(field runner <<<"$ticked")" = succeeded ] || fail "the first backup after the update did not succeed (C-2): $ticked"

log "the package night upgrades from the security repository and leaves the services ready (W13b-8)"
night="$(printf '{"run_id":"package-night-%s-proof0"}' "$(now)" | "${engine[@]}" package-night)" \
    || fail "package-night: $night"
echo "$night"
[ "$(field result <<<"$night")" = ok ] || fail "the package night did not finish: $night"
ready || fail "the services are not ready after the package night"
log "passed: receive, prefetch, install without email, HTTPS /api/ready, trust routes, WebSocket, password sign-in, email_not_configured, rerun without change, set-email, password reset mail, renewal, backups, update refusal, rollback, recover after a restart, update, package night"
