import { expect, test, type Page } from "./helpers/test";
import {
  installListApi,
  listIds,
  recordId,
  type Viewer,
} from "./helpers/openview-list-api";
import {
  installSheetsApi,
  wireSheetSummary,
} from "./helpers/openview-sheets-api";
import { openedSheet } from "./helpers/settled";

// docs/specs/sheets.md P2, C1, C3, P7 (SH-48, SH-52) and Screens 1 and 2: the
// record panel's Sheets tab and the blank New sheet dialog.

const contacts = `/openview?section=views&module=${listIds.module}`;
const anaCruz = recordId(0);
const ids = {
  mine: "00000000-0000-4000-8000-0000000007c1",
  shared: "00000000-0000-4000-8000-0000000007c2",
  elsewhere: "00000000-0000-4000-8000-0000000007c3",
};

const twoSheetsOnAna = () => ({
  live: [
    wireSheetSummary(ids.mine, "Follow-up calls", {
      recordId: anaCruz,
      rows: 15,
      updatedAt: "2026-11-21T08:30:00Z",
    }),
    wireSheetSummary(ids.shared, "Renewal checklist", {
      recordId: anaCruz,
      owner: "colleague",
      level: "edit",
      rows: 9,
      updatedAt: "2026-11-15T08:30:00Z",
    }),
    wireSheetSummary(ids.elsewhere, "Another record's sheet", {
      recordId: recordId(1),
    }),
  ],
});

async function openAnaCruz(
  page: Page,
  viewer: Viewer,
  sheets: Parameters<typeof installSheetsApi>[1],
) {
  await installListApi(page, { viewer });
  const api = await installSheetsApi(page, sheets);
  await page.goto(`${contacts}&record=${anaCruz}`);
  const panel = await openedSheet(
    page.getByRole("dialog", { name: "Record details" }),
  );
  return { api, panel };
}

test("a reader lists the record's sheets in its last tab and creates a blank sheet", async ({
  page,
}) => {
  const { api, panel } = await openAnaCruz(page, "reader", twoSheetsOnAna());

  // A reader has no Edit on the record and can still create a sheet (C1).
  await expect(panel.getByRole("button", { name: "Edit" })).toHaveCount(0);
  const tabs = panel.getByRole("tab");
  await expect(tabs.last()).toHaveAccessibleName("Sheets 2");
  await tabs.last().click();

  const onRecord = panel.getByRole("region", { name: "On this record" });
  const rows = onRecord.getByRole("listitem");
  await expect(rows).toHaveCount(2);
  await expect(rows.nth(0)).toContainText("Follow-up calls");
  await expect(rows.nth(0)).toContainText("15 rows · changed Nov 21");
  await expect(rows.nth(0)).toContainText("Only you");
  await expect(rows.nth(1)).toContainText(
    "9 rows · Bernard Ocampo · changed Nov 15",
  );
  await expect(rows.nth(1)).toContainText("Edit");
  await expect(
    onRecord.getByRole("link", { name: "Follow-up calls" }),
  ).toHaveAttribute("href", `/openview?sheet=${ids.mine}`);

  // Keyboard: Escape closes New sheet only, and focus returns to its button.
  const newSheet = onRecord.getByRole("button", { name: "New sheet" });
  await newSheet.click();
  const dialog = page.getByRole("dialog", { name: "New sheet" });
  await expect(dialog).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(dialog).toBeHidden();
  await expect(panel).toBeVisible();
  await expect(newSheet).toBeFocused();

  await newSheet.click();
  await expect(dialog).toContainText("On Ana Cruz · Contacts");
  await expect(dialog).toContainText("Only you can see it until you share it.");
  await dialog.getByRole("button", { name: "Create sheet" }).click();
  await expect(dialog.getByText("Enter a name.")).toBeVisible();
  expect(api.creates).toEqual([]);

  // Enter in Name creates the sheet.
  await dialog.getByRole("textbox", { name: "Name" }).fill("  Class 4D  ");
  await page.keyboard.press("Enter");

  // The new sheet opens on its own page.
  await expect(
    page.getByRole("heading", { level: 1, name: "Class 4D" }),
  ).toBeVisible();
  await expect(page).toHaveURL(`/openview?sheet=${api.createdId}`);
  expect(api.creates).toEqual([
    { record_id: anaCruz, title: "Class 4D", source: { kind: "blank" } },
  ]);
  // Users see "Sheets" and "sheet" only (P7, SH-52).
  await expect(page.locator("body")).not.toContainText(/worksheet/i);
});

test("a refused create keeps the dialog and the name", async ({ page }) => {
  const { api, panel } = await openAnaCruz(page, "reader", twoSheetsOnAna());
  api.refuseNextCreate = {
    status: 409,
    code: "record_not_active",
    message: "The record is not active",
  };
  await panel.getByRole("tab", { name: "Sheets 2" }).click();
  await panel
    .getByRole("region", { name: "On this record" })
    .getByRole("button", { name: "New sheet" })
    .click();
  const dialog = page.getByRole("dialog", { name: "New sheet" });
  const name = dialog.getByRole("textbox", { name: "Name" });
  await name.fill("Class 4D");
  await dialog.getByRole("button", { name: "Create sheet" }).click();

  await expect(dialog).toContainText(
    "This record was deleted or its module was closed, so it cannot hold a new sheet.",
  );
  await expect(name).toHaveValue("Class 4D");
  await expect(page).toHaveURL(new RegExp(`record=${anaCruz}`));
});

test("a guest sees the same structure with no count and no New sheet", async ({
  page,
}) => {
  const { panel } = await openAnaCruz(page, "guest", { live: [] });

  const tab = panel.getByRole("tab").last();
  await expect(tab).toHaveAccessibleName("Sheets");
  await tab.click();
  const onRecord = panel.getByRole("region", { name: "On this record" });
  await expect(onRecord).toContainText("No sheets on this record yet");
  await expect(onRecord).toContainText(
    "A new sheet is visible only to you until you share it.",
  );
  await expect(onRecord.getByRole("button", { name: "New sheet" })).toHaveCount(
    0,
  );
});
