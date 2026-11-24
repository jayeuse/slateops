import type { WorksheetCell } from "../adapters/worksheets-api";

// A computed column's expression in the editor (docs/specs/sheets.md K3 to
// K5, D7.1, D7.2, D7.4). The stored form names column keys ("{c3}") with "."
// in numbers and "," between values; the editor names columns ("{Quiz 1}")
// and uses the organization's separators (";" between values where "," is
// the decimal mark). This mirrors the server's grammar and limits so the
// editor can say what is wrong while the person types, and works out row 1
// as a preview. The server checks and computes again on save and read.

export type ExpressionColumn = { key: string; name: string; numeric: boolean };
export type DecimalMark = "." | ",";

export type ExpressionNode =
  | { kind: "number"; value: number }
  | { kind: "ref"; key: string }
  | { kind: "negate"; operand: ExpressionNode }
  | {
      kind: "binary";
      operator: "+" | "-" | "*" | "/";
      left: ExpressionNode;
      right: ExpressionNode;
    }
  | { kind: "call"; name: ExpressionFunction; args: ExpressionNode[] };

export type ExpressionFunction = "SUM" | "AVERAGE" | "MIN" | "MAX" | "ROUND";
export const EXPRESSION_FUNCTIONS: readonly ExpressionFunction[] = [
  "SUM",
  "AVERAGE",
  "MIN",
  "MAX",
  "ROUND",
];

export type ExpressionCheck =
  | { ok: true; node: ExpressionNode }
  | { ok: false; reason: string; words: string; names: string[] };

const MAX_CHARACTERS = 1000;
const MAX_NODES = 100;
const MAX_DEPTH = 20;
const MAX_ARGUMENTS = 50;
const MAX_LITERAL_DIGITS = 38;
const KEY = /^c[0-9a-z]{1,8}$/;
const CELL_REFERENCE = /^[A-Za-z]{1,3}[0-9]+$/;

export function decimalMarkOf(locale: string): DecimalMark {
  const part = new Intl.NumberFormat(locale)
    .formatToParts(1.5)
    .find((item) => item.type === "decimal");
  return part?.value === "," ? "," : ".";
}

/**
 * The stored text as the editor shows it: names for keys, and in a
 * comma-decimal locale "," in numbers and ";" between values. Text inside
 * braces is a name and never changes its separators.
 */
export function editorExpression(
  stored: string,
  columns: readonly { key: string; name: string }[],
  mark: DecimalMark,
): string {
  const names = new Map(columns.map((column) => [column.key, column.name]));
  let out = "";
  let index = 0;
  while (index < stored.length) {
    const char = stored[index];
    if (char === "{") {
      const end = stored.indexOf("}", index);
      if (end < 0) return out + stored.slice(index);
      const key = stored.slice(index + 1, end);
      out += `{${names.get(key) ?? key}}`;
      index = end + 1;
      continue;
    }
    if (mark === "," && char === ".") out += ",";
    else if (mark === "," && char === ",") out += ";";
    else out += char;
    index += 1;
  }
  return out;
}

class Refused extends Error {
  constructor(
    readonly reason: string,
    readonly words: string,
    readonly names: string[] = [],
  ) {
    super(words);
  }
}

type Token =
  | { kind: "number"; text: string }
  | { kind: "ref"; text: string }
  | { kind: "word"; text: string }
  | { kind: "op"; text: "+" | "-" | "*" | "/" }
  | { kind: "open" | "close" | "separator" | "end"; text: string };

const isDigit = (char: string | undefined) =>
  char !== undefined && char >= "0" && char <= "9";
const isWordStart = (char: string) => /\p{L}|_/u.test(char);
const isWordPart = (char: string | undefined) =>
  char !== undefined && /[\p{L}\p{N}_]/u.test(char);

