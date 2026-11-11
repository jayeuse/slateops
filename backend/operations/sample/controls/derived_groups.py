"""Groups that a publish derives beside a pack's own groups (setup spec R2, SD3, SD5)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from operations.sample.blueprint import SampleDataset


def with_derived(
    original: Mapping[str, Any], planned: Mapping[str, list[str]], dataset: SampleDataset
) -> bool:
    """``original`` holds the pack's groups as planned, and other groups only as derived ones.

    The initial publish creates every pack department open, so it derives three empty groups
    for each department (R2, SD3). An organization populated before derived setup has none
    (SD5). Any other share of extra groups, or an extra group with a member, is refused.
    """
    derived = [members for group, members in original.items() if group not in planned]
    return (
        {group: original.get(group) for group in planned} == planned
        and len(derived) in {0, 3 * len(dataset.department_ids)}
        and all(members == [] for members in derived)
    )
