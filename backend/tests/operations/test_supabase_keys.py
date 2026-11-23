"""Validate generated keys with the libraries used by independent consumers."""

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import jwt
import pytest
from cryptography.fernet import Fernet

from app.core.config.environment import ConfigurationError, read_environment
from operations import supabase_keys
from operations.supabase_keys import (
    add_realtime_secrets,
    generate_secrets,
    installer_secrets,
    write_secret_file,
)


def test_generated_keys_support_provider_signing_and_session_encryption() -> None:
    values = generate_secrets()
    assert {"JWT_KEYS", "JWT_JWKS", "ANON_KEY", "SERVICE_ROLE_KEY"} <= values.keys()
    private_keys = json.loads(values["JWT_KEYS"])
    public_keys = json.loads(values["JWT_JWKS"])["keys"]
    signing_key = jwt.PyJWK(private_keys[0]).key
    verification_key = jwt.PyJWK(public_keys[0]).key
    signed = jwt.encode({"sub": "provider-user"}, signing_key, algorithm="ES256")
    assert jwt.decode(signed, verification_key, algorithms=["ES256"])["sub"] == "provider-user"
    assert "d" not in public_keys[0]
    for name, role in (("ANON_KEY", "anon"), ("SERVICE_ROLE_KEY", "service_role")):
        assert jwt.decode(
            values[name], values["JWT_SECRET"], algorithms=["HS256"], issuer="supabase",
        )["role"] == role
        assert jwt.decode(
            values[f"{name}_ASYMMETRIC"], verification_key,
            algorithms=["ES256"], issuer="supabase",
        )["role"] == role
    cipher = Fernet(values["SUPABASE_SESSION_ENCRYPTION_KEY"])
    assert cipher.decrypt(cipher.encrypt(b"provider-refresh")) == b"provider-refresh"


def test_each_installation_gets_independent_keys(capsys) -> None:
    first, second = generate_secrets(), generate_secrets()
    assert first
    assert first.keys() == second.keys()
    assert all(first[key] != second[key] for key in first)
    assert not capsys.readouterr().out


def test_secret_file_is_private_and_round_trips_without_stdout(tmp_path: Path, capsys) -> None:
    path = tmp_path / ".env"
    write_secret_file(path)
    assert path.is_file()
    if os.name != "nt":
        assert path.stat().st_mode & 0o777 == 0o600
    values = read_environment(path)
    assert "JWT_KEYS" in values
    jwt.PyJWK(json.loads(values["JWT_KEYS"])[0])
    assert not capsys.readouterr().out


def test_key_generation_cannot_overwrite_existing_installation(tmp_path: Path) -> None:
    path = tmp_path / ".env"
    path.write_text("existing-installation", encoding="utf-8")
    with pytest.raises(FileExistsError):
        write_secret_file(path)
    assert path.read_text(encoding="utf-8") == "existing-installation"


def test_realtime_token_key_verifies_only_through_the_service_jwks() -> None:
    values = generate_secrets()
    private_jwk = json.loads(values["REALTIME_TOKEN_SIGNING_KEY"])
    service_keys = json.loads(values["JWT_JWKS"])["keys"]
    auth_signing_kids = {key.get("kid") for key in json.loads(values["JWT_KEYS"])}
    public = [key for key in service_keys if key.get("kid") == private_jwk["kid"]]
    assert len(public) == 1 and "d" not in public[0]
    # GoTrue signs and publishes only JWT_KEYS; the Realtime key must not be among them.
    assert private_jwk["kid"] not in auth_signing_kids
    token = jwt.encode(
        {"role": "authenticated"}, jwt.PyJWK(private_jwk).key, algorithm="ES256",
        headers={"kid": private_jwk["kid"]},
    )
    assert jwt.decode(token, jwt.PyJWK(public[0]).key, algorithms=["ES256"])["role"] == (
        "authenticated"
    )
    assert len(values["REALTIME_DB_ENC_KEY"].encode()) == 16
    assert len(values["REALTIME_SECRET_KEY_BASE"]) >= 64


