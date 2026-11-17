"""``install`` and ``resend-invitation`` (TASK-0086; plan 6.1, 6.2; W5b-1 logic, W5b-2, W5b-7).

A fake world stands in for Docker: the one-shot containers write what the real commands
write (the W2 generator, ``local_ca.py init``), Compose keeps per-project volumes and
started services, and bootstrap keeps invitation records. A kill is a ``BaseException`` raised
before or after a command's effect, as a power cut would stop the process.
"""

from __future__ import annotations

import base64
import io
import json
import re
import shutil
import stat
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from engine import cli, install, smtp_env
from engine.core import Paths, private_dir
from engine.docker_api import DockerError
from engine.logs import RunLog
from engine.runner import ENVIRONMENT, Result, Runner

from .helpers import RUN_ID, VERSION, deps, log_text, make_paths

ROOT = Path(__file__).resolve().parents[3]
DIGEST = {"server": "sha256:" + "a" * 64, "caddy": "sha256:" + "b" * 64}
REF = {role: f"ghcr.io/jayeuse/slateops-{role}:{VERSION}@{DIGEST[role]}" for role in DIGEST}
PROVIDERS = [
    "ghcr.io/supabase/postgres:17.11.0.004@sha256:" + "c" * 64,
    "envoyproxy/envoy:v1.39.1@sha256:" + "d" * 64,
]
EMAIL = "owner" + "@frontdesk.test"
USERNAME = "frontowner" + "77"
SMTP_PASSWORD = "app " + 'pa$$ "q" #x'
ANSWERS: dict[str, Any] = {
    "business_name": "Front Desk Dental",
    "slug": "front-desk",
    "admin_email": EMAIL,
    "admin_username": USERNAME,
    "public_host": "frontdesk-pc.local",
    "backup_target": "E:\\SlateOps\\Backups",
    "data_vhd_max_gb": 256,
    "time_zone": "Asia/Manila",
}
GENERATED_KEY_NAMES = (
    "POSTGRES_PASSWORD JWT_SECRET JWT_KEYS JWT_JWKS ANON_KEY SERVICE_ROLE_KEY ANON_KEY_ASYMMETRIC "
    "SERVICE_ROLE_KEY_ASYMMETRIC SUPABASE_PUBLISHABLE_KEY SUPABASE_SECRET_KEY "
    "SUPABASE_SESSION_ENCRYPTION_KEY PUBLICATION_SIGNING_KEY PG_META_CRYPTO_KEY DASHBOARD_PASSWORD "
    "REALTIME_TOKEN_SIGNING_KEY REALTIME_SECRET_KEY_BASE REALTIME_DB_ENC_KEY "
    "SECURITY_EVENT_SERVER_KEY SLATEOPS_OWNER_DB_PASSWORD SLATEOPS_RUNTIME_DB_PASSWORD"
).split()
ROOT_PEM = "-----BEGIN CERTIFICATE-----\nZmFrZSByb290IGNlcnRpZmljYXRl\n-----END CERTIFICATE-----\n"


class Killed(BaseException):
    """The process stops here (a power cut or ``kill -9``)."""


def _mount(argv: list[str], target: str) -> Path:
    for item in argv:
        if item.startswith("type=bind,") and item.endswith(f",target={target}"):
            return Path(item.split("source=", 1)[1].split(",", 1)[0])
    raise AssertionError(f"no mount for {target}")


