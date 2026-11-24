"""Computed-column expressions: the grammar and the save-time checks (spec D7.1, D7.4, S3).

A hand-written recursive-descent parser builds an allowlisted tree; nothing is evaluated
here (D7.2). The editor form names columns (``{Quiz 1}``) and uses the organization's
separators; the stored form names column keys (``{c3}``) with ``.`` and ``,``. An
expression saved unchanged is read in its stored form. Limits hold while parsing: the
length first, then the nesting depth and the node count as the tree grows, so a hostile
expression is refused before it costs recursion or memory. Across columns, a reference
loop, a chain deeper than ten computed columns or an expanded size above 2,000 nodes is
refused, so one save cannot make every read build a huge expression.
"""

import re
from collections.abc import Collection, Iterator, Mapping
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from app.systems.openview.worksheets.structure import (
    MAX_EXPRESSION_CHARACTERS,
    Column,
    SheetComputedColumn,
    SheetFromSheetColumn,
    SheetLookupColumn,
)

# The stored form (keys, spaces around operators) may be longer than the typed one; reads
# and saves share this bound, and route 6's request schema allows it (B10 review B1).
MAX_STORED_CHARACTERS = 2 * MAX_EXPRESSION_CHARACTERS
# Digits a number may carry on each side of the point when it is saved (B10 review U1).
MAX_LITERAL_DIGITS = 38
MAX_NODES = 100
MAX_DEPTH = 20
MAX_CHAIN = 10
MAX_EXPANDED_NODES = 2_000
MAX_ARGUMENTS = 50
NUMERIC_TYPES = frozenset({"number", "decimal", "int"})
_KEY = re.compile(r"c[0-9a-z]{1,8}")
_CELL_REFERENCE = re.compile(r"[A-Za-z]{1,3}[0-9]+")

Function = Literal["SUM", "AVERAGE", "MIN", "MAX", "ROUND"]
Operator = Literal["+", "-", "*", "/"]
_OPERATORS: dict[str, Operator] = {"+": "+", "-": "-", "*": "*", "/": "/"}
_FUNCTIONS: dict[str, Function] = {
    "SUM": "SUM", "AVERAGE": "AVERAGE", "MIN": "MIN", "MAX": "MAX", "ROUND": "ROUND",
}


class ExpressionError(Exception):
    """A refused expression: the column key, a reason code and a message for people."""

    def __init__(self, key: str, reason: str, message: str) -> None:
        super().__init__(message)
        self.key, self.reason, self.message = key, reason, message


@dataclass(frozen=True)
class Number:
    text: str  # canonical digits with "." as the decimal mark

    @property
    def value(self) -> Decimal:
        return Decimal(self.text)


@dataclass(frozen=True)
class Ref:
    key: str


@dataclass(frozen=True)
class Negate:
    operand: "Node"


@dataclass(frozen=True)
class Binary:
    operator: Operator
    left: "Node"
    right: "Node"


@dataclass(frozen=True)
class Call:
    function: Function
    arguments: tuple["Node", ...]


Node = Number | Ref | Negate | Binary | Call


@dataclass(frozen=True)
class Parsed:
    node: Node
    node_count: int


class _Refused(Exception):
    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message)
        self.reason, self.message = reason, message


@dataclass(frozen=True)
class _Token:
    kind: Literal["number", "ref", "word", "op", "open", "close", "separator", "end"]
    text: str


def _tokens(text: str, decimal_mark: str, stored: bool) -> Iterator[_Token]:
    """``stored`` reads the canonical form only: ``.`` in numbers, ``,`` between values."""

    separators = "," if stored else (";" if decimal_mark == "," else ",;")
    marks = "." if stored else (",." if decimal_mark == "," else ".")
    index = 0
    while index < len(text):
        char = text[index]
        if char.isspace():
            index += 1
        elif char.isdigit():
            end = index
            while end < len(text) and text[end].isdigit():
                end += 1
            if end + 1 < len(text) and text[end] in marks and text[end + 1].isdigit():
                end += 1
                while end < len(text) and text[end].isdigit():
                    end += 1
            yield _Token("number", text[index:end].replace(",", "."))
            index = end
        elif char == "{":
            end = text.find("}", index)
            if end < 0:
                raise _Refused("syntax", "a column name is missing its closing }")
            yield _Token("ref", text[index + 1:end])
            index = end + 1
        elif char.isalpha() or char == "_":
            end = index
            while end < len(text) and (text[end].isalnum() or text[end] == "_"):
                end += 1
            yield _Token("word", text[index:end])
            index = end
        elif char in "+-*/":
            yield _Token("op", char)
            index += 1
        elif char in "()":
            yield _Token("open" if char == "(" else "close", char)
            index += 1
        elif char in separators:
            yield _Token("separator", char)
            index += 1
        else:
            raise _Refused("syntax", f"{char!r} is not allowed")
    yield _Token("end", "")


