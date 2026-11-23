import { expect, signedInAs, test, type Page } from "./helpers/test";
import { memberCard } from "./helpers/person-card-api";
import {
  installSheetEditApi,
  installSheetPageApi,
  sheetPeople,
  sheetPlace,
  wireSheetDetail,
  wireSheetRow,
  wireSheetSummary,
} from "./helpers/openview-sheets-api";

// docs/specs/sheets.md F4, K1, P9, X11 (SH-20, SH-26, SH-42, SH-54) and
// Screens 2 and 3: editing a sheet.

const sheetId = "00000000-0000-4000-8000-0000000008a1";
const recordId = "00000000-0000-4000-8000-0000000008a2";
const students = "00000000-0000-4000-8000-0000000008a3";
const titleField = "00000000-0000-4000-8000-0000000008a4";
const numberField = "00000000-0000-4000-8000-0000000008a5";
const teacherId = "00000000-0000-4000-8000-0000000008a6";
const alice = "00000000-0000-4000-8000-0000000008b1";
const mara = {
  id: "00000000-0000-4000-8000-0000000008b2",
  display_name: "Mara Diaz",
};
const studentId = (index: number) =>
  `00000000-0000-4000-8000-${String(880000 + index).padStart(12, "0")}`;
const names = [
  "Ana Cruz",
  "Bea Santos",
  "Carlo Reyes",
  "Diego Navarro",
  "Elena Cruz",
];

const reader = {
  id: sheetPeople.viewer.id,
  role: "member",
  access: [
    { department_id: sheetPlace.department, module_id: null, level: "read" },
  ],
} as const;

function sheet(level: "owner" | "view" = "owner") {
  const summary = wireSheetSummary(sheetId, "Class roster", {
    recordId,
    recordTitle: "Ana Cruz",
    moduleName: "Contacts",
    owner: level === "owner" ? "viewer" : "colleague",
    level,
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
          {
            key: "c2",
            name: "Student number",
            type: "lookup",
            lookup: { linkKey: "c1", fieldId: numberField },
          },
          { key: "c3", name: "Quiz 1", type: "int" },
          {
            key: "c4",
            name: "Remarks",
            type: "select",
            select: {
              options: [
                { id: "o1", label: "Passed" },
                { id: "o2", label: "Failed" },
              ],
            },
          },
          { key: "c5", name: "Notes", type: "text" },
          { key: "c6", name: "Teacher", type: "user" },
        ],
        groups: [],
        totals: { c3: "average" },
      },
    },
    rows: names.map((name, index) =>
      wireSheetRow(index, {
        c1: { link: { record_id: studentId(index), label: name } },
        c2: { value: `S-${index + 1}` },
        c3: { value: 10 + index * 2 },
        c4: { value: "o1" },
        c5: { value: null },
        c6: { value: teacherId },
      }),
    ),
    totals: { c3: { fn: "average", value: "14", hidden_count: 0 } },
    modules: [{ id: students, name: "Students", titleFieldId: titleField }],
  };
}

async function openSheet(page: Page, level: "owner" | "view" = "owner") {
  await signedInAs(page, reader);
  await page.route(`**/api/users/${teacherId}/card`, (route) =>
    route.fulfill({ json: { ...memberCard, display_name: "Rosa Lim" } }),
  );
  await page.route(`**/api/users/${mara.id}/card`, (route) =>
    route.fulfill({ json: { ...memberCard, display_name: mara.display_name } }),
  );
  const data = sheet(level);
  const api = await installSheetPageApi(page, data);
  const writes = await installSheetEditApi(page, api, {
    linkTargets: [
      {
        moduleId: students,
        titleFieldId: titleField,
        id: alice,
        title: "Alice Reyes",
      },
    ],
    moduleFields: {
      [students]: [
        { id: titleField, name: "Name", type: "text" },
        { id: numberField, name: "Student number", type: "text" },
      ],
    },
    people: [mara, { id: teacherId, display_name: "Rosa Lim" }],
  });
  await page.goto(`/openview?sheet=${sheetId}`);
  const grid = page.getByRole("grid", { name: "Class roster" });
  await expect(
    grid.getByRole("gridcell", { name: /Ana Cruz/ }).first(),
  ).toBeVisible();
  return { api, writes, grid };
}

function cell(page: Page, row: number, column: string) {
  return page
    .getByRole("grid", { name: "Class roster" })
    .locator(`[data-cell="${row}:${column}"]`);
}