def test_realtime_keys_join_an_existing_installation_once(tmp_path: Path, capsys) -> None:
    original = generate_secrets()
    del original["REALTIME_TOKEN_SIGNING_KEY"], original["REALTIME_SECRET_KEY_BASE"]
    del original["REALTIME_DB_ENC_KEY"]
    original["JWT_JWKS"] = json.dumps({"keys": json.loads(original["JWT_JWKS"])["keys"][:2]})
    path = tmp_path / ".env"
    path.write_text(
        "# kept comment\n" + "".join(f"{name}='{value}'\n" for name, value in original.items()),
        encoding="utf-8",
    )
    path.chmod(0o600)

    add_realtime_secrets(path)

    values = read_environment(path)
    assert path.read_text(encoding="utf-8").startswith("# kept comment\n")
    assert {name: values[name] for name in original if name != "JWT_JWKS"} == {
        name: value for name, value in original.items() if name != "JWT_JWKS"
    }
    keys = json.loads(values["JWT_JWKS"])["keys"]
    assert keys[:2] == json.loads(original["JWT_JWKS"])["keys"]
    assert keys[2]["kid"] == json.loads(values["REALTIME_TOKEN_SIGNING_KEY"])["kid"]
    if os.name != "nt":
        assert path.stat().st_mode & 0o777 == 0o600
    before = path.read_text(encoding="utf-8")
    with pytest.raises(FileExistsError):
        add_realtime_secrets(path)
    assert path.read_text(encoding="utf-8") == before
    assert not capsys.readouterr().out


# Installer secret set (plan W2, TASK-0081). The default output above stays unchanged.
KEYS_COMMAND = Path(__file__).resolve().parents[2] / "operations" / "supabase_keys.py"
INSTALLER_NAMES = {
    "ANON_KEY", "ANON_KEY_ASYMMETRIC", "DASHBOARD_PASSWORD", "JWT_JWKS", "JWT_KEYS",
    "JWT_SECRET", "PG_META_CRYPTO_KEY", "POSTGRES_PASSWORD", "PUBLICATION_SIGNING_KEY",
    "REALTIME_DB_ENC_KEY", "REALTIME_SECRET_KEY_BASE", "REALTIME_TOKEN_SIGNING_KEY",
    "SECURITY_EVENT_SERVER_KEY", "SERVICE_ROLE_KEY", "SERVICE_ROLE_KEY_ASYMMETRIC",
    "SLATEOPS_INSTANCE_ID", "SLATEOPS_OWNER_DB_PASSWORD", "SLATEOPS_RUNTIME_DB_PASSWORD",
    "SUPABASE_PUBLISHABLE_KEY", "SUPABASE_SECRET_KEY", "SUPABASE_SESSION_ENCRYPTION_KEY",
}
# A-2: an unquoted value that every Docker and Compose reader keeps byte for byte.
UNSAFE_LITERAL = set("$#'`\\") | {chr(code) for code in (*range(0x21), 0x7F)}


def run_keys(*arguments: str | Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(KEYS_COMMAND), *map(str, arguments)],
        capture_output=True, text=True, check=False, timeout=60,
    )


def test_default_output_keeps_single_quoted_dotenv_lines(tmp_path: Path) -> None:
    path = tmp_path / ".env"
    write_secret_file(path)
    lines = path.read_text(encoding="utf-8").splitlines()
    assert [line.partition("=")[0] for line in lines] == list(generate_secrets())
    assert all(re.fullmatch(r"[A-Z_]+='[^'\n]+'", line) for line in lines)


