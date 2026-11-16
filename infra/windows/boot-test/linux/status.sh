#!/bin/sh
# status.sh - prints the state of the distribution, Docker and the test stack (run as root).
# Read-only: it starts and changes nothing.
echo "== Linux"
echo "uptime_seconds: $(cut -d' ' -f1 /proc/uptime)"
echo "boot_id: $(cat /proc/sys/kernel/random/boot_id)"
echo "systemd: $(systemctl is-system-running 2>&1)"
echo "docker.service: $(systemctl is-active docker 2>&1)"
echo "== Disk and memory"
df -h / 2>&1
free -m 2>&1
echo "== Test stack"
docker compose --project-name slateops-boottest ps --all \
    --format 'table {{.Service}}\t{{.State}}\t{{.Status}}\t{{.Ports}}' 2>&1
echo "== Listening TCP ports in the WSL VM"
if command -v ss >/dev/null 2>&1; then ss -ltn 2>&1; else echo "ss is not installed"; fi
echo "== Inside check: http://127.0.0.1:8443/"
curl -fsS --max-time 5 http://127.0.0.1:8443/ 2>&1 || echo "(no answer inside the distribution)"
echo
