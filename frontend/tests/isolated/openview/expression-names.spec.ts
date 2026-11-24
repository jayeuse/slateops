import { expect, test } from "@playwright/test";
import {
  cellOperand,
  checkExpression,
  decimalMarkOf,
  editorExpression,
  evaluateExpression,
  type ExpressionColumn,
} from "../../../src/components/systems/openview/domain/sheet-expression";

// docs/specs/sheets.md K3 to K5, D7.1, D7.2 and D7.4 (SH-21, SH-22, SH-23):
// a computed column's expression as the editor shows and checks it. The
// stored form names column keys with "." and ","; the editor names columns
// with the organization's separators. The server is the one that saves and
// computes; the editor's result for row 1 is a preview only.

const columns: ExpressionColumn[] = [
  { key: "c1", name: "Quiz 1", numeric: true },
  { key: "c2", name: "Quiz 2", numeric: true },
  { key: "c3", name: "Mid, term", numeric: true },
  { key: "c4", name: "Notes", numeric: false },
  { key: "c5", name: "Final grade", numeric: true },
];

test("a stored expression shows column names and the organization's separators", () => {
  const stored = "ROUND({c1} * 0.3 + {c3}, 2)";
  expect(editorExpression(stored, columns, ".")).toBe(
    "ROUND({Quiz 1} * 0.3 + {Mid, term}, 2)",
  );
  expect(editorExpression(stored, columns, ",")).toBe(
    "ROUND({Quiz 1} * 0,3 + {Mid, term}; 2)",
  );
  // A renamed column shows its new name: the expression stores its key.
  const renamed = columns.map((column) =>
    column.key === "c1" ? { ...column, name: "First quiz" } : column,
  );
  expect(editorExpression("{c1} + {c2}", renamed, ".")).toBe(
    "{First quiz} + {Quiz 2}",
  );
});

test("the decimal mark follows the organization's locale", () => {
  expect(decimalMarkOf("en-US")).toBe(".");
  expect(decimalMarkOf("de-DE")).toBe(",");
  expect(decimalMarkOf("fil-PH")).toBe(".");
});

test("typed names find columns ignoring case, and keys work too; unknown names are named", () => {
  expect(checkExpression("{quiz 1} + {c2}", columns, ".").ok).toBe(true);
  expect(checkExpression("{Quiz 1} + {Quiz 7}", columns, ".")).toEqual({
    ok: false,
    reason: "unknown_column",
    words: "{Quiz 7} is not a column of this sheet.",
    names: ["Quiz 7"],
  });
  expect(
    checkExpression("SUM({Quiz 7}, {Bonus}, {Quiz 1})", columns, "."),
  ).toEqual({
    ok: false,
    reason: "unknown_column",
    words: "{Quiz 7} and {Bonus} are not columns of this sheet.",
    names: ["Quiz 7", "Bonus"],
  });
});

test("each refused expression says why in plain words", () => {
  const cases: [text: string, reason: string, words: string][] = [
    ["{Quiz 1} + {Notes}", "not_numeric", "{Notes} does not hold numbers."],
    ["{Final grade} * 2", "loop", "Final grade cannot use itself."],
    [
      "B2 + {Quiz 1}",
      "cell_reference",
      "Cell references such as B2 are not supported. Name a column in braces, such as {Quiz 1}.",
    ],
    ["Quiz + 1", "bare_name", "Put column names in braces, such as {Quiz 1}."],
    [
      "LOG({Quiz 1})",
      "unknown_function",
      "LOG is not supported. Use SUM, AVERAGE, MIN, MAX or ROUND.",
    ],
    [
      "ROUND({Quiz 1})",
      "arguments",
      "ROUND takes a value and a number of places.",
    ],
    [
      "ROUND({Quiz 1}, 11)",
      "round_places",
      "ROUND needs a whole number of places from 0 to 10.",
    ],
    ["({Quiz 1} + 2", "syntax", "A ( is missing its )."],
    ["{Quiz 1 + 2", "syntax", "A column name is missing its closing }."],
    ["{Quiz 1} % 2", "syntax", "% cannot be used here."],
    [
      `${"(".repeat(21)}1${")".repeat(21)}`,
      "too_deep",
      "Nest at most 20 levels.",
    ],
    [
      Array.from({ length: 51 }, () => "1").join(" + "),
      "too_many_nodes",
      "Use at most 100 numbers, columns and operations.",
    ],
    [
      `{Quiz 1} + ${"1".repeat(1000)}`,
      "too_long",
      "Use at most 1,000 characters.",
    ],
  ];
  for (const [text, reason, words] of cases)
    expect(
      checkExpression(text, columns, ".", "c5"),
      `${reason}: ${text.slice(0, 40)}`,
    ).toMatchObject({ ok: false, reason, words });
});

test("in a comma-decimal locale 1,5 is a number and ; separates values", () => {
  expect(checkExpression("ROUND({Quiz 1} * 1,5; 2)", columns, ",").ok).toBe(
    true,
  );
  expect(
    checkExpression("SUM({Quiz 1}, {Quiz 2})", columns, ","),
  ).toMatchObject({
    ok: false,
    reason: "syntax",
    words: "Separate values with ;.",
  });
  // The same typed text in a dot-decimal locale is not a number.
  expect(checkExpression("ROUND({Quiz 1} * 1,5; 2)", columns, ".").ok).toBe(
    false,
  );
});

test("the preview follows the server's rules for blanks, functions, errors and rounding", () => {
  const cells = {
    c1: { value: "10" },
    c2: { value: null },
    c3: { value: 4 },
    c4: { value: "0" },
    c6: { state: "no_access" as const },
    c7: { value: null, error: "overflow" },
  };
  const scope: ExpressionColumn[] = [
    { key: "c1", name: "A", numeric: true },
    { key: "c2", name: "Blank", numeric: true },
    { key: "c3", name: "C", numeric: true },
    { key: "c4", name: "Zero", numeric: true },
    { key: "c6", name: "Hidden", numeric: true },
    { key: "c7", name: "Broken", numeric: true },
  ];
  const run = (text: string) => {
    const checked = checkExpression(text, scope, ".");
    if (!checked.ok) throw new Error(`${text}: ${checked.words}`);
    return evaluateExpression(checked.node, (key) =>
      cellOperand(cells[key as keyof typeof cells]),
    );
  };
  const cases: [text: string, result: unknown][] = [
    ["{A} + {Blank}", { kind: "blank" }],
    ["SUM({A}, {Blank}, {C})", { kind: "number", value: 14 }],
    ["AVERAGE({A}, {Blank}, {C})", { kind: "number", value: 7 }],
    ["MIN({Blank})", { kind: "blank" }],
    ["MAX({A}, {C}, {Blank})", { kind: "number", value: 10 }],
    ["{A} / {Zero}", { kind: "error", error: "division_by_zero" }],
    ["ROUND(2.5, 0)", { kind: "number", value: 3 }],
    ["ROUND(-2.5, 0)", { kind: "number", value: -3 }],
    ["ROUND(1.005, 2)", { kind: "number", value: 1.01 }],
    ["-{A} + 2 * (3 - 1)", { kind: "number", value: -6 }],
    ["{A} + {Hidden}", { kind: "no_access" }],
    ["{A} + {Broken}", { kind: "error", error: "overflow" }],
  ];
  for (const [text, result] of cases) expect(run(text), text).toEqual(result);
});
