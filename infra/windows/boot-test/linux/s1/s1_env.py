#!/usr/bin/env python3
"""s1_env.py - private files and safe reports for the P1 measurement stack (S1).

Python standard library only. s1.sh runs it as root inside the distribution.

Commands:
  write-env  ROOT HOST PORT BIND GATEWAY_PORT [APP_SUBNET]
      Reads ROOT/private/keys.env (written by backend/operations/supabase_keys.py in a
      one-shot container), adds the values that supabase_keys.py does not make, and writes
      the owner-only files provider.env, app.env, provision.env and restic-password.
      Never overwrites an existing file. Prints names and counts only.
  backup-config ROOT MARKER
      Writes a new version-3 backup config for one manual offline backup run.
  redact ROOT FILE
      Prints FILE with every generated secret value replaced by [REDACTED].
  scan ROOT FILE...
      Counts generated secret values in each FILE. Prints counts only; exit 1 on a hit.
  report ROOT
      Prints one safe JSON document with the measurements (no secret values).

Throwaway secrets: the stack is a measurement stack with test data only. The values never
leave Linux: they are written only under ROOT/private (root, 0700/0600).
"""

from __future__ import annotations

import json
import os
import re
import secrets
import statistics
import sys
import time
from pathlib import Path

PROJECT = "slateops-s1"
SERVER_IMAGE = "slateops-s1-server:p1"
CADDY_IMAGE = "slateops-s1-caddy:p1"
# Names whose values are secrets. Every value of these names is redacted and scanned for.
SECRET_NAMES = {
    "POSTGRES_PASSWORD", "JWT_SECRET", "JWT_KEYS", "JWT_JWKS", "ANON_KEY", "SERVICE_ROLE_KEY",
    "ANON_KEY_ASYMMETRIC", "SERVICE_ROLE_KEY_ASYMMETRIC", "SUPABASE_PUBLISHABLE_KEY",
    "SUPABASE_SECRET_KEY", "SUPABASE_SESSION_ENCRYPTION_KEY", "PUBLICATION_SIGNING_KEY",
    "DASHBOARD_PASSWORD", "PG_META_CRYPTO_KEY", "REALTIME_TOKEN_SIGNING_KEY",
    "REALTIME_SECRET_KEY_BASE", "REALTIME_DB_ENC_KEY", "SECURITY_EVENT_SERVER_KEY",
    "S1_OWNER_PASSWORD", "S1_RUNTIME_PASSWORD", "S1_RESTIC_PASSWORD",
}
_LINE = re.compile(r"^([A-Z][A-Z0-9_]*)=(.*)$")


def _private_dir(root: Path) -> Path:
    return root / "private"


def read_env(path: Path) -> dict[str, str]:
    """Reads NAME=value or NAME='value' lines. Values never hold a single quote."""
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        match = _LINE.match(raw.strip())
        if not match:
            continue
        name, value = match.groups()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        values[name] = value
    return values


def _write_new(path: Path, text: str) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            output.write(text)
            output.flush()
            os.fsync(output.fileno())
    except BaseException:
        path.unlink(missing_ok=True)
        raise


def _literal(values: dict[str, str]) -> str:
    """Docker's literal KEY=value format: no quotes, no interpolation."""
    for name, value in values.items():
        if "\n" in value or "$" in value or "'" in value or " #" in value:
            raise SystemExit(f"value of {name} cannot be written in the literal format")
    return "".join(f"{name}={value}\n" for name, value in values.items())


def _quoted(values: dict[str, str]) -> str:
    """Compose --env-file format with single quotes (no interpolation inside)."""
    for name, value in values.items():
        if "\n" in value or "'" in value:
            raise SystemExit(f"value of {name} cannot be single-quoted")
    return "".join(f"{name}='{value}'\n" for name, value in values.items())


