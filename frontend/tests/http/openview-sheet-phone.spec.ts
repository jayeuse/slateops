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

// docs/specs/sheets.md P5 (SH-50) and Screens 9: on a phone a tapped row
// opens as a form in a bottom panel.

test.use({ viewport: { width: 390, height: 844 }, hasTouch: true });

const sheetId = "00000000-0000-4000-8000-0000000009b1";
const students = "00000000-0000-4000-8000-0000000009b2";
const numberField = "00000000-0000-4000-8000-0000000009b3";
const names = ["Ana Cruz", "Bea Santos", "Carlo Reyes"];
const teacherId = "00000000-0000-4000-8000-0000000009b5";
const titleField = "00000000-0000-4000-8000-0000000009b6";
const alice = "00000000-0000-4000-8000-0000000009b7";
const mara = {
  id: "00000000-0000-4000-8000-0000000009b8",
  display_name: "Mara Diaz",
};

const reader = {
  id: sheetPeople.viewer.id,
  role: "member",
  access: [
    { department_id: sheetPlace.department, module_id: null, level: "read" },
  ],
} as const;

async function openSheet(page: Page, level: "owner" | "view") {
  await signedInAs(page, reader);
  await page.route(`**/api/users/${teacherId}/card`, (route) =>
    route.fulfill({ json: { ...memberCard, display_name: "Rosa Lim" } }),
  );
  await page.route(`**/api/users/${mara.id}/card`, (route) =>
    route.fulfill({ json: { ...memberCard, display_name: mara.display_name } }),
  );
  const summary = wireSheetSummary(sheetId, "Class roster", {
    recordId: "00000000-0000-4000-8000-0000000009b4",
    recordTitle: "Ana Cruz",
    moduleName: "Contacts",
    owner: level === "owner" ? "viewer" : "colleague",
    level,
    rows: names.length,
  });
  const api = await installSheetPageApi(page, {
    detail: {
      ...wireSheetDetail(summary),
      structure: {
        structureVersion: 1,
        nextColumnSeq: 5,
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
          { key: "c4", name: "Quiz 2", type: "int" },
          { key: "c5", name: "Teacher", type: "user" },
        ],
        groups: [{ name: "Prelim", keys: ["c3", "c4"] }],
        totals: {},
      },
    },
    rows: names.map((name, index) =>
      wireSheetRow(index, {
        c1: {
          link: {
            record_id: `00000000-0000-4000-8000-${String(990000 + index).padStart(12, "0")}`,
            label: name,
          },
        },
        c2: { value: `S-${index + 1}` },
        c3: { value: 10 + index },
        c4: { value: 20 + index },
        c5: { value: teacherId },
      }),
    ),
    totals: {},
    modules: [{ id: students, name: "Students", titleFieldId: titleField }],
  });
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
      [students]: [{ id: titleField, name: "Name", type: "text" }],
    },
    people: [mara],
  });
  await page.goto(`/openview?sheet=${sheetId}`);
  const grid = page.getByRole("grid", { name: "Class roster" });
  await expect(
    grid.getByRole("gridcell", { name: /Bea Santos/ }),
  ).toBeVisible();
  return { api, writes, grid };
}

test("a tapped row opens as a form; Save row sends only the changed cells", async ({
  page,
}) => {
  const { writes, grid } = await openSheet(page, "owner");
  await grid.locator('[data-cell="1:c3"]').tap();

  const form = page.getByRole("dialog", { name: "Bea Santos" });
  await expect(form).toContainText("Row 2 of 3 · Class roster");
  await expect(form).toContainText("Prelim");
  const quiz = form.getByRole("textbox", { name: "Quiz 1" });
  await expect(quiz).toHaveValue("11");
  const box = await quiz.boundingBox();
  expect(box?.height ?? 0).toBeGreaterThanOrEqual(44);
  const lookup = form.getByRole("textbox", { name: "Student number" });
  await expect(lookup).toHaveAttribute("aria-readonly", "true");
  await expect(lookup).toHaveText("S-2");
  await expect(form).toContainText("Lookup from Students. Read-only.");
  const close = form.getByRole("button", { name: "Close", exact: true });
  const closeBox = await close.boundingBox();
  expect(closeBox?.height ?? 0).toBeGreaterThanOrEqual(44);

  await form.getByRole("button", { name: "Next row" }).click();
  await expect(page.getByRole("dialog", { name: "Carlo Reyes" })).toContainText(
    "Row 3 of 3 · Class roster",
  );
  await page.getByRole("button", { name: "Previous row" }).click();

  await quiz.fill("19");
  await form.getByRole("button", { name: "Save row" }).click();
  await expect(form).toHaveCount(0);
  await expect(grid.locator('[data-cell="1:c3"]')).toHaveText("19");
  expect(writes.patches).toEqual([
    {
      rowId: wireSheetRow(1, {}).id,
      cells: { c3: { value: "19", expected: { value: 11 } } },
    },
  ]);

  await grid.locator('[data-cell="0:c4"]').tap();
  await page.getByRole("button", { name: "Cancel" }).click();
  await expect(page.getByRole("dialog", { name: "Ana Cruz" })).toHaveCount(0);
  expect(writes.patches).toHaveLength(1);
});

