"""Each ``MATERIALIZED`` Comms access input keeps a name that no later CTE takes (N2).

An anonymous CTE's name holds the ``id()`` of the CTE that ``prefix_with`` copied. If that
first CTE were freed, a later CTE could take its address and so its name, and a statement
that joins both fails to compile ("Multiple, unrelated CTEs found with the same name").
"""

import gc
import re

from sqlalchemy import CTE, literal, select

from app.systems.comms.access_inputs import materialized


def _later_names(count: int) -> list[str]:
    # Each CTE is freed at once, so the allocator hands its address to the next one.
    return [str(select(literal(2).label("two")).cte().name) for _ in range(count)]


def test_a_materialized_input_keeps_a_name_that_no_later_cte_takes() -> None:
    for _round in range(5):
        kept = materialized(select(literal(1).label("one")))
        gc.collect()

        # Whether a freed address comes back depends on the allocator, so the first check
        # can miss; the second does not: the CTE whose id() the name holds is still alive.
        assert str(kept.name) not in _later_names(1000)
        [address] = re.findall(r"\d+", str(kept.name))
        owners = [found for found in gc.get_objects() if id(found) == int(address)]
        assert [
            found for found in owners if isinstance(found, CTE) and found.name == kept.name
        ] != [], kept.name
