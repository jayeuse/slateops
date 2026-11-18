"""The engine's provisioning job (plan 6.2 step 8): plan order, safe JSON, exits 0, 2 and 3,
and redacted, capped child output in the log (plan 10.1 item 3, 10.6)."""

import base64
import json
import os
import secrets
import subprocess
import sys
import time
from collections.abc import Sequence
from pathlib import Path

import pytest

from operations.install import joblog, provisioning
from operations.install.provisioning import ChildResult

BACKEND = Path(provisioning.__file__).resolve().parents[2]
PLAN_ORDER = [
    ("roles", [sys.executable, str(BACKEND / "operations/provision_database_role.py"),
               "--confirm"]),
    ("migrate", [sys.executable, "-m", "alembic", "upgrade", "head"]),
    ("check", [sys.executable, "-m", "alembic", "check"]),
    ("storage", [sys.executable, str(BACKEND / "operations/provision_storage.py"), "--confirm"]),
]
MIB = 1024 * 1024
# Seeded secrets are made at run time, so no secret-shaped literal sits in the source
# (the repository secret scan stays meaningful without allowlist entries).
ENV_SECRET = "envsecret-" + secrets.token_hex(6)
OWNER_PASSWORD = "ownerpw-" + secrets.token_hex(6)
URL_PASSWORD = "urlpw-" + secrets.token_hex(6)


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


TOKEN = ".".join(
    _b64url(part)
    for part in (b'{"alg":"HS256"}', b'{"role":"service_role"}', secrets.token_bytes(16))
)
KEY_BODY = base64.b64encode(secrets.token_bytes(36)).decode()
BEGIN = "-----BEGIN "
END = "-----END "
QUOTED_SECRET = 'smtp"pass\\word-55'
HELD = {
    "SUPABASE_SECRET_KEY": ENV_SECRET,
    "MIGRATION_DATABASE_URL": f"postgresql+psycopg://slateops_owner:{OWNER_PASSWORD}@db/x",
    "SMTP_PASS": QUOTED_SECRET,
    "POSTGRES_HOST": "db",
}


class _Children:
    """Record each child command; the step named in ``failing`` exits with ``status``."""

    def __init__(self, failing: str | None = None, status: int | None = 1) -> None:
        self.calls: list[tuple[list[str], float]] = []
        self.failing, self.status = failing, status

    def __call__(self, command: Sequence[str], cwd: Path, limit: float) -> ChildResult:
        assert cwd == BACKEND
        self.calls.append((list(command), limit))
        step = PLAN_ORDER[len(self.calls) - 1][0]
        return ChildResult(self.status if step == self.failing else 0, b"", b"", 0, 0)

    @property
    def commands(self) -> list[list[str]]:
        return [command for command, _limit in self.calls]


def _json_line(output: str) -> dict[str, str]:
    (line,) = output.splitlines()
    return json.loads(line)


def test_w5a_2_runs_the_four_steps_in_plan_order_and_prints_one_json_line(
    capsys: pytest.CaptureFixture[str],
) -> None:
    children = _Children()

    assert provisioning.main(["--confirm"], run_child=children) == 0

    assert children.commands == [command for _step, command in PLAN_ORDER]
    assert {limit for _command, limit in children.calls} == {900.0}
    assert _json_line(capsys.readouterr().out) == {"result": "provisioned"}


@pytest.mark.parametrize(("failing", "status", "code"), [
    pytest.param("roles", 1, "roles_failed", id="roles"),
    pytest.param("migrate", 1, "migration_failed", id="migrate"),
    pytest.param("check", 255, "schema_check_failed", id="check"),
    pytest.param("storage", -9, "storage_failed", id="storage-killed"),
    pytest.param("migrate", None, "step_timeout", id="migrate-timed-out"),
])
def test_w5a_2_the_first_failed_step_stops_the_job_with_its_step_and_code(
    capsys: pytest.CaptureFixture[str], failing: str, status: int | None, code: str,
) -> None:
    children = _Children(failing, status)

    assert provisioning.main(["--confirm", "--step-timeout", "30"], run_child=children) == 3

    steps = [step for step, _command in PLAN_ORDER]
    assert len(children.calls) == steps.index(failing) + 1
    assert {limit for _command, limit in children.calls} == {30.0}
    assert _json_line(capsys.readouterr().out) == {"step": failing, "code": code}


@pytest.mark.parametrize("arguments", [
    pytest.param([], id="no-confirmation"),
    pytest.param(["--confirm", "--step-timeout", "0"], id="no-time-limit"),
])
def test_w5a_2_it_refuses_before_any_step(
    capsys: pytest.CaptureFixture[str], arguments: list[str],
) -> None:
    children = _Children()

    assert provisioning.main(arguments, run_child=children) == 2

    assert children.calls == []
    assert _json_line(capsys.readouterr().out) == {"code": "invalid_input"}


