import { expect, expectNoHorizontalScroll, test } from "./helpers/test";
import { installListApi, listIds } from "./helpers/openview-list-api";
import {
  installSheetsApi,
  wireSheetSummary,
} from "./helpers/openview-sheets-api";

// docs/specs/sheets.md P1, P2, C1, C3 (SH-67, SH-52): the module page lists
// its module sheets in a Sheets view beside Records and Reports.

const contacts = `/openview?section=views&module=${listIds.module}`;
const callList = "00000000-0000-4000-8000-0000000008c1";

test("a reader opens the module's Sheets view and creates a module sheet", async ({
  page,
}) => {
  await installListApi(page, { viewer: "reader" });
  const api = await installSheetsApi(page, {
    live: [
      wireSheetSummary(callList, "Quarterly call list", {
        moduleId: listIds.module,
        owner: "colleague",
        level: "view",
        rows: 40,
        updatedAt: "2026-11-18T08:30:00Z",
      }),
    ],
  });
  await page.goto(contacts);

  const views = page.getByRole("navigation", { name: "Contacts page" });
  await expect(views.getByRole("link", { name: "Sheets 1" })).toBeVisible();
  await views.getByRole("link", { name: "Sheets 1" }).click();

  // The view's address keeps the saved view, as the Reports view's does.
  await expect(page).toHaveURL(/[?&]tab=sheets(&|$)/);
  await expect(views.getByRole("link", { name: "Sheets 1" })).toHaveAttribute(
    "aria-current",
    "page",
  );
  const list = page.getByRole("region", { name: "Module sheets" });
  const row = list.getByRole("listitem");
  await expect(row).toHaveCount(1);
  await expect(row).toContainText("40 rows · Bernard Ocampo · changed Nov 18");
  await expect(row).toContainText("View");
  await expect(
    list.getByRole("link", { name: "Quarterly call list" }),
  ).toHaveAttribute("href", `/openview?sheet=${callList}`);

  await list.getByRole("button", { name: "New sheet" }).click();
  const dialog = page.getByRole("dialog", { name: "New sheet" });
  await expect(dialog).toContainText("On Contacts");
  await dialog.getByRole("textbox", { name: "Name" }).fill("Visit plan");
  await dialog.getByRole("button", { name: "Create sheet" }).click();

  // The new sheet opens on its own page.
  await expect(
    page.getByRole("heading", { level: 1, name: "Visit plan" }),
  ).toBeVisible();
  await expect(page).toHaveURL(`/openview?sheet=${api.createdId}`);
  expect(api.creates).toEqual([
    {
      module_id: listIds.module,
      title: "Visit plan",
      source: { kind: "blank" },
    },
  ]);
  await expect(page.locator("body")).not.toContainText(/worksheet/i);
});

test("a Sheets address for a module the person cannot read lists no other module's sheets", async ({
  page,
}) => {
  await installListApi(page, { viewer: "reader" });
  await installSheetsApi(page, {
    live: [
      wireSheetSummary(callList, "Quarterly call list", {
        moduleId: listIds.module,
      }),
    ],
  });
  const unreadable = "00000000-0000-4000-8000-0000000008f1";
  await page.goto(`/openview?section=views&module=${unreadable}&tab=sheets`);

  await expect(
    page.getByText("This OpenView link is unavailable or contains"),
  ).toBeVisible();
  await expect(page.getByRole("region", { name: "Module sheets" })).toHaveCount(
    0,
  );
  await expect(page.getByText("Quarterly call list")).toHaveCount(0);
});

test.describe("on a phone", () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test("a guest sees the empty Sheets view with no New sheet", async ({
    page,
  }) => {
    await installListApi(page, { viewer: "guest" });
    await installSheetsApi(page, { live: [] });
    await page.goto(`${contacts}&tab=sheets`);

    const list = page.getByRole("region", { name: "Module sheets" });
    await expect(list).toContainText("No module sheets yet");
    await expect(list.getByRole("button", { name: "New sheet" })).toHaveCount(
      0,
    );
    await expect(
      page
        .getByRole("navigation", { name: "Contacts page" })
        .getByRole("link", { name: "Sheets" }),
    ).toHaveAttribute("aria-current", "page");
    await expectNoHorizontalScroll(page);
  });
});