def _extra_secrets(private: Path) -> dict[str, str]:
    path = private / "extra.env"
    if not path.exists():
        values = {
            "SECURITY_EVENT_SERVER_KEY": secrets.token_urlsafe(32),
            "S1_OWNER_PASSWORD": secrets.token_urlsafe(32),
            "S1_RUNTIME_PASSWORD": secrets.token_urlsafe(32),
            "S1_RESTIC_PASSWORD": secrets.token_urlsafe(48),
            "S1_INSTANCE_ID": "slateops-s1-" + secrets.token_hex(4),
        }
        _write_new(path, _quoted(values))
    return read_env(path)


def write_env(root: Path, host: str, port: int, bind: str, gateway_port: int, subnet: str = "") -> None:
    private = _private_dir(root)
    keys = read_env(private / "keys.env")
    extra = _extra_secrets(private)
    instance = extra["S1_INSTANCE_ID"]
    origin = f"https://{host}" if port == 443 else f"https://{host}:{port}"
    issuer = f"{origin}/auth/v1"
    database = "db:5432/postgres"
    runtime_url = f"postgresql+psycopg://slateops_runtime:{extra['S1_RUNTIME_PASSWORD']}@{database}"
    provider = dict(keys)
    provider.update({
        "SLATEOPS_INSTANCE_ID": instance,
        "DASHBOARD_USERNAME": "operator",
        "API_EXTERNAL_URL": issuer,
        "SITE_URL": origin,
        "SUPABASE_PUBLIC_URL": f"http://127.0.0.1:{gateway_port}",
        "SUPABASE_API_PORT": str(gateway_port),
        "AUTH_TEMPLATE_BASE_URL": "http://api:8000/api/auth/email-templates",
        # Placeholder SMTP: readiness checks only that the values exist. No mail is sent.
        "SMTP_ADMIN_EMAIL": "s1-noreply@example.invalid",
        "SMTP_HOST": "smtp.example.invalid",
        "SMTP_PORT": "587",
        "SMTP_USER": "",
        "SMTP_PASS": "",
        "SMTP_SENDER_NAME": "Slate Operations S1",
        "SLATEOPS_SERVER_IMAGE": SERVER_IMAGE,
        "SLATEOPS_CADDY_IMAGE": CADDY_IMAGE,
        "SLATEOPS_APP_ENV_FILE": str(private / "app.env"),
        "SLATEOPS_LOG_ROOT": str(root / "logs"),
        "SLATEOPS_BACKUP_EXPORT_ROOT": str(root / "backup" / "backup-exports"),
        "CADDY_CONFIG_PATH": str(private / "Caddyfile"),
        "CADDY_TLS_DIR": str(private / "tls"),
        "CADDY_PUBLIC_BIND_HOST": bind,
        "CADDY_HTTPS_PORT": str(port),
        "API_WORKERS": "1",
    })
    if subnet:
        provider["SLATEOPS_APP_PRIVATE_SUBNET"] = subnet
    app = {
        "ENVIRONMENT": "production",
        "SLATEOPS_INSTANCE_ID": instance,
        "PUBLIC_ORIGIN": origin,
        "DATABASE_URL": runtime_url,
        "REALTIME_PUBLISH_URL": "http://api-gw:8001/realtime/v1/api/broadcast",
        "SUPABASE_PUBLISHABLE_KEY": keys["SUPABASE_PUBLISHABLE_KEY"],
        "SUPABASE_SECRET_KEY": keys["SUPABASE_SECRET_KEY"],
        "SUPABASE_SESSION_ENCRYPTION_KEY": keys["SUPABASE_SESSION_ENCRYPTION_KEY"],
        "PUBLICATION_SIGNING_KEY": keys["PUBLICATION_SIGNING_KEY"],
        "REALTIME_TOKEN_SIGNING_KEY": keys["REALTIME_TOKEN_SIGNING_KEY"],
        "SECURITY_EVENT_SERVER_KEY": extra["SECURITY_EVENT_SERVER_KEY"],
        "SUPABASE_TIMEOUT_SECONDS": "10",
        "AUTH_REFRESH_TOKEN_DAYS": "7",
        "LIFECYCLE_PURGE_ENABLED": "true",
        "SERVER_MAX_CONCURRENCY": "64",
        "SERVER_KEEP_ALIVE_SECONDS": "5",
        "REQUEST_BODY_MAX_BYTES": "1048576",
        "DATABASE_POOL_SIZE": "5",
        "DATABASE_MAX_OVERFLOW": "5",
        "DATABASE_POOL_TIMEOUT_SECONDS": "5",
        "DATABASE_CONNECT_TIMEOUT_SECONDS": "3",
        "DATABASE_STATEMENT_TIMEOUT_MS": "15000",
        "READINESS_POOL_TIMEOUT_SECONDS": "0.25",
        "READINESS_CONNECT_TIMEOUT_SECONDS": "1",
        "READINESS_STATEMENT_TIMEOUT_MS": "500",
        "READINESS_CALLER_TIMEOUT_SECONDS": "2",
    }
    provision = {
        "ENVIRONMENT": "production",
        "SLATEOPS_INSTANCE_ID": instance,
        "POSTGRES_HOST": "db",
        "POSTGRES_PORT": "5432",
        "POSTGRES_DATABASE": "postgres",
        "DATABASE_BOOTSTRAP_URL": f"postgresql+psycopg://supabase_admin:{keys['POSTGRES_PASSWORD']}@{database}",
        "MIGRATION_DATABASE_URL": f"postgresql+psycopg://slateops_owner:{extra['S1_OWNER_PASSWORD']}@{database}",
        "DATABASE_URL": runtime_url,
        "SUPABASE_URL": "http://api-gw:8000",
        "SUPABASE_AUTH_ISSUER": issuer,
        "SUPABASE_SECRET_KEY": keys["SUPABASE_SECRET_KEY"],
    }
    written = []
    for name, text in (
        ("provider.env", _quoted(provider)),
        ("app.env", _literal(app)),
        ("provision.env", _literal(provision)),
        ("restic-password", extra["S1_RESTIC_PASSWORD"] + "\n"),
    ):
        path = private / name
        if path.exists():
            continue
        _write_new(path, text)
        written.append(name)
    print(f"private files written: {', '.join(written) if written else 'none (all existed)'}; "
          f"instance {instance}; no secret values printed")


