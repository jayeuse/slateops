#!/bin/sh
# setup-base.sh - first configuration of the SlateOpsBootTest distribution (run as root).
# Writes /etc/wsl.conf. The new settings take effect after "wsl --terminate", which
# svc-exec.ps1 runs next.
#   [boot] systemd=true          Docker Engine runs as a systemd service.
#   [user] default=root          The imported distribution has no other user.
#   [interop] enabled=false      Linux cannot start Windows programs (server, not desktop).
#   [interop] appendWindowsPath  No Windows folders in the Linux PATH.
# Automount stays on: the setup job reads the kit from /mnt/c.
set -eu

cat > /etc/wsl.conf <<'EOF'
# Written by the Slate Operations boot-test kit (setup-base.sh).
[boot]
systemd=true

[user]
default=root

[interop]
enabled=false
appendWindowsPath=false
EOF
chmod 0644 /etc/wsl.conf

. /etc/os-release
echo "Distribution: ${PRETTY_NAME} (Debian $(cat /etc/debian_version))"
echo "Wrote /etc/wsl.conf:"
cat /etc/wsl.conf
