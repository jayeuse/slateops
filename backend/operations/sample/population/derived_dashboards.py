"""Fill each department's derived home Dashboard with the pack's Overview (setup spec SD12).

A publish that creates an open department also creates its empty home Dashboard. The pack
reads that Dashboard and saves its name and widgets on it; it never posts a second one.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from operations.sample.client import SampleClient
from operations.sample.population.content import SampleContentError, _id, _json, _pages


def fill_derived_home(
    writer: SampleClient,
    department_key: str,
    department_id: str,
    name: str,
    widgets: Sequence[Mapping[str, Any]],
) -> int:
    """Save ``name`` and ``widgets`` on the department's one empty home; return the widget count.

    The department must have exactly one Dashboard, the active, empty derived home.
    """
    rows = _pages(writer, "/api/dashboards", {"department_id": department_id, "deleted": "include"})
    home = rows[0] if len(rows) == 1 else None
    if (
        home is None
        or home.get("department_id") != department_id
        or home.get("is_home") is not True
        or home.get("is_deleted") is not False
        or home.get("widgets") != []
        or type(home.get("revision")) is not int
    ):
        raise SampleContentError(f"Expected one empty derived home Dashboard for {department_key}")
    dashboard = _json(
        writer,
        "PATCH",
        f"/api/dashboards/{_id(home)}",
        body={"revision": home["revision"], "name": name, "widgets": list(widgets)},
        expected=(200,),
    )
    saved = dashboard.get("widgets")
    if (
        dashboard.get("id") != home["id"]
        or dashboard.get("name") != name
        or not isinstance(saved, list)
        or len(saved) != len(widgets)
    ):
        raise SampleContentError("Dashboard response did not contain its saved widgets")
    writer.record_mapping("dashboards", f"department:{department_key}:dashboard", home["id"])
    for index, widget in enumerate(saved):
        if not isinstance(widget, dict):
            raise SampleContentError("Dashboard response contains an invalid widget")
        writer.record_mapping(
            "widgets",
            f"department:{department_key}:dashboard:widget:{index + 1:02d}",
            _id(widget),
        )
    return len(saved)