def backup_config(root: Path, marker: Path) -> None:
    private = _private_dir(root)
    config = {
        "version": 3,
        "installation_id": read_env(private / "extra.env")["S1_INSTANCE_ID"],
        "project_name": PROJECT,
        "deployment": "production",
        "compose_root": str(root / "src" / "infra" / "supabase"),
        "provider_env_file": str(private / "provider.env"),
        "app_env_file": str(private / "app.env"),
        "caddy_config_file": str(private / "Caddyfile"),
        "tls_directory": str(private / "tls"),
        "restic_repository": str(root / "backup" / "restic-repository"),
        "restic_password_file": str(private / "restic-password"),
        "staging_directory": str(root / "backup" / "staging"),
        "completion_marker": str(marker),
    }
    path = private / f"backup-config-{marker.stem}.json"
    _write_new(path, json.dumps(config, indent=2) + "\n")
    print(path)


def secret_values(root: Path) -> list[str]:
    private = _private_dir(root)
    found: set[str] = set()
    for name in ("keys.env", "extra.env"):
        path = private / name
        if path.exists():
            for key, value in read_env(path).items():
                if (key in SECRET_NAMES or key.startswith("S1_")) and len(value) >= 8:
                    if key != "S1_INSTANCE_ID":
                        found.add(value)
    # A JSON key set also carries its parts; redact each long JSON string value too.
    for value in list(found):
        if value.startswith(("{", "[")):
            for part in re.findall(r'"([^"]{16,})"', value):
                found.add(part)
    return sorted(found, key=len, reverse=True)


def redact(root: Path, path: Path) -> None:
    text = path.read_text(encoding="utf-8", errors="replace")
    for value in secret_values(root):
        text = text.replace(value, "[REDACTED]")
    sys.stdout.write(text)


def scan(root: Path, paths: list[Path]) -> int:
    values = secret_values(root)
    hits = 0
    for path in paths:
        text = path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""
        count = sum(text.count(value) for value in values)
        hits += count
        print(f"secret scan: {path}: {count} hit(s), {len(values)} values checked")
    return 1 if hits else 0


