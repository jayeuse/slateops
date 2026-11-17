"""The trust routes of the Caddy generator (TASK-0089: plan W6a-1, W6a-7, 6.3, H10; R1 to R10).

Static checks of the rendered Caddyfile. The release job ``install-proof`` sends real requests
to the same output (W6a-1 paths, the redirect, ``/trust/ok``, the content types).
"""

from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
CADDY_DIR = ROOT / "infra" / "caddy"
sys.path.insert(0, str(CADDY_DIR))
generate_config = __import__("generate_config")

TRUST_ROOT = Path("/srv/slateops-trust")
HOST = "frontdesk-pc.local"


def render(**overrides: object) -> str:
    settings: dict[str, object] = {
        "public_host": HOST,
        "listen_address": "0.0.0.0",
        "https_port": 443,
        "health_port": 3449,
        "backend_port": 8000,
        "tls_mode": "custom",
        "upstream_host": "api",
        "cert_file": Path("/run/caddy-tls/server.crt"),
        "key_file": Path("/run/caddy-tls/server.key"),
        "trust_root": TRUST_ROOT,
    }
    settings.update(overrides)
    return str(generate_config.render_config(**settings))


def site(rendered: str, address: str) -> str:
    """The body of one site block, from its address line to its closing brace."""
    start = rendered.index(f"\n{address} {{\n")
    end = rendered.index("\n}\n", start)
    return rendered[start:end]


def handler(block: str, matcher: str) -> str:
    start = block.index(f"    handle @{matcher} {{\n")
    return block[start : block.index("\n    }\n", start)]


class TrustRoutesTests(unittest.TestCase):
    def test_ac_g6_without_a_trust_root_the_output_is_unchanged(self) -> None:
        with_none = render(trust_root=None)
        omitted = generate_config.render_config(
            public_host=HOST,
            listen_address="0.0.0.0",
            https_port=443,
            health_port=3449,
            backend_port=8000,
            tls_mode="custom",
            upstream_host="api",
            cert_file=Path("/run/caddy-tls/server.crt"),
            key_file=Path("/run/caddy-tls/server.key"),
        )

        self.assertEqual(with_none, omitted)
        self.assertNotIn("trust", omitted)
        self.assertNotIn("http://:80", omitted)

    def test_ac_g1_port_80_serves_exactly_three_paths_for_the_host_and_redirects_the_rest(
        self,
    ) -> None:
        http = site(render(), "http://:80")

        self.assertIn("    bind 0.0.0.0\n", http)
        matchers = re.findall(r"(?m)^    @(\w+) \{\n        host (\S+)\n        path (\S+)\n", http)
        self.assertEqual(
            matchers,
            [
                ("trust_page", HOST, "/trust"),
                ("trust_crt", HOST, "/trust/slateops-ca.crt"),
                ("trust_profile", HOST, "/trust/slateops.mobileconfig"),
            ],
        )
        self.assertNotIn("/trust/ok", http)
        # Every other Host or path: a fixed-host redirect, never the request's Host.
        self.assertTrue(
            http.endswith("    handle {\n        redir https://frontdesk-pc.local{uri} 308\n    }")
        )
        self.assertNotIn("{host}", http)
        self.assertNotIn("reverse_proxy", http)

    def test_ac_g1_the_redirect_names_a_https_port_other_than_443(self) -> None:
        http = site(render(https_port=8443), "http://:80")

        self.assertIn("redir https://frontdesk-pc.local:8443{uri} 308", http)

    def test_ac_g2_port_443_serves_the_trust_paths_first_and_trust_ok_as_an_empty_204(
        self,
    ) -> None:
        rendered = render()
        https = site(rendered, "https://frontdesk-pc.local:443")

        for matcher, path in (
            ("trust_page", "/trust"),
            ("trust_crt", "/trust/slateops-ca.crt"),
            ("trust_profile", "/trust/slateops.mobileconfig"),
            ("trust_ok", "/trust/ok"),
        ):
            with self.subTest(matcher=matcher):
                self.assertIn(f"    @{matcher} path {path}\n", https)
                self.assertLess(https.index(f"handle @{matcher}"), https.index("handle @realtime"))
        self.assertEqual(handler(https, "trust_ok"), "    handle @trust_ok {\n        respond 204")
        for matcher in ("trust_page", "trust_crt", "trust_profile", "trust_ok"):
            body = handler(https, matcher)
            with self.subTest(matcher=matcher):
                self.assertNotIn("reverse_proxy", body)
                self.assertNotIn("Cookie", body)
                self.assertNotIn("Access-Control", body)
        self.assertNotIn("Access-Control", rendered)
        self.assertIn('header Strict-Transport-Security "max-age=31536000"', https)

    def test_ac_g3_templates_runs_only_for_the_page_with_its_own_root(self) -> None:
        rendered = render()
        page_handlers = [
            handler(site(rendered, address), "trust_page")
            for address in ("http://:80", "https://frontdesk-pc.local:443")
        ]

        self.assertEqual(rendered.count("templates {"), 2)
        for body in page_handlers:
            self.assertIn(
                '        templates {\n            root "/srv/slateops-trust"\n        }', body
            )
            self.assertIn('        root * "/srv/slateops-trust-page"', body)
            self.assertIn("        rewrite * /index.html", body)
        for address in ("http://:80", "https://frontdesk-pc.local:443"):
            for matcher in ("trust_crt", "trust_profile"):
                self.assertNotIn("templates", handler(site(rendered, address), matcher))

    def test_ac_g5_the_downloads_have_their_types_and_come_from_the_trust_root(self) -> None:
        for address in ("http://:80", "https://frontdesk-pc.local:443"):
            block = site(render(), address)
            for matcher, name, content_type in (
                ("trust_crt", "slateops-ca.crt", "application/x-x509-ca-cert"),
                ("trust_profile", "slateops.mobileconfig", "application/x-apple-aspen-config"),
            ):
                body = handler(block, matcher)
                with self.subTest(address=address, matcher=matcher):
                    self.assertIn('        root * "/srv/slateops-trust"', body)
                    self.assertIn(f"        rewrite * /{name}", body)
                    self.assertIn(f"        header Content-Type {content_type}", body)
                    self.assertIn("        file_server", body)

    def test_ac_g4_the_trust_root_is_never_the_key_folder_its_parent_or_inside_it(
        self,
    ) -> None:
        refused = [
            Path("/run/caddy-tls"),
            Path("/run"),
            Path("/"),
            Path("/run/caddy-tls/trust"),
            Path("/srv/../run/caddy-tls"),
            Path("/srv/slateops-trust/.."),
            Path("relative/trust"),
            Path("/srv/{env.HOME}"),
            Path("/srv/trust root"),
        ]
        for trust_root in refused:
            with (
                self.subTest(trust_root=str(trust_root)),
                self.assertRaises((generate_config.ConfigurationError, ValueError)),
            ):
                render(trust_root=trust_root)
        self.assertIn('root "/srv/slateops-trust"', render())

    def test_ac_g4_the_http_port_cannot_collide_with_another_listener(self) -> None:
        for port in (443, 3449):
            with self.subTest(port=port), self.assertRaises(generate_config.ConfigurationError):
                render(http_port=port)

    def test_ac_g1_the_cli_takes_the_trust_root_and_the_http_port(self) -> None:
        arguments = generate_config.build_parser().parse_args(
            [
                "--public-host",
                HOST,
                "--output",
                "/tmp/Caddyfile",
                "--trust-root",
                "/srv/slateops-trust",
                "--http-port",
                "8080",
            ]
        )

        self.assertEqual(arguments.trust_root, Path("/srv/slateops-trust"))
        self.assertEqual(arguments.http_port, 8080)


