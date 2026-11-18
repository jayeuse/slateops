"""``log-bundle`` and the seeded redaction test (plan 10.6, W5b-9; AC-L4, AC-L6, AC-L7).

Every seeded value is built at run time, so the repository secret scan sees no literal.
"""

from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import tarfile
from pathlib import Path
from typing import Any
from urllib.parse import quote, quote_plus

import pytest

from engine import log_bundle, report
from engine.core import Paths, private_dir
from engine.redaction import forms

from .helpers import Script, call, deps, make_paths, ok, progress_lines

REPORT_RUN = "report-20261117T120000Z-zz99yy"
OLD_RUN = "install-20261116T080000Z-aa11bb"

# Held secrets (as the engine would find them in /etc/slateops) and personal data.
EVENT_KEY = "Sx" + "Q2vN8pLr5TzW1mKc7YhD4fGb9JaE3uRo"
DB_PASSWORD = "Rt" + "9!pQ@w#Lz$2"
SMTP_PASSWORD = "app " + 'pass $1 "q"'
EMAIL = "maria.santos" + "@example.test"
USERNAME = "msantos" + "77"
WINDOWS_ACCOUNT = "JDela" + "cruz"
# Values found only by the patterns.
QUERY_TOKEN = "f1e2d3c4" + "b5a69788"
JWT = "eyJ" + "hbGciOiJFUzI1NiJ9.eyJzdWIiOiIxMjM0In0.c2lnbmF0dXJlLXZhbHVl"
JWK_D = "Vq" + "8sP3xL0kN6mZ2rT9wY5cB1aH7jU4eF"
BASIC = base64.b64encode(("admin:" + "Hunter" + "2Pass").encode()).decode()
COOKIE = "csrf" + "Zz8899aa"
URL_PASSWORD = "url" + "Pw7788kk"
# A key body line, built from short pieces so the secret scan sees no literal.
BODY_LINE = "".join(
    [
        "MIIEvQIB",
        "ADANBgkq",
        "hkiG9w0B",
        "AQEFAASC",
        "BKcwggSj",
        "AgEAAoIB",
        "AQC3sZ9y",
        "XcVb",
    ]
)
PEM_BEGIN = "-----BEGIN " + "PRIVATE KEY-----"
PEM_END = "-----END " + "PRIVATE KEY-----"


def _held(paths: Paths) -> None:
    private_dir(paths.etc / "new")
    (paths.etc / "app.env").write_text(
        f"SECURITY_EVENT_SERVER_KEY={EVENT_KEY}\n"
        f"DATABASE_URL=postgresql+psycopg://slateops_runtime:{DB_PASSWORD}@db:5432/postgres\n"
    )
    (paths.etc / "new/smtp.env").write_text(
        "SMTP_HOST=smtp.example.test\nSMTP_PORT=587\n"
        f'SMTP_ADMIN_EMAIL="{EMAIL}"\nSMTP_USER="{EMAIL}"\n'
        f'SMTP_PASS="{SMTP_PASSWORD.replace(chr(34), chr(92) + chr(34)).replace("$", "$$")}"\n'
        'SMTP_SENDER_NAME="Front Desk"\n'
    )
    private_dir(paths.state)
    paths.answers.write_text(json.dumps({"admin_email": EMAIL, "admin_username": USERNAME}))


