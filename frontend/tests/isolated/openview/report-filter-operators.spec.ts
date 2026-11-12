import { expect, test } from "@playwright/test";
import { reportOperatorOptions } from "../../../src/components/systems/openview/components/report-recipe-editor";

// UF-C9.3 in Reports: the report editor's condition menu offers one "no
// value" pair, and a stored empty keeps its operator with a distinct label.
test("UF-C9.3: report conditions offer one no-value pair; a stored empty reads (exact) on text", () => {
  const labels = (options: { value: string; label: string }[]) =>
    options.map((option) => option.label);
  expect(labels(reportOperatorOptions("text", "eq"))).toEqual([
    "Is",
    "Is not",
    "Contains",
    "Starts with",
    "Ends with",
    "Is empty",
    "Is not empty",
  ]);
  expect(reportOperatorOptions("text", "empty")).toContainEqual({
    value: "empty",
    label: "Is empty (exact)",
  });
  expect(reportOperatorOptions("number", "not_empty")).toContainEqual({
    value: "not_empty",
    label: "Is not empty",
  });
});
