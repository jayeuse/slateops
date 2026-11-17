"""The app subnet check (plan W5b-7; TASK-0074 finding; README ``SLATEOPS_APP_PRIVATE_SUBNET``).

Before the install, the default ``app-private`` subnet is compared with every IPv4 address
and route of the host (``ip -json``; in WSL mirrored mode these include the PC's LAN) and
with every Docker network. On a collision the engine takes the first free /28 of a fixed
private list. ``install`` journals the choice once, so a rerun never sees the project's own
``app-private`` network as a collision.
"""

from __future__ import annotations

import ipaddress
import json
from collections.abc import Iterator
from typing import Any

from engine.context import Context
from engine.core import failed, refused
from engine.docker_api import DockerError

DEFAULT = "172.31.248.0/28"
# The default's /21 first, then a second private /21 (Proposed; 256 choices in all).
RANGES = ("172.31.248.0/21", "10.213.248.0/21")
Network = ipaddress.IPv4Network


def candidates() -> Iterator[Network]:
    yield ipaddress.IPv4Network(DEFAULT)
    for block in RANGES:
        yield from ipaddress.IPv4Network(block).subnets(new_prefix=28)


def _json(text: str) -> list[dict[str, Any]]:
    data = json.loads(text)
    return [item for item in data if isinstance(item, dict)] if isinstance(data, list) else []


def host_networks(ctx: Context, step: str) -> list[Network]:
    addresses = ctx.runner.run(step, ["ip", "-json", "-4", "address", "show"], timeout=30)
    routes = ctx.runner.run(
        step, ["ip", "-json", "-4", "route", "show", "table", "all"], timeout=30
    )
    if not addresses.ok or not routes.ok:
        raise failed("subnet_unknown")
    found: list[Network] = []
    try:
        for link in _json(addresses.text()):
            for info in link.get("addr_info") or []:
                if info.get("family") == "inet":
                    interface = f"{info['local']}/{info['prefixlen']}"
                    found.append(ipaddress.IPv4Interface(interface).network)
        for route in _json(routes.text()):
            destination = str(route.get("dst", ""))
            if destination and destination != "default":
                found.append(ipaddress.IPv4Network(destination, strict=False))
    except (ValueError, KeyError, TypeError) as error:
        raise failed("subnet_unknown") from error
    return found


def docker_networks(ctx: Context) -> list[Network]:
    try:
        subnets = ctx.deps.docker_api(ctx.paths.docker_socket).networks()
    except DockerError as error:
        raise failed("subnet_unknown") from error
    found: list[Network] = []
    for subnet in subnets:
        try:
            network = ipaddress.ip_network(subnet, strict=False)
        except ValueError:
            continue
        if isinstance(network, Network):
            found.append(network)
    return found


def choose(ctx: Context, step: str) -> str:
    used = [*host_networks(ctx, step), *docker_networks(ctx)]
    for candidate in candidates():
        clashes = [str(network) for network in used if network.overlaps(candidate)]
        if not clashes:
            note = "" if str(candidate) == DEFAULT else f" (default {DEFAULT} collides)"
            ctx.log.line(step, "INFO", f"app subnet {candidate}{note}")
            return str(candidate)
        if str(candidate) == DEFAULT:
            ctx.log.line(step, "WARN", f"default app subnet collides with {', '.join(clashes)}")
    raise refused("subnet_unavailable")