class World:
    def __init__(self, paths: Paths) -> None:
        self.paths = paths
        self.count = 0
        self.kill_at: int | None = None
        self.kill_after = False
        self.generations = 0
        self.ca_created = 0
        self.volume_creations: list[str] = []
        self.volumes: set[str] = set()
        self.started: set[str] = set()
        self.records: dict[str, int] = {}
        self.sent = 0
        self.active = False
        self.bootstrap_exit: tuple[int, str] | None = None
        self.provisioning: tuple[int, str] = (0, '{"result":"provisioned"}')
        self.provisioning_stderr = "provision.roles info ok\n"
        self.healthy = True
        self.host_addresses: list[dict[str, Any]] = []
        self.host_routes: list[dict[str, Any]] = []
        self.docker_subnets: list[str] = []
        self.ip_fails = False
        self.present: set[str] = set(PROVIDERS)
        self.pulled: list[str] = []
        self.image_ids = dict(DIGEST)
        self.calls: list[list[str]] = []
        self.environments: list[dict[str, str]] = []
        self.chowns: list[tuple[str, int, int]] = []
        self.leaves = 0
        self.key_owner = 0
        self.check_fails = False
        self.renew_due = False
        self.served: bytes | None = None  # the leaf that Caddy serves (DER)
        self.reloads = 0

    # The runner -----------------------------------------------------------------------------

    def runner(self, log: RunLog) -> Runner:
        world = self

        class WorldRunner(Runner):
            def _execute(self, argv: list[str], timeout: float, env: dict[str, str]) -> Result:
                return world.answer(argv, env)

        return WorldRunner(log)

    def answer(self, argv: list[str], env: dict[str, str]) -> Result:
        self.count += 1
        self.calls.append(argv)
        self.environments.append(env)
        kill = self.kill_at == self.count
        if kill and not self.kill_after:
            raise Killed
        result = self._do(argv, env)
        if kill:
            raise Killed
        return result

    def _do(self, argv: list[str], env: dict[str, str]) -> Result:
        text = " ".join(argv)
        if argv[0] == "ip":
            if self.ip_fails:
                return Result(1, b"", b"")
            data = self.host_addresses if "address" in argv else self.host_routes
            return Result(0, json.dumps(data).encode(), b"")
        if argv[:3] == ["docker", "image", "inspect"]:
            role = "server" if "slateops-server" in argv[-1] else "caddy"
            return Result(0, self.image_ids[role].encode() + b"\n", b"")
        if "operations/supabase_keys.py" in argv:
            return self._generate(_mount(argv, "/new"))
        if "operations/local_ca.py" in argv:
            return self._ca(argv, _mount(argv, "/ca"), _mount(argv, "/tls"))
        if argv[:2] == ["docker", "compose"]:
            return self._compose(argv)
        if "operations.install.provisioning" in argv:
            code, out = self.provisioning
            return Result(code, out.encode() + b"\n", self.provisioning_stderr.encode())
        if "operations/bootstrap_admin.py" in argv:
            return self._bootstrap(env)
        if text.startswith(("systemctl", "journalctl", "docker ps", "docker logs")):
            return Result(0, b"", b"")
        return Result(0, b"", b"")

    def _generate(self, folder: Path) -> Result:
        self.generations += 1
        output, second = folder / "generated.env", folder / "restic-password"
        if output.exists() or second.exists():
            return Result(1, b"Refusing to overwrite existing installation keys.\n", b"")
        n = self.generations
        lines = [f"{name}=g{n}-{name.lower()}-0123456789abcdef" for name in GENERATED_KEY_NAMES]
        lines.append(f"SLATEOPS_INSTANCE_ID=slateops-{n:010x}")
        output.write_text("\n".join(lines) + "\n")
        second.write_text(f"restic-g{n}-dummy-value")
        return Result(0, b"Created installation keys; no secret values were printed.\n", b"")

    def _leaf_pem(self) -> str:
        body = base64.b64encode(f"leaf-{self.leaves}".encode()).decode()
        return f"-----BEGIN CERTIFICATE-----\n{body}\n-----END CERTIFICATE-----\n"

    def _issue_leaf(self, tls: Path) -> None:
        self.leaves += 1
        (tls / "server.crt").write_text(self._leaf_pem() + "-----BEGIN CERTIFICATE-----\naW50\n"
                                        "-----END CERTIFICATE-----\n")  # fmt: skip
        (tls / "server.key").write_text(f"leaf key {self.leaves}")
        self.key_owner = 0  # a new key file belongs to the job's user (root)

    def _ca(self, argv: list[str], ca: Path, tls: Path) -> Result:
        command = argv[argv.index("operations/local_ca.py") + 1]
        # Root with every capability dropped cannot read a key owned by Caddy (UID 1000).
        readable = self.key_owner == 0 or "DAC_READ_SEARCH" in argv
        leaf = readable and all((tls / name).exists() for name in ("server.crt", "server.key"))
        current = ca / "current"
        if command == "check":
            if self.check_fails or not leaf:
                return Result(3 if self.check_fails else 2,
                              b'{"code":"self_check_failed"}', b"")  # fmt: skip
            return Result(0, b'{"result":"valid","root_sha256":"x"}', b"")
        if command == "renew":
            if self.renew_due or not leaf:
                self._issue_leaf(tls)
                return Result(0, b'{"result":"renewed","root_sha256":"x"}', b"")
            return Result(0, b'{"result":"not_due","root_sha256":"x"}', b"")
        if current.exists():
            result = "exists" if leaf else "created"
        else:
            current.mkdir()
            (current / "root.crt").write_text(ROOT_PEM)
            (current / "intermediate.crt").write_text("intermediate")
            (current / "intermediate.key").write_text("intermediate key")
            self.ca_created += 1
            result = "created"
        if not leaf:
            self._issue_leaf(tls)
        return Result(0, json.dumps({"result": result, "root_sha256": "x"}).encode(), b"")

    def _compose(self, argv: list[str]) -> Result:
        project = argv[argv.index("--project-name") + 1]
        tail = argv[argv.index("-f", argv.index("-f") + 3) + 2 :]
        if tail[0] == "up":
            services = [item for item in tail[1:] if not item.startswith("--") and item != "never"]
            self.started.update(services)
            if "caddy" in services:
                self.served = self.file_leaf()  # Caddy reads the files when it starts
            if "db" in services:
                for volume in ("supabase-db-data", "supabase-storage-data"):
                    name = f"{project}_{volume}"
                    if name not in self.volumes:
                        self.volumes.add(name)
                        self.volume_creations.append(name)
            return Result(0, b"", b"")
        if tail[0] == "ps":
            rows = [
                {"Service": name, "State": "running", "Health": "healthy" if self.healthy else
                 "starting", "ExitCode": 0}
                for name in sorted(self.started)
            ]  # fmt: skip
            return Result(0, "\n".join(json.dumps(row) for row in rows).encode(), b"")
        if tail[:4] == ["exec", "-T", "caddy", "caddy"]:
            assert tail[4:6] == ["reload", "--force"], tail
            self.reloads += 1
            self.served = self.file_leaf()
            return Result(0, b"", b"")
        if tail[0] == "exec":
            if "api" not in self.started:
                return Result(1, b"", b"service api is not running")
            return Result(0, b'200 {"status":"ready"}', b"")
        return Result(0, b"", b"")

    def _bootstrap(self, env: dict[str, str]) -> Result:
        if self.bootstrap_exit is not None:
            code, output = self.bootstrap_exit
            return Result(code, output.encode() + b"\n", b"")
        email = env["ADMIN_EMAIL"]
        if self.active:
            return Result(0, b'{"result":"already_active"}\n', b"")
        self.records[email] = 1  # the same record on every rerun (W5a resume path)
        self.sent += 1
        return Result(0, b'{"result":"sent"}\n', b"")

    # The Docker API and HTTPS --------------------------------------------------------------

    def docker_api(self, socket: Path) -> FakeApi:
        return FakeApi(self)

    def https_get(self, host: str, path: str, cafile: Path, timeout: float) -> tuple[int, bytes]:
        if "caddy" not in self.started or not cafile.is_file():
            raise ConnectionRefusedError("connection refused")
        return 200, b'{"status":"ready"}'

    def chown(self, path: Path, uid: int, gid: int) -> None:
        self.chowns.append((path.name, uid, gid))
        if path.name == "server.key":
            self.key_owner = uid

    def file_leaf(self) -> bytes:
        """The DER of the leaf in server.crt (the fake PEM body is base64 of this)."""
        return f"leaf-{self.leaves}".encode()

    def served_certificate(self, host: str, cafile: Path, timeout: float) -> bytes:
        if "caddy" not in self.started or self.served is None:
            raise ConnectionRefusedError("connection refused")
        return self.served