function tokens(text: string, mark: DecimalMark): Token[] {
  const separators = mark === "," ? ";" : ",;";
  const marks = mark === "," ? ",." : ".";
  const found: Token[] = [];
  let index = 0;
  while (index < text.length) {
    const char = text[index];
    if (/\s/.test(char)) index += 1;
    else if (isDigit(char)) {
      let end = index;
      while (isDigit(text[end])) end += 1;
      if (marks.includes(text[end] ?? "") && isDigit(text[end + 1])) {
        end += 1;
        while (isDigit(text[end])) end += 1;
      }
      found.push({
        kind: "number",
        text: text.slice(index, end).replace(",", "."),
      });
      index = end;
    } else if (char === "{") {
      const end = text.indexOf("}", index);
      if (end < 0)
        throw new Refused("syntax", "A column name is missing its closing }.");
      found.push({ kind: "ref", text: text.slice(index + 1, end) });
      index = end + 1;
    } else if (isWordStart(char)) {
      let end = index;
      while (isWordPart(text[end])) end += 1;
      found.push({ kind: "word", text: text.slice(index, end) });
      index = end;
    } else if (char === "+" || char === "-" || char === "*" || char === "/") {
      found.push({ kind: "op", text: char });
      index += 1;
    } else if (char === "(" || char === ")") {
      found.push({ kind: char === "(" ? "open" : "close", text: char });
      index += 1;
    } else if (separators.includes(char)) {
      found.push({ kind: "separator", text: char });
      index += 1;
    } else if (char === "," && mark === ",")
      throw new Refused("syntax", "Separate values with ;.");
    else throw new Refused("syntax", `${char} cannot be used here.`);
  }
  found.push({ kind: "end", text: "" });
  return found;
}

class Parser {
  private position = 0;
  private depth = 0;
  private nodes = 0;

  constructor(
    private readonly list: Token[],
    private readonly resolve: (text: string) => string,
  ) {}

  private peek() {
    return this.list[this.position];
  }

  private take() {
    const token = this.list[this.position];
    this.position += 1;
    return token;
  }

  private counted<N extends ExpressionNode>(node: N): N {
    this.nodes += 1;
    if (this.nodes > MAX_NODES)
      throw new Refused(
        "too_many_nodes",
        `Use at most ${MAX_NODES} numbers, columns and operations.`,
      );
    return node;
  }

  private nested() {
    this.depth += 1;
    if (this.depth > MAX_DEPTH)
      throw new Refused("too_deep", `Nest at most ${MAX_DEPTH} levels.`);
  }

  parse(): ExpressionNode {
    const node = this.expression();
    if (this.peek().kind !== "end") throw this.unexpected(this.peek());
    return node;
  }

  private unexpected(token: Token) {
    return new Refused(
      "syntax",
      token.kind === "end"
        ? "The expression ends too early."
        : `${token.text} is not expected here.`,
    );
  }

  private expression(): ExpressionNode {
    let node = this.term();
    for (;;) {
      const token = this.peek();
      if (token.kind !== "op" || (token.text !== "+" && token.text !== "-"))
        return node;
      this.take();
      node = this.counted({
        kind: "binary",
        operator: token.text,
        left: node,
        right: this.term(),
      });
    }
  }

  private term(): ExpressionNode {
    let node = this.unary();
    for (;;) {
      const token = this.peek();
      if (token.kind !== "op" || (token.text !== "*" && token.text !== "/"))
        return node;
      this.take();
      node = this.counted({
        kind: "binary",
        operator: token.text,
        left: node,
        right: this.unary(),
      });
    }
  }

  private unary(): ExpressionNode {
    const token = this.peek();
    if (token.kind === "op" && token.text === "-") {
      this.take();
      this.nested();
      const node = this.counted<ExpressionNode>({
        kind: "negate",
        operand: this.unary(),
      });
      this.depth -= 1;
      return node;
    }
    return this.primary();
  }