def test_w5a_2_runs_as_a_python_module_from_the_backend_root() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "operations.install.provisioning"],
        cwd=BACKEND, capture_output=True, text=True, check=False, timeout=60,
    )

    assert result.returncode == 2
    assert _json_line(result.stdout) == {"code": "invalid_input"}


@pytest.mark.parametrize(("line", "hidden"), [
    pytest.param(f"connect failed for {ENV_SECRET}", ENV_SECRET, id="secret-env-value"),
    pytest.param(f"auth failed: {OWNER_PASSWORD}", OWNER_PASSWORD, id="password-from-env-url"),
    pytest.param(f"dsn postgresql://other:{URL_PASSWORD}@db:5432/postgres", URL_PASSWORD,
                 id="connection-string"),
    pytest.param(f"host=db user=x password={URL_PASSWORD} dbname=postgres", URL_PASSWORD,
                 id="libpq-keyword"),
    pytest.param(f"Authorization: Bearer {TOKEN}", TOKEN, id="bearer-jwt"),
    pytest.param(f"apikey sb_secret_{URL_PASSWORD}", URL_PASSWORD, id="opaque-supabase-key"),
    pytest.param(f"SMTP_PASS={URL_PASSWORD}", URL_PASSWORD, id="secret-name-line"),
    pytest.param(f"{BEGIN}PRIVATE KEY-----\n{KEY_BODY}\n{END}PRIVATE KEY-----", KEY_BODY,
                 id="private-key"),
    pytest.param(f"{BEGIN}EC PRIVATE KEY-----\n{KEY_BODY}", KEY_BODY,
                 id="unterminated-private-key"),
    pytest.param(f"{KEY_BODY}\n{END}PRIVATE KEY-----\nnext", KEY_BODY,
                 id="key-body-whose-begin-fell-before-the-window"),
    pytest.param(f'{{"password": "{URL_PASSWORD}", "user": "x"}}', URL_PASSWORD,
                 id="json-password"),
    pytest.param(f'{{"Client_Secret":"{URL_PASSWORD}"}}', URL_PASSWORD, id="json-secret"),
    pytest.param(f"  api_key: {URL_PASSWORD}", URL_PASSWORD, id="yaml-key"),
    pytest.param(f"  Access_Token: '{URL_PASSWORD}'", URL_PASSWORD, id="yaml-token"),
    pytest.param("blob " + base64.b64encode(ENV_SECRET.encode()).decode(),
                 base64.b64encode(ENV_SECRET.encode()).decode(), id="held-secret-base64"),
    pytest.param("body " + json.dumps(QUOTED_SECRET), json.dumps(QUOTED_SECRET)[1:-1],
                 id="held-secret-json-escaped"),
])
def test_d7_redaction_removes_held_secrets_and_secret_patterns(line: str, hidden: str) -> None:
    redacted = provisioning.redactor(HELD)(line)

    assert hidden not in redacted
    assert "[REDACTED]" in redacted


@pytest.mark.parametrize("line", [
    pytest.param("INFO  [alembic.runtime.migration] Running upgrade a1 -> b2, add index on db",
                 id="alembic"),
    pytest.param("KeyError: 'DATABASE_URL'", id="traceback-key-error"),
])
def test_d7_redaction_keeps_ordinary_text(line: str) -> None:
    assert provisioning.redactor(HELD)(line) == line


AT_HASH_PASSWORD = "pa@ss#wo" + "/rd-9x"


@pytest.mark.parametrize(("environ", "line"), [
    pytest.param(
        {"MIGRATION_DATABASE_URL":
         f"postgresql+psycopg://slateops_owner:{AT_HASH_PASSWORD}@db:5432/postgres"},
        f"auth failed for slateops_owner with {AT_HASH_PASSWORD} here",
        id="held-url-password-alone",
    ),
    pytest.param(
        HELD, f"dsn postgresql://other:{AT_HASH_PASSWORD}@db:5432/postgres", id="unheld-url",
    ),
])
def test_redaction_masks_a_database_password_with_at_and_hash(
    environ: dict[str, str], line: str,
) -> None:
    redacted = provisioning.redactor(environ)(line)

    for fragment in (AT_HASH_PASSWORD, "pa@ss", "ss#wo", "rd-9x"):
        assert fragment not in redacted
    assert "[REDACTED]" in redacted


