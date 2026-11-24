import { expect, signedInAs, test, type Page } from "./helpers/test";
import {
  installSheetEditApi,
  installSheetPageApi,
  sheetPeople,
  sheetPlace,
  wireSheetDetail,
  wireSheetRow,
  wireSheetSummary,
} from "./helpers/openview-sheets-api";

// docs/specs/sheets.md K3 to K8, D7.1 to D7.4 and Screens 2 and 3 (SH-21,
// SH-22, SH-23, SH-25, SH-58, SH-72): computed columns, column groups,
// Delete column and the totals' hidden count, in the sheet's editor. The
// expression rules and the preview's arithmetic are owned by the isolated
// expression-names spec; this one proves the journeys.

const sheetId = "00000000-0000-4000-8000-0000000009a1";
const recordId = "00000000-0000-4000-8000-0000000009a2";
const students = "00000000-0000-4000-8000-0000000009a3";
const titleField = "00000000-0000-4000-8000-0000000009a4";
const studentId = (index: number) =>
  `00000000-0000-4000-8000-${String(990000 + index).padStart(12, "0")}`;
const names = ["Ana Cruz", "Bea Santos", "Carlo Reyes"];

const editor = {
  id: sheetPeople.viewer.id,
  role: "member",
  access: [
    { department_id: sheetPlace.department, module_id: null, level: "read" },
  ],
} as const;

function sheet() {
  const summary = wireSheetSummary(sheetId, "Class 1A", {
    recordId,
    recordTitle: "Ana Cruz",
    moduleName: "Contacts",
    level: "owner",
    rows: names.length,
  });
  return {
    detail: {
      ...wireSheetDetail(summary),
      structure: {
        structureVersion: 1,
        nextColumnSeq: 7,
        columns: [
          {
            key: "c1",
            name: "Student",
            type: "link",
            link: { moduleId: students },
          },
          { key: "c2", name: "Quiz 1", type: "int" },
          { key: "c3", name: "Quiz 2", type: "int" },
          { key: "c4", name: "Notes", type: "text" },
          {
            key: "c5",
            name: "Quiz total",
            type: "computed",
            computed: { expression: "{c2} + {c3}", places: 0 },
          },
          {
            key: "c6",
            name: "Average",
            type: "computed",
            computed: { expression: "{c5} / 2", places: 1 },
          },
        ],
        groups: [{ name: "Prelim", keys: ["c2", "c3"] }],
        totals: { c5: "average" },
      },
    },
    rows: names.map((name, index) =>
      wireSheetRow(index, {
        c1: { link: { record_id: studentId(index), label: name } },
        c2: { value: 10 + index },
        c3: { value: 12 },
        c4: { value: null },
        c5: { value: String(22 + index) },
        c6:
          index === 1
            ? { value: null, error: "division_by_zero" }
            : index === 2
              ? { value: null, error: "overflow" }
              : { value: "11.0" },
      }),
    ),
    totals: { c5: { fn: "average", value: "23", hidden_count: 1 } },
    modules: [{ id: students, name: "Students", titleFieldId: titleField }],
  };
}

async function openSheet(page: Page) {
  await signedInAs(page, editor);
  const api = await installSheetPageApi(page, sheet());
  const writes = await installSheetEditApi(page, api);
  await page.goto(`/openview?sheet=${sheetId}`);
  const grid = page.getByRole("grid", { name: "Class 1A" });
  await expect(
    grid.getByRole("gridcell", { name: /Ana Cruz/ }).first(),
  ).toBeVisible();
  return { api, writes, grid };
}

const lastColumns = (writes: {
  structures: { body: Record<string, unknown> }[];
}) => writes.structures.at(-1)?.body.columns as Record<string, unknown>[];

test("a computed column is built from inserted names and functions, previews row 1, and shows its values", async ({
  page,
}) => {
  const { api, writes, grid } = await openSheet(page);

  await grid.getByRole("button", { name: "Add column" }).click();
  const popover = page.getByRole("dialog", { name: "Add column" });
  await popover
    .getByRole("textbox", { name: "Name", exact: true })
    .fill("Best quiz");
  await popover
    .getByRole("combobox", { name: "Type" })
    .selectOption("Computed");
  const expression = popover.getByRole("textbox", { name: "Expression" });
  const columns = popover.getByRole("group", { name: "Insert a column" });
  // Numeric columns only, computed ones included; never a text column.
  await expect(columns.getByRole("button")).toHaveText([
    "{Quiz 1}",
    "{Quiz 2}",
    "{Quiz total}",
    "{Average}",
  ]);

  await columns.getByRole("button", { name: "{Quiz 1}" }).click();
  await expression.press("End");
  await expression.pressSequentially(", ");
  await columns.getByRole("button", { name: "{Quiz 2}" }).click();
  await expression.selectText();
  await popover
    .getByRole("group", { name: "Insert a function" })
    .getByRole("button", { name: "MAX" })
    .click();
  await expect(expression).toHaveValue("MAX({Quiz 1}, {Quiz 2})");
  // Row 1 is Ana Cruz: Quiz 1 10, Quiz 2 12; two places by default.
  await expect(popover.getByText("Row 1, Ana Cruz: 12.00")).toBeVisible();

  for (const row of api.rows) row.cells.c7 = { value: "12.00" };
  await popover.getByRole("button", { name: "Add column" }).click();
  await expect(popover).toBeHidden();
  expect(lastColumns(writes)).toContainEqual({
    key: "c7",
    name: "Best quiz",
    type: "computed",
    computed: { expression: "MAX({Quiz 1}, {Quiz 2})", places: 2 },
  });
  await expect(
    grid.getByRole("columnheader", { name: /Best quiz/ }),
  ).toBeVisible();
  await expect(
    grid.getByRole("gridcell", { name: "12.00" }).first(),
  ).toHaveAttribute("aria-readonly", "true");
});

