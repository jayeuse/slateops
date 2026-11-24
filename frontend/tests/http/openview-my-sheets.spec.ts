import {
  expect,
  expectNoHorizontalScroll,
  signedInAs,
  test,
  type Page,
} from "./helpers/test";
import {
  installSheetsApi,
  sheetPeople,
  wireSheetSummary,
} from "./helpers/openview-sheets-api";

// docs/specs/sheets.md P4 (SH-62) and Screens 7: My sheets, from the sidebar
// foot, for an account with no department access.

const moduleId = "00000000-0000-4000-8000-0000000006b2";
const ids = {
  class1a: "00000000-0000-4000-8000-0000000006c1",
  class2b: "00000000-0000-4000-8000-0000000006c2",
  council: "00000000-0000-4000-8000-0000000006c3",
  draft: "00000000-0000-4000-8000-0000000006c4",
};
const noAccessMember = {
  id: sheetPeople.viewer.id,
  role: "member",
  access: [],
} as const;

const threeSheets = () => ({
  live: [
    wireSheetSummary(ids.class1a, "Class 1A", { rows: 15, shared: true }),
    wireSheetSummary(ids.class2b, "Class 2B", { rows: 14, moduleId }),
    wireSheetSummary(ids.council, "Student Council records", {
      owner: "colleague",
      level: "edit",
      rows: 9,
      recordTitle: "Bernard Ocampo",
    }),
  ],
  deleted: [
    // Deleted on Nov 19; its last change before that was Nov 10.
    wireSheetSummary(ids.draft, "Class 4D draft", {
      deleted: true,
      updatedAt: "2026-11-10T02:00:00Z",
      deletedAt: "2026-11-19T02:00:00Z",
    }),
  ],
});

function mySheetsLink(page: Page) {
  return page
    .locator("[data-sidebar=footer]")
    .getByRole("link", { name: "My sheets" });
}

function sheetsTable(page: Page) {
  return page.getByRole("table", { name: "My sheets" });
}

test("an account with no department access opens My sheets from the sidebar foot", async ({
  page,
}) => {
  await signedInAs(page, noAccessMember);
  // With no department access, OpenView's record reads are refused; My
  // sheets does not depend on them.
  await page.route(
    (url) => url.pathname === "/api/views/data-sources",
    (route) => route.fulfill({ status: 403, json: { detail: "Forbidden" } }),
  );
  await installSheetsApi(page, threeSheets());
  await page.goto("/settings");

  await expect(mySheetsLink(page)).toBeVisible();
  await mySheetsLink(page).focus();
  await page.keyboard.press("Enter");

  await expect(page).toHaveURL(/\/openview\?section=sheets$/);
  await expect(mySheetsLink(page)).toHaveAttribute("aria-current", "page");
  await expect(
    page.getByRole("heading", { level: 1, name: "My sheets" }),
  ).toBeVisible();
  await expect(
    page.getByText("Sheets you own and sheets shared with you · 3 sheets"),
  ).toBeVisible();
  await expect(
    page
      .getByRole("navigation", { name: "Breadcrumb" })
      .locator('[aria-current="page"]'),
  ).toHaveText("My sheets");

  const show = page.getByRole("group", { name: "Show" });
  await expect(show.getByRole("button", { name: "All 3" })).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  await expect(
    show.getByRole("button", { name: "Owned by me 2" }),
  ).toBeVisible();
  await expect(
    show.getByRole("button", { name: "Shared with me 1" }),
  ).toBeVisible();
  await expect(show.getByRole("button", { name: "Deleted 1" })).toBeVisible();

  const table = sheetsTable(page);
  await expect(table.getByRole("columnheader")).toHaveText([
    "Sheet",
    "On record",
    "Owner",
    "Your access",
    "Rows",
    "Last change",
  ]);
  await expect(table.getByRole("row")).toHaveCount(4);
  await expect(
    table.getByRole("row", { name: /Student Council records/ }),
  ).toContainText("Bernard Ocampo");
  await expect(
    table.getByRole("row", { name: /Student Council records/ }),
  ).toContainText("Edit");
  // On record names the record and its module; a module sheet its module.
  const class1a = table.getByRole("row", { name: /Class 1A/ });
  await expect(class1a.getByRole("cell").nth(1)).toHaveText(
    "Andrea Villamor · Faculty Members",
  );
  await expect(class1a).toContainText("Owner · shared");
  const class2b = table.getByRole("row", { name: /Class 2B/ });
  await expect(class2b.getByRole("cell").nth(1)).toHaveText("Faculty Members");
  await expect(class2b).toContainText("Owner · only you");
  await expect(table.getByRole("link", { name: "Class 1A" })).toHaveAttribute(
    "href",
    `/openview?sheet=${ids.class1a}`,
  );

  // Keyboard: search, the chosen option of Show, then the first sheet.
  const search = page.getByRole("searchbox", { name: "Search sheets" });
  await search.focus();
  await page.keyboard.press("Tab");
  await expect(show.getByRole("button", { name: "All 3" })).toBeFocused();
  await page.keyboard.press("Tab");
  const first = table.getByRole("link", { name: "Class 1A" });
  await expect(first).toBeFocused();
  await expect(first).toHaveCSS("outline-style", "solid");

  await show.getByRole("button", { name: "Shared with me 1" }).click();
  await expect(table.getByRole("row")).toHaveCount(2);
  await expect(
    table.getByRole("link", { name: "Student Council records" }),
  ).toBeVisible();

  await show.getByRole("button", { name: "Owned by me 2" }).click();
  await page.getByRole("searchbox", { name: "Search sheets" }).fill("2b");
  await expect(table.getByRole("row")).toHaveCount(2);
  await expect(table.getByRole("link", { name: "Class 2B" })).toBeVisible();

  // Users see "Sheets" and "sheet" only (P7, SH-52).
  await expect(page.locator("body")).not.toContainText(/worksheet/i);
});