class FakeApi:
    def __init__(self, world: World) -> None:
        self.world = world

    def networks(self) -> list[str]:
        return list(self.world.docker_subnets)

    def image_exists(self, reference: str) -> bool:
        return reference in self.world.present

    def pull(self, name: str, digest: str) -> Iterator[dict[str, Any]]:
        reference = next(ref for ref in PROVIDERS if ref.endswith(digest))
        self.world.pulled.append(reference)
        self.world.present.add(reference)
        yield {"status": "Pull complete", "id": "layer"}


def _stage_smtp(paths: Paths) -> None:
    private_dir(paths.etc / "new")
    values = {
        "SMTP_HOST": "smtp.frontdesk.test",
        "SMTP_PORT": "587",
        "SMTP_ADMIN_EMAIL": "noreply" + "@frontdesk.test",
        "SMTP_USER": "mailer" + "@frontdesk.test",
        "SMTP_PASS": SMTP_PASSWORD,
        "SMTP_SENDER_NAME": "Front Desk",
    }
    (paths.etc / "new" / "smtp.env").write_text(smtp_env.render(values))


def _setup(root: Path) -> tuple[Paths, World]:
    paths = make_paths(root)
    shutil.copytree(ROOT / "packaging/engine/templates", paths.engine_home / "templates")
    supabase = paths.bundle_root / "infra/supabase"
    supabase.mkdir(parents=True)
    for name in ("compose.yaml", "compose.production.yaml", "compose.installer.yaml"):
        (supabase / name).write_text("services: {}\n")
    caddy = paths.bundle_root / "infra/caddy"
    caddy.mkdir(parents=True)
    for name in ("generate_config.py", "Caddyfile.template"):
        shutil.copy(ROOT / "infra/caddy" / name, caddy / name)
    kept = private_dir(paths.state / "release" / VERSION)
    manifest = {
        "schema_version": 1,
        "version": VERSION,
        "images": {
            "server": {"ref": REF["server"]},
            "caddy": {"ref": REF["caddy"]},
            "providers": PROVIDERS,
        },
    }
    (kept / "release-manifest.json").write_text(json.dumps(manifest))
    _stage_smtp(paths)
    return paths, World(paths)


@pytest.fixture
def world(tmp_path: Path) -> tuple[Paths, World]:
    return _setup(tmp_path)


def run(
    paths: Paths, world: World, request: dict[str, Any] | None = None, job: str = "install"
) -> tuple[int, dict[str, Any]]:
    if request is None:
        request = {"run_id": RUN_ID, "version": VERSION, "answers": ANSWERS}
    out = io.StringIO()
    dependencies = deps(
        paths,
        make_runner=world.runner,
        docker_api=world.docker_api,
        https_get=world.https_get,
        chown=world.chown,
        served_certificate=world.served_certificate,
    )
    code = cli.main(
        [job], stdin=io.BytesIO(json.dumps(request).encode()), stdout=out, deps=dependencies
    )
    lines = out.getvalue().splitlines()
    assert len(lines) == 1, out.getvalue()
    return code, json.loads(lines[0])


def _mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


def _commands(world: World, marker: str) -> list[list[str]]:
    return [argv for argv in world.calls if marker in " ".join(argv)]


# W5b-1 logic: the full run -------------------------------------------------------------------


def test_ac_i10_a_full_install_runs_every_step_in_plan_order(world: tuple[Paths, World]) -> None:
    paths, fake = world

    code, result = run(paths, fake)

    assert code == 0, result
    order = [
        "supabase_keys.py",
        "local_ca.py init",
        "config --quiet",
        "--detach --pull never db auth storage realtime api-gw",
        "operations.install.provisioning",
        "--no-deps api",
        "--no-deps caddy",
        "bootstrap_admin.py",
    ]
    positions = [next(i for i, argv in enumerate(fake.calls) if m in " ".join(argv)) for m in order]
    assert positions == sorted(positions)
    steps = json.loads(paths.journal.read_text())["steps"]
    assert sorted(steps) == [f"{n:02d}" for n in range(1, 14)]


def test_ac_i13_the_result_is_safe_and_names_the_ca_and_the_invitation(
    world: tuple[Paths, World],
) -> None:
    paths, fake = world

    _, result = run(paths, fake)

    assert set(result) == {
        "code", "version", "invitation", "backup_setup", "ca_root_sha256", "ca_certificate_pem",
        "ca_security_code",
    }  # fmt: skip
    assert result["code"] == "installed"
    assert result["invitation"] == "sent"
    assert result["ca_certificate_pem"] == ROOT_PEM
    assert len(result["ca_root_sha256"]) == 64
    record = json.loads(paths.installation.read_text())
    assert set(record) == {"instance_id", "project", "public_host", "version"}
    assert _mode(paths.installation) == 0o600
    assert EMAIL not in json.dumps(result) and USERNAME not in json.dumps(result)


def test_ac_i12_the_backup_step_is_a_w10b_hook_that_reports_not_built(
    world: tuple[Paths, World],
) -> None:
    paths, fake = world

    _, result = run(paths, fake)

    assert result["backup_setup"] == "not_built"
    assert "backup setup not built in this release (W10b)" in log_text(paths)


def test_ac_i6_env_files_are_private_and_the_generator_output_is_gone(
    world: tuple[Paths, World],
) -> None:
    paths, fake = world

    run(paths, fake)

    for name in ("provider.env", "app.env", "provision.env", "restic-password"):
        assert _mode(paths.etc / name) == 0o600, name
    assert sorted(path.name for path in paths.new.iterdir()) == []
    assert not (paths.etc / "install-smtp.env").exists()
    provider = (paths.etc / "provider.env").read_text()
    assert 'SMTP_PASS="app pa$$$$ \\"q\\" #x"' in provider
    assert "SLATEOPS_APP_PRIVATE_SUBNET=172.31.248.0/28" in provider
    assert f"SLATEOPS_SERVER_IMAGE=ghcr.io/jayeuse/slateops-server:{VERSION}" in provider
    app = (paths.etc / "app.env").read_text()
    assert "PUBLIC_ORIGIN=https://frontdesk-pc.local" in app
    assert (paths.etc / "restic-password").read_text() == "restic-g1-dummy-value"