def _provider_logs() -> dict[str, str]:
    """Real-shaped provider log lines that carry the seeded values."""
    event_key_b64 = base64.b64encode(EVENT_KEY.encode()).decode()
    return {
        "gotrue.log": "\n".join(
            [
                json.dumps(
                    {
                        "component": "api",
                        "level": "info",
                        "method": "POST",
                        "msg": "request completed",
                        "path": "/invite",
                        "remote_addr": "192.168.1.44",
                        "auth_event": {
                            "action": "user_invited",
                            "actor_username": USERNAME,
                            "traits": {"user_email": EMAIL},
                        },
                    }
                ),
                json.dumps({"level": "error", "msg": f"smtp auth failed for {SMTP_PASSWORD}"}),
                json.dumps({"level": "debug", "msg": "signing", "key": event_key_b64}),
            ]
        ),
        # The stack's Envoy format (infra/supabase/upstream/envoy/lds.template.yaml).
        "envoy.log": (
            "[17/Nov/2026:10:15:00 +0000] GET 303 0\n"
            f"debug: request headers: authorization: Basic {BASIC}\n"
            f"debug: forwarded secret {quote_plus(SMTP_PASSWORD)}\n"
        ),
        "postgres.log": (
            "2026-11-17 10:15:00.000 UTC [88] FATAL:  password authentication failed for user"
            ' "slateops_runtime"\n'
            f"2026-11-17 10:15:01.000 UTC [89] LOG:  dsn postgresql://slateops_owner:{URL_PASSWORD}"
            "@db:5432/postgres\n"
            f"2026-11-17 10:15:02.000 UTC [90] LOG:  statement: select '{DB_PASSWORD}'\n"
        ),
        "caddy.log": json.dumps(
            {
                "level": "info",
                "logger": "http.log.access",
                "msg": "handled request",
                "request": {
                    "remote_ip": "192.168.1.44",
                    "client_ip": "192.168.1.44",
                    "method": "GET",
                    "host": "frontdesk.local",
                    "uri": f"/auth/v1/verify?token={QUERY_TOKEN}&type=invite"
                    f"&email={quote(EMAIL, safe='')}",
                    "headers": {
                        "Cookie": [f"sb-access-token={JWT}; csrf={COOKIE}"],
                        "Authorization": [f"Bearer {JWT}"],
                    },
                },
                "status": 200,
            }
        )
        + "\n",
        "api.log": json.dumps(
            {
                "level": "error",
                "event": "jwk rejected",
                "detail": json.dumps({"kty": "EC", "crv": "P-256", "d": JWK_D}),
                "env": f"SECURITY_EVENT_SERVER_KEY={json.dumps(EVENT_KEY)[1:-1]}",
            }
        )
        + "\n",
        "realtime.log": (
            f"10:15:00.000 project=realtime external_id=realtime [info] socket opened"
            f" /realtime/v1/websocket?apikey={EVENT_KEY}&vsn=1.0.0\n"
        ),
        "wsl.log": f"mount failed for C:\\Users\\{WINDOWS_ACCOUNT}\\AppData\\Local\\Temp\n",
    }


def _cut_key_output() -> str:
    """More than 1 MiB of container output: the cap keeps the key body without its BEGIN."""
    return (
        "noise\n" * 2000
        + PEM_BEGIN
        + "\n"
        + (BODY_LINE + "\n") * 18000
        + PEM_END
        + "\nafter the key\n"
        + BODY_LINE
        + "\n"
        + PEM_BEGIN
        + "\n"
        + BODY_LINE
        + "\n"
    )


def _seed(paths: Paths) -> None:
    _held(paths)
    folder = private_dir(paths.logs / "install" / OLD_RUN)
    for name, text in _provider_logs().items():
        (folder / f"snapshot-1/logs-{name}").parent.mkdir(parents=True, exist_ok=True)
        (folder / f"snapshot-1/logs-{name}").write_text(text)
    (folder / "binary.log").write_bytes(b"\xff\xfe\x00 not text")
    report.record(paths, "time_sync", {"offset_seconds": 0.0001})


def _bundle(result: dict[str, Any]) -> dict[str, str]:
    data = base64.b64decode(result["bundle_base64"])
    assert hashlib.sha256(data).hexdigest() == result["bundle_sha256"]
    assert len(data) == result["bundle_size"]
    files: dict[str, str] = {}
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
        for member in tar.getmembers():
            file = tar.extractfile(member)
            assert file is not None
            files[member.name] = file.read().decode()
    return files


@pytest.fixture
def seeded(tmp_path: Path) -> tuple[Paths, dict[str, str], dict[str, Any]]:
    paths = make_paths(tmp_path)
    _seed(paths)
    script = Script(
        {
            ("docker", "ps"): ok("slateops-api-1\trunning\tUp\nslateops-db-1\trunning\tUp\n"),
            ("docker", "logs"): lambda argv: ok(
                _cut_key_output()
                if argv[-1] == "slateops-api-1"
                else _provider_logs()["postgres.log"]
            ),
            ("journalctl",): ok(f"wsl: mounted C:/Users/{WINDOWS_ACCOUNT}/Desktop\n"),
        }
    )
    code, result, _ = call(["log-bundle"], {"run_id": REPORT_RUN}, deps(paths, script))
    assert code == 0
    return paths, _bundle(result), result


def _seeded_values() -> list[str]:
    held = [EVENT_KEY, DB_PASSWORD, SMTP_PASSWORD, EMAIL, USERNAME]
    every_form = [form for value in held for form in forms(value) if len(form) >= 6]
    patterns = [WINDOWS_ACCOUNT, QUERY_TOKEN, JWT, JWK_D, BASIC, COOKIE, URL_PASSWORD, BODY_LINE]
    return [*every_form, *patterns, "192.168.1.44"]


