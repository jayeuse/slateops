#!/bin/bash
# heartbeat.sh - writes one heartbeat row to PostgreSQL every interval and publishes a
# small status document (status.json) for the web service.
#
# Runs in the "heartbeat" container (postgres image, uid 999). On any error it exits, and
# Docker restarts the container (restart: unless-stopped). Rows are never deleted, so the
# count and the first heartbeat show that data survived each boot event.
set -euo pipefail

interval="${HEARTBEAT_INTERVAL_SECONDS:-60}"
PGPASSWORD="$(cat /run/secrets/pg_password)"
export PGPASSWORD
container_started_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

until pg_isready -q; do sleep 2; done

psql -X -q -v ON_ERROR_STOP=1 <<'SQL'
CREATE TABLE IF NOT EXISTS heartbeat (
    id            bigserial   PRIMARY KEY,
    at            timestamptz NOT NULL DEFAULT now(),
    linux_boot_id text        NOT NULL,
    windows_boot  jsonb       NOT NULL DEFAULT '{}'::jsonb
);
SQL

while :; do
    boot_id="$(cat /proc/sys/kernel/random/boot_id)"
    uptime_seconds="$(cut -d' ' -f1 /proc/uptime)"
    windows='{}'
    if [ -s /host/windows.json ]; then windows="$(cat /host/windows.json)"; fi

    psql -X -q -A -t -v ON_ERROR_STOP=1 \
        -v boot_id="$boot_id" \
        -v uptime="$uptime_seconds" \
        -v windows="$windows" \
        -v container_started_at="$container_started_at" \
        > /status/status.json.tmp <<'SQL'
INSERT INTO heartbeat (linux_boot_id, windows_boot) VALUES (:'boot_id', :'windows'::jsonb);
WITH ordered AS (
    SELECT at, extract(epoch FROM at - lag(at) OVER (ORDER BY id)) AS gap FROM heartbeat
), worst AS (
    SELECT gap, at FROM ordered WHERE gap IS NOT NULL ORDER BY gap DESC LIMIT 1
), totals AS (
    SELECT count(*) AS n, min(at) AS first_at, max(at) AS last_at FROM heartbeat
), outages AS (
    SELECT count(*) FILTER (WHERE gap > 120) AS n FROM ordered
)
SELECT json_build_object(
    'generated_epoch', floor(extract(epoch FROM now()))::bigint,
    'generated_at', to_char(now() AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"'),
    'heartbeat_count', totals.n,
    'first_heartbeat', to_char(totals.first_at AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"'),
    'last_heartbeat', to_char(totals.last_at AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"'),
    'largest_gap_seconds', round(coalesce(worst.gap, 0)::numeric, 0),
    'largest_gap_ended_at', to_char(worst.at AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"'),
    'gaps_over_120s', outages.n,
    'linux_boot_id', :'boot_id',
    'linux_uptime_seconds', round(:'uptime'::numeric, 0),
    'heartbeat_container_started_at', :'container_started_at',
    'postgres_started_at', to_char(pg_postmaster_start_time() AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"'),
    'windows', :'windows'::json
)
FROM totals CROSS JOIN outages LEFT JOIN worst ON true;
SQL
    mv -f /status/status.json.tmp /status/status.json
    sleep "$interval"
done