  private primary(): ExpressionNode {
    const token = this.take();
    if (token.kind === "number") {
      const [whole, fraction = ""] = token.text.split(".");
      if (Math.max(whole.length, fraction.length) > MAX_LITERAL_DIGITS)
        throw new Refused(
          "number_too_large",
          `Use at most ${MAX_LITERAL_DIGITS} digits before and after the point.`,
        );
      return this.counted({ kind: "number", value: Number(token.text) });
    }
    if (token.kind === "ref")
      return this.counted({ kind: "ref", key: this.resolve(token.text) });
    if (token.kind === "open") {
      this.nested();
      const node = this.expression();
      this.expect("close", "A ( is missing its ).");
      this.depth -= 1;
      return node;
    }
    if (token.kind === "word") {
      if (this.peek().kind === "open") return this.call(token.text);
      if (CELL_REFERENCE.test(token.text))
        throw new Refused(
          "cell_reference",
          `Cell references such as ${token.text} are not supported. Name a column in braces, such as {Quiz 1}.`,
        );
      throw new Refused(
        "bare_name",
        "Put column names in braces, such as {Quiz 1}.",
      );
    }
    throw this.unexpected(token);
  }

  private expect(kind: Token["kind"], words: string) {
    if (this.take().kind !== kind) throw new Refused("syntax", words);
  }

  private call(word: string): ExpressionNode {
    const name = EXPRESSION_FUNCTIONS.find(
      (item) => item === word.toUpperCase(),
    );
    if (!name)
      throw new Refused(
        "unknown_function",
        `${word} is not supported. Use SUM, AVERAGE, MIN, MAX or ROUND.`,
      );
    this.take();
    this.nested();
    this.counted({ kind: "call", name, args: [] });
    const args: ExpressionNode[] = [];
    if (this.peek().kind !== "close") {
      args.push(this.expression());
      while (this.peek().kind === "separator") {
        this.take();
        args.push(this.expression());
      }
    }
    this.expect("close", `${name}( is missing its ).`);
    this.depth -= 1;
    if (name === "ROUND") {
      if (args.length !== 2)
        throw new Refused(
          "arguments",
          "ROUND takes a value and a number of places.",
        );
      const places = args[1];
      if (
        places.kind !== "number" ||
        !Number.isInteger(places.value) ||
        places.value > 10
      )
        throw new Refused(
          "round_places",
          "ROUND needs a whole number of places from 0 to 10.",
        );
    } else if (args.length < 1 || args.length > MAX_ARGUMENTS)
      throw new Refused(
        "arguments",
        `${name} takes 1 to ${MAX_ARGUMENTS} values.`,
      );
    return { kind: "call", name, args };
  }
}

function joinNames(names: string[]): string {
  const braced = names.map((name) => `{${name}}`);
  return braced.length === 1
    ? braced[0]
    : `${braced.slice(0, -1).join(", ")} and ${braced.at(-1)}`;
}

/** The braced names of a text, in order, each once. */
function bracedNames(text: string): string[] {
  return [
    ...new Set([...text.matchAll(/\{([^}]*)\}/g)].map((match) => match[1])),
  ];
}

/**
 * Checks a typed expression as the server will: names (any case) or keys in
 * braces, numeric columns only, not the column itself. `self` is the key of
 * the column being edited.
 */
export function checkExpression(
  text: string,
  columns: readonly ExpressionColumn[],
  mark: DecimalMark,
  self?: string,
): ExpressionCheck {
  const byName = new Map(
    columns.map((column) => [column.name.trim().toLowerCase(), column]),
  );
  const byKey = new Map(columns.map((column) => [column.key, column]));
  const find = (name: string) =>
    byName.get(name.trim().toLowerCase()) ??
    (KEY.test(name) ? byKey.get(name) : undefined);
  try {
    if (text.length > MAX_CHARACTERS)
      throw new Refused(
        "too_long",
        `Use at most ${MAX_CHARACTERS.toLocaleString("en-US")} characters.`,
      );
    if (!text.trim()) throw new Refused("syntax", "Enter an expression.");
    const unknown = bracedNames(text).filter((name) => !find(name));
    if (unknown.length)
      throw new Refused(
        "unknown_column",
        `${joinNames(unknown)} ${unknown.length === 1 ? "is not a column" : "are not columns"} of this sheet.`,
        unknown,
      );
    for (const name of bracedNames(text)) {
      const column = find(name);
      if (column && column.key === self)
        throw new Refused("loop", `${column.name} cannot use itself.`, [name]);
      if (column && !column.numeric)
        throw new Refused(
          "not_numeric",
          `{${column.name}} does not hold numbers.`,
          [name],
        );
    }
    const node = new Parser(tokens(text, mark), (name) => {
      const column = find(name);
      if (!column)
        throw new Refused(
          "unknown_column",
          `{${name}} is not a column of this sheet.`,
          [name],
        );
      return column.key;
    }).parse();
    return { ok: true, node };
  } catch (error) {
    if (error instanceof Refused)
      return {
        ok: false,
        reason: error.reason,
        words: error.words,
        names: error.names,
      };
    throw error;
  }
}