if __name__ == "__main__":
    unittest.main()


class TrustImageAndMountTests(unittest.TestCase):
    """AC-D1 (R5) and the R3 binding: one trust root from the image to the engine."""

    def test_ac_d1_the_image_carries_the_page_and_an_empty_trust_root_mount_point(self) -> None:
        lines = (ROOT / "infra/docker/caddy.Dockerfile").read_text().splitlines()

        self.assertTrue(lines[3].startswith("# caddy-license: v2.10.2 "))
        self.assertEqual(
            lines[4],
            "FROM caddy@sha256:4c6e91c6ed0e2fa03efd5b44747b625fec79bc9cd06ac5235a779726618e530d",
        )
        self.assertIn("RUN setcap -r /usr/bin/caddy \\", lines)
        # Both folders exist before the COPY: a folder that COPY --chmod creates gets the
        # file's mode 0644, and user 1000 could not enter it.
        self.assertIn(f"    && mkdir -p {TRUST_ROOT} {generate_config.TRUST_PAGE_ROOT}", lines)
        self.assertIn(
            "COPY --chown=0:0 --chmod=0644 infra/caddy/trust/index.html "
            f"{generate_config.TRUST_PAGE_ROOT}/index.html",
            lines,
        )
        self.assertIn("USER 1000:1000", lines)
        # R5: the page never goes into the template root.
        self.assertNotIn(f"{TRUST_ROOT}/index.html", "\n".join(lines))

    def test_r3_the_engine_overlay_image_and_generator_name_one_trust_root(self) -> None:
        sys.path.insert(0, str(ROOT / "packaging"))
        install = __import__("engine.install", fromlist=["TRUST_MOUNT"])
        core = __import__("engine.core", fromlist=["Paths"])
        paths = core.Paths()
        overlay = yaml.safe_load(
            (ROOT / "infra/supabase/compose.installer.yaml")
            .read_text()
            .replace("!reset", "")
            .replace("!override", "")
        )
        [mount] = [
            volume
            for volume in overlay["services"]["caddy"]["volumes"]
            if volume["target"] == install.TRUST_MOUNT
        ]

        self.assertEqual(install.TRUST_MOUNT, str(TRUST_ROOT))
        self.assertEqual(mount["source"], str(paths.trust))
        self.assertEqual(
            (mount["type"], mount["read_only"], mount["bind"]["create_host_path"]),
            ("bind", True, False),
        )
        for private in (paths.etc / "tls", paths.etc / "ca"):
            self.assertNotEqual(paths.trust, private)
            self.assertNotIn(paths.trust, private.parents)
            self.assertNotIn(private, paths.trust.parents)
        self.assertIn(
            "${CADDY_PUBLIC_BIND_HOST:-0.0.0.0}:80:80", overlay["services"]["caddy"]["ports"]
        )
