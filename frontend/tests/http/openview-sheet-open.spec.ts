import { expect, signedInAs, test, type Page } from "./helpers/test";
import {
  installSheetActionsApi,
  installSheetPageApi,
  sheetPeople,
  sheetPlace,
  wireSheetDetail,
  wireSheetRow,
  wireSheetSummary,
} from "./helpers/openview-sheets-api";

// docs/specs/sheets.md L2, L7, L10, X2, X3, H3 (SH-18, SH-31 menu, SH-46)
// and Screens 3 and 5: an open sheet after its owner left, the Export menu
// and the sheet history. The line's words are owned by
// tests/isolated/openview/sheet-share.spec.ts.

const sheetId = "00000000-0000-4000-8000-0000000009a1";
const recordId = "00000000-0000-4000-8000-0000000009a2";
const studentModule = "00000000-0000-4000-8000-0000000009a3";
const rowId = (index: number) =>
  `00000000-0000-4000-8000-${String(990000 + index).padStart(12, "0")}`;
const diego = {
  id: "00000000-0000-4000-8000-0000000009b1",
  display_name: "Diego Navarro",
};

const reader = {
  id: sheetPeople.viewer.id,
  role: "member",
  access: [
    { department_id: sheetPlace.department, module_id: null, level: "read" },
  ],
} as const;

function openSheet(level: "owner" | "view" = "view") {
  const summary = wireSheetSummary(sheetId, "Class roster", {
    recordId,
    recordTitle: "Ana Cruz",
    moduleName: "Contacts",
    owner: level === "owner" ? "viewer" : "colleague",
    level,
    rows: 2,
  });
  return {
    detail: {
      ...wireSheetDetail({ ...summary, state: "open" as const, shared: null }),
      structure: {
        structureVersion: 1,
        nextColumnSeq: 3,
        columns: [
          {
            key: "c1",
            name: "Student",
            type: "link",
            link: { moduleId: studentModule },
          },
          { key: "c2", name: "Quiz 1", type: "int" },
        ],
        groups: [],
        totals: {},
      },
    },
    rows: [
      wireSheetRow(0, {
        c1: { link: { record_id: rowId(50), label: "Alyssa Mercado" } },
        c2: { value: 17 },
      }),
      wireSheetRow(1, { c1: { state: "no_access" }, c2: { value: 12 } }),
    ],
    totals: {},
  };
}

const history = [
  {
    id: rowId(1),
    row_id: rowId(10),
    revision: 3,
    action: "update" as const,
    changed_keys: ["c2"],
    cells: {
      c1: { link: { record_id: rowId(50), label: "Alyssa Mercado" } },
      c2: { value: 18 },
    },
    author: diego,
    created_at: "2026-11-22T09:00:00Z",
  },
  {
    id: rowId(2),
    row_id: rowId(11),
    revision: 1,
    action: "create" as const,
    changed_keys: ["c1", "c2"],
    cells: { c1: { state: "no_access" }, c2: { value: 12 } },
    author: null,
    created_at: "2026-11-21T09:00:00Z",
  },
];

const address = `/openview?sheet=${sheetId}`;

function header(page: Page) {
  return page.locator("header").filter({
    has: page.getByRole("heading", { level: 1 }),
  });
}