// ------------------------------------------------------------- the preview

export type Operand =
  | { kind: "number"; value: number }
  | { kind: "blank" }
  | { kind: "error"; error: string }
  | { kind: "no_access" };

/** A cell as an expression reads it (D7.2, D7.3). */
export function cellOperand(cell: WorksheetCell | undefined): Operand {
  if (!cell) return { kind: "blank" };
  if ("error" in cell) return { kind: "error", error: cell.error };
  if ("state" in cell)
    return cell.state === "no_access"
      ? { kind: "no_access" }
      : { kind: "blank" };
  if (!("value" in cell)) return { kind: "blank" };
  const value = cell.value;
  const number =
    typeof value === "number"
      ? value
      : typeof value === "string" && value.trim() !== ""
        ? Number(value)
        : NaN;
  return Number.isFinite(number)
    ? { kind: "number", value: number }
    : { kind: "blank" };
}

/** The first error, then No access, then a blank, among the operands. */
function stopper(operands: Operand[]): Operand | null {
  return (
    operands.find((item) => item.kind === "error") ??
    operands.find((item) => item.kind === "no_access") ??
    null
  );
}

function finite(value: number): Operand {
  return Number.isFinite(value)
    ? { kind: "number", value }
    : { kind: "error", error: "overflow" };
}

/** Rounds half away from zero, as PostgreSQL's round(numeric, n) does. */
function roundAway(value: number, places: number): number {
  const shifted = Number(`${Math.abs(value)}e${places}`);
  return Math.sign(value) * Number(`${Math.round(shifted)}e-${places}`);
}

/**
 * Works out a tree for one row. A blank operand gives a blank; the
 * functions skip blanks; division by zero is an error (D7.2).
 */
export function evaluateExpression(
  node: ExpressionNode,
  read: (key: string) => Operand,
): Operand {
  switch (node.kind) {
    case "number":
      return { kind: "number", value: node.value };
    case "ref":
      return read(node.key);
    case "negate": {
      const operand = evaluateExpression(node.operand, read);
      return operand.kind === "number"
        ? { kind: "number", value: -operand.value }
        : operand;
    }
    case "binary": {
      const left = evaluateExpression(node.left, read);
      const right = evaluateExpression(node.right, read);
      const stop = stopper([left, right]);
      if (stop) return stop;
      if (left.kind !== "number" || right.kind !== "number")
        return { kind: "blank" };
      if (node.operator === "/")
        return right.value === 0
          ? { kind: "error", error: "division_by_zero" }
          : finite(left.value / right.value);
      return finite(
        node.operator === "+"
          ? left.value + right.value
          : node.operator === "-"
            ? left.value - right.value
            : left.value * right.value,
      );
    }
    case "call": {
      const args = node.args.map((arg) => evaluateExpression(arg, read));
      const stop = stopper(args);
      if (stop) return stop;
      if (node.name === "ROUND") {
        const [value, places] = args;
        if (value.kind !== "number" || places.kind !== "number")
          return { kind: "blank" };
        return finite(roundAway(value.value, places.value));
      }
      const values = args.flatMap((arg) =>
        arg.kind === "number" ? [arg.value] : [],
      );
      if (values.length === 0) return { kind: "blank" };
      const sum = values.reduce((total, value) => total + value, 0);
      return finite(
        node.name === "SUM"
          ? sum
          : node.name === "AVERAGE"
            ? sum / values.length
            : node.name === "MIN"
              ? Math.min(...values)
              : Math.max(...values),
      );
    }
  }
}
