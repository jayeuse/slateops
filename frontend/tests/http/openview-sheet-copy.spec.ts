import { expect, signedInAs, test, type Page } from "./helpers/test";
import {
  installSheetPageApi,
  installSheetsApi,
  sheetPeople,
  sheetPlace,
  wireSheetDetail,
  wireSheetRow,
  wireSheetSummary,
} from "./helpers/openview-sheets-api";

// docs/specs/sheets.md L6, X7, D9.5, Decision 3 (SH-17, SH-34) and Screens 3
// and 5: Make a copy of an open sheet, the owner's copy, and New sheet from
// this structure.

const sheetId = "00000000-0000-4000-8000-000000000ca1";
const recordId = "00000000-0000-4000-8000-000000000ca2";

function access(role: "member" | "guest") {
  return {
    id: sheetPeople.viewer.id,
    role,
    access: [
      { department_id: sheetPlace.department, module_id: null, level: "read" },
    ],
  } as const;
}

function sheet(state: "open" | "private") {
  const summary = wireSheetSummary(sheetId, "Class roster", {
    recordId,
    recordTitle: "Ana Cruz",
    moduleName: "Contacts",
    owner: state === "open" ? "colleague" : "viewer",
    level: state === "open" ? "view" : "owner",
    rows: 1,
  });
  return {
    detail: {
      ...wireSheetDetail({
        ...summary,
        state,
        shared: state === "open" ? null : false,
      }),
      structure: {
        structureVersion: 1,
        nextColumnSeq: 2,
        columns: [{ key: "c1", name: "Quiz 1", type: "int" }],
        groups: [],
        totals: {},
      },
    },
    rows: [wireSheetRow(0, { c1: { value: 18 } })],
    totals: {},
  };
}

async function openSheet(
  page: Page,
  state: "open" | "private",
  role: "member" | "guest" = "member",
) {
  await signedInAs(page, access(role));
  // The create route first: the sheet's own page routes win for its id.
  const sheets = await installSheetsApi(page, { live: [] });
  await installSheetPageApi(page, sheet(state));
  await page.goto(`/openview?sheet=${sheetId}`);
  await expect(page.getByRole("grid", { name: "Class roster" })).toBeVisible();
  const header = page.locator("header").filter({
    has: page.getByRole("heading", { level: 1 }),
  });
  return { sheets, header };
}

test("a reader of an open sheet makes a private copy on the same record", async ({
  page,
}) => {
  const { sheets, header } = await openSheet(page, "open");
  await header.getByRole("button", { name: "Make a copy" }).click();
  const dialog = page.getByRole("dialog", {
    name: "Make a copy of Class roster",
  });
  await expect(dialog.getByRole("textbox", { name: "Name" })).toHaveValue(
    "Class roster (copy)",
  );
  await expect(dialog).toContainText(
    "On Ana Cruz · Contacts, the same record.",
  );
  await expect(dialog).toContainText(
    "You get the same columns, rows and links. Only you can see the copy until you share it.",
  );

  // A sheet over the copy limit is refused with its way out.
  sheets.refuseNextCreate = {
    status: 422,
    code: "copy_too_large",
    message: "A copy holds at most 5,000 rows",
  };
  await dialog
    .getByRole("button", { name: "Make a copy", exact: true })
    .click();
  await expect(dialog.getByRole("alert")).toContainText(
    "This sheet has too many rows to copy (over 5,000). Export it and import the file instead.",
  );

  await dialog
    .getByRole("button", { name: "Make a copy", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { level: 1, name: "Class roster (copy)" }),
  ).toBeVisible();
  await expect(page).toHaveURL(`/openview?sheet=${sheets.createdId}`);
  expect(sheets.creates.at(-1)).toEqual({
    record_id: recordId,
    title: "Class roster (copy)",
    source: { kind: "copy", worksheet_id: sheetId },
  });
});

test("the owner copies from More, and starts a module sheet from this structure", async ({
  page,
}) => {
  const { sheets, header } = await openSheet(page, "private");
  const more = header.getByRole("button", { name: "More sheet actions" });
  await more.click();
  await expect(
    page.getByRole("menuitem", { name: "Make a copy" }),
  ).toBeVisible();
  await page
    .getByRole("menuitem", { name: /New sheet from this structure/ })
    .click();

  const dialog = page.getByRole("dialog", {
    name: "New sheet from this structure",
  });
  await expect(dialog).toContainText(
    "Same columns, groups, computed columns and totals. No rows and no shares.",
  );
  await expect(dialog.getByRole("textbox", { name: "Name" })).toHaveValue(
    "Class roster",
  );
  await dialog.getByRole("textbox", { name: "Name" }).fill("Class 4D");
  const place = dialog.getByRole("radiogroup", { name: "Put it on" });
  await expect(
    place.getByRole("radio", { name: "Ana Cruz · Contacts" }),
  ).toBeChecked();
  await place.getByRole("radio", { name: "The Contacts module" }).check();
  await dialog.getByRole("button", { name: "Create sheet" }).click();

  await expect(
    page.getByRole("heading", { level: 1, name: "Class 4D" }),
  ).toBeVisible();
  expect(sheets.creates).toEqual([
    {
      module_id: sheetPlace.module,
      title: "Class 4D",
      source: { kind: "structure", worksheet_id: sheetId },
    },
  ]);
});

test("a guest reading an open sheet can neither copy it nor start a sheet from it", async ({
  page,
}) => {
  const { header } = await openSheet(page, "open", "guest");
  await expect(header.getByRole("button", { name: "Export" })).toBeVisible();
  await expect(header.getByRole("button", { name: "Make a copy" })).toHaveCount(
    0,
  );
  await header.getByRole("button", { name: "More sheet actions" }).click();
  await expect(page.getByRole("menuitem")).toHaveText(["Sheet history"]);
});