# ---------------------------------------------------------------------------
# Measurements report
# ---------------------------------------------------------------------------

def _read_json(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _samples(path: Path) -> list[tuple[float, int, int]]:
    rows = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return rows
    for line in lines:
        parts = line.split(",")
        if len(parts) < 3 or not parts[0].replace(".", "", 1).isdigit():
            continue
        try:
            rows.append((float(parts[0]), int(parts[1]), int(parts[2])))
        except ValueError:
            continue
    return rows


def _used_mib(row: tuple[float, int, int]) -> float:
    return round((row[1] - row[2]) / 1024, 1)


def _window(rows: list[tuple[float, int, int]], start: float, end: float) -> dict[str, object]:
    chosen = [row for row in rows if start <= row[0] <= end]
    if not chosen:
        return {"samples": 0}
    used = [_used_mib(row) for row in chosen]
    return {
        "samples": len(chosen),
        "used_mib_max": max(used),
        "used_mib_median": round(statistics.median(used), 1),
        "mem_total_mib": round(chosen[0][1] / 1024, 1),
    }


def report(root: Path) -> None:
    measure = root / "measure"
    state = root / "state"
    result: dict[str, object] = {"generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    result["install"] = _read_json(state / "install-timings.json")
    result["sizes"] = _read_json(state / "sizes.json")
    result["idle"] = {path.stem[len("idle-"):]: _read_json(path) for path in sorted(state.glob("idle-*.json"))}
    ports: list[dict[str, str]] = []
    try:
        for line in (state / "ports.txt").read_text(encoding="utf-8").splitlines():
            name, _, mapping = line.partition("\t")
            if name:
                ports.append({"name": name, "ports": mapping})
    except OSError:
        pass
    result["containers"] = ports
    boots = []
    for ready_file in sorted(measure.glob("ready-*.json")):
        ready = _read_json(ready_file)
        if not isinstance(ready, dict):
            continue
        boot_id = str(ready.get("boot_id", ""))
        rows = _samples(measure / f"mem-{boot_id}.csv")
        btime = float(ready.get("linux_boot_epoch") or 0)
        ready_at = ready.get("ready_epoch")
        entry = dict(ready)
        if isinstance(ready_at, (int, float)) and btime:
            entry["startup_memory"] = _window(rows, btime, float(ready_at) + 120)
            entry["linux_boot_to_ready_seconds"] = round(float(ready_at) - btime, 1)
        boots.append(entry)
    result["boots"] = boots
    backups = []
    for backup_file in sorted(state.glob("backup-*.json")):
        backup = _read_json(backup_file)
        if isinstance(backup, dict):
            rows = _samples(measure / f"mem-{backup.get('boot_id', '')}.csv")
            started, ended = backup.get("stop_started_epoch"), backup.get("ingress_ready_epoch")
            if isinstance(started, (int, float)) and isinstance(ended, (int, float)):
                backup["memory_during_backup"] = _window(rows, float(started), float(ended))
            backups.append(backup)
    result["backups"] = backups
    result["restore_timing"] = _read_json(state / "restore-timing.json")
    result["windows_facts"] = _read_json(Path("/var/lib/slateops-boottest/host/windows.json"))
    print(json.dumps(result, sort_keys=True))


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        print(__doc__)
        return 2
    command, root = argv[1], Path(argv[2])
    if command == "write-env" and len(argv) in (7, 8):
        write_env(root, argv[3], int(argv[4]), argv[5], int(argv[6]), argv[7] if len(argv) == 8 else "")
        return 0
    if command == "backup-config" and len(argv) == 4:
        backup_config(root, Path(argv[3]))
        return 0
    if command == "redact" and len(argv) == 4:
        redact(root, Path(argv[3]))
        return 0
    if command == "scan" and len(argv) >= 4:
        return scan(root, [Path(item) for item in argv[3:]])
    if command == "report" and len(argv) == 3:
        report(root)
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