test("a renamed column keeps every expression that reads it, which then shows the new name", async ({
  page,
}) => {
  const { writes, grid } = await openSheet(page);

  await grid
    .getByRole("button", { name: "Quiz total, column settings" })
    .click();
  let popover = page.getByRole("dialog", { name: "Column settings" });
  await expect(
    popover.getByRole("textbox", { name: "Expression" }),
  ).toHaveValue("{Quiz 1} + {Quiz 2}");
  await popover.getByRole("button", { name: "Cancel" }).click();

  await grid.getByRole("button", { name: "Quiz 1, column settings" }).click();
  popover = page.getByRole("dialog", { name: "Column settings" });
  await popover
    .getByRole("textbox", { name: "Name", exact: true })
    .fill("Prelim quiz");
  await popover.getByRole("button", { name: "Save column" }).click();
  await expect(popover).toBeHidden();
  // The stored expressions go back exactly as they came, with keys.
  expect(lastColumns(writes)).toContainEqual({
    key: "c5",
    name: "Quiz total",
    type: "computed",
    computed: { expression: "{c2} + {c3}", places: 0 },
  });

  await grid
    .getByRole("button", { name: "Quiz total, column settings" })
    .click();
  popover = page.getByRole("dialog", { name: "Column settings" });
  await expect(
    popover.getByRole("textbox", { name: "Expression" }),
  ).toHaveValue("{Prelim quiz} + {Quiz 2}");
});

test("an unknown name is marked and blocks the save; a server refusal shows under the expression", async ({
  page,
}) => {
  const { writes, grid } = await openSheet(page);

  await grid.getByRole("button", { name: "Add column" }).click();
  const popover = page.getByRole("dialog", { name: "Add column" });
  await popover
    .getByRole("textbox", { name: "Name", exact: true })
    .fill("Quiz average");
  await popover
    .getByRole("combobox", { name: "Type" })
    .selectOption("Computed");
  const expression = popover.getByRole("textbox", { name: "Expression" });
  await expression.fill("ROUND(AVERAGE({Quiz 1}, {Quiz 7}), 2)");
  await expect(
    popover.getByText("{Quiz 7} is not a column of this sheet."),
  ).toBeVisible();
  await expect(popover.locator("mark")).toHaveText(["{Quiz 7}"]);
  await expect(expression).toHaveAttribute("aria-invalid", "true");
  const add = popover.getByRole("button", { name: "Add column" });
  await expect(add).toHaveAttribute("aria-disabled", "true");
  await expect(add).toHaveAccessibleDescription("Fix the expression first.");
  expect(writes.structures).toHaveLength(0);

  // The size across computed columns is the server's to check (SH-72).
  await expression.fill("ROUND(AVERAGE({Quiz 1}, {Average}), 2)");
  await expect(add).not.toHaveAttribute("aria-disabled", "true");
  writes.refuseNextStructure = {
    status: 422,
    detail: {
      code: "expression_invalid",
      message:
        "Quiz average: with the computed columns it uses, the expression is above 2,000 parts",
      key: "c7",
      reason: "too_large",
    },
  };
  await add.click();
  await expect(popover.getByRole("alert")).toHaveText(
    "With the computed columns it uses, the expression is above 2,000 parts.",
  );
  await expect(popover).toBeVisible();
  await expect(expression).toHaveValue(
    "ROUND(AVERAGE({Quiz 1}, {Average}), 2)",
  );
});