test("a keyboard editor moves between cells, edits one, and saves only a change", async ({
  page,
}) => {
  const { writes, grid } = await openSheet(page);
  await expect(grid).not.toHaveAttribute("aria-readonly", "true");
  // A person cell names the person.
  await expect(cell(page, 0, "c6")).toHaveText("Rosa Lim");

  // One tab stop: Tab from Sort lands on the grid's first cell.
  await page.getByRole("button", { name: "Sort" }).focus();
  await page.keyboard.press("Tab");
  await expect(cell(page, 0, "c1")).toBeFocused();
  await page.keyboard.press("ArrowRight");
  await page.keyboard.press("ArrowRight");
  const quiz = cell(page, 0, "c3");
  await expect(quiz).toBeFocused();
  await expect(quiz).toHaveCSS("outline-width", "2px");

  await page.keyboard.press("Enter");
  const editor = grid.getByRole("textbox", { name: "Quiz 1, row 1" });
  await expect(editor).toHaveValue("10");
  await editor.fill("99");
  await page.keyboard.press("Escape");
  await expect(editor).toHaveCount(0);
  await expect(quiz).toHaveText("10");
  await expect(quiz).toBeFocused();

  // Enter with no change sends nothing.
  await page.keyboard.press("Enter");
  await page.keyboard.press("Enter");
  expect(writes.patches).toEqual([]);

  await page.keyboard.press("Enter");
  await grid.getByRole("textbox", { name: "Quiz 1, row 1" }).fill("18");
  await page.keyboard.press("Enter");
  await expect(quiz).toHaveText("18");
  expect(writes.patches).toEqual([
    {
      rowId: wireSheetRow(0, {}).id,
      cells: { c3: { value: "18", expected: { value: 10 } } },
    },
  ]);
  await expect(page.getByText("Saved", { exact: true })).toBeVisible();
  // Lookup cells take no edit.
  await page.keyboard.press("ArrowLeft");
  await page.keyboard.press("Enter");
  await expect(grid.getByRole("textbox")).toHaveCount(0);
});

test("a cell someone else changed shows the newer value and the conflict row", async ({
  page,
}) => {
  const { api, writes, grid } = await openSheet(page);
  // Another editor changes Bea's Quiz 1 after this page loaded it.
  api.rows[1].cells.c3 = { value: 7 };

  await cell(page, 1, "c3").dblclick();
  await grid.getByRole("textbox", { name: "Quiz 1, row 2" }).fill("15");
  await page.keyboard.press("Enter");

  const note = grid.getByRole("status").filter({ hasText: "changed this row" });
  await expect(note).toContainText(
    "Someone changed this row while you were editing it. It now shows the newer values. Your Quiz 1 (15) was not saved.",
  );
  await expect(cell(page, 1, "c3")).toHaveText("7");
  await expect(page.getByText("1 change not saved")).toBeVisible();

  await note.getByRole("button", { name: "Edit Quiz 1 again" }).click();
  const editor = grid.getByRole("textbox", { name: "Quiz 1, row 2" });
  await expect(editor).toHaveValue("15");
  await page.keyboard.press("Enter");
  await expect(cell(page, 1, "c3")).toHaveText("15");
  await expect(note).toHaveCount(0);
  expect(writes.patches.at(-1)?.cells).toEqual({
    c3: { value: "15", expected: { value: 7 } },
  });
  await expect(page.getByText("Saved", { exact: true })).toBeVisible();
});

test("a refused value keeps the editor and says why", async ({ page }) => {
  const { writes, grid } = await openSheet(page);
  writes.refuseNextPatch = {
    status: 422,
    code: "cell_invalid",
    message: "Enter a number",
  };
  await cell(page, 0, "c3").dblclick();
  const editor = grid.getByRole("textbox", { name: "Quiz 1, row 1" });
  await editor.fill("ten");
  await page.keyboard.press("Enter");
  await expect(
    page.getByRole("alert").filter({ hasText: "Quiz 1" }),
  ).toContainText("Quiz 1: Enter a number");
  await expect(editor).toHaveValue("ten");
});

test("rows are added at the end and deleted with their version", async ({
  page,
}) => {
  const { api, writes, grid } = await openSheet(page);
  await grid.getByRole("button", { name: "Add row" }).click();
  await expect(grid.locator("[data-cell^='5:']").first()).toBeVisible();
  expect(writes.creates).toEqual([{}]);

  const deleted = api.rows[0];
  await grid.getByRole("button", { name: "Row 1 actions" }).click();
  await page.getByRole("menuitem", { name: "Delete row" }).click();
  const confirm = page.getByRole("alertdialog", { name: "Delete row 1?" });
  await expect(confirm).toContainText(
    "It leaves this sheet for everyone who can see it. You cannot undo this.",
  );
  await confirm.getByRole("button", { name: "Delete row" }).click();
  await expect(grid.getByRole("gridcell", { name: "Ana Cruz" })).toHaveCount(0);
  expect(writes.deletes).toEqual([
    { rowId: deleted.id, ifMatch: deleted.etag },
  ]);
});

