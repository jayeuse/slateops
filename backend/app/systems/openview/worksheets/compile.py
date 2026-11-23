"""A computed column as SQL over one row (spec D7.2, D7.3; K5, K6).

Each tree compiles to a ``numeric`` value, an error flag and a hidden flag, with every
literal bound. A blank operand makes arithmetic blank (SQL ``NULL``); ``SUM`` and
``AVERAGE`` aggregate the listed values with ``unnest`` so blanks are skipped and each
argument appears once; ``MIN`` and ``MAX`` are ``LEAST`` and ``GREATEST``. A division by
zero gives ``NULL`` through ``NULLIF`` (never a database error, even when the planner folds
bound values) and sets the error flag, which every computed column that reads it carries.
A column that reads a value the viewer cannot read is hidden, like that value (D7.3).
"""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from sqlalchemy import Integer, Numeric, case, column, false, func, literal, null, or_, select
from sqlalchemy import cast as sql_cast
from sqlalchemy.dialects.postgresql import array
from sqlalchemy.sql.elements import ColumnElement

from app.systems.openview.worksheets.expression import Binary, Call, Negate, Node, Number, Ref

Expression = ColumnElement[Any]


@dataclass(frozen=True)
class Operand:
    """What a reference reads: the masked number, and whether it is hidden or an error."""

    number: Expression
    hidden: Expression
    error: Expression


def _no_number() -> Expression:
    return sql_cast(null(), Numeric)


def _any(flags: list[Expression]) -> Expression:
    return func.coalesce(or_(*flags), false()) if flags else false()


def _aggregate(name: str, values: list[Expression]) -> Expression:
    listed = func.unnest(array(values, type_=Numeric)).table_valued(
        column("value", Numeric)
    ).render_derived()
    function = func.sum if name == "SUM" else func.avg
    return select(function(listed.c.value)).select_from(listed).scalar_subquery()


class _Compiler:
    def __init__(self, operands: Mapping[str, Operand]) -> None:
        self.operands = operands
        self.errors: list[Expression] = []
        self.hidden: list[Expression] = []

    def value(self, node: Node) -> Expression:
        if isinstance(node, Number):
            return literal(node.value, Numeric())
        if isinstance(node, Ref):
            operand = self.operands.get(node.key)
            if operand is None:
                return _no_number()
            self.errors.append(operand.error)
            self.hidden.append(operand.hidden)
            return operand.number
        if isinstance(node, Negate):
            return -self.value(node.operand)
        if isinstance(node, Binary):
            left, right = self.value(node.left), self.value(node.right)
            if node.operator == "+":
                return left + right
            if node.operator == "-":
                return left - right
            if node.operator == "*":
                return left * right
            self.errors.append(func.coalesce(right == 0, false()))
            return left / func.nullif(right, 0)
        return self.call(node)

    def call(self, node: Call) -> Expression:
        values = [self.value(argument) for argument in node.arguments]
        if node.function == "ROUND":
            places = node.arguments[1]
            assert isinstance(places, Number)  # the parser allows only a literal here
            return func.round(values[0], literal(int(places.text), Integer()), type_=Numeric)
        if node.function == "MIN":
            return func.least(*values, type_=Numeric)
        if node.function == "MAX":
            return func.greatest(*values, type_=Numeric)
        return _aggregate(node.function, values)


def compile_expression(
    node: Node, operands: Mapping[str, Operand],
) -> tuple[Expression, Expression, Expression]:
    """The masked value, the error flag and the hidden flag of one computed column.

    A hidden or erroneous cell has no value, so the sort, the search and the totals treat
    it as blank, as the grid shows it (K6).
    """

    compiler = _Compiler(operands)
    raw = compiler.value(node)
    hidden = _any(compiler.hidden)
    error = _any(compiler.errors)
    masked = case((or_(hidden, error), _no_number()), else_=raw)
    return masked, case((hidden, false()), else_=error), hidden
