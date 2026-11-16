#!/bin/sh
# index.cgi - BusyBox httpd answers "/" with this script. It returns the last status.json
# from the heartbeat container, plus its age, so a phone browser shows at a glance whether
# the heartbeat is current.
# "fresh": true means both: a heartbeat in the last 150 s, and that heartbeat was written in
# the current Linux boot (so a status file left from before a restart never counts as fresh).
now="$(date -u +%s)"
served_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
network="${BOOTTEST_WEB_NETWORK:-unknown}"
boot_now="$(cat /proc/sys/kernel/random/boot_id 2>/dev/null)"
printf 'Content-Type: application/json\r\nCache-Control: no-store\r\n\r\n'
if [ -s /status/status.json ]; then
    generated="$(sed -n 's/.*"generated_epoch" *: *\([0-9][0-9]*\).*/\1/p' /status/status.json)"
    boot_status="$(sed -n 's/.*"linux_boot_id" *: *"\([0-9a-f-]*\)".*/\1/p' /status/status.json)"
    age=$(( now - ${generated:-0} ))
    same_boot=false
    if [ -n "$boot_now" ] && [ "$boot_status" = "$boot_now" ]; then same_boot=true; fi
    fresh=false
    if [ "$age" -le 150 ] && [ "$same_boot" = true ]; then fresh=true; fi
    printf '{"fresh":%s,"status_age_seconds":%s,"same_linux_boot":%s,"served_at":"%s","web_network":"%s","status":' \
        "$fresh" "$age" "$same_boot" "$served_at" "$network"
    cat /status/status.json
    printf '}\n'
else
    printf '{"fresh":false,"status_age_seconds":null,"same_linux_boot":false,"served_at":"%s","web_network":"%s","status":null}\n' \
        "$served_at" "$network"
fi