test("Add column and Column settings save the column list with the sheet's version", async ({
  page,
}) => {
  const { api, writes, grid } = await openSheet(page);
  const etag = api.detail?.etag;

  await grid.getByRole("button", { name: "Add column" }).click();
  let popover = page.getByRole("dialog", { name: "Add column" });
  await popover.getByRole("textbox", { name: "Name" }).fill("Attendance");
  await popover
    .getByRole("combobox", { name: "Type" })
    .selectOption("Whole number");
  await popover
    .getByRole("combobox", { name: "Total" })
    .selectOption("Average");
  await popover.getByRole("button", { name: "Add column" }).click();
  await expect(
    grid.getByRole("columnheader", { name: /Attendance/ }),
  ).toBeVisible();
  expect(writes.structures[0].ifMatch).toBe(etag);
  expect(writes.structures[0].body.columns).toContainEqual({
    key: "c7",
    name: "Attendance",
    type: "int",
  });
  expect(writes.structures[0].body.totals).toEqual({
    c3: "average",
    c7: "average",
  });

  // A link column to a readable module, then a lookup through it.
  await grid.getByRole("button", { name: "Add column" }).click();
  popover = page.getByRole("dialog", { name: "Add column" });
  await popover.getByRole("textbox", { name: "Name" }).fill("Buddy");
  await popover
    .getByRole("combobox", { name: "Type" })
    .selectOption("Link to records");
  await popover
    .getByRole("combobox", { name: "Links to" })
    .selectOption("Students");
  await popover.getByRole("button", { name: "Add column" }).click();
  await expect(grid.getByRole("columnheader", { name: /Buddy/ })).toBeVisible();
  expect(writes.structures[1].body.columns).toContainEqual({
    key: "c8",
    name: "Buddy",
    type: "link",
    link: { moduleId: students },
  });

  await grid.getByRole("button", { name: "Add column" }).click();
  popover = page.getByRole("dialog", { name: "Add column" });
  await popover.getByRole("textbox", { name: "Name" }).fill("Buddy number");
  await popover.getByRole("combobox", { name: "Type" }).selectOption("Lookup");
  await popover.getByRole("combobox", { name: "From" }).selectOption("Buddy");
  await popover
    .getByRole("combobox", { name: "Shows" })
    .selectOption("Student number");
  await popover.getByRole("button", { name: "Add column" }).click();
  expect(writes.structures[2].body.columns).toContainEqual({
    key: "c9",
    name: "Buddy number",
    type: "lookup",
    lookup: { linkKey: "c8", fieldId: numberField },
  });

  await grid.getByRole("button", { name: "Notes, column settings" }).click();
  popover = page.getByRole("dialog", { name: "Column settings" });
  await popover.getByRole("textbox", { name: "Name" }).fill("Comments");
  await popover.getByRole("button", { name: "Save column" }).click();
  await expect(
    grid.getByRole("columnheader", { name: /Comments/ }),
  ).toBeVisible();
  expect(writes.structures[3].body.columns).toContainEqual({
    key: "c5",
    name: "Comments",
    type: "text",
  });
});

test("a link cell offers only records the person can read; a choice cell its choices", async ({
  page,
}) => {
  const { writes, grid } = await openSheet(page);
  await cell(page, 2, "c1").focus();
  await page.keyboard.press("Enter");
  const picker = page.getByRole("dialog", { name: "Choose Student" });
  // The record linked now is one step away.
  await expect(
    picker.getByRole("link", { name: "Open Carlo Reyes's record" }),
  ).toBeVisible();
  await picker.getByRole("searchbox", { name: "Search Students" }).fill("Ali");
  await picker.getByRole("button", { name: "Alice Reyes" }).click();
  await expect(cell(page, 2, "c1")).toHaveText("Alice Reyes");
  expect(writes.patches.at(-1)?.cells).toEqual({
    c1: {
      value: { record_id: alice },
      expected: { link: { record_id: studentId(2), label: "Carlo Reyes" } },
    },
  });

  await cell(page, 2, "c4").dblclick();
  await grid
    .getByRole("combobox", { name: "Remarks, row 3" })
    .selectOption("Failed");
  await expect(cell(page, 2, "c4")).toHaveText("Failed");
  expect(writes.patches.at(-1)?.cells).toEqual({
    c4: { value: "o2", expected: { value: "o1" } },
  });
});