test("a reader of an open sheet sees why it is read-only, downloads it and reads its history", async ({
  page,
}) => {
  await signedInAs(page, reader);
  const sheetState = await installSheetPageApi(page, openSheet());
  const api = await installSheetActionsApi(page, sheetState, { history });
  await page.goto(address);

  await expect(
    header(page).getByText("Read-only", { exact: true }),
  ).toBeVisible();
  await expect(header(page)).toContainText(
    "Bernard Ocampo no longer has access to Slate Operations. Everyone who can read Ana Cruz's record can read this sheet. Nobody can change it.",
  );
  await expect(page.getByRole("grid", { name: "Class roster" })).toBeVisible();
  for (const name of ["Share", "Import", "Add row", "Add column"])
    await expect(page.getByRole("button", { name, exact: true })).toHaveCount(
      0,
    );

  await header(page).getByRole("button", { name: "Export" }).click();
  const exportMenu = page.getByRole("menu");
  await expect(exportMenu.getByRole("menuitem")).toHaveText([
    /^Download CSVAll rows\. Computed and lookup columns as values\.$/,
    /^Download ExcelThe same, as an \.xlsx file\.$/,
    /^Download templateColumns and settings only, no rows \(\.json\)\.$/,
  ]);
  const [download] = await Promise.all([
    page.waitForEvent("download"),
    exportMenu.getByRole("menuitem", { name: /Download CSV/ }).click(),
  ]);
  expect(download.suggestedFilename()).toBe("class-roster-2026-11-24.csv");
  expect(api.exports).toEqual([{ format: "csv" }]);

  await header(page)
    .getByRole("button", { name: "More sheet actions" })
    .click();
  await expect(page.getByRole("menu").getByRole("menuitem")).toHaveText([
    "Sheet history",
  ]);
  await page.getByRole("menuitem", { name: "Sheet history" }).click();
  const panel = page.getByRole("dialog", { name: "Sheet history" });
  const entries = panel.getByRole("listitem");
  await expect(entries).toHaveCount(2);
  await expect(entries.nth(0)).toContainText("Diego Navarro");
  await expect(entries.nth(0)).toContainText("Changed Quiz 1 · Alyssa Mercado");
  await expect(entries.nth(0)).toContainText("Quiz 1: 18");
  await expect(entries.nth(1)).toContainText("Unknown person");
  await expect(entries.nth(1)).toContainText("Added a row");
  await expect(entries.nth(1)).toContainText("Student: No access");
  // Development mode's Strict Mode may read twice; every read asks the same.
  expect([...new Set(api.historyReads)]).toEqual([
    "?limit=50&offset=0&sort_order=desc",
  ]);
  await page.keyboard.press("Escape");
  await expect(panel).toBeHidden();
  await expect(
    header(page).getByRole("button", { name: "More sheet actions" }),
  ).toBeFocused();
});

test("a refused export says why and downloads nothing", async ({ page }) => {
  await signedInAs(page, reader);
  const sheetState = await installSheetPageApi(page, openSheet());
  const api = await installSheetActionsApi(page, sheetState);
  await page.goto(address);
  const exportButton = header(page).getByRole("button", { name: "Export" });

  api.refuseNextExport = {
    status: 422,
    code: "export_limit_exceeded",
    message: "Too many rows",
  };
  await exportButton.click();
  await page.getByRole("menuitem", { name: /Download Excel/ }).click();
  const alert = page
    .getByRole("alert")
    .filter({ hasText: "Nothing was exported" });
  await expect(alert).toContainText(
    "This sheet is larger than an export allows (10,000 rows or 8 MiB). Nothing was exported.",
  );

  // The recheck after the build answers FastAPI's plain 403 (D9.1).
  api.refuseNextExport = { status: 403, code: "", message: "Forbidden" };
  await exportButton.click();
  await page.getByRole("menuitem", { name: /Download template/ }).click();
  await expect(alert).toContainText(
    "You can no longer read one of the linked modules. Nothing was exported.",
  );
  expect(api.exports).toEqual([{ format: "xlsx" }, { format: "template" }]);
});

test("the owner of an open sheet cannot share, rename or delete it, on a phone too", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await signedInAs(page, reader);
  const sheetState = await installSheetPageApi(page, openSheet("owner"));
  const api = await installSheetActionsApi(page, sheetState);
  await page.goto(address);

  await expect(
    header(page).getByText("Read-only", { exact: true }),
  ).toBeVisible();
  await expect(header(page)).toContainText(
    "Andrea Villamor no longer has access to Slate Operations.",
  );
  await expect(
    header(page).getByRole("button", { name: "Share", exact: true }),
  ).toHaveCount(0);
  for (const name of ["Export", "More sheet actions"]) {
    const box = await header(page).getByRole("button", { name }).boundingBox();
    expect(box?.height ?? 0, name).toBeGreaterThanOrEqual(44);
  }
  await header(page)
    .getByRole("button", { name: "More sheet actions" })
    .click();
  await expect(page.getByRole("menu").getByRole("menuitem")).toHaveText([
    "Sheet history",
  ]);
  // The owner's shares are not read while the sheet is open (409).
  expect(api.shareReads).toBe(0);
});