test("the owner restores a deleted sheet from the Deleted list", async ({
  page,
}) => {
  await signedInAs(page, noAccessMember);
  const api = await installSheetsApi(page, threeSheets());
  await page.goto("/openview?section=sheets");

  const show = page.getByRole("group", { name: "Show" });
  await show.getByRole("button", { name: "Deleted 1" }).click();
  const table = sheetsTable(page);
  await expect(table.getByRole("columnheader")).toHaveText([
    "Sheet",
    "On record",
    "Deleted",
    "Actions",
  ]);
  const row = table.getByRole("row", { name: /Class 4D draft/ });
  await expect(row).toContainText("Nov 19");
  await expect(row).not.toContainText("Nov 10");
  await expect(row.getByRole("cell").nth(1)).toHaveText(
    "Andrea Villamor · Faculty Members",
  );

  await row.getByRole("button", { name: "Restore Class 4D draft" }).focus();
  await page.keyboard.press("Enter");

  await expect(show.getByRole("button", { name: "Deleted 0" })).toBeVisible();
  await expect(show.getByRole("button", { name: "All 4" })).toBeVisible();
  expect(api.restores).toEqual([ids.draft]);
  await show.getByRole("button", { name: "All 4" }).click();
  await expect(
    table.getByRole("link", { name: "Class 4D draft" }),
  ).toBeVisible();
});

test("a guest with no sheets sees the same structure with the empty line", async ({
  page,
}) => {
  await signedInAs(page, {
    id: sheetPeople.viewer.id,
    role: "guest",
    access: [],
  });
  await installSheetsApi(page, { live: [], deleted: [] });
  await page.goto("/openview?section=sheets");

  await expect(mySheetsLink(page)).toBeVisible();
  await expect(
    page.getByText("Sheets you own and sheets shared with you show here."),
  ).toBeVisible();
  await expect(
    page.getByRole("group", { name: "Show" }).getByRole("button", {
      name: "All 0",
    }),
  ).toBeVisible();
  await expect(sheetsTable(page).getByRole("columnheader")).toHaveCount(6);
  await expect(
    sheetsTable(page).getByText(
      "No sheets yet. Open a record and use New sheet in its Sheets tab.",
    ),
  ).toBeVisible();
});

test("a sheet shared through a group names that group", async ({ page }) => {
  await signedInAs(page, noAccessMember);
  await installSheetsApi(page, {
    live: [
      wireSheetSummary(ids.council, "Mid-Year Enrollment list", {
        owner: "colleague",
        level: "view",
        accessGroup: "CCS Faculty",
      }),
    ],
  });
  await page.goto("/openview?section=sheets");

  await expect(
    sheetsTable(page).getByRole("row", { name: /Mid-Year Enrollment list/ }),
  ).toContainText("View · CCS Faculty");
});

test("a failed read offers Retry, which loads the list", async ({ page }) => {
  await signedInAs(page, noAccessMember);
  await installSheetsApi(page, threeSheets(), { failFirstMyRead: true });
  await page.goto("/openview?section=sheets");

  // The route announcer is an alert too, so the failure is found by its words.
  const failure = page
    .getByRole("alert")
    .filter({ hasText: "Your sheets could not be loaded." });
  await expect(failure).toBeVisible();
  await failure.getByRole("button", { name: "Retry" }).click();

  await expect(sheetsTable(page).getByRole("row")).toHaveCount(4);
  await expect(failure).toHaveCount(0);
});

test("a list the server answers in part shows how many of how many", async ({
  page,
}) => {
  await signedInAs(page, noAccessMember);
  await installSheetsApi(page, threeSheets());
  await page.route(
    (url) =>
      url.pathname === "/api/worksheets" &&
      url.searchParams.get("deleted") === "exclude",
    (route) =>
      route.fulfill({
        json: {
          items: threeSheets().live,
          pagination: {
            limit: 100,
            offset: 0,
            count: 3,
            total: 5_100,
            has_more: false,
            total_is_capped: false,
          },
        },
      }),
  );
  await page.goto("/openview?section=sheets");
  await expect(page.getByText("Showing 3 of 5,100 sheets.")).toBeVisible();
});

test.describe("on a phone", () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test("the drawer opens My sheets, where each sheet shows its name, its access and a line of details", async ({
    page,
  }) => {
    await signedInAs(page, noAccessMember);
    await installSheetsApi(page, threeSheets());
    await page.goto("/settings");

    await page.getByRole("button", { name: "Open navigation" }).click();
    const drawer = page.getByRole("dialog", {
      name: "Slate Operations navigation",
    });
    await drawer.getByRole("link", { name: "My sheets" }).click();
    await expect(drawer).toBeHidden();
    await expect(page).toHaveURL(/\/openview\?section=sheets$/);

    const list = page.getByRole("list", { name: "My sheets" });
    const item = list.getByRole("listitem").filter({ hasText: "Class 1A" });
    await expect(item.getByRole("link", { name: "Class 1A" })).toBeVisible();
    await expect(item).toContainText("Owner");
    await expect(item).toContainText("15 rows · Nov 21");
    await expect(item).toContainText(
      "Andrea Villamor · Faculty Members · 15 rows · Nov 21",
    );
    await expect(item).toContainText("Owner · shared");
    await expectNoHorizontalScroll(page);
  });
});