test("a viewer reads only: no editor, no Add row, no Add column", async ({
  page,
}) => {
  const { writes, grid } = await openSheet(page, "view");
  await expect(grid).toHaveAttribute("aria-readonly", "true");
  await cell(page, 0, "c3").focus();
  await page.keyboard.press("Enter");
  await expect(grid.getByRole("textbox")).toHaveCount(0);
  await expect(grid.getByRole("button", { name: "Add row" })).toHaveCount(0);
  await expect(grid.getByRole("button", { name: "Add column" })).toHaveCount(0);
  expect(writes.patches).toEqual([]);
});

test("a conflict names who changed the row when the editor can see them", async ({
  page,
}) => {
  const { api, writes, grid } = await openSheet(page);
  writes.changedBy = {
    id: "00000000-0000-4000-8000-0000000008c9",
    display_name: "Diego Navarro",
  };
  api.rows[1].cells.c3 = { value: 7 };
  await cell(page, 1, "c3").dblclick();
  await grid.getByRole("textbox", { name: "Quiz 1, row 2" }).fill("15");
  await page.keyboard.press("Enter");
  await expect(
    grid.getByRole("status").filter({ hasText: "changed this row" }),
  ).toContainText(
    "Diego Navarro changed this row while you were editing it. It now shows the newer values. Your Quiz 1 (15) was not saved.",
  );
});

test("a person cell takes one of the people the editor can see", async ({
  page,
}) => {
  const { writes, grid } = await openSheet(page);
  await cell(page, 0, "c6").focus();
  await page.keyboard.press("Enter");
  const picker = page.getByRole("dialog", { name: "Choose Teacher" });
  await picker.getByRole("searchbox", { name: "Search people" }).fill("ma");
  await picker.getByRole("button", { name: "Mara Diaz" }).click();
  await expect(cell(page, 0, "c6")).toHaveText("Mara Diaz");
  expect(writes.patches.at(-1)?.cells).toEqual({
    c6: { value: mara.id, expected: { value: teacherId } },
  });
  await expect(cell(page, 0, "c6")).toBeFocused();
  await expect(grid).not.toHaveAttribute("aria-readonly", "true");
});

test("the keyboard reaches a row's actions from its first cell, and the grid counts its header rows", async ({
  page,
}) => {
  const { grid } = await openSheet(page);
  // One header row, five rows, Add row and the totals row.
  await expect(grid).toHaveAttribute("aria-rowcount", "8");
  await expect(grid.getByRole("row").nth(1)).toHaveAttribute(
    "aria-rowindex",
    "2",
  );
  await cell(page, 0, "c1").focus();
  await page.keyboard.press("ArrowLeft");
  const actions = grid.getByRole("button", { name: "Row 1 actions" });
  await expect(actions).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(
    page.getByRole("menuitem", { name: "Delete row" }),
  ).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(actions).toBeFocused();
  await page.keyboard.press("ArrowRight");
  await expect(cell(page, 0, "c1")).toBeFocused();
});

test("a viewer opens a linked record with Enter", async ({ page }) => {
  await openSheet(page, "view");
  await cell(page, 0, "c1").focus();
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(new RegExp(`record=${studentId(0)}`));
});

test("a paste lands only on a cell, never from a row's actions", async ({
  page,
}) => {
  const { writes } = await openSheet(page);
  const paste = (text: string) =>
    page.evaluate((value) => {
      const data = new DataTransfer();
      data.setData("text/plain", value);
      document.activeElement?.dispatchEvent(
        new ClipboardEvent("paste", {
          clipboardData: data,
          bubbles: true,
          cancelable: true,
        }),
      );
    }, text);
  await cell(page, 0, "c1").focus();
  await page.keyboard.press("ArrowLeft");
  await expect(
    page.getByRole("button", { name: "Row 1 actions" }),
  ).toBeFocused();
  // From the actions, the fourth value would land on Quiz 1 if the paste
  // started one column to the left of the first cell.
  await paste("1\t2\t3\t42");

  await page.keyboard.press("ArrowRight");
  await page.keyboard.press("ArrowRight");
  await page.keyboard.press("ArrowRight");
  await expect(cell(page, 0, "c3")).toBeFocused();
  await paste("17");
  await expect(cell(page, 0, "c3")).toHaveText("17");
  // Only the paste on Quiz 1 was sent.
  expect(writes.patches).toEqual([
    {
      rowId: wireSheetRow(0, {}).id,
      cells: { c3: { value: "17", expected: { value: 10 } } },
    },
  ]);
});