test("column groups are made, renamed and removed in Column settings, and the band row follows", async ({
  page,
}) => {
  const { writes, grid } = await openSheet(page);
  await expect(
    grid.getByRole("columnheader", { name: "Prelim" }),
  ).toBeVisible();

  // Notes starts a group of its own.
  await grid.getByRole("button", { name: "Notes, column settings" }).click();
  let popover = page.getByRole("dialog", { name: "Column settings" });
  await popover
    .getByRole("combobox", { name: "Column group" })
    .selectOption("New group…");
  await popover
    .getByRole("textbox", { name: "New group's name" })
    .fill("Finals");
  await popover.getByRole("button", { name: "Save column" }).click();
  await expect(popover).toBeHidden();
  expect(writes.structures.at(-1)?.body.groups).toEqual([
    { name: "Prelim", keys: ["c2", "c3"] },
    { name: "Finals", keys: ["c4"] },
  ]);
  await expect(
    grid.getByRole("columnheader", { name: "Finals" }),
  ).toBeVisible();

  // Quiz 2's group is renamed from its settings.
  await grid.getByRole("button", { name: "Quiz 2, column settings" }).click();
  popover = page.getByRole("dialog", { name: "Column settings" });
  await expect(
    popover.getByRole("combobox", { name: "Column group" }),
  ).toHaveValue("g0");
  const groupName = popover.getByRole("textbox", { name: "Group name" });
  await expect(groupName).toHaveAccessibleDescription(
    "Renames the group for all its columns.",
  );
  await groupName.fill("Period 1");
  await popover.getByRole("button", { name: "Save column" }).click();
  await expect(popover).toBeHidden();
  await expect(
    grid.getByRole("columnheader", { name: "Period 1" }),
  ).toBeVisible();

  // Quiz total joins Period 1: it moves next to the group's columns.
  await grid
    .getByRole("button", { name: "Quiz total, column settings" })
    .click();
  popover = page.getByRole("dialog", { name: "Column settings" });
  await popover
    .getByRole("combobox", { name: "Column group" })
    .selectOption("Period 1");
  await popover.getByRole("button", { name: "Save column" }).click();
  await expect(popover).toBeHidden();
  expect(lastColumns(writes).map((column) => column.key)).toEqual([
    "c1",
    "c2",
    "c3",
    "c5",
    "c4",
    "c6",
  ]);
  expect(writes.structures.at(-1)?.body.groups).toEqual([
    { name: "Period 1", keys: ["c2", "c3", "c5"] },
    { name: "Finals", keys: ["c4"] },
  ]);

  // Finals is removed; Notes stays, without a group.
  await grid.getByRole("button", { name: "Notes, column settings" }).click();
  popover = page.getByRole("dialog", { name: "Column settings" });
  await popover.getByRole("button", { name: "Remove group" }).click();
  await popover.getByRole("button", { name: "Save column" }).click();
  await expect(popover).toBeHidden();
  await expect(grid.getByRole("columnheader", { name: "Finals" })).toHaveCount(
    0,
  );
  await expect(grid.getByRole("columnheader", { name: /Notes/ })).toBeVisible();
});

test("Delete column asks first, removes the column, and a refusal names the column that uses it", async ({
  page,
}) => {
  const { writes, grid } = await openSheet(page);

  await grid.getByRole("button", { name: "Notes, column settings" }).click();
  let popover = page.getByRole("dialog", { name: "Column settings" });
  await popover.getByRole("button", { name: "Delete column" }).click();
  popover = page.getByRole("dialog", { name: "Delete Notes?" });
  await expect(
    popover.getByText(
      "It disappears for everyone who can see this sheet. You cannot undo this.",
    ),
  ).toBeVisible();
  await popover.getByRole("button", { name: "Delete column" }).click();
  await expect(popover).toBeHidden();
  expect(lastColumns(writes).map((column) => column.key)).toEqual([
    "c1",
    "c2",
    "c3",
    "c5",
    "c6",
  ]);
  await expect(grid.getByRole("columnheader", { name: /Notes/ })).toHaveCount(
    0,
  );
  // Focus lands on the header that took its place.
  await expect(
    grid.getByRole("button", { name: "Quiz total, column settings" }),
  ).toBeFocused();

  // Quiz total reads Quiz 1, so the server refuses its removal.
  writes.refuseNextStructure = {
    status: 422,
    detail: {
      code: "expression_invalid",
      message: "Quiz total: the sheet has no column {c2}",
      key: "c5",
      reason: "unknown_column",
    },
  };
  await grid.getByRole("button", { name: "Quiz 1, column settings" }).click();
  await page
    .getByRole("dialog", { name: "Column settings" })
    .getByRole("button", { name: "Delete column" })
    .click();
  popover = page.getByRole("dialog", { name: "Delete Quiz 1?" });
  await popover.getByRole("button", { name: "Delete column" }).click();
  await expect(popover.getByRole("alert")).toContainText(
    "Quiz total uses Quiz 1. Change Quiz total first.",
  );
  await expect(
    grid.getByRole("columnheader", { name: /Quiz 1/ }),
  ).toBeVisible();
});

test("cells that cannot be worked out read in words, and a total says how many cells it skipped", async ({
  page,
}) => {
  const { grid } = await openSheet(page);
  await expect(
    grid.getByRole("gridcell", { name: "Division by zero" }),
  ).toBeVisible();
  await expect(
    grid.getByRole("gridcell", { name: "Number too large" }),
  ).toBeVisible();
  await expect(grid.getByText("Average · 1 hidden")).toBeVisible();
  // Long words stay inside their cell, cut with an ellipsis.
  const cell = grid.getByRole("gridcell", { name: "Number too large" });
  const words = cell.getByText("Number too large");
  // A cut word can be read whole on hover.
  await expect(words).toHaveAttribute("title", "Number too large");
  const [outer, inner] = [await cell.boundingBox(), await words.boundingBox()];
  expect(inner && outer && inner.x + inner.width).toBeLessThanOrEqual(
    (outer?.x ?? 0) + (outer?.width ?? 0),
  );
});