def test_ac_i5_ac_i7_one_shot_jobs_have_no_network_and_only_their_folders(
    world: tuple[Paths, World],
) -> None:
    paths, fake = world

    run(paths, fake)

    jobs = [(argv, ["/new"]) for argv in _commands(fake, "supabase_keys.py")]
    jobs += [(argv, ["/ca", "/tls"]) for argv in _commands(fake, "local_ca.py")]
    assert len(jobs) == 3  # the generator, then local_ca init and check (TASK-0089)
    for argv, mounts in jobs:
        assert argv[argv.index("--network") + 1] == "none"
        assert [a.rsplit("target=", 1)[1] for a in argv if a.startswith("type=bind")] == mounts
        for flag in ("--read-only", "--no-healthcheck"):
            assert flag in argv
        assert argv[argv.index("--cap-drop") + 1] == "ALL"
        assert argv[argv.index("--security-opt") + 1] == "no-new-privileges"
        assert argv[argv.index("--pull") + 1] == "never"
        assert "-v" not in argv and "--volume" not in argv
    for ca in _commands(fake, "local_ca.py"):
        assert ca[ca.index("--host") + 1] == "frontdesk-pc.local"


def test_ac_i8_ac_i7_owners_and_modes_follow_the_installation_rules(
    world: tuple[Paths, World],
) -> None:
    paths, fake = world

    run(paths, fake)

    assert {"app": (10001, 10001), "backup-exports": (0, 10001)}.items() <= {
        name: (uid, gid) for name, uid, gid in fake.chowns
    }.items()
    assert (".Caddyfile.new", 1000, 1000) in fake.chowns
    assert ("server.key", 1000, 1000) in fake.chowns
    expected = {
        paths.etc: 0o700, paths.new: 0o700, paths.etc / "ca": 0o700, paths.etc / "tls": 0o755,
        paths.logs / "app": 0o700, paths.state / "backup-exports": 0o750,
        paths.etc / "Caddyfile": 0o600, paths.etc / "tls" / "server.key": 0o600,
    }  # fmt: skip
    assert {path: _mode(path) for path in expected} == expected
    caddyfile = (paths.etc / "Caddyfile").read_text()
    assert re.search(r"^https://frontdesk-pc\.local:443[ {]", caddyfile, re.M)
    assert 'tls "/run/caddy-tls/server.crt" "/run/caddy-tls/server.key"' in caddyfile
    assert "reverse_proxy api:8000" in caddyfile


def test_ac_i10_compose_runs_with_the_three_files_and_only_the_minimal_environment(
    world: tuple[Paths, World],
) -> None:
    paths, fake = world

    run(paths, fake)

    compose_calls = [(a, e) for a, e in zip(fake.calls, fake.environments, strict=True)
                     if a[:2] == ["docker", "compose"]]  # fmt: skip
    assert compose_calls
    project = json.loads(paths.installation.read_text())["project"]
    files = [str(paths.bundle_root / "infra/supabase" / name) for name in
             ("compose.yaml", "compose.production.yaml", "compose.installer.yaml")]  # fmt: skip
    for argv, env in compose_calls:
        assert env == ENVIRONMENT
        assert argv[2:6] == [
            "--project-name",
            project,
            "--env-file",
            str(paths.etc / "provider.env"),
        ]
        assert [argv[i + 1] for i, item in enumerate(argv) if item == "-f"] == files
        if "config" in argv:
            assert "--quiet" in argv
    assert not [a for a in fake.calls if "inspect" in a and a[:3] != ["docker", "image", "inspect"]]
    [provision] = _commands(fake, "operations.install.provisioning")
    assert provision[provision.index("--network") + 1] == f"{project}_provider"
    assert provision[provision.index("--env-file") + 1] == str(paths.etc / "provision.env")
    assert f"SLATEOPS_RUN_ID={RUN_ID}" in provision


def test_ac_i11_ac_s1_the_email_and_user_name_reach_bootstrap_only_through_its_environment(
    world: tuple[Paths, World],
) -> None:
    paths, fake = world

    run(paths, fake)

    [(argv, env)] = [(a, e) for a, e in zip(fake.calls, fake.environments, strict=True)
                     if "operations/bootstrap_admin.py" in a]  # fmt: skip
    assert env == {**ENVIRONMENT, "ADMIN_EMAIL": EMAIL, "ADMIN_USERNAME": USERNAME}
    assert argv[argv.index("ADMIN_EMAIL") - 1] == "--env"
    assert "--provider-user-id" not in argv
    tail = argv[argv.index("operations/bootstrap_admin.py") :]
    assert tail == [
        "operations/bootstrap_admin.py",
        "--confirm",
        "--json",
        "--name=Front Desk Dental",
        "--slug=front-desk",
        "--time-zone=Asia/Manila",
    ]
    everything = json.dumps(fake.calls) + log_text(paths)
    for value in (EMAIL, USERNAME, SMTP_PASSWORD, "g1-postgres_password", "restic-g1"):
        assert value not in everything, value


def test_f2_s86_1_a_first_run_masks_the_answers_and_the_generated_secrets(
    world: tuple[Paths, World],
) -> None:
    # The job starts before the answers are stored and the secrets exist (cli.py loads the
    # held values once); a child that prints them on the first run must not reach the log.
    paths, fake = world
    generated = "g1-postgres_password-0123456789abcdef"
    fake.provisioning_stderr = (
        f"provision.roles error connect as {USERNAME} with password {generated}\n"
    )
    fake.bootstrap_exit = (3, f"user {USERNAME} at {EMAIL} key {generated}")

    code, result = run(paths, fake)

    assert (code, result["code"]) == (3, "bootstrap_failed")
    logs = log_text(paths)
    assert "provision.roles error connect as" in logs
    for value in (USERNAME, EMAIL, generated, SMTP_PASSWORD):
        assert value not in logs, value


