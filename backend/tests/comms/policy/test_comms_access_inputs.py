"""Each ``MATERIALIZED`` Comms access input keeps a name that no later CTE takes (N2).

If a later CTE took the same anonymous name, a statement that joins both would fail to
compile ("Multiple, unrelated CTEs found with the same name"). SQLAlchemy 2.0 built the
name from an object's ``id()``, so a freed address could hand the name on; 2.1 seeds it
with random bits instead.
"""

import gc

from sqlalchemy import literal, select

from app.systems.comms.access_inputs import materialized


def _later_names(count: int) -> list[str]:
    # Each CTE is freed at once, so the allocator hands its address to the next one.
    return [str(select(literal(2).label("two")).cte().name) for _ in range(count)]


def test_a_materialized_input_keeps_a_name_that_no_later_cte_takes() -> None:
    for _round in range(5):
        kept = materialized(select(literal(1).label("one")))
        name = str(kept.name)
        gc.collect()

        assert str(kept.name) == name
        assert name not in _later_names(1000)
        later = select(literal(2).label("two")).cte()
        compiled = str(select(kept.c.one, later.c.two).compile())
        assert compiled.startswith("WITH anon_1 AS MATERIALIZED"), compiled
        assert "anon_2 AS" in compiled, compiled
