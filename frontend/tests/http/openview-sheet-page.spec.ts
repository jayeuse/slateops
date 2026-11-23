import {
  expect,
  expectNoHorizontalScroll,
  expectNoPageScroll,
  signedInAs,
  test,
  type Page,
} from "./helpers/test";
import {
  installOpenViewEventSource,
  sendOpenViewEvent,
} from "./helpers/openview-event-source";
import {
  installSheetPageApi,
  sheetPeople,
  sheetPlace,
  wireSheetDetail,
  wireSheetRow,
  wireSheetSummary,
  type WireSheetCell,
} from "./helpers/openview-sheets-api";

// docs/specs/sheets.md P3, P6, F7, N4, N6 to N8 (SH-49, SH-53) and Screens 3
// and 9: the read-only sheet page.

const sheetId = "00000000-0000-4000-8000-0000000007a1";
const recordId = "00000000-0000-4000-8000-0000000007a2";
const studentModule = "00000000-0000-4000-8000-0000000007a3";
const fieldId = "00000000-0000-4000-8000-0000000007a4";
const studentId = (index: number) =>
  `00000000-0000-4000-8000-${String(800000 + index).padStart(12, "0")}`;

const reader = {
  id: sheetPeople.viewer.id,
  role: "member",
  access: [
    { department_id: sheetPlace.department, module_id: null, level: "read" },
  ],
} as const;

const special: Record<number, WireSheetCell> = {
  1: { state: "deleted" },
  2: { state: "removed" },
  3: { state: "unavailable" },
  4: { state: "no_access" },
};

function rows(count: number) {
  return Array.from({ length: count }, (_, index) =>
    wireSheetRow(index, {
      c1: special[index] ?? {
        link: { record_id: studentId(index), label: `Student ${index + 1}` },
      },
      c2:
        index === 5 ? { state: "field_removed" } : { value: `S-${index + 1}` },
      c3: { value: (index * 7) % 20 },
      c4: { value: null },
    }),
  );
}

function sheet(options: {
  level?: "owner" | "edit" | "view";
  shared?: boolean;
  count?: number;
}) {
  const level = options.level ?? "owner";
  const summary = wireSheetSummary(sheetId, "Class roster", {
    recordId,
    recordTitle: "Ana Cruz",
    moduleName: "Contacts",
    owner: level === "owner" ? "viewer" : "colleague",
    level,
    shared: options.shared,
    rows: options.count ?? 450,
  });
  return {
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
            link: { moduleId: studentModule },
          },
          {
            key: "c2",
            name: "Student number",
            type: "lookup",
            lookup: { linkKey: "c1", fieldId },
          },
          { key: "c3", name: "Quiz 1", type: "int" },
          {
            key: "c4",
            name: "Final grade",
            type: "computed",
            computed: { expression: "{Quiz 1} * 5", places: 2 },
          },
        ],
        groups: [],
        totals: { c1: "count", c3: "average" },
      },
    },
    rows: rows(options.count ?? 450),
    totals: {
      c1: { fn: "count", value: 446, hidden_count: 1 },
      c3: { fn: "average", value: "9.5", hidden_count: 0 },
    },
  };
}

const address = `/openview?sheet=${sheetId}`;

function grid(page: Page) {
  return page.getByRole("grid", { name: "Class roster" });
}

test("the owner reads a sheet as one still page with fixed headers and totals", async ({
  page,
}) => {
  await signedInAs(page, reader);
  const api = await installSheetPageApi(page, sheet({}));
  await page.goto(address);

  await expect(
    page.getByRole("heading", { level: 1, name: "Class roster" }),
  ).toBeVisible();
  await expect(page.getByText("Only you", { exact: true })).toBeVisible();
  await expect(
    page.getByText("On Ana Cruz · Contacts · 450 rows · Owner: you"),
  ).toBeVisible();
  const crumbs = page.getByRole("navigation", { name: "Breadcrumb" });
  await expect(crumbs).toContainText("Sales");
  await expect(crumbs.getByRole("link", { name: "Contacts" })).toHaveAttribute(
    "href",
    `/openview?section=views&module=${sheetPlace.module}`,
  );
  // The record crumb opens the record panel.
  await expect(crumbs.getByRole("link", { name: "Ana Cruz" })).toHaveAttribute(
    "href",
    `/openview?section=views&module=${sheetPlace.module}&record=${recordId}`,
  );
  await expect(crumbs.locator('[aria-current="page"]')).toHaveText(
    "Class roster",
  );

  const table = grid(page);
  await expect(table.getByRole("columnheader")).toHaveText([
    "Row",
    "Student",
    "Student number, read-only",
    "Quiz 1",
    "Final grade, read-only",
  ]);
  await expect(
    table.getByRole("link", { name: "Student 1", exact: true }),
  ).toHaveAttribute(
    "href",
    `/openview?section=views&module=${studentModule}&record=${studentId(0)}`,
  );
  for (const words of [
    "Deleted record",
    "Removed record",
    "Unavailable",
    "No access",
    "Field removed",
  ])
    await expect(table.getByText(words, { exact: true })).toBeVisible();
  const totals = table.locator("tfoot");
  await expect(totals).toContainText("Count");
  await expect(totals).toContainText("446");
  await expect(totals).toContainText("Average");
  await expect(totals).toContainText("9.5");
  await expectNoPageScroll(page);

  // The grid loads the next page of 200 rows as it scrolls.
  expect(api.queries.map((query) => query.offset)).toEqual([0]);
  await page
    .getByRole("region", { name: "Class roster rows" })
    .evaluate((pane) => {
      pane.scrollTop = 8_800;
    });
  await expect(
    table.getByRole("link", { name: "Student 221", exact: true }),
  ).toBeVisible();
  expect(api.queries.map((query) => query.offset)).toContain(200);
  // Users see "Sheets" and "sheet" only (P7, SH-52).
  await expect(page.locator("body")).not.toContainText(/worksheet/i);
});

