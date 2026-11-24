import { expect, signedInAs, test, type Page } from "./helpers/test";
import {
  installOpenViewEventSource,
  sendOpenViewEvent,
} from "./helpers/openview-event-source";
import {
  installSheetEditApi,
  installSheetPageApi,
  installSheetsApi,
  sheetPeople,
  sheetPlace,
  wireSheetDetail,
  wireSheetRow,
  wireSheetSummary,
} from "./helpers/openview-sheets-api";

// docs/specs/sheets.md K9, D7.3a, D14 S1 and Screens 2 (SH-69 UI): a From
// another sheet column shows a column of another sheet for the same linked
// record. The person picks a sheet they can see, the link columns that
// point to the same module, and the column; the server refuses what it
// cannot accept. A column whose source the editor cannot see comes masked
// and goes back unchanged.

const sheetId = "00000000-0000-4000-8000-000000000ba1";
const sourceId = "00000000-0000-4000-8000-000000000ba2";
const otherId = "00000000-0000-4000-8000-000000000ba3";
const recordId = "00000000-0000-4000-8000-000000000ba4";
const students = "00000000-0000-4000-8000-000000000ba5";
const titleField = "00000000-0000-4000-8000-000000000ba6";
const projects = "00000000-0000-4000-8000-000000000ba7";
const studentId = (index: number) =>
  `00000000-0000-4000-8000-${String(990100 + index).padStart(12, "0")}`;
const names = ["Ana Cruz", "Bea Santos", "Carlo Reyes", "Dina Lopez"];

const member = {
  id: sheetPeople.viewer.id,
  role: "member",
  access: [
    { department_id: sheetPlace.department, module_id: null, level: "read" },
  ],
} as const;

function summary(level: "owner" | "edit") {
  return wireSheetSummary(sheetId, "Summary", {
    recordId,
    recordTitle: "Ana Cruz",
    moduleName: "Contacts",
    owner: level === "owner" ? "viewer" : "colleague",
    level,
    rows: names.length,
  });
}

function sheet(level: "owner" | "edit", extra: unknown[] = []) {
  return {
    detail: {
      ...wireSheetDetail(summary(level)),
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
          { key: "c2", name: "Quiz", type: "int" },
          ...extra,
        ],
        groups: [],
        totals: {},
      },
    },
    rows: names.map((name, index) =>
      wireSheetRow(index, {
        c1: { link: { record_id: studentId(index), label: name } },
        c2: { value: index },
      }),
    ),
    totals: {},
    modules: [{ id: students, name: "Students", titleFieldId: titleField }],
  };
}

/** The source sheet as route 4 answers it to someone who can see it. */
async function installSource(page: Page) {
  const source = wireSheetSummary(sourceId, "Class 1A", {
    owner: "colleague",
    level: "view",
  });
  await page.route(
    (url) => url.pathname === `/api/worksheets/${sourceId}`,
    (route) =>
      route.fulfill({
        json: {
          ...wireSheetDetail(source),
          structure: {
            structureVersion: 1,
            nextColumnSeq: 4,
            columns: [
              {
                key: "c1",
                name: "Learner",
                type: "link",
                link: { moduleId: students },
              },
              {
                key: "c2",
                name: "Final grade",
                type: "computed",
                computed: { expression: "{c3}", places: 2 },
              },
              {
                key: "c3",
                name: "Exam",
                type: "decimal",
                decimal: { places: 2, currency: false },
              },
            ],
            groups: [],
            totals: {},
          },
        },
      }),
  );
  return source;
}

async function openSheet(
  page: Page,
  level: "owner" | "edit",
  extra: unknown[] = [],
) {
  await installOpenViewEventSource(page);
  await signedInAs(page, member);
  // My sheets (route 1): this sheet, the source and a sheet of projects.
  // The routes registered after it answer the two other sheets' details.
  await installSheetsApi(page, {
    live: [
      summary(level),
      wireSheetSummary(sourceId, "Class 1A", {
        owner: "colleague",
        level: "view",
      }),
      wireSheetSummary(otherId, "Budget", { owner: "viewer" }),
    ],
  });
  await installSource(page);
  await page.route(
    (url) => url.pathname === `/api/worksheets/${otherId}`,
    (route) =>
      route.fulfill({
        json: {
          ...wireSheetDetail(wireSheetSummary(otherId, "Budget")),
          structure: {
            structureVersion: 1,
            nextColumnSeq: 2,
            columns: [
              {
                key: "c1",
                name: "Project",
                type: "link",
                link: { moduleId: projects },
              },
            ],
            groups: [],
            totals: {},
          },
        },
      }),
  );
  const api = await installSheetPageApi(page, sheet(level, extra));
  const writes = await installSheetEditApi(page, api);
  await page.goto(`/openview?sheet=${sheetId}`);
  const grid = page.getByRole("grid", { name: "Summary" });
  await expect(
    grid.getByRole("gridcell", { name: /Ana Cruz/ }).first(),
  ).toBeVisible();
  return { api, writes, grid };
}