def test_ac_l7_no_seeded_secret_or_personal_value_reaches_the_bundle(
    seeded: tuple[Paths, dict[str, str], dict[str, Any]],
) -> None:
    _, files, _ = seeded
    everything = "\n".join(files.values())

    found = [value for value in _seeded_values() if value in everything]

    assert found == []
    assert f"slateops/install/{OLD_RUN}/snapshot-1/logs-gotrue.log" in files
    assert f"slateops/report/{REPORT_RUN}/snapshot/logs-slateops-api-1.txt" in files
    assert "after the key" in everything
    assert "request completed" in everything


def test_ac_l6_the_index_lists_left_out_files_and_the_result_is_one_safe_json(
    seeded: tuple[Paths, dict[str, str], dict[str, Any]],
) -> None:
    _, files, result = seeded
    index = json.loads(files["bundle-index.json"])

    assert index["left_out"] == [
        {"file": f"slateops/install/{OLD_RUN}/binary.log", "reason": "not_text"}
    ]
    assert result["code"] == "bundle_ready"
    assert set(result) == {
        "code",
        "bundle_base64",
        "bundle_sha256",
        "bundle_size",
        "files",
        "left_out",
    }
    assert result["left_out"] == len(index["left_out"])
    assert "report.json" in files


def test_ac_l4_the_report_holds_safe_values_only(
    seeded: tuple[Paths, dict[str, str], dict[str, Any]],
) -> None:
    paths, files, _ = seeded

    data = json.loads(files["report.json"])

    assert set(data) == {"time_sync", "disk"}
    assert set(data["disk"]) == {"at", "total", "used", "free"}
    assert report.load(paths) == data


def test_ac_l6_files_past_the_limit_are_left_out_by_size(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = make_paths(tmp_path)
    _seed(paths)
    monkeypatch.setattr(log_bundle, "BUNDLE_LIMIT", 2000)

    code, result, _ = call(["log-bundle"], {"run_id": REPORT_RUN}, deps(paths, Script()))

    index = json.loads(_bundle(result)["bundle-index.json"])
    assert code == 0
    assert "size" in {item["reason"] for item in index["left_out"]}
    assert sum(len(text) for text in _bundle(result).values()) < 2000 + 4096


def test_s85_8_only_the_engine_log_kinds_are_read(tmp_path: Path) -> None:
    # /var/log/slateops/app belongs to UID 10001 (the API); the bundle never reads it.
    paths = make_paths(tmp_path)
    _seed(paths)
    app = paths.logs / "app" / "api"
    app.mkdir(parents=True)
    (app / "api.log").write_text("api line\n")
    stray = paths.logs / "unknown-kind" / OLD_RUN
    stray.mkdir(parents=True)
    (stray / "engine.log").write_text("stray line\n")

    code, result, _ = call(["log-bundle"], {"run_id": REPORT_RUN}, deps(paths, Script()))

    names = set(_bundle(result))
    assert code == 0
    assert not any(name.startswith(("slateops/app/", "slateops/unknown-kind/")) for name in names)
    assert f"slateops/install/{OLD_RUN}/snapshot-1/logs-gotrue.log" in names


def test_s85_8_a_file_swapped_for_a_symlink_or_fifo_after_listing_is_left_out(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = make_paths(tmp_path)
    _seed(paths)
    folder = paths.logs / "install" / OLD_RUN
    secret_file = paths.etc / "app.env"
    listed = log_bundle._candidates

    def swap_after_listing(ctx: Any) -> list[tuple[str, Path]]:
        found = listed(ctx)
        link, fifo = folder / "linked.log", folder / "fifo.log"
        link.symlink_to(secret_file)
        os.mkfifo(fifo)
        return [*found, (f"slateops/install/{OLD_RUN}/linked.log", link),
                (f"slateops/install/{OLD_RUN}/fifo.log", fifo)]

    monkeypatch.setattr(log_bundle, "_candidates", swap_after_listing)

    code, result, _ = call(["log-bundle"], {"run_id": REPORT_RUN}, deps(paths, Script()))

    index = json.loads(_bundle(result)["bundle-index.json"])
    left_out = {item["file"]: item["reason"] for item in index["left_out"]}
    assert code == 0
    assert left_out[f"slateops/install/{OLD_RUN}/linked.log"] == "not_regular"
    assert left_out[f"slateops/install/{OLD_RUN}/fifo.log"] == "not_regular"


def test_w14_d5_log_bundle_reports_each_step(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    paths = make_paths(tmp_path)

    code, _, _ = call(["log-bundle"], {"run_id": REPORT_RUN}, deps(paths, Script()))

    assert code == 0
    assert progress_lines(capsys.readouterr().err) == [
        "progress log-bundle 1/3 facts start",
        "progress log-bundle 2/3 snapshot start",
        "progress log-bundle 3/3 bundle start",
    ]
