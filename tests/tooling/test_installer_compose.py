"""The installer Compose overlay (TASK-0086 AC-O1; space-cut and W2 carries in TASK-0083).

The files are read as data, with Compose's merge tags kept as markers; the release job
``install-proof`` proves the merged file with Compose itself (``config --quiet``, health).
"""

from __future__ import annotations

import importlib
import sys
import unittest
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
SUPABASE = ROOT / "infra" / "supabase"
sys.path.insert(0, str(ROOT / "packaging"))
compose = importlib.import_module("engine.compose")  # the engine package is under packaging/


@dataclass(frozen=True)
class Reset:
    """``!reset``: the attribute is removed from the merged file."""


@dataclass(frozen=True)
class Override:
    """``!override``: the value replaces the base value instead of merging with it."""

    value: Any


class ComposeLoader(yaml.SafeLoader):
    pass


ComposeLoader.add_constructor("!reset", lambda loader, node: Reset())
ComposeLoader.add_constructor(
    "!override", lambda loader, node: Override(loader.construct_mapping(node, deep=True))
)


def load(name: str) -> dict[str, Any]:
    loader = ComposeLoader((SUPABASE / name).read_text())
    try:
        data = loader.get_single_data()
    finally:
        loader.dispose()
    assert isinstance(data, dict)
    return data


def merged() -> dict[str, dict[str, Any]]:
    """The service attributes this test needs, merged as Compose merges them."""
    services: dict[str, dict[str, Any]] = {}
    for name in compose.FILES:
        for service, attributes in (load(name).get("services") or {}).items():
            target = services.setdefault(service, {})
            for key, value in attributes.items():
                if isinstance(value, Reset):
                    target.pop(key, None)
                elif isinstance(value, Override):
                    target[key] = value.value
                elif isinstance(value, dict) and isinstance(target.get(key), dict):
                    target[key] = {**target[key], **value}
                elif isinstance(value, list) and isinstance(target.get(key), list):
                    target[key] = [*target[key], *value]  # Compose merges sequences
                else:
                    target[key] = value
    return services


class InstallerOverlayTests(unittest.TestCase):
    def setUp(self) -> None:
        self.services = merged()
        self.started = (*compose.PROVIDER_SERVICES, *compose.APP_SERVICES)

    def test_ac_o1_customer_installs_start_exactly_the_customer_services(self) -> None:
        self.assertEqual(
            set(self.started), {"db", "auth", "storage", "realtime", "api-gw", "api", "caddy"}
        )
        for name in ("studio", "meta", "imgproxy"):
            with self.subTest(service=name):
                self.assertEqual(self.services[name]["profiles"], ["operator-tools"])
        for name in self.started:
            with self.subTest(service=name):
                self.assertNotIn("profiles", self.services[name])

    def test_ac_o1_every_dependency_of_a_started_service_is_started_or_a_one_shot(self) -> None:
        allowed = {*self.started, "provider-volume-init"}
        for name in self.started:
            with self.subTest(service=name):
                dependencies = set(self.services[name].get("depends_on") or {})
                self.assertLessEqual(dependencies, allowed)
        self.assertEqual(
            self.services["storage"]["depends_on"]["provider-volume-init"],
            {"condition": "service_completed_successfully"},
        )

    def test_ac_o1_storage_runs_without_image_transformation(self) -> None:
        storage = self.services["storage"]

        self.assertEqual(storage["environment"]["ENABLE_IMAGE_TRANSFORMATION"], "false")
        self.assertNotIn("imgproxy", storage["depends_on"])

    def test_ac_o1_only_caddy_publishes_a_port(self) -> None:
        published = {name for name in self.started if self.services[name].get("ports")}

        self.assertEqual(published, {"caddy"})

    def test_ac_o1_our_images_are_never_pulled_or_built(self) -> None:
        for name in compose.APP_SERVICES:
            with self.subTest(service=name):
                self.assertEqual(self.services[name]["pull_policy"], "never")
                self.assertNotIn("build", self.services[name])

    def test_ac_o1_the_development_files_are_unchanged_by_the_overlay(self) -> None:
        base = load("compose.yaml")["services"]

        self.assertIn("studio", base["api-gw"]["depends_on"])
        self.assertEqual(base["storage"]["environment"]["ENABLE_IMAGE_TRANSFORMATION"], "true")
        self.assertNotIn("compose.installer.yaml", (ROOT / "scripts" / "dev.py").read_text())


if __name__ == "__main__":
    unittest.main()