class _Parser:
    def __init__(self, text: str, decimal_mark: str, resolve: "_Resolver", *,
                 stored: bool, saving: bool) -> None:
        self.tokens = list(_tokens(text, decimal_mark, stored))
        self.saving = saving
        self.position = 0
        self.depth = 0
        self.nodes = 0
        self.resolve = resolve

    def peek(self) -> _Token:
        return self.tokens[self.position]

    def take(self) -> _Token:
        token = self.tokens[self.position]
        self.position += 1
        return token

    def counted[N: Node](self, node: N) -> N:
        self.nodes += 1
        if self.nodes > MAX_NODES:
            raise _Refused("too_many_nodes", f"use at most {MAX_NODES} numbers, columns "
                                             "and operations")
        return node

    def nested(self) -> None:
        self.depth += 1
        if self.depth > MAX_DEPTH:
            raise _Refused("too_deep", f"nest at most {MAX_DEPTH} levels")

    def parse(self) -> Parsed:
        node = self.expression()
        if self.peek().kind != "end":
            raise _Refused("syntax", f"unexpected {self.peek().text or 'end'}")
        return Parsed(node, self.nodes)

    def expression(self) -> Node:
        node = self.term()
        while self.peek().kind == "op" and self.peek().text in "+-":
            operator = _OPERATORS[self.take().text]
            node = self.counted(Binary(operator, node, self.term()))
        return node

    def term(self) -> Node:
        node = self.unary()
        while self.peek().kind == "op" and self.peek().text in "*/":
            operator = _OPERATORS[self.take().text]
            node = self.counted(Binary(operator, node, self.unary()))
        return node

    def unary(self) -> Node:
        if self.peek().kind == "op" and self.peek().text == "-":
            self.take()
            self.nested()
            node = self.counted(Negate(self.unary()))
            self.depth -= 1
            return node
        return self.primary()

    def primary(self) -> Node:
        token = self.take()
        if token.kind == "number":
            whole, _point, fraction = token.text.partition(".")
            if self.saving and max(len(whole), len(fraction)) > MAX_LITERAL_DIGITS:
                raise _Refused("number_too_large", f"use at most {MAX_LITERAL_DIGITS} digits "
                                                   "before and after the point")
            return self.counted(Number(token.text))
        if token.kind == "ref":
            return self.counted(Ref(self.resolve(token.text)))
        if token.kind == "open":
            self.nested()
            node = self.expression()
            self.expect("close", "a ( is missing its )")
            self.depth -= 1
            return node
        if token.kind == "word":
            if self.peek().kind == "open":
                return self.call(token.text)
            if _CELL_REFERENCE.fullmatch(token.text):
                raise _Refused("cell_reference", f"cell references such as {token.text} are "
                                                 "not supported; name a column in braces")
            raise _Refused("bare_name", f"{token.text} is not a function; put column names "
                                        "in braces, such as {Quiz 1}")
        raise _Refused("syntax", f"unexpected {token.text or 'end'}")

    def expect(self, kind: str, message: str) -> None:
        if self.take().kind != kind:
            raise _Refused("syntax", message)

    def call(self, word: str) -> Node:
        name = _FUNCTIONS.get(word.upper())
        if name is None:
            raise _Refused("unknown_function", f"{word} is not supported; use "
                                               "SUM, AVERAGE, MIN, MAX or ROUND")
        self.take()  # (
        self.nested()
        self.counted(Call(name, ()))
        arguments: list[Node] = []
        if self.peek().kind != "close":
            arguments.append(self.expression())
            while self.peek().kind == "separator":
                self.take()
                arguments.append(self.expression())
        self.expect("close", f"{name}( is missing its )")
        self.depth -= 1
        if name == "ROUND":
            if len(arguments) != 2:
                raise _Refused("arguments", "ROUND takes a value and a number of places")
            places = arguments[1]
            if not (isinstance(places, Number) and places.text.isdigit()
                    and int(places.text) <= 10):
                raise _Refused("round_places", "ROUND needs a whole number of places "
                                               "from 0 to 10")
        elif not 1 <= len(arguments) <= MAX_ARGUMENTS:
            raise _Refused("arguments", f"{name} takes 1 to {MAX_ARGUMENTS} values")
        return Call(name, tuple(arguments))


