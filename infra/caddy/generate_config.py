#!/usr/bin/env python3
"""Render a secret-free Caddyfile for Slate Operations' single-origin gateway."""

from __future__ import annotations

import argparse
import ipaddress
import re
from pathlib import Path, PurePosixPath, PureWindowsPath

PRODUCTION_TEMPLATE_PATH = Path(__file__).with_name("Caddyfile.template")
_PLACEHOLDER = re.compile(r"\{\{([A-Z_]+)\}\}")
_HOSTNAME = re.compile(
    r"(?=.{1,253}\Z)(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)*"
    r"[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\Z"
)
_LISTENER_PORT_LABELS = ("HTTPS_PORT", "HEALTH_PORT", "BACKEND_PORT")
# The trust page inside the Caddy image (infra/docker/caddy.Dockerfile; TASK-0089 R5).
TRUST_PAGE_ROOT = PurePosixPath("/srv/slateops-trust-page")
# The three public files of the trust root (R3) and their types (R9).
TRUST_DOWNLOADS = (
    ("trust_crt", "slateops-ca.crt", "application/x-x509-ca-cert"),
    ("trust_profile", "slateops.mobileconfig", "application/x-apple-aspen-config"),
)
_HSTS_LINE = '    header Strict-Transport-Security "max-age=31536000"\n'
_HEALTH_COMMENT = "# This loopback listener is used only by Compose health checks."


class ConfigurationError(ValueError):
    """Raised when a generated gateway configuration would be unsafe or invalid."""


def _port(value: str) -> int:
    try:
        port = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("must be an integer port") from error
    if not 1 <= port <= 65535:
        raise argparse.ArgumentTypeError("must be between 1 and 65535")
    return port


def _public_host(value: str) -> str:
    if not value or value != value.strip() or any(character.isspace() for character in value):
        raise argparse.ArgumentTypeError("must be a hostname or IP address without whitespace")
    if _HOSTNAME.fullmatch(value):
        return value.lower()
    try:
        return str(ipaddress.ip_address(value))
    except ValueError as error:
        raise argparse.ArgumentTypeError("must be a hostname or IP address") from error