@pytest.mark.parametrize("name", ["-Clinic", "--json", "--provider-user-id=0000"])
def test_architect_a_name_that_looks_like_an_option_stays_one_value(
    world: tuple[Paths, World], name: str
) -> None:
    # A name that step 1 accepts must reach bootstrap as the value of --name, never as an
    # option of its own (argparse reads "--name -Clinic" as a missing value).
    paths, fake = world
    request = {"run_id": RUN_ID, "version": VERSION, "answers": {**ANSWERS, "business_name": name}}

    code, _ = run(paths, fake, request)

    [argv] = _commands(fake, "bootstrap_admin.py")
    values = argv[argv.index("operations/bootstrap_admin.py") + 1 :]
    assert code == 0
    assert values[2] == f"--name={name}"
    assert all(
        item.startswith("--") and (item in ("--confirm", "--json") or "=" in item)
        for item in values
    )


# AC-I1, AC-I2: input and resume ----------------------------------------------------------------


def test_ac_i1_invalid_answers_are_refused_before_any_change(world: tuple[Paths, World]) -> None:
    paths, fake = world

    code, result = run(
        paths,
        fake,
        {
            "run_id": RUN_ID,
            "version": VERSION,
            "answers": {**ANSWERS, "public_host": "frontdesk.lan"},
        },
    )

    assert (code, result["code"]) == (2, "invalid_input")
    assert not paths.journal.exists() and not paths.answers.exists()
    assert fake.calls == []


def test_ac_i1_a_first_run_without_answers_is_refused(world: tuple[Paths, World]) -> None:
    paths, fake = world

    code, result = run(paths, fake, {"run_id": RUN_ID, "version": VERSION})

    assert (code, result["code"]) == (2, "invalid_input")


def test_ac_i5_without_staged_email_settings_nothing_starts(world: tuple[Paths, World]) -> None:
    paths, fake = world
    (paths.etc / "new" / "smtp.env").unlink()

    code, result = run(paths, fake)

    assert (code, result["code"]) == (2, "smtp_not_staged")
    assert not paths.journal.exists()


def test_ac_i2_a_resume_takes_the_stored_answers_and_refuses_changed_ones(
    world: tuple[Paths, World],
) -> None:
    paths, fake = world
    fake.kill_at = 6
    with pytest.raises(Killed):
        run(paths, fake)
    fake.kill_at = None
    resume = {"run_id": "install-20261117T110000Z-cd34ef", "version": VERSION}

    changed = run(paths, fake, {**resume, "answers": {**ANSWERS, "slug": "other"}})
    other_version = run(paths, fake, {**resume, "version": "0.1.0-rc.10"})
    resumed = run(paths, fake, resume)

    invalid = run(paths, fake, {**resume, "answers": {**ANSWERS, "public_host": "x.lan"}})

    assert changed == (2, {"code": "answers_changed", "message_key": "install.answers_changed"})
    assert invalid == (2, {"code": "invalid_input", "message_key": "install.invalid_input"})
    assert other_version[1]["code"] == "version_mismatch"
    assert resumed[0] == 0 and resumed[1]["code"] == "installed"
    assert json.loads(paths.journal.read_text())["runs"][-1] == resume["run_id"]


# AC-I3, AC-I4: the journal against the state --------------------------------------------------


def test_ac_i3_a_completed_step_with_a_missing_file_stops_and_changes_nothing(
    world: tuple[Paths, World],
) -> None:
    paths, fake = world
    run(paths, fake)
    (paths.etc / "app.env").unlink()
    calls = len(fake.calls)

    code, result = run(paths, fake)

    assert (code, result["code"], result["part"]) == (2, "install_state_mismatch", "env")
    assert len(fake.calls) == calls


def test_ac_i3_existing_secrets_without_a_journal_are_never_reused(
    world: tuple[Paths, World],
) -> None:
    paths, fake = world
    private_dir(paths.etc)
    (paths.etc / "provider.env").write_text("POSTGRES_PASSWORD=from-an-earlier-install\n")

    code, result = run(paths, fake)

    assert (code, result["code"]) == (2, "install_state_mismatch")
    assert (paths.etc / "provider.env").read_text() == "POSTGRES_PASSWORD=from-an-earlier-install\n"
    assert fake.calls == []


def test_ac_i4_a_different_existing_file_is_refused_and_kept(
    world: tuple[Paths, World], monkeypatch: pytest.MonkeyPatch
) -> None:
    paths, fake = world
    commit = install.commit_new
    written: list[str] = []

    def stop_after_provider(ctx: Any, path: Path, data: bytes, **kwargs: Any) -> bool:
        changed = commit(ctx, path, data, **kwargs)
        written.append(path.name)
        if path.name == "provider.env":
            raise Killed
        return changed

    monkeypatch.setattr(install, "commit_new", stop_after_provider)
    with pytest.raises(Killed):
        run(paths, fake)
    monkeypatch.setattr(install, "commit_new", commit)
    (paths.etc / "provider.env").write_text("SOMETHING=else\n")

    code, result = run(paths, fake)

    assert (code, result["code"], result["part"]) == (2, "install_state_mismatch", "provider.env")
    assert (paths.etc / "provider.env").read_text() == "SOMETHING=else\n"


# AC-K1 (W5b-2): kill at any step and run again -------------------------------------------------


def _complete_run_length(root: Path) -> int:
    paths, fake = _setup(root / "measure")
    assert run(paths, fake)[0] == 0
    return fake.count


