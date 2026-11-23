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
  });
  const writes = await installSheetEditApi(page, api);
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
  await expect(
    form.getByRole("textbox", { name: "Student number" }),
  ).toHaveAttribute("readonly", "");

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

test("a viewer's row form has only Close", async ({ page }) => {
  const { grid } = await openSheet(page, "view");
  await grid.locator('[data-cell="0:c3"]').tap();
  const form = page.getByRole("dialog", { name: "Ana Cruz" });
  await expect(form.getByRole("button", { name: "Close" })).toBeVisible();
  await expect(form.getByRole("button", { name: "Save row" })).toHaveCount(0);
  await expect(form.getByRole("textbox", { name: "Quiz 1" })).toHaveAttribute(
    "readonly",
    "",
  );
  // A person field names the person, never their id.
  await expect(form.getByRole("textbox", { name: "Teacher" })).toHaveValue(
    "Rosa Lim",
  );
});
