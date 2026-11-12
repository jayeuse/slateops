import { expect, test } from "@playwright/test";
import type { OpenViewQueryDefinition } from "../../../src/components/systems/openview/adapters/views-api";
import { serializeOpenViewQueryDefinition } from "../../../src/components/systems/openview/adapters/views-serialization";
import {
  appliedDefinition,
  filterValueForType,
  hasUnsafeIntegerFilter,
  isFilterReady,
  operatorChoices,
  operatorLabel,
} from "../../../src/components/systems/openview/domain/server-view-draft";
import { emptyQuery } from "../../helpers/query-definitions";

const fieldId = "00000000-0000-4000-8000-000000000301";

type Filter = OpenViewQueryDefinition["filters"][number];

function equalsFilter(
  expectedType: Filter["expectedType"],
  value: Filter["value"],
): Filter {
  return { fieldId, expectedType, operator: "eq", value };
}

function definitionWith(filter: Filter): OpenViewQueryDefinition {
  return emptyQuery({ filters: [filter] });
}

// Each typed value reaches the query unchanged: decimal text keeps its
// precision, a number filter sends a number.
for (const current of [
  { type: "decimal", input: "1.25", value: "1.25" },
  { type: "decimal", input: "9007199254740993", value: "9007199254740993" },
  { type: "number", input: "12.5", value: 12.5 },
] as const) {
  test(`a ${current.type} View filter sends ${JSON.stringify(current.input)} as a ${typeof current.value}`, () => {
    const value = filterValueForType(current.type, current.input);
    expect(value).toBe(current.value);
    const filter = equalsFilter(current.type, value);
    expect(isFilterReady(filter)).toBe(true);
    expect(
      serializeOpenViewQueryDefinition(definitionWith(filter)).filters,
    ).toEqual([
      {
        field_id: fieldId,
        expected_type: current.type,
        operator: "eq",
        value: current.value,
      },
    ]);
  });
}

// An integer that a number cannot hold stays text and blocks the query, and a
// cleared number stays blank instead of becoming zero.
for (const current of [
  {
    title: "an integer View filter keeps an unsafe integer as text",
    type: "int",
    input: "9007199254740993",
    value: "9007199254740993",
    unsafe: true,
  },
  {
    title: "an integer View filter keeps a fraction as text",
    type: "int",
    input: "1.0000000000000001",
    value: "1.0000000000000001",
    unsafe: true,
  },
  {
    title: "a cleared number View filter stays blank instead of zero",
    type: "number",
    input: "",
    value: "",
    unsafe: false,
    ready: false,
  },
] as const) {
  test(current.title, () => {
    const value = filterValueForType(current.type, current.input);
    expect(value).toBe(current.value);
    const filter = equalsFilter(current.type, value);
    expect(hasUnsafeIntegerFilter(filter)).toBe(current.unsafe);
    if ("ready" in current) expect(isFilterReady(filter)).toBe(current.ready);
  });
}

// UF-C3.1, UF-C3.4: a read sends only applied conditions. A row without a
// value, an empty choice list, or an unsafe integer stays in the draft only.
test("UF-C3.1 UF-C3.4: a View read keeps only complete conditions without an unsafe integer", () => {
  const complete: Filter = equalsFilter("text", "Pump");
  const noValueNeeded: Filter = {
    fieldId,
    expectedType: "text",
    operator: "empty",
    value: null,
  };
  const choices: Filter = {
    fieldId,
    expectedType: "select",
    operator: "in",
    value: ["00000000-0000-4000-8000-000000000401"],
  };
  const definition = emptyQuery({
    filters: [
      complete,
      equalsFilter("text", ""),
      noValueNeeded,
      { ...choices, value: [] },
      choices,
      equalsFilter("int", "9007199254740993"),
      equalsFilter("int", 12),
    ],
  });

  expect(appliedDefinition(definition)).toEqual({
    ...definition,
    filters: [complete, noValueNeeded, choices, equalsFilter("int", 12)],
  });
});

// UF-C9.3: one "no value" pair in the menu, backed by the stored blank pair;
// a saved condition that still uses empty keeps its operator and reads apart
// where its result differs (text-like fields trim spaces for blank).
test("UF-C9.3: the condition menu offers one no-value pair and a saved empty reads distinctly", () => {
  const labels = (type: Filter["expectedType"]) =>
    operatorChoices(type).map((operator) => operatorLabel(operator, type));
  for (const type of ["text", "number", "select"] as const) {
    expect(operatorChoices(type)).toContain("blank");
    expect(operatorChoices(type)).toContain("not_blank");
    expect(operatorChoices(type)).not.toContain("empty");
    expect(operatorChoices(type)).not.toContain("not_empty");
    expect(labels(type).filter((label) => label === "is empty")).toHaveLength(
      1,
    );
    expect(
      labels(type).filter((label) => label === "is not empty"),
    ).toHaveLength(1);
  }
  // A saved condition keeps its stored operator in the menu.
  expect(operatorChoices("text", "empty")).toContain("empty");
  expect(operatorChoices("text", "not_empty")).toContain("not_empty");
  expect(
    [
      ["empty", "text"],
      ["not_empty", "text"],
      ["empty", "number"],
      ["not_empty", "date"],
      ["blank", "text"],
      ["not_blank", "number"],
    ].map(([operator, type]) =>
      operatorLabel(
        operator as Filter["operator"],
        type as Filter["expectedType"],
      ),
    ),
  ).toEqual([
    "is empty (exact)",
    "is not empty (exact)",
    "is empty",
    "is not empty",
    "is empty",
    "is not empty",
  ]);
});

// UF-C9.3 (review N-1): "(exact)" marks text fields only; a Choice list and
// every other type read the plain words.
test("UF-C9.3: a stored empty reads (exact) on text, long text, email and web link only", () => {
  const read = (type: Filter["expectedType"]) => [
    operatorLabel("empty", type),
    operatorLabel("not_empty", type),
  ];
  for (const type of ["text", "long_text", "email", "url"] as const)
    expect(read(type), type).toEqual([
      "is empty (exact)",
      "is not empty (exact)",
    ]);
  for (const type of ["select", "user", "boolean", "number", "date"] as const)
    expect(read(type), type).toEqual(["is empty", "is not empty"]);
});