def _assert_one_installation(paths: Paths, fake: World) -> None:
    provider = install.literal_lines(paths.etc / "provider.env")
    app = install.literal_lines(paths.etc / "app.env")
    provision = install.literal_lines(paths.etc / "provision.env")
    generation = provider["POSTGRES_PASSWORD"].split("-", 1)[0]
    # Every file holds the values of one generation (no secret mixed in from a second one).
    assert app["SUPABASE_SECRET_KEY"].startswith(generation + "-")
    assert provision["MIGRATION_DATABASE_URL"].count(generation + "-") == 1
    assert app["SLATEOPS_INSTANCE_ID"] == provider["SLATEOPS_INSTANCE_ID"]
    assert (paths.etc / "restic-password").read_text() == f"restic-{generation}-dummy-value"
    assert fake.ca_created == 1
    project = provider["SLATEOPS_INSTANCE_ID"]
    assert sorted(fake.volume_creations) == [
        f"{project}_supabase-db-data", f"{project}_supabase-storage-data",
    ]  # fmt: skip
    assert fake.records == {EMAIL: 1}


def _kill_after_commit(commit: Any, stop: int) -> Any:
    seen = [0]

    def killing(ctx: Any, path: Path, data: bytes, **kwargs: Any) -> bool:
        changed: bool = commit(ctx, path, data, **kwargs)
        seen[0] += 1
        if seen[0] == stop:
            raise Killed
        return changed

    return killing


@pytest.mark.parametrize("after", [False, True], ids=["before-effect", "after-effect"])
def test_ac_k1_a_kill_at_any_command_then_a_rerun_completes_one_installation(
    tmp_path: Path, after: bool
) -> None:
    total = _complete_run_length(tmp_path)
    assert total == 16  # every command of a full run is a kill point
    for kill_at in range(1, total + 1):
        paths, fake = _setup(tmp_path / f"kill-{kill_at}")
        fake.kill_at, fake.kill_after = kill_at, after
        with pytest.raises(Killed):
            run(paths, fake)
        fake.kill_at = None
        resume = {"run_id": "install-20261117T110000Z-cd34ef", "version": VERSION}
        code, result = run(paths, fake, resume if paths.journal.exists() else None)

        assert (code, result["code"]) == (0, "installed"), (kill_at, result)
        _assert_one_installation(paths, fake)
        bootstrap_runs = len(_commands(fake, "bootstrap_admin.py"))
        # Only a kill inside step 11 runs bootstrap twice (the residual: one resend).
        assert bootstrap_runs == 1 or "bootstrap_admin.py" in " ".join(fake.calls[kill_at - 1])


def test_ac_k1_a_kill_between_file_writes_then_a_rerun_completes_one_installation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    commit = install.commit_new
    for stop in range(1, 7):  # three env files, the Restic password, Caddyfile, installation
        paths, fake = _setup(tmp_path / f"stop-{stop}")
        killing = _kill_after_commit(commit, stop)
        monkeypatch.setattr(install, "commit_new", killing)
        with pytest.raises(Killed):
            run(paths, fake)
        monkeypatch.setattr(install, "commit_new", commit)

        code, result = run(paths, fake, {"run_id": RUN_ID, "version": VERSION})

        assert (code, result["code"]) == (0, "installed"), stop
        _assert_one_installation(paths, fake)


def test_ac_k1_a_rerun_after_completion_changes_nothing_and_sends_nothing(
    world: tuple[Paths, World],
) -> None:
    paths, fake = world
    first = run(paths, fake)
    calls, sent = len(fake.calls), fake.sent
    before = {path: path.read_bytes() for path in paths.etc.rglob("*") if path.is_file()}
    state = {path: path.read_bytes() for path in (paths.journal, paths.answers, paths.installation)}

    again = run(paths, fake, {"run_id": "install-20261117T120000Z-ee55ff", "version": VERSION})

    assert again == first
    assert (len(fake.calls), fake.sent) == (calls, sent)
    assert {path: path.read_bytes() for path in paths.etc.rglob("*") if path.is_file()} == before
    # Architect 6: a rerun after completion writes nothing, the journal included.
    assert {path: path.read_bytes() for path in state} == state


# AC-N1 (W5b-7): the app subnet ------------------------------------------------------------------


def test_ac_n1_a_collision_takes_the_next_free_private_28(world: tuple[Paths, World]) -> None:
    paths, fake = world
    fake.host_addresses = [{"addr_info": [{"family": "inet", "local": "172.31.248.9",
                                           "prefixlen": 24}]}]  # fmt: skip
    fake.docker_subnets = ["172.31.249.0/28", "fd00::/64"]

    code, _ = run(paths, fake)

    assert code == 0
    provider = (paths.etc / "provider.env").read_text()
    assert "SLATEOPS_APP_PRIVATE_SUBNET=172.31.249.16/28" in provider
    assert "default app subnet collides with 172.31.248.0/24" in log_text(paths)


def test_ac_n1_a_route_collision_counts_and_no_free_subnet_refuses(
    world: tuple[Paths, World],
) -> None:
    paths, fake = world
    fake.host_routes = [{"dst": "172.31.248.0/21"}, {"dst": "10.213.248.0/21"}]

    code, result = run(paths, fake)

    assert (code, result["code"]) == (2, "subnet_unavailable")


def test_architect_4_a_vpn_split_default_route_does_not_block_the_subnet(
    world: tuple[Paths, World],
) -> None:
    # VPN clients replace the default route with 0.0.0.0/1 and 128.0.0.0/1; routes wider
    # than /8 do not count, while a narrower route does.
    paths, fake = world
    fake.host_routes = [
        {"dst": "default"},
        {"dst": "0.0.0.0/1"},
        {"dst": "128.0.0.0/1"},
        {"dst": "172.31.0.0/16"},
    ]

    code, _ = run(paths, fake)

    assert code == 0
    provider = (paths.etc / "provider.env").read_text()
    assert "SLATEOPS_APP_PRIVATE_SUBNET=10.213.248.0/28" in provider


def test_ac_n1_unreadable_host_networks_never_pass(world: tuple[Paths, World]) -> None:
    paths, fake = world
    fake.ip_fails = True

    code, result = run(paths, fake)

    assert (code, result["code"]) == (3, "subnet_unknown")