def test_w2_1_w2_2_installer_set_is_complete_and_uses_the_literal_alphabet() -> None:
    first, first_password = installer_secrets()
    second, second_password = installer_secrets()
    assert first.keys() == INSTALLER_NAMES
    assert all(first[name] != second[name] for name in first)
    assert first_password != second_password
    for name, value in (*first.items(), ("restic", first_password)):
        assert value, name
        assert not set(value) & UNSAFE_LITERAL, name
        assert value.isascii() and not value.startswith('"'), name
    for name in ("JWT_KEYS", "JWT_JWKS", "REALTIME_TOKEN_SIGNING_KEY"):
        assert json.dumps(json.loads(first[name]), separators=(",", ":")) == first[name]
    assert re.fullmatch(r"[a-z][a-z0-9-]{2,62}", first["SLATEOPS_INSTANCE_ID"])
    for name in ("POSTGRES_PASSWORD", "SLATEOPS_OWNER_DB_PASSWORD", "SLATEOPS_RUNTIME_DB_PASSWORD"):
        assert re.fullmatch(r"[0-9a-f]{48}", first[name]), name
    assert len(first_password) >= 43


def test_w2_1_w2_5_docker_format_writes_unquoted_set_and_separate_restic_password(
    tmp_path: Path,
) -> None:
    env_path, password_path = tmp_path / "generated.env", tmp_path / "restic-password"
    completed = run_keys(
        "--format", "docker", "--output", env_path, "--restic-password-file", password_path,
    )
    assert completed.returncode == 0, completed.stderr
    text = env_path.read_text(encoding="utf-8")
    password = password_path.read_text(encoding="utf-8")
    lines = text.splitlines()
    assert text.endswith("\n") and "\n" not in password
    values = dict(line.split("=", 1) for line in lines)
    assert values.keys() == INSTALLER_NAMES and len(lines) == len(INSTALLER_NAMES)
    assert all(not value.startswith(("'", '"')) for value in values.values())
    assert jwt.PyJWK(json.loads(values["JWT_KEYS"])[0])
    if os.name != "nt":
        assert env_path.stat().st_mode & 0o777 == 0o600
        assert password_path.stat().st_mode & 0o777 == 0o600
    printed = completed.stdout + completed.stderr
    assert completed.stdout == "Created installation keys; no secret values were printed.\n"
    assert all(value not in printed for value in (*values.values(), password))


@pytest.mark.parametrize("existing", ["generated.env", "restic-password"])
def test_w2_3_docker_format_never_overwrites_either_output(tmp_path: Path, existing: str) -> None:
    env_path, password_path = tmp_path / "generated.env", tmp_path / "restic-password"
    (tmp_path / existing).write_text("existing-installation", encoding="utf-8")
    completed = run_keys(
        "--format", "docker", "--output", env_path, "--restic-password-file", password_path,
    )
    assert completed.returncode == 1
    assert sorted(path.name for path in tmp_path.iterdir()) == [existing]
    assert (tmp_path / existing).read_text(encoding="utf-8") == "existing-installation"


@pytest.mark.parametrize(
    "arguments",
    [
        ("--format", "docker", "--output", "{out}"),
        ("--output", "{out}", "--restic-password-file", "{pw}"),
        ("--format", "docker", "--add-realtime", "{out}", "--restic-password-file", "{pw}"),
    ],
    ids=["docker-without-password-file", "password-file-without-docker", "docker-add-realtime"],
)
def test_w2_2_docker_format_needs_output_and_password_file_only(
    tmp_path: Path, arguments: tuple[str, ...]
) -> None:
    out, pw = tmp_path / "generated.env", tmp_path / "restic-password"
    completed = run_keys(*(item.format(out=out, pw=pw) for item in arguments))
    assert completed.returncode == 2
    assert not out.exists() and not pw.exists()


@pytest.mark.parametrize("bad", ["a$b", '"quoted', "two words", "tab\tvalue", "café"])
def test_w2_2_docker_format_refuses_a_value_outside_the_literal_alphabet(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, bad: str
) -> None:
    values, password = installer_secrets()
    monkeypatch.setattr(
        supabase_keys, "installer_secrets", lambda: ({**values, "JWT_SECRET": bad}, password)
    )
    with pytest.raises(ConfigurationError, match="JWT_SECRET") as raised:
        supabase_keys.write_installer_files(tmp_path / "generated.env", tmp_path / "pw")
    assert bad not in str(raised.value)
    assert list(tmp_path.iterdir()) == []