def _listen_address(value: str) -> str:
    invalid_character = any(
        character.isspace() or not character.isprintable() for character in value
    )
    if not value or "%" in value or invalid_character:
        raise argparse.ArgumentTypeError("must be an unscoped literal IPv4 or IPv6 address")
    try:
        address = ipaddress.ip_address(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("must be a literal IPv4 or IPv6 address") from error
    return str(address)


def _absolute_path(value: str) -> Path:
    path = Path(value)
    if not (path.is_absolute() or PureWindowsPath(value).is_absolute()):
        raise argparse.ArgumentTypeError("must be an absolute path")
    if any(not character.isprintable() for character in value):
        raise argparse.ArgumentTypeError("must be an absolute path without control characters")
    if "{" in value or "}" in value:
        raise argparse.ArgumentTypeError("must not contain Caddy interpolation braces")
    return path


def _certificate_path(path: Path) -> Path:
    return _absolute_path(str(path))


def _caddy_string_token(value: str) -> str:
    """Return one Caddyfile token without allowing token-boundary injection."""
    if "{" in value or "}" in value:
        raise ConfigurationError("Caddy interpolation braces are not allowed in certificate paths")
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _site_host(host: str) -> str:
    """Return a Caddy site-address host, adding brackets only for IPv6."""
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return host
    return f"[{address}]" if address.version == 6 else str(address)


def validate_listener_ports(
    *,
    https_port: int,
    health_port: int,
    backend_port: int,
    labels: tuple[str, ...] = _LISTENER_PORT_LABELS,
    require_host_namespace_separation: bool = True,
) -> None:
    """Reject collisions in Caddy and, when applicable, its host namespace."""
    ports = (https_port, health_port, backend_port)
    if len(labels) != len(ports):
        raise ConfigurationError("listener labels do not match listener ports")
    pairs = (
        tuple(
            (first, second)
            for first in range(len(ports))
            for second in range(first + 1, len(ports))
        )
        if require_host_namespace_separation
        else ((0, 1),)
    )
    for first, second in pairs:
        if ports[first] == ports[second]:
            raise ConfigurationError(f"{labels[second]} conflicts with {labels[first]}")


def _trust_root(value: Path, certificate_folders: list[PurePosixPath]) -> PurePosixPath:
    """A dedicated folder for the template root (R3): absolute, no ``..``, never ``/``, and
    never equal to, a parent of, or inside a folder that holds the certificate or its key."""
    text = str(value)
    if (
        not text.startswith("/")
        or ".." in PurePosixPath(text).parts
        or any(character.isspace() or not character.isprintable() for character in text)
        or "{" in text
        or "}" in text
    ):
        raise ConfigurationError("the trust root must be an absolute path without '..'")
    root = PurePosixPath(text)
    if root == PurePosixPath("/"):
        raise ConfigurationError("the trust root cannot be /")
    for folder in certificate_folders:
        if root == folder or root in folder.parents or folder in root.parents:
            raise ConfigurationError("the trust root cannot share the certificate folder")
    return root


def _trust_handlers(trust_root: PurePosixPath, host: str | None) -> str:
    """The page and the two downloads (R1 to R5, R9); ``host`` limits them to one name."""

    def matcher(name: str, path: str) -> str:
        if host is None:
            return f"    @{name} path {path}\n"
        return f"    @{name} {{\n        host {host}\n        path {path}\n    }}\n"

    root = _caddy_string_token(str(trust_root))
    blocks = [
        matcher("trust_page", "/trust")
        + "    handle @trust_page {\n"
        + f"        root * {_caddy_string_token(str(TRUST_PAGE_ROOT))}\n"
        + "        rewrite * /index.html\n"
        + f"        templates {{\n            root {root}\n        }}\n"
        + '        header Cache-Control "no-store"\n'
        + "        file_server\n"
        + "    }\n"
    ]
    for name, file_name, content_type in TRUST_DOWNLOADS:
        blocks.append(
            matcher(name, f"/trust/{file_name}")
            + f"    handle @{name} {{\n"
            + f"        root * {root}\n"
            + f"        rewrite * /{file_name}\n"
            + f"        header Content-Type {content_type}\n"
            + "        file_server\n"
            + "    }\n"
        )
    return "".join(blocks)


def _add_trust_routes(
    rendered: str,
    *,
    trust_root: PurePosixPath,
    host: str,
    listen_address: str,
    http_port: int,
    https_port: int,
) -> str:
    """Add the trust routes to the HTTPS site and the port 80 trust site (W6a, H10)."""
    https_routes = (
        "    # Trust routes (W6a; plan 6.3): before every other route, outside /api, no proxy,\n"
        "    # no cookie read and no CORS header. /trust/ok is the page's trust probe (R10).\n"
        + _trust_handlers(trust_root, None)
        + "    @trust_ok path /trust/ok\n"
        + "    handle @trust_ok {\n        respond 204\n    }\n\n"
    )
    if rendered.count(_HSTS_LINE) != 1 or rendered.count(_HEALTH_COMMENT) != 1:
        raise ConfigurationError("the template has no single anchor for the trust routes")
    rendered = rendered.replace(_HSTS_LINE, _HSTS_LINE + "\n" + https_routes)
    target = f"https://{host}" + ("" if https_port == 443 else f":{https_port}")
    http_site = (
        "# Port 80 (H10): only the trust page and the two trust files for the installation's\n"
        "# name; every other name or path is redirected to the HTTPS site.\n"
        f"http://:{http_port} {{\n"
        f"    bind {listen_address}\n\n"
        + _trust_handlers(trust_root, host)
        + "\n    handle {\n"
        + f"        redir {target}{{uri}} 308\n"
        + "    }\n}\n\n"
    )
    return rendered.replace(_HEALTH_COMMENT, http_site + _HEALTH_COMMENT)


def render_config(
    *,
    public_host: str,
    listen_address: str,
    https_port: int,
    health_port: int = 3449,
    backend_port: int,
    tls_mode: str,
    upstream_host: str = "127.0.0.1",
    cert_file: Path | None = None,
    key_file: Path | None = None,
    require_host_namespace_separation: bool = True,
    trust_root: Path | None = None,
    http_port: int = 80,
) -> str:
    """Render the checked-in template after validating all operator inputs."""
    if tls_mode == "internal":
        if cert_file is not None or key_file is not None:
            raise ConfigurationError("certificate paths are only valid with custom TLS")
        tls_directive = "internal"
    elif tls_mode == "custom":
        if cert_file is None or key_file is None:
            raise ConfigurationError("custom TLS requires both certificate and key paths")
        tls_directive = " ".join(
            (
                _caddy_string_token(str(_certificate_path(cert_file))),
                _caddy_string_token(str(_certificate_path(key_file))),
            )
        )
    else:
        raise ConfigurationError("TLS mode must be internal or custom")

    rendered_https_port = _port(str(https_port))
    rendered_health_port = _port(str(health_port))
    rendered_backend_port = _port(str(backend_port))
    validate_listener_ports(
        https_port=rendered_https_port,
        health_port=rendered_health_port,
        backend_port=rendered_backend_port,
        require_host_namespace_separation=require_host_namespace_separation,
    )

    replacements = {
        "PUBLIC_HOST": _site_host(_public_host(public_host)),
        "LISTEN_ADDRESS": _listen_address(listen_address),
        "HTTPS_PORT": str(rendered_https_port),
        "HEALTH_PORT": str(rendered_health_port),
        "BACKEND_PORT": str(rendered_backend_port),
        "UPSTREAM_HOST": _site_host(_public_host(upstream_host)),
        "TLS_DIRECTIVE": tls_directive,
    }
    template = PRODUCTION_TEMPLATE_PATH.read_text(encoding="utf-8")
    rendered = _PLACEHOLDER.sub(lambda match: replacements[match.group(1)], template)
    remaining = _PLACEHOLDER.search(rendered)
    if remaining:
        raise ConfigurationError(f"unreplaced template variable: {remaining.group(1)}")
    if trust_root is None:
        return rendered
    rendered_http_port = _port(str(http_port))
    if rendered_http_port in (rendered_https_port, rendered_health_port) or (
        require_host_namespace_separation and rendered_http_port == rendered_backend_port
    ):
        raise ConfigurationError("HTTP_PORT conflicts with another listener")
    folders = [
        PurePosixPath(str(path)).parent for path in (cert_file, key_file) if path is not None
    ]
    return _add_trust_routes(
        rendered,
        trust_root=_trust_root(trust_root, folders),
        host=replacements["PUBLIC_HOST"],
        listen_address=replacements["LISTEN_ADDRESS"],
        http_port=rendered_http_port,
        https_port=rendered_https_port,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--public-host", required=True, type=_public_host)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--listen-address", default="0.0.0.0", type=_listen_address)
    parser.add_argument("--https-port", default=443, type=_port)
    parser.add_argument("--health-port", default=3449, type=_port)
    parser.add_argument("--backend-port", default=8000, type=_port)
    parser.add_argument("--upstream-host", default="127.0.0.1", type=_public_host)
    parser.add_argument("--tls-mode", choices=("internal", "custom"), default="internal")
    parser.add_argument("--cert-file", type=_absolute_path)
    parser.add_argument("--key-file", type=_absolute_path)
    parser.add_argument(
        "--trust-root",
        type=Path,
        help="the read-only folder of the public trust files; adds the port 80 trust site",
    )
    parser.add_argument("--http-port", default=80, type=_port)
    return parser


def parse_arguments() -> argparse.Namespace:
    return build_parser().parse_args()


def main() -> None:
    arguments = parse_arguments()
    try:
        rendered = render_config(
            public_host=arguments.public_host,
            listen_address=arguments.listen_address,
            https_port=arguments.https_port,
            health_port=arguments.health_port,
            backend_port=arguments.backend_port,
            tls_mode=arguments.tls_mode,
            upstream_host=arguments.upstream_host,
            cert_file=arguments.cert_file,
            key_file=arguments.key_file,
            trust_root=arguments.trust_root,
            http_port=arguments.http_port,
        )
    except ConfigurationError as error:
        raise SystemExit(f"invalid gateway configuration: {error}") from error
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(rendered, encoding="utf-8")


if __name__ == "__main__":
    main()
