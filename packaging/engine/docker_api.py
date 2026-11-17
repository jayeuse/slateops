"""A small Docker Engine API client on the local socket, for the image pulls of ``prefetch``.

The pull reports per-layer byte counts only through the API's JSON progress stream, so the
engine reads that stream instead of the CLI's text. Requests go only to the Unix socket;
the daemon does the registry traffic. Image inspection here reads images, never
containers.
"""

from __future__ import annotations

import http.client
import json
import socket
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlencode

LINE_LIMIT = 1024 * 1024


class DockerError(Exception):
    """The daemon refused a request or reported an error; ``message`` is its text."""

    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.status = status


class _UnixConnection(http.client.HTTPConnection):
    def __init__(self, path: Path, timeout: float) -> None:
        super().__init__("localhost", timeout=timeout)
        self._path = path

    def connect(self) -> None:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(self.timeout)
        sock.connect(str(self._path))
        self.sock = sock


class DockerApi:
    def __init__(self, socket_path: Path, timeout: float = 600.0) -> None:
        self.socket_path = socket_path
        self.timeout = timeout

    def _request(self, method: str, path: str) -> tuple[_UnixConnection, http.client.HTTPResponse]:
        connection = _UnixConnection(self.socket_path, self.timeout)
        try:
            connection.request(method, path, headers={"Content-Type": "application/json"})
            return connection, connection.getresponse()
        except OSError as error:
            connection.close()
            raise DockerError(f"docker socket: {error}") from error

    @staticmethod
    def _error(response: http.client.HTTPResponse) -> DockerError:
        body = response.read(LINE_LIMIT)
        try:
            message = str(json.loads(body).get("message", ""))
        except (ValueError, AttributeError):
            message = body.decode("utf-8", errors="replace")
        return DockerError(message or f"HTTP {response.status}", response.status)

    def pull(self, name: str, digest: str) -> Iterator[dict[str, Any]]:
        """Pull ``name@digest``; yield each progress object; raise on an error object."""
        query = urlencode({"fromImage": name, "tag": digest})
        connection, response = self._request("POST", f"/images/create?{query}")
        try:
            if response.status != 200:
                raise self._error(response)
            while True:
                try:
                    line = response.readline(LINE_LIMIT)
                except TimeoutError as error:
                    # The daemon stopped sending progress: plan 10.7 counts it as a time-out.
                    raise DockerError(
                        f"pull timed out: no progress for {self.timeout} s"
                    ) from error
                except OSError as error:
                    raise DockerError(f"docker socket: {error}") from error
                if not line:
                    return
                if not line.strip():
                    continue
                try:
                    event = json.loads(line)
                except ValueError as error:
                    raise DockerError("unreadable progress line") from error
                if not isinstance(event, dict):
                    continue
                if "error" in event:
                    detail = event.get("errorDetail") or {}
                    raise DockerError(str(detail.get("message") or event["error"]))
                yield event
        finally:
            connection.close()

    def networks(self) -> list[str]:
        """The IPAM subnets of every Docker network (W5b-7); configuration, not containers."""
        connection, response = self._request("GET", "/networks")
        try:
            if response.status != 200:
                raise self._error(response)
            data = json.loads(response.read(16 * LINE_LIMIT))
        except ValueError as error:
            raise DockerError("unreadable network list") from error
        finally:
            connection.close()
        subnets: list[str] = []
        for network in data if isinstance(data, list) else []:
            ipam = network.get("IPAM") if isinstance(network, dict) else None
            for config in (ipam or {}).get("Config") or []:
                if isinstance(config, dict) and isinstance(config.get("Subnet"), str):
                    subnets.append(config["Subnet"])
        return subnets

    def image_exists(self, reference: str) -> bool:
        connection, response = self._request("GET", f"/images/{quote(reference, safe='')}/json")
        try:
            if response.status == 200:
                response.read()
                return True
            if response.status == 404:
                response.read()
                return False
            raise self._error(response)
        finally:
            connection.close()