test("a search and a sort show only for this person and leave no trace after a reload", async ({
  page,
}) => {
  await page.clock.install();
  await signedInAs(page, reader);
  const api = await installSheetPageApi(page, sheet({ shared: true }));
  await page.goto(address);
  await expect(page.getByText("Shared", { exact: true })).toBeVisible();
  const table = grid(page);
  await expect(
    table.getByRole("link", { name: "Student 1", exact: true }),
  ).toBeVisible();

  await page
    .getByRole("searchbox", { name: "Search this sheet" })
    .fill("Student 7");
  await page.clock.runFor(500);
  await expect(page.getByText("11 of 450 rows")).toBeVisible();
  await expect(table.locator("tfoot")).toContainText("Count · all 450 rows");

  // Keyboard: Enter opens Sort, Enter chooses.
  await page.getByRole("button", { name: "Sort" }).focus();
  await page.keyboard.press("Enter");
  await page.getByRole("menuitem", { name: "Quiz 1, high to low" }).focus();
  await page.keyboard.press("Enter");
  await expect(
    page.getByRole("button", { name: "Quiz 1, high to low" }),
  ).toBeVisible();
  await expect(table.locator("tbody tr").first()).toContainText("Student 78");
  expect(api.queries.at(-1)).toMatchObject({
    search: "Student 7",
    sort: { key: "c3", order: "desc" },
  });
  await expect(page).toHaveURL(address);

  await page.reload();
  await expect(
    page.getByRole("searchbox", { name: "Search this sheet" }),
  ).toHaveValue("");
  await expect(page.getByText(/of 450 rows/)).toHaveCount(0);
  await expect(table.locator("tbody tr").first()).toContainText("Student 1");
  expect(api.queries.at(-1)).toEqual({ limit: 200, offset: 0 });
});

test("a viewer's sheet names who shared it and refreshes on its events", async ({
  page,
}) => {
  // The stream opens with a resync, as the real one does.
  await installOpenViewEventSource(page, { autoResync: true });
  await signedInAs(page, reader);
  const api = await installSheetPageApi(
    page,
    sheet({ level: "view", count: 20 }),
  );
  await page.goto(address);

  await expect(
    page.getByText("You can view · shared by Bernard Ocampo"),
  ).toBeVisible();
  await expect(
    page.getByText("On Ana Cruz · Contacts · 20 rows · Owner: Bernard Ocampo"),
  ).toBeVisible();
  await expect(page.getByText("Saved")).toHaveCount(0);
  const table = grid(page);
  await expect(
    table.getByRole("link", { name: "Student 1", exact: true }),
  ).toBeVisible();
  // The opening resync rereads the sheet and its first page at most once.
  expect(api.detailReads).toBeLessThanOrEqual(2);
  expect(api.queries.length).toBeLessThanOrEqual(2);

  api.rows[0].cells.c1 = {
    link: { record_id: studentId(0), label: "Student One" },
  };
  await sendOpenViewEvent(page, "invalidate", {
    entity: "worksheets",
    entity_id: sheetId,
  });
  await expect(
    table.getByRole("link", { name: "Student One", exact: true }),
  ).toBeVisible();

  // A linked record changed: its module's records event refreshes lookups.
  api.rows[0].cells.c2 = { value: "S-0001" };
  await sendOpenViewEvent(page, "invalidate", {
    entity: "records",
    module_id: studentModule,
  });
  await expect(table.getByText("S-0001", { exact: true })).toBeVisible();
});