test("a From another sheet column is chosen from visible sheets, matched by link columns to the same module", async ({
  page,
}) => {
  const { api, writes, grid } = await openSheet(page, "owner");

  await grid.getByRole("button", { name: "Add column" }).click();
  const popover = page.getByRole("dialog", { name: "Add column" });
  await popover
    .getByRole("textbox", { name: "Name", exact: true })
    .fill("Grade in 1A");
  await popover
    .getByRole("combobox", { name: "Type" })
    .selectOption("From another sheet");
  const source = popover.getByRole("combobox", { name: "Sheet" });
  // Not this sheet itself.
  await expect(source.getByRole("option")).toHaveText([
    "Choose a sheet",
    "Class 1A",
    "Budget",
  ]);
  await source.selectOption("Budget");
  await expect(
    popover.getByText(
      "Budget has no link column to the same module as this sheet.",
    ),
  ).toBeVisible();
  await source.selectOption("Class 1A");
  await popover
    .getByRole("combobox", { name: "Match rows by" })
    .selectOption("Student (this sheet) = Learner (Class 1A)");
  const shows = popover.getByRole("combobox", { name: "Shows" });
  await expect(shows.getByRole("option")).toHaveText([
    "Choose a column",
    "Final grade",
    "Exam",
  ]);
  await shows.selectOption("Final grade");

  // A source the server cannot accept: refused with the reason.
  writes.refuseNextStructure = {
    status: 422,
    detail: {
      code: "sheet_lookup_invalid",
      message: "Grade in 1A: choose a sheet you can see",
      key: "c7",
    },
  };
  await popover.getByRole("button", { name: "Add column" }).click();
  await expect(popover.getByRole("alert")).toContainText(
    "Choose a sheet you can see.",
  );

  api.rows[0].cells.c7 = { value: "88.50" };
  api.rows[1].cells.c7 = { state: "no_access" };
  api.rows[2].cells.c7 = { state: "column_removed" };
  api.rows[3].cells.c7 = { state: "multiple_matches", count: 2 };
  await popover.getByRole("button", { name: "Add column" }).click();
  await expect(popover).toBeHidden();
  expect((writes.structures.at(-1)?.body.columns as unknown[]).at(-1)).toEqual({
    key: "c7",
    name: "Grade in 1A",
    type: "sheet_lookup",
    sheet_lookup: {
      sourceWorksheetId: sourceId,
      sourceColumnKey: "c2",
      linkKey: "c1",
      sourceLinkKey: "c1",
    },
  });
  for (const words of ["No access", "Column removed", "2 matches"])
    await expect(grid.getByRole("gridcell", { name: words })).toBeVisible();

  // A change in the source sheet reaches this sheet.
  api.rows[0].cells.c7 = { value: "91.00" };
  await sendOpenViewEvent(page, "invalidate", {
    entity: "worksheets",
    entity_id: sourceId,
  });
  await expect(grid.getByRole("gridcell", { name: "91.00" })).toBeVisible();
});

test("a column whose source the editor cannot see goes back unchanged, and only the owner can delete it", async ({
  page,
}) => {
  const hidden = {
    key: "c5",
    name: "From roster",
    type: "sheet_lookup",
    state: "no_access",
  };
  const bonus = {
    key: "c6",
    name: "Roster bonus",
    type: "computed",
    computed: { expression: "{c5} + 1", places: 0 },
  };
  const { writes, grid } = await openSheet(page, "edit", [hidden, bonus]);

  // A computed column can read it: its name shows, and the stored text goes
  // back unchanged when the computed column is only renamed.
  await grid
    .getByRole("button", { name: "Roster bonus, column settings" })
    .click();
  const settings = page.getByRole("dialog", { name: "Column settings" });
  await expect(
    settings.getByRole("textbox", { name: "Expression" }),
  ).toHaveValue("{From roster} + 1");
  await expect(settings.getByRole("alert")).toHaveCount(0);
  await expect(
    settings
      .getByRole("group", { name: "Insert a column" })
      .getByRole("button", { name: "{From roster}" }),
  ).toBeVisible();
  await settings
    .getByRole("textbox", { name: "Name", exact: true })
    .fill("Bonus");
  await settings.getByRole("button", { name: "Save column" }).click();
  await expect(settings).toBeHidden();
  expect(writes.structures.at(-1)?.body.columns).toContainEqual({
    ...bonus,
    name: "Bonus",
  });

  // Another column can still be added; the masked one goes back as it came.
  await grid.getByRole("button", { name: "Add column" }).click();
  let popover = page.getByRole("dialog", { name: "Add column" });
  await popover
    .getByRole("textbox", { name: "Name", exact: true })
    .fill("Attendance");
  await popover
    .getByRole("combobox", { name: "Type" })
    .selectOption("Whole number");
  await popover.getByRole("button", { name: "Add column" }).click();
  await expect(popover).toBeHidden();
  expect(writes.structures.at(-1)?.body.columns).toContainEqual(hidden);

  await grid
    .getByRole("button", { name: "From roster, column settings" })
    .click();
  popover = page.getByRole("dialog", { name: "Column settings" });
  await expect(
    popover.getByText("From another sheet that you cannot see."),
  ).toBeVisible();
  await popover.getByRole("button", { name: "Delete column" }).click();
  writes.refuseNextStructure = {
    status: 422,
    detail: {
      code: "column_not_visible",
      message:
        "From roster: only the owner can remove a column whose source you cannot see",
      key: "c5",
    },
  };
  popover = page.getByRole("dialog", { name: "Delete From roster?" });
  await popover.getByRole("button", { name: "Delete column" }).click();
  await expect(popover.getByRole("alert")).toContainText(
    "Only the owner can remove a column whose source you cannot see.",
  );
  await expect(
    grid.getByRole("columnheader", { name: /From roster/ }),
  ).toBeVisible();
});