test("a link field in the row form picks a readable record", async ({
  page,
}) => {
  const { writes, grid } = await openSheet(page, "owner");
  await grid.locator('[data-cell="2:c1"]').tap();
  const form = page.getByRole("dialog", { name: "Carlo Reyes" });
  // A phone grid shows the name as text; the form carries the way there.
  await expect(grid.getByRole("link")).toHaveCount(0);
  await expect(
    form.getByRole("link", { name: "Open Carlo Reyes's record" }),
  ).toBeVisible();
  const field = form.getByRole("button", { name: "Student: Carlo Reyes" });
  expect((await field.boundingBox())?.height ?? 0).toBeGreaterThanOrEqual(44);
  await field.click();
  const picker = page.getByRole("dialog", { name: "Choose Student" });
  await picker.getByRole("searchbox", { name: "Search Students" }).fill("Ali");
  await picker.getByRole("button", { name: "Alice Reyes" }).click();
  await expect(
    form.getByRole("button", { name: "Student: Alice Reyes" }),
  ).toBeVisible();
  await form.getByRole("button", { name: "Save row" }).click();
  await expect(grid.locator('[data-cell="2:c1"]')).toHaveText("Alice Reyes");
  expect(writes.patches.at(-1)?.cells).toEqual({
    c1: {
      value: { record_id: alice },
      expected: {
        link: {
          record_id: "00000000-0000-4000-8000-000000990002",
          label: "Carlo Reyes",
        },
      },
    },
  });
});

test("a viewer's row form has only Close", async ({ page }) => {
  const { grid } = await openSheet(page, "view");
  await grid.locator('[data-cell="0:c3"]').tap();
  const form = page.getByRole("dialog", { name: "Ana Cruz" });
  // The header's close and the footer's Close.
  await expect(form.getByRole("button", { name: "Close" })).toHaveCount(2);
  await expect(form.getByRole("button", { name: "Save row" })).toHaveCount(0);
  await expect(form.getByRole("button", { name: "Delete row" })).toHaveCount(0);
  await expect(form.getByRole("textbox", { name: "Quiz 1" })).toHaveAttribute(
    "aria-readonly",
    "true",
  );
  // A person field names the person, never their id.
  await expect(form.getByRole("textbox", { name: "Teacher" })).toHaveText(
    "Rosa Lim",
  );
  // A read-only link field shows the name and the way to the record.
  await expect(
    form.getByRole("textbox", { name: "Student", exact: true }),
  ).toHaveText("Ana Cruz");
  await expect(
    form.getByRole("link", { name: "Open Ana Cruz's record" }),
  ).toBeVisible();
});

test("the row form reloads on a conflict and keeps a refused value with its reason", async ({
  page,
}) => {
  const { api, writes, grid } = await openSheet(page, "owner");
  writes.changedBy = mara;
  api.rows[1].cells.c3 = { value: 7 };
  await grid.locator('[data-cell="1:c3"]').tap();
  const form = page.getByRole("dialog", { name: "Bea Santos" });
  const quiz = form.getByRole("textbox", { name: "Quiz 1" });
  await quiz.fill("19");
  await form.getByRole("button", { name: "Save row" }).click();
  await expect(
    form.getByRole("status").filter({ hasText: "changed this row" }),
  ).toContainText(
    "Mara Diaz changed this row while you were editing it. It now shows the newer values. Your Quiz 1 (19) was not saved.",
  );
  await expect(quiz).toHaveValue("7");

  writes.refuseNextPatch = {
    status: 422,
    code: "cell_invalid",
    message: "Enter a whole number",
  };
  await quiz.fill("1.5");
  await form.getByRole("button", { name: "Save row" }).click();
  await expect(form.getByRole("alert")).toHaveText(
    "Quiz 1: Enter a whole number",
  );
  await expect(quiz).toHaveValue("1.5");
  await expect(form).toBeVisible();
});

test("an editor picks a person and deletes a row from the row form", async ({
  page,
}) => {
  const { api, writes, grid } = await openSheet(page, "owner");
  await grid.locator('[data-cell="0:c3"]').tap();
  const form = page.getByRole("dialog", { name: "Ana Cruz" });
  await form.getByRole("button", { name: "Teacher: Rosa Lim" }).click();
  const picker = page.getByRole("dialog", { name: "Choose Teacher" });
  await picker.getByRole("button", { name: "Mara Diaz" }).click();
  await form.getByRole("button", { name: "Save row" }).click();
  await expect(form).toHaveCount(0);
  expect(writes.patches.at(-1)?.cells).toEqual({
    c5: { value: mara.id, expected: { value: teacherId } },
  });

  const second = api.rows[1];
  await grid.locator('[data-cell="1:c3"]').tap();
  await page
    .getByRole("dialog", { name: "Bea Santos" })
    .getByRole("button", { name: "Delete row" })
    .click();
  await page
    .getByRole("alertdialog", { name: "Delete row 2?" })
    .getByRole("button", { name: "Delete row" })
    .click();
  await expect(grid.getByRole("gridcell", { name: "Bea Santos" })).toHaveCount(
    0,
  );
  expect(writes.deletes).toEqual([{ rowId: second.id, ifMatch: second.etag }]);
});