test("a hidden sheet and a malformed address get the same not-found page", async ({
  page,
}) => {
  await signedInAs(page, reader);
  const api = await installSheetPageApi(page, sheet({}));
  api.detail = null;
  await page.goto(address);
  await expect(
    page.getByRole("heading", { level: 1, name: "Sheet not found" }),
  ).toBeVisible();
  await expect(page.getByText("Class roster")).toHaveCount(0);
  await expect(
    page.getByRole("link", { name: "My sheets" }).last(),
  ).toHaveAttribute("href", "/openview?section=sheets");

  const reads: string[] = [];
  page.on("request", (request) => {
    const path = new URL(request.url()).pathname;
    if (path.startsWith("/api/worksheets/")) reads.push(path);
  });
  await page.goto("/openview?sheet=not-a-sheet");
  await expect(
    page.getByRole("heading", { level: 1, name: "Sheet not found" }),
  ).toBeVisible();
  expect(reads).toEqual([]);
});

test("a sheet that becomes hidden while open leaves no rows and no title", async ({
  page,
}) => {
  await installOpenViewEventSource(page);
  await signedInAs(page, reader);
  const api = await installSheetPageApi(page, sheet({ count: 20 }));
  await page.goto(address);
  await expect(
    grid(page).getByRole("link", { name: "Student 1", exact: true }),
  ).toBeVisible();

  api.detail = null;
  await sendOpenViewEvent(page, "resync");

  await expect(
    page.getByRole("heading", { level: 1, name: "Sheet not found" }),
  ).toBeVisible();
  await expect(grid(page)).toHaveCount(0);
  await expect(page.getByText("Class roster")).toHaveCount(0);
});

test("a cell reached by the keyboard is never under the fixed header, column or totals", async ({
  page,
}) => {
  await signedInAs(page, reader);
  await installSheetPageApi(page, sheet({}));
  await page.goto(address);
  const pane = page.getByRole("region", { name: "Class roster rows" });
  await expect(
    grid(page).getByRole("link", { name: "Student 1", exact: true }),
  ).toBeVisible();
  await pane.evaluate((element) => {
    element.scrollTop = 4_000;
    element.scrollLeft = 400;
  });
  // One tab stop: Tab from Sort reaches the grid's active cell, which the
  // grid scrolls back into view; arrows then move it.
  await page.getByRole("button", { name: "Sort" }).focus();
  await page.keyboard.press("Tab");
  await page.keyboard.press("ArrowDown");
  await page.keyboard.press("ArrowDown");
  await page.keyboard.press("ArrowRight");

  const focused = page.locator(":focus");
  await expect(focused).toHaveAttribute("data-cell", "2:c2");
  const box = await focused.boundingBox();
  if (!box) throw new Error("The focused cell has no box");
  const landsOnCell = await page.evaluate(
    ([x, y]) => {
      const hit = document.elementFromPoint(x, y);
      return Boolean(hit && hit.closest("td") === document.activeElement);
    },
    [box.x + box.width / 2, box.y + box.height / 2],
  );
  expect(landsOnCell).toBe(true);
});

test("the page stays still at 1280×720", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 720 });
  await signedInAs(page, reader);
  await installSheetPageApi(page, sheet({}));
  await page.goto(address);
  await expect(
    grid(page).getByRole("link", { name: "Student 1", exact: true }),
  ).toBeVisible();
  await expectNoPageScroll(page);
});

test.describe("on a phone", () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test("the header wraps over a grid pane that scrolls on its own", async ({
    page,
  }) => {
    await signedInAs(page, reader);
    await installSheetPageApi(page, sheet({}));
    await page.goto(address);

    await expect(
      page.getByRole("heading", { level: 1, name: "Class roster" }),
    ).toBeVisible();
    await expect(
      page.getByRole("searchbox", { name: "Search this sheet" }),
    ).toBeVisible();
    // On a phone the name is text; the row form carries the record link.
    await expect(
      grid(page).getByRole("gridcell", { name: "Student 1", exact: true }),
    ).toBeVisible();
    await expect(grid(page).getByRole("link")).toHaveCount(0);
    await expectNoPageScroll(page);
    await expectNoHorizontalScroll(page);
    // One 160px first column, the row number with the name, stays fixed.
    const firstRow = grid(page).locator("tbody tr").first();
    const number = await firstRow.locator("td").nth(0).boundingBox();
    const name = await firstRow.locator("td").nth(1).boundingBox();
    if (!number || !name) throw new Error("The first column has no box");
    expect(Math.round(name.x + name.width - number.x)).toBe(160);
  });
});