class _Resolver:
    """A ``{...}`` reference to a column key: by key in the stored form, by name or key in
    the editor form; a name that is also another column's key is ambiguous."""

    def __init__(self, keys: Collection[str], names: Mapping[str, str], stored: bool) -> None:
        self.keys, self.names, self.stored = keys, names, stored

    def __call__(self, text: str) -> str:
        if self.stored:
            if _KEY.fullmatch(text) and text in self.keys:
                return text
            raise _Refused("unknown_column", f"the sheet has no column {{{text}}}")
        named = self.names.get(text.strip().casefold())
        keyed = text if text in self.keys else None
        if named is not None and keyed is not None and named != keyed:
            raise _Refused("ambiguous_column", f"{{{text}}} is a column name and another "
                                               "column's key; rename the column")
        found = named or keyed
        if found is None:
            raise _Refused("unknown_column", f"the sheet has no column {{{text}}}")
        return found


def _parse(text: str, resolve: _Resolver, decimal_mark: str, *, stored: bool,
           saving: bool) -> Parsed:
    limit = MAX_STORED_CHARACTERS if stored else MAX_EXPRESSION_CHARACTERS
    if len(text) > limit:
        raise _Refused("too_long", f"use at most {MAX_EXPRESSION_CHARACTERS:,} characters")
    if not text.strip():
        raise _Refused("syntax", "enter an expression")
    return _Parser(text, decimal_mark, resolve, stored=stored, saving=saving).parse()


def parse_stored(text: str) -> Parsed:
    """A stored expression, read back for a request: keys only, canonical separators."""

    try:
        return _parse(text, _Resolver(_StoredKeys(), {}, stored=True), ".", stored=True,
                      saving=False)
    except _Refused as refused:
        raise ExpressionError("", refused.reason, refused.message) from refused


class _StoredKeys(set[str]):
    """Any well-formed key: the structure that holds the expression was checked on save."""

    def __contains__(self, item: object) -> bool:
        return isinstance(item, str) and _KEY.fullmatch(item) is not None


_PRECEDENCE: dict[Operator, int] = {"+": 1, "-": 1, "*": 2, "/": 2}


def stored_text(node: Node) -> str:
    """The canonical text of a tree, with brackets only where the tree needs them."""

    if isinstance(node, Number):
        return node.text
    if isinstance(node, Ref):
        return f"{{{node.key}}}"
    if isinstance(node, Negate):
        inner = stored_text(node.operand)
        return f"-({inner})" if isinstance(node.operand, Binary) else f"-{inner}"
    if isinstance(node, Call):
        return f"{node.function}({', '.join(stored_text(item) for item in node.arguments)})"
    level = _PRECEDENCE[node.operator]
    left, right = stored_text(node.left), stored_text(node.right)
    if isinstance(node.left, Binary) and _PRECEDENCE[node.left.operator] < level:
        left = f"({left})"
    if isinstance(node.right, Binary) and _PRECEDENCE[node.right.operator] <= level:
        right = f"({right})"
    return f"{left} {node.operator} {right}"


def renamed(node: Node, keys: Mapping[str, str]) -> Node:
    """The same tree reading ``keys[old]`` wherever it read ``old`` (copies, templates)."""

    if isinstance(node, Ref):
        return Ref(keys.get(node.key, node.key))
    if isinstance(node, Negate):
        return Negate(renamed(node.operand, keys))
    if isinstance(node, Binary):
        return Binary(node.operator, renamed(node.left, keys), renamed(node.right, keys))
    if isinstance(node, Call):
        return Call(node.function, tuple(renamed(item, keys) for item in node.arguments))
    return node


def references(node: Node) -> list[str]:
    """Every column key the tree reads, once per occurrence."""

    if isinstance(node, Ref):
        return [node.key]
    if isinstance(node, Negate):
        return references(node.operand)
    if isinstance(node, Binary):
        return references(node.left) + references(node.right)
    if isinstance(node, Call):
        return [key for item in node.arguments for key in references(item)]
    return []