@pytest.mark.parametrize(("unit", "count"), [
    pytest.param("a", MIB, id="letters"),
    pytest.param("a.", MIB // 2, id="dots"),
    pytest.param("x://", MIB // 4, id="url-runs"),
    pytest.param('"key": "', MIB // 8, id="open-quotes"),
    pytest.param("a@b.", MIB // 4, id="at-runs"),
])
def test_redaction_of_one_1_mib_line_finishes_in_one_pass(unit: str, count: int) -> None:
    # A hang guard, not a speed measure: rules that scan again from every position take
    # minutes to hours on these lines; a linear pass takes seconds.
    script = (
        "import sys\n"
        "from operations.install.redaction import redactor\n"
        "line = sys.argv[1] * int(sys.argv[2])\n"
        "print(len(redactor({'SUPABASE_SECRET_KEY': 'A' * 40})(line)))\n"
    )

    result = subprocess.run(
        [sys.executable, "-c", script, unit, str(count)],
        cwd=BACKEND, capture_output=True, text=True, check=True, timeout=60,
    )

    assert int(result.stdout) > 0


@pytest.mark.parametrize("unit", [
    pytest.param("eyJ-", id="token-starts-after-hyphens"),
    pytest.param("KEY", id="secret-word-repeated-without-equals"),
    pytest.param("PASS_", id="secret-word-with-underscores"),
])
def test_s85_1_a_64_kib_line_is_redacted_in_linear_time(unit: str) -> None:
    # Requested timing check (S85-1): these lines took 1.1 to 1.9 s at 64 KiB when the token
    # and KEY=value rules scanned again from every start; a linear pass takes milliseconds.
    line = unit * (64 * 1024 // len(unit))
    redact = provisioning.redactor(HELD)

    started = time.perf_counter()
    redact(line)

    assert time.perf_counter() - started < 0.5


UNHELD_SECRET = "Hx7" + "kPq2Lm9Rt4Wv8Zc1Nb6Qa5Ys3Ux0Jf"


def _logged(capsys: pytest.CaptureFixture[str], result: ChildResult) -> list[str]:
    """The child output lines that the job logs for one failing step."""

    def child(command: Sequence[str], cwd: Path, limit: float) -> ChildResult:
        return result

    assert provisioning.main(["--confirm"], run_child=child) == 3
    lines = capsys.readouterr().err.splitlines()
    return [line.split(" ", 4)[4] for line in lines if line.split(" ")[3] == "stdout"]


@pytest.mark.parametrize("status", [
    pytest.param(None, id="killed-at-the-time-limit"),
    pytest.param(1, id="failed"),
])
def test_w84_1_an_unfinished_last_line_is_not_logged(
    capsys: pytest.CaptureFixture[str], status: int | None,
) -> None:
    # The child printed half of a password with no newline, then hung or stopped.
    data = f"connecting\nretry with {UNHELD_SECRET[:16]}".encode()

    logged = _logged(capsys, ChildResult(status, data, b"", len(data), 0))

    assert logged == ["connecting"]


def test_w84_2_a_window_cut_drops_the_partial_first_line(
    capsys: pytest.CaptureFixture[str],
) -> None:
    # The kept window starts 22 characters before the end of an unheld secret.
    data = (UNHELD_SECRET[-22:] + "\nnext line\nlast line\n").encode()

    logged = _logged(capsys, ChildResult(1, data, b"", len(data) + 5000, 0))

    assert logged == ["next line", "last line"]


def test_d7_child_output_is_logged_redacted_and_capped_after_the_step_line(
    monkeypatch: pytest.MonkeyPatch, capfd: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("SUPABASE_SECRET_KEY", ENV_SECRET)
    monkeypatch.setenv("MIGRATION_DATABASE_URL",
                       f"postgresql+psycopg://slateops_owner:{OWNER_PASSWORD}@db:5432/postgres")
    noisy = [sys.executable, "-c", (
        "import sys\n"
        "sys.stdout.write('filler line\\n' * 120000)\n"
        f"print('dsn postgresql://other:{URL_PASSWORD}@db/postgres')\n"
        f"print('{BEGIN}PRIVATE KEY-----'); print('{KEY_BODY}')\n"
        f"print('{END}PRIVATE KEY-----')\n"
        f"print('tail marker {ENV_SECRET}')\n"
        f"print('Traceback marker {OWNER_PASSWORD} {TOKEN}', file=sys.stderr)\n"
        "sys.exit(1)\n"
    )]
    monkeypatch.setattr(provisioning, "STEPS", (("roles", noisy),))

    assert provisioning.main(["--confirm"]) == 3

    output = capfd.readouterr()
    assert _json_line(output.out) == {"step": "roles", "code": "roles_failed"}
    for secret in (ENV_SECRET, OWNER_PASSWORD, URL_PASSWORD, KEY_BODY, TOKEN):
        assert secret not in output.out + output.err
    lines = output.err.splitlines()
    kinds = [line.split(" ", 4)[2:4] for line in lines]
    assert kinds[:2] == [["provision.roles", "info"], ["provision.roles", "error"]]
    child_stdout = [line for line in lines if line.split(" ")[3] == "stdout"]
    child_stderr = [line.split(" ", 4)[4] for line in lines if line.split(" ")[3] == "stderr"]
    assert child_stdout[-1].split(" ", 4)[4] == "tail marker [REDACTED]"
    written = sum(len(line.encode()) + 1 for line in child_stdout)
    assert written <= MIB
    assert child_stderr == ["Traceback marker [REDACTED] [REDACTED]"]
    assert any("stdout_bytes=1440" in line and f"kept_bytes={written}" in line for line in lines)


def test_d7_n4_cap_counts_the_bytes_written_after_escaping(
    monkeypatch: pytest.MonkeyPatch, capfd: pytest.CaptureFixture[str],
) -> None:
    # 700 KiB of control characters: each becomes four bytes when escaped in the log.
    controls = [sys.executable, "-c",
                "import sys\nsys.stdout.write(('\\x01' * 99 + '\\n') * 7168)\n"
                "print('last line')\nsys.exit(1)\n"]
    monkeypatch.setattr(provisioning, "STEPS", (("roles", controls),))

    assert provisioning.main(["--confirm"]) == 3

    lines = capfd.readouterr().err.splitlines()
    child_stdout = [line for line in lines if line.split(" ")[3] == "stdout"]
    assert child_stdout[-1].split(" ", 4)[4] == "last line"
    assert sum(len(line.encode()) + 1 for line in child_stdout) <= MIB


def test_d7_a_hanging_step_is_ended_with_step_timeout(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path,
) -> None:
    pid_file, later_marker = tmp_path / "child.pid", tmp_path / "later-step-ran"
    hang = [sys.executable, "-c",
            f"import os, signal; open({str(pid_file)!r}, 'w').write(str(os.getpid())); "
            "print('waiting', flush=True); signal.pause()"]
    later = [sys.executable, "-c", f"open({str(later_marker)!r}, 'w').write('ran')"]
    monkeypatch.setattr(provisioning, "STEPS", (("migrate", hang), ("check", later)))

    assert provisioning.main(["--confirm", "--step-timeout", "5"]) == 3

    assert _json_line(capsys.readouterr().out) == {"step": "migrate", "code": "step_timeout"}
    assert not later_marker.exists()
    with pytest.raises(ProcessLookupError):
        os.kill(int(pid_file.read_text()), 0)


@pytest.mark.parametrize(("run_id", "printed"), [
    pytest.param("install-20261116T175200Z-a1b2c3", "install-20261116T175200Z-a1b2c3",
                 id="valid"),
    pytest.param("install x\nforged line", "-", id="unsafe"),
    pytest.param(None, "-", id="absent"),
])
def test_w5a_5_log_lines_carry_the_run_id_only_when_it_is_safe(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
    run_id: str | None, printed: str,
) -> None:
    if run_id is None:
        monkeypatch.delenv("SLATEOPS_RUN_ID", raising=False)
    else:
        monkeypatch.setenv("SLATEOPS_RUN_ID", run_id)

    assert provisioning.main(["--confirm"], run_child=_Children("check")) == 3

    lines = capsys.readouterr().err.splitlines()
    assert [line.split(" ")[1:5] for line in lines] == [
        [printed, "provision.roles", "info", "start"],
        [printed, "provision.roles", "info", "ok"],
        [printed, "provision.migrate", "info", "start"],
        [printed, "provision.migrate", "info", "ok"],
        [printed, "provision.check", "info", "start"],
        [printed, "provision.check", "error", "schema_check_failed"],
    ]


def test_d7_a_logged_text_cannot_forge_or_hide_log_lines(
    capsys: pytest.CaptureFixture[str],
) -> None:
    forged = "fails\n2026-11-16T00:00:00Z - forged\r\x1b[2J\x85\x9b2J\u2028x\u2029\tend"

    joblog.log_line("provision.roles", "stderr", forged)

    (line,) = capsys.readouterr().err.splitlines()
    assert line.split(" ", 4)[4] == (
        "fails\\x0a2026-11-16T00:00:00Z - forged\\x0d\\x1b[2J\\x85\\x9b2J\\u2028x\\u2029\tend"
    )