def test_ac_n1_the_chosen_subnet_is_kept_on_a_rerun(world: tuple[Paths, World]) -> None:
    paths, fake = world
    fake.kill_at = 4  # after steps 1 and 2, before step 5 writes the subnet
    with pytest.raises(Killed):
        run(paths, fake)
    fake.kill_at = None
    fake.docker_subnets = ["172.31.248.0/28"]  # now the project's own app-private network

    code, _ = run(paths, fake, {"run_id": RUN_ID, "version": VERSION})

    assert code == 0
    assert "SLATEOPS_APP_PRIVATE_SUBNET=172.31.248.0/28" in (paths.etc / "provider.env").read_text()


# AC-I9: images ------------------------------------------------------------------------------------


def test_ac_i9_our_image_must_have_its_manifest_digest(world: tuple[Paths, World]) -> None:
    paths, fake = world
    fake.image_ids["caddy"] = "sha256:" + "e" * 64

    code, result = run(paths, fake)

    assert (code, result["code"], result["part"]) == (3, "image_missing", "caddy")


def test_ac_i9_missing_provider_images_are_pulled_by_digest(world: tuple[Paths, World]) -> None:
    paths, fake = world
    fake.present = {PROVIDERS[0]}

    code, _ = run(paths, fake)

    assert code == 0
    assert fake.pulled == PROVIDERS


def test_ac_i9_a_pull_error_gets_its_class(
    world: tuple[Paths, World], monkeypatch: pytest.MonkeyPatch
) -> None:
    paths, fake = world
    fake.present = set()

    def refuse(self: FakeApi, name: str, digest: str) -> Iterator[dict[str, Any]]:
        raise DockerError("dial tcp: lookup ghcr.io: no such host")

    monkeypatch.setattr(FakeApi, "pull", refuse)

    code, result = run(paths, fake)

    assert (code, result["code"]) == (3, "pull_name_lookup")


# AC-I10, AC-I11, AC-I14: failures ---------------------------------------------------------------


def test_ac_i10_providers_that_never_turn_healthy_stop_the_install(
    world: tuple[Paths, World],
) -> None:
    paths, fake = world
    fake.healthy = False

    code, result = run(paths, fake)

    assert (code, result["code"]) == (3, "services_not_healthy")
    assert "not healthy after 300 s" in log_text(paths)


def test_ac_i10_the_provisioning_code_is_passed_on(world: tuple[Paths, World]) -> None:
    paths, fake = world
    fake.provisioning = (3, '{"step":"migrate","code":"migration_failed"}')

    code, result = run(paths, fake)

    assert (code, result["code"], result["part"], result["cause"]) == (
        3, "provisioning_failed", "migrate", "migration_failed",
    )  # fmt: skip


def test_ac_i10_https_through_loopback_must_answer_200(
    world: tuple[Paths, World], monkeypatch: pytest.MonkeyPatch
) -> None:
    paths, fake = world
    monkeypatch.setattr(World, "https_get", lambda *args: (503, b"{}"))

    code, result = run(paths, fake)

    assert (code, result["code"]) == (3, "https_not_ready")


@pytest.mark.parametrize(
    ("exit_code", "output", "expected"),
    [
        (2, '{"code":"bootstrap_refused"}', (2, "bootstrap_refused")),
        (3, '{"code":"bootstrap_failed"}', (3, "bootstrap_failed")),
        (2, "not json", (3, "bootstrap_failed")),
    ],
)
def test_ac_i11_bootstrap_refusals_and_failures_pass_through(
    world: tuple[Paths, World], exit_code: int, output: str, expected: tuple[int, str]
) -> None:
    paths, fake = world
    fake.bootstrap_exit = (exit_code, output)

    code, result = run(paths, fake)

    assert (code, result["code"]) == expected


def test_ac_i14_a_failed_install_snapshot_has_the_compose_states_and_the_api_reads(
    world: tuple[Paths, World],
) -> None:
    paths, fake = world
    fake.bootstrap_exit = (3, '{"code":"bootstrap_failed"}')

    run(paths, fake)

    [snapshot] = list((paths.logs / "install" / RUN_ID).glob("snapshot-*"))
    names = {path.name for path in snapshot.iterdir()}
    assert {"compose-ps.txt", "api-ready.txt", "api-health.txt"} <= names
    assert (snapshot / "api-ready.txt").read_text().startswith("200 ")
    [ps] = [a for a in fake.calls if a[:2] == ["docker", "compose"] and "ps" in a
            and "{{.Service}}\t{{.State}}\t{{.Health}}" in a]  # fmt: skip
    assert ps


# AC-V1: resend-invitation ------------------------------------------------------------------------


def test_ac_v1_resend_before_the_install_is_refused(world: tuple[Paths, World]) -> None:
    paths, fake = world

    code, result = run(paths, fake, {"run_id": RUN_ID}, job="resend-invitation")

    assert (code, result["code"]) == (2, "not_installed")
    assert fake.calls == []


def test_ac_v1_resend_sends_again_or_reports_an_active_administrator(
    world: tuple[Paths, World],
) -> None:
    paths, fake = world
    run(paths, fake)
    request = {"run_id": "maintenance-20261118T080000Z-mm11nn"}

    pending = run(paths, fake, request, job="resend-invitation")
    fake.active = True
    active = run(paths, fake, request, job="resend-invitation")
    fake.bootstrap_exit = (3, '{"code":"bootstrap_failed"}')
    failure = run(paths, fake, request, job="resend-invitation")

    assert pending == (0, {"code": "sent"})
    assert active == (0, {"code": "already_active"})
    assert failure[0] == 3 and failure[1]["code"] == "bootstrap_failed"
    assert fake.records == {EMAIL: 1} and fake.sent == 2
    first, resent = _commands(fake, "bootstrap_admin.py")[:2]
    assert resent[-6:] == first[-6:]  # the same fixed arguments from the stored answers


# TASK-0089 (W6a): the trust files, the chain check, the key that Caddy owns, renewal ---------