def _graph(parsed: dict[str, Parsed], names: dict[str, str]) -> None:
    """Loops, the chain depth and the expanded size, each named by its column (D7.4, S3)."""

    state: dict[str, int] = {}  # 1 visiting, 2 done
    depth: dict[str, int] = {}
    expanded: dict[str, int] = {}

    def visit(key: str, path: list[str]) -> None:
        if state.get(key) == 2:
            return
        if state.get(key) == 1:
            cycle = list(dict.fromkeys(path[path.index(key):]))
            raise ExpressionError(key, "loop", f"{names[key]}: the columns "
                                  f"{', '.join(names[item] for item in cycle)} use each other")
        state[key] = 1
        computed = [ref for ref in references(parsed[key].node) if ref in parsed]
        for ref in dict.fromkeys(computed):
            visit(ref, [*path, ref])
        depth[key] = 1 + max((depth[ref] for ref in computed), default=0)
        if depth[key] > MAX_CHAIN:
            raise ExpressionError(key, "chain_too_deep", f"{names[key]}: at most {MAX_CHAIN} "
                                  "computed columns can build on each other")
        size = parsed[key].node_count + sum(expanded[ref] - 1 for ref in computed)
        if size > MAX_EXPANDED_NODES:
            raise ExpressionError(key, "too_large", f"{names[key]}: with the computed columns "
                                  f"it uses, the expression is above {MAX_EXPANDED_NODES:,} "
                                  "parts")
        expanded[key] = size
        state[key] = 2

    for key in parsed:
        visit(key, [key])


_BRACED = re.compile(r"\{([^}]*)\}")


def _keys_only(text: str, keys: Collection[str], names: Mapping[str, str]) -> bool:
    """The text names columns only by key, the way a copy or a template sends it."""

    braced = _BRACED.findall(text)
    return bool(braced) and all(
        item in keys and names.get(item.strip().casefold(), item) == item for item in braced
    )


def _saved_form(column: SheetComputedColumn, keys: Collection[str], names: Mapping[str, str],
                unchanged: Collection[str], decimal_mark: str) -> Parsed:
    """The stored form when the text is saved again or sent in it (B10 review N-2), else
    the editor form with names and the organization's separators."""

    text = column.computed.expression
    if column.key in unchanged:
        return _parse(text, _Resolver(keys, names, True), ".", stored=True, saving=True)
    if _keys_only(text, keys, names):
        try:
            return _parse(text, _Resolver(keys, names, True), ".", stored=True, saving=True)
        except _Refused:
            pass  # typed with keys in the editor form, such as "{c3} * 1,5"
    return _parse(text, _Resolver(keys, names, False), decimal_mark, stored=False, saving=True)


def check_expressions(columns: list[Column], *, numeric_lookups: Collection[str],
                      unchanged: Collection[str], decimal_mark: str) -> dict[str, str]:
    """The stored text of each computed column, or :class:`ExpressionError` (route 6).

    ``numeric_lookups`` are the lookup and From another sheet keys that hold numbers
    (route 6 checks the From another sheet ones across sheets afterwards); ``unchanged`` are
    computed keys saved again with their stored text, read in the stored form.
    """

    keys = {column.key for column in columns}
    names = {column.key: column.name for column in columns}
    by_name = {column.name.strip().casefold(): column.key for column in columns}
    numeric = {
        column.key for column in columns
        if column.type in NUMERIC_TYPES or isinstance(column, SheetComputedColumn)
        or (isinstance(column, SheetLookupColumn | SheetFromSheetColumn)
            and column.key in numeric_lookups)
    }
    parsed: dict[str, Parsed] = {}
    for column in columns:
        if not isinstance(column, SheetComputedColumn):
            continue
        try:
            found = _saved_form(column, keys, by_name, unchanged, decimal_mark)
        except _Refused as refused:
            raise ExpressionError(column.key, refused.reason,
                                  f"{column.name}: {refused.message}") from refused
        if len(stored_text(found.node)) > MAX_STORED_CHARACTERS:
            raise ExpressionError(column.key, "too_long", f"{column.name}: the expression is "
                                  "too long to keep; shorten it")
        for ref in references(found.node):
            if ref not in numeric:
                raise ExpressionError(column.key, "not_numeric",
                                      f"{column.name}: {names[ref]} does not hold numbers")
        parsed[column.key] = found
    _graph(parsed, names)
    return {key: stored_text(found.node) for key, found in parsed.items()}