def test_ac_e1_ac_e7_install_writes_the_trust_files_and_returns_the_security_code(
    world: tuple[Paths, World],
) -> None:
    paths, fake = world

    code, result = run(paths, fake)

    assert code == 0
    files = sorted(path.name for path in paths.trust.iterdir())
    assert files == ["slateops-ca.crt", "slateops-ca.sha256", "slateops.mobileconfig"]
    assert (paths.trust / "slateops-ca.sha256").read_text() == result["ca_security_code"] + "\n"
    assert result["ca_security_code"] == ":".join(
        result["ca_root_sha256"].upper()[i : i + 2] for i in range(0, 64, 2)
    )
    caddyfile = (paths.etc / "Caddyfile").read_text()
    assert "\nhttp://:80 {\n" in caddyfile
    assert 'templates {\n            root "/srv/slateops-trust"' in caddyfile


def test_ac_e4_a_failed_chain_check_writes_no_trust_file_and_no_caddyfile(
    world: tuple[Paths, World],
) -> None:
    # W6a-5: local_ca.py init checks the chain before it writes the CA (W2 owner test
    # test_w2_4_chain_verifies_only_for_the_host); the engine adds `check` before its files.
    paths, fake = world
    fake.check_fails = True

    code, result = run(paths, fake)

    assert (code, result["code"]) == (3, "ca_check_failed")
    assert not (paths.trust / "slateops-ca.sha256").exists()
    assert not (paths.etc / "Caddyfile").exists()
    [check] = _commands(fake, "local_ca.py check")
    assert check[check.index("--network") + 1] == "none"


def test_ac_e5_a_rerun_of_step_6_reads_the_key_that_caddy_owns(
    world: tuple[Paths, World], monkeypatch: pytest.MonkeyPatch
) -> None:
    paths, fake = world
    commit = install.commit_new

    def stop_after_caddyfile(ctx: Any, path: Path, data: bytes, **kwargs: Any) -> bool:
        changed = commit(ctx, path, data, **kwargs)
        if path.name == "Caddyfile":
            raise Killed
        return changed

    monkeypatch.setattr(install, "commit_new", stop_after_caddyfile)
    with pytest.raises(Killed):
        run(paths, fake)
    monkeypatch.setattr(install, "commit_new", commit)
    assert fake.key_owner == 1000

    code, _ = run(paths, fake, {"run_id": RUN_ID, "version": VERSION})

    assert code == 0
    assert fake.leaves == 1  # the rerun kept the leaf: no second certificate
    assert fake.key_owner == 1000
    for argv in _commands(fake, "operations/local_ca.py"):
        caps = [argv[i + 1] for i, item in enumerate(argv) if item == "--cap-add"]
        assert caps == ["DAC_READ_SEARCH"], argv


RENEW = {"run_id": "renewal-20261118T020000Z-rr11ss"}


def renew(paths: Paths, fake: World) -> tuple[int, dict[str, Any]]:
    return run(paths, fake, RENEW, job="renew-certificate")


def test_ac_e6_renewal_before_the_install_is_refused(world: tuple[Paths, World]) -> None:
    paths, fake = world

    assert renew(paths, fake) == (
        2,
        {"code": "not_installed", "message_key": "renew-certificate.not_installed"},
    )
    assert fake.calls == []


def test_ac_e6_a_certificate_that_is_not_due_changes_nothing_and_reloads_nothing(
    world: tuple[Paths, World],
) -> None:
    paths, fake = world
    run(paths, fake)
    before = (paths.etc / "tls" / "server.crt").read_bytes()

    code, result = renew(paths, fake)

    assert (code, result) == (0, {"code": "not_due", "reloaded": False})
    assert (paths.etc / "tls" / "server.crt").read_bytes() == before
    assert fake.reloads == 0
    assert (paths.trust / "slateops-ca.sha256").exists()


def test_ac_e6_w6a_4_a_due_certificate_is_renewed_and_caddy_reloads_it(
    world: tuple[Paths, World],
) -> None:
    paths, fake = world
    run(paths, fake)
    fake.renew_due = True

    code, result = renew(paths, fake)

    assert (code, result) == (0, {"code": "renewed", "reloaded": True})
    assert fake.leaves == 2 and fake.served == fake.file_leaf() == b"leaf-2"
    assert fake.reloads == 1 and fake.key_owner == 1000
    order = [" ".join(argv) for argv in fake.calls[-3:]]
    assert "local_ca.py renew" in order[0] and "local_ca.py check" in order[1]
    assert "caddy reload --force --config /etc/caddy/Caddyfile --adapter caddyfile" in order[2]


@pytest.mark.parametrize("stop", ["after-renew", "after-owner"])
def test_ac_e6_a_kill_inside_a_renewal_is_finished_by_the_next_run(
    world: tuple[Paths, World], monkeypatch: pytest.MonkeyPatch, stop: str
) -> None:
    paths, fake = world
    run(paths, fake)
    fake.renew_due = True
    if stop == "after-renew":
        fake.kill_at, fake.kill_after = fake.count + 1, True  # the renew command
    else:
        real_chown = fake.chown

        def chown_then_stop(path: Path, uid: int, gid: int) -> None:
            real_chown(path, uid, gid)
            if path.name == "server.key":
                raise Killed

        monkeypatch.setattr(fake, "chown", chown_then_stop)
    with pytest.raises(Killed):
        renew(paths, fake)
    monkeypatch.setattr(fake, "chown", World.chown.__get__(fake))
    fake.kill_at, fake.renew_due = None, False

    code, result = renew(paths, fake)

    assert (code, result) == (0, {"code": "not_due", "reloaded": True})
    assert fake.key_owner == 1000 and fake.served == fake.file_leaf()


def test_ac_e6_renewal_does_not_need_caddy_to_answer(world: tuple[Paths, World]) -> None:
    paths, fake = world
    run(paths, fake)
    fake.renew_due = True
    fake.started.discard("caddy")

    code, result = renew(paths, fake)

    assert (code, result) == (0, {"code": "renewed", "reloaded": False})
    assert "Caddy does not answer" in log_text(paths)
