import { expect, test, type Page } from "./helpers/test";
import { installListApi, listIds, recordId } from "./helpers/openview-list-api";
import { sendOpenViewEvent } from "./helpers/openview-event-source";
import {
  installSheetsApi,
  sheetPeople,
  wireSheetDetail,
  wireSheetSummary,
  type WireSheetCell,
} from "./helpers/openview-sheets-api";
import { openedSheet } from "./helpers/settled";

// docs/specs/sheets.md N5, V7, D10 route 23 (SH-28) and Screens 6: the
// record panel's Appears in, read only, a page at a time, live.

const contacts = `/openview?section=views&module=${listIds.module}`;
const alyssa = recordId(0);
const class1a = "00000000-0000-4000-8000-000000000da1";
const enrollment = "00000000-0000-4000-8000-000000000da2";
const rowOf = (n: number) =>
  `00000000-0000-4000-8000-${String(870000 + n).padStart(12, "0")}`;

const columns = [
  { key: "c1", name: "Student", type: "link" },
  { key: "c2", name: "Remarks", type: "select" },
  { key: "c3", name: "Quiz 1", type: "int" },
  { key: "c4", name: "Advisor", type: "link" },
];

function appearance(
  sheet: string,
  title: string,
  owner: { id: string; display_name: string },
  rowNumber: number,
) {
  return {
    worksheet_id: sheet,
    worksheet_title: title,
    owner,
    row_id: rowOf(rowNumber),
    row_number: rowNumber,
    column_key: "c1",
    column_name: "Student",
    columns,
    cells: {
      c1: { link: { record_id: alyssa, label: "Ana Cruz" } },
      c2: { value: "o1" },
      c3: { value: 18 },
      c4: { state: "no_access" },
    } as Record<string, WireSheetCell>,
  };
}

const you = { id: listIds.user, display_name: "Andrea Villamor" };
const bernard = {
  id: sheetPeople.colleague.id,
  display_name: sheetPeople.colleague.name,
};

type Held = { offset: number; release: () => Promise<void> };

/**
 * Route 23 over a list the test can change, and route 4 for its sheets.
 * `hidden` drops rows from the answers after counting (as a row the viewer
 * stops seeing between the count and the page); `fail` answers every read
 * with that status; `hold` keeps the read of that offset until released.
 */
async function installAppearsApi(
  page: Page,
  items: ReturnType<typeof appearance>[],
  options: {
    extraColumns?: Record<string, unknown>[];
    missingSheets?: string[];
  } = {},
) {
  const state = {
    items,
    offsets: [] as number[],
    hidden: new Set<number>(),
    fail: null as number | null,
    hold: null as number | null,
    held: [] as Held[],
  };
  await page.route(
    (url) => url.pathname === `/api/records/${alyssa}/worksheet-rows`,
    async (route) => {
      const url = new URL(route.request().url());
      const limit = Number(url.searchParams.get("limit"));
      const offset = Number(url.searchParams.get("offset"));
      state.offsets.push(offset);
      if (state.fail !== null)
        return route.fulfill({
          status: state.fail,
          json: {
            detail:
              state.fail === 404
                ? { code: "record_not_found", message: "Record not found" }
                : { code: "internal_error", message: "Try again" },
          },
        });
      const shown = state.items
        .slice(offset, offset + limit)
        .filter((_, index) => !state.hidden.has(offset + index));
      const answer = () =>
        route.fulfill({
          headers: { "Cache-Control": "no-store" },
          json: {
            items: shown,
            pagination: {
              limit,
              offset,
              count: shown.length,
              total: state.items.length,
              has_more: offset + limit < state.items.length,
              total_is_capped: false,
            },
          },
        });
      if (state.hold === offset) {
        // A read the page gave up on cannot be answered; that is the point.
        state.held.push({ offset, release: () => answer().catch(() => {}) });
        return;
      }
      return answer();
    },
  );
  await page.route(
    (url) =>
      (options.missingSheets ?? []).some(
        (sheet) => url.pathname === `/api/worksheets/${sheet}`,
      ),
    (route) =>
      route.fulfill({
        status: 404,
        json: {
          detail: { code: "worksheet_not_found", message: "Sheet not found" },
        },
      }),
  );
  await page.route(
    (url) => url.pathname === `/api/worksheets/${class1a}`,
    (route) =>
      route.fulfill({
        json: {
          ...wireSheetDetail(
            wireSheetSummary(class1a, "Class 1A", { recordId: alyssa }),
          ),
          structure: {
            structureVersion: 1,
            nextColumnSeq: 6,
            columns: [
              {
                key: "c1",
                name: "Student",
                type: "link",
                link: { moduleId: listIds.module },
              },
              {
                key: "c2",
                name: "Remarks",
                type: "select",
                select: { options: [{ id: "o1", label: "Passed" }] },
              },
              { key: "c3", name: "Quiz 1", type: "int" },
              {
                key: "c4",
                name: "Advisor",
                type: "link",
                link: { moduleId: listIds.module },
              },
              ...(options.extraColumns ?? []),
            ],
            groups: [],
            totals: {},
          },
        },
      }),
  );
  return state;
}

async function openSheetsTab(
  page: Page,
  items: ReturnType<typeof appearance>[],
  options: Parameters<typeof installAppearsApi>[2] & {
    /** After the fakes, before the page opens (a later route wins). */
    before?: (api: Awaited<ReturnType<typeof installAppearsApi>>) => unknown;
  } = {},
) {
  await installListApi(page, { viewer: "reader" });
  await installSheetsApi(page, { live: [] });
  const api = await installAppearsApi(page, items, options);
  await options.before?.(api);
  await page.goto(`${contacts}&record=${alyssa}`);
  const panel = await openedSheet(
    page.getByRole("dialog", { name: "Record details" }),
  );
  await panel.getByRole("tab").last().click();
  return {
    api,
    panel,
    appears: panel.getByRole("region", { name: "Appears in" }),
  };
}

test("Appears in lists the rows that link here, read only, each opening to its values and its sheet", async ({
  page,
}) => {
  const { appears } = await openSheetsTab(page, [
    appearance(class1a, "Class 1A", you, 1),
    appearance(enrollment, "Mid-Year Enrollment list", bernard, 7),
  ]);
  await expect(
    appears.getByRole("heading", { name: "Appears in" }),
  ).toBeVisible();
  await expect(appears).toContainText("2");
  const entries = appears.getByRole("listitem");
  await expect(entries).toHaveCount(2);
  await expect(entries.nth(0)).toContainText("Class 1A");
  await expect(entries.nth(0)).toContainText("Andrea Villamor (you) · row 1");
  await expect(entries.nth(1)).toContainText("Mid-Year Enrollment list");
  await expect(entries.nth(1)).toContainText("Bernard Ocampo · row 7");

  const open = entries.nth(0).getByRole("button", { name: /Class 1A/ });
  await expect(open).toHaveAttribute("aria-expanded", "false");
  await open.click();
  await expect(open).toHaveAttribute("aria-expanded", "true");
  const values = entries.nth(0).getByRole("definition");
  // The whole row as the sheet shows it; the column that links here holds
  // this record (Screens 6).
  await expect(entries.nth(0).getByRole("term")).toHaveText([
    "Student",
    "Remarks",
    "Quiz 1",
    "Advisor",
  ]);
  await expect(values).toHaveText(["Ana Cruz", "Passed", "18", "No access"]);
  // The sheet opens at this row: its id, and its number to find it by.
  await expect(
    entries.nth(0).getByRole("link", { name: "Open the sheet at this row" }),
  ).toHaveAttribute("href", `/openview?sheet=${class1a}&row=${rowOf(1)}&n=1`);
  // A definition list holds only its terms and values.
  await expect(entries.nth(0).locator("dl").getByRole("link")).toHaveCount(0);
  // Read only: nothing to type into or save.
  await expect(appears.getByRole("textbox")).toHaveCount(0);
  await expect(appears.getByRole("combobox")).toHaveCount(0);
});

test("with no rows linking here, Appears in keeps its frame and says so", async ({
  page,
}) => {
  const { appears } = await openSheetsTab(page, []);
  await expect(appears).toContainText("No rows link here");
  await expect(appears).toContainText(
    "Rows of sheets you can see that link to this record show here.",
  );
  await expect(appears.getByRole("button")).toHaveCount(0);
});

test("more rows load after the page's window, focus goes to the first new row, and an event reads the list once", async ({
  page,
}) => {
  const many = Array.from({ length: 30 }, (_, index) =>
    appearance(class1a, "Class 1A", you, index + 1),
  );
  const { api, appears } = await openSheetsTab(page, many, {
    // The first row leaves the viewer's sight after the count: page one
    // holds 24 rows of its 25.
    before: (state) => state.hidden.add(0),
  });
  const entries = appears.getByRole("listitem");
  await expect(entries).toHaveCount(24);
  await expect(appears).toContainText("30");
  await appears.getByRole("button", { name: "Show more" }).click();
  await expect(entries).toHaveCount(29);
  await expect(appears.getByRole("button", { name: "Show more" })).toHaveCount(
    0,
  );
  expect(api.offsets.filter((offset) => offset > 0)).toEqual([25]);
  await expect(entries.nth(24).getByRole("button")).toBeFocused();
  await expect(entries.nth(24)).toContainText("row 26");

  // The stream's resync reads the first page once, and later pages go.
  const atResync = api.offsets.length;
  await sendOpenViewEvent(page, "resync");
  await expect(entries).toHaveCount(24);
  expect(api.offsets.slice(atResync)).toEqual([0]);

  // A row of another sheet now links here (its owner shared it).
  api.hidden.clear();
  api.items = [appearance(enrollment, "Mid-Year Enrollment list", bernard, 3)];
  const atEvent = api.offsets.length;
  await sendOpenViewEvent(page, "invalidate", {
    entity: "worksheets",
    entity_id: enrollment,
  });
  await expect(entries).toHaveCount(1);
  await expect(appears).toContainText("Bernard Ocampo · row 3");
  expect(api.offsets.slice(atEvent)).toEqual([0]);
});

test("a later page answered after the list was read again is dropped", async ({
  page,
}) => {
  const many = Array.from({ length: 30 }, (_, index) =>
    appearance(class1a, "Class 1A", you, index + 1),
  );
  const { api, appears } = await openSheetsTab(page, many);
  const entries = appears.getByRole("listitem");
  await expect(entries).toHaveCount(25);
  api.hold = 25;
  await appears.getByRole("button", { name: "Show more" }).click();
  await expect.poll(() => api.held.length).toBe(1);

  // The held read ends one way or the other: given up, or answered late.
  const settled = new Promise<void>((done) => {
    const ended = (request: { url(): string }) => {
      if (request.url().includes("offset=25")) done();
    };
    page.on("requestfinished", ended);
    page.on("requestfailed", ended);
  });
  api.items = many.slice(0, 2);
  await sendOpenViewEvent(page, "invalidate", {
    entity: "worksheets",
    entity_id: class1a,
  });
  await expect(entries).toHaveCount(2);
  await api.held[0].release();
  await settled;
  await page.evaluate(
    () => new Promise((done) => requestAnimationFrame(() => done(null))),
  );
  await expect(entries).toHaveCount(2);
  await expect(appears.getByRole("button", { name: "Show more" })).toHaveCount(
    0,
  );
});

test("a row that links here through two columns names the column in each entry", async ({
  page,
}) => {
  const student = appearance(class1a, "Class 1A", you, 1);
  const advisor = {
    ...student,
    column_key: "c4",
    column_name: "Advisor",
    cells: {
      ...student.cells,
      c4: { link: { record_id: alyssa, label: "Ana Cruz" } },
    },
  };
  const { appears } = await openSheetsTab(page, [
    student,
    advisor,
    appearance(enrollment, "Mid-Year Enrollment list", bernard, 7),
  ]);
  const entries = appears.getByRole("listitem");
  await expect(entries.nth(0)).toContainText(
    "Andrea Villamor (you) · row 1 · Student",
  );
  await expect(entries.nth(1)).toContainText(
    "Andrea Villamor (you) · row 1 · Advisor",
  );
  // A row that links here once keeps the short line.
  await expect(entries.nth(2)).toContainText("Bernard Ocampo · row 7");
  await expect(entries.nth(2)).not.toContainText("Student");
});

test("a failed read offers Retry, and the list it brings takes focus", async ({
  page,
}) => {
  const { api, appears } = await openSheetsTab(
    page,
    [appearance(class1a, "Class 1A", you, 1)],
    { before: (state) => (state.fail = 500) },
  );
  await expect(appears).toContainText("Appears in could not be loaded.");
  api.fail = null;
  await appears.getByRole("button", { name: "Retry" }).click();
  const entries = appears.getByRole("listitem");
  await expect(entries).toHaveCount(1);
  await expect(entries.nth(0).getByRole("button")).toBeFocused();
});

test("a failed background read keeps the list and says so in one line", async ({
  page,
}) => {
  const { api, appears } = await openSheetsTab(page, [
    appearance(class1a, "Class 1A", you, 1),
  ]);
  const entries = appears.getByRole("listitem");
  await expect(entries).toHaveCount(1);
  api.fail = 500;
  await sendOpenViewEvent(page, "invalidate", {
    entity: "worksheets",
    entity_id: class1a,
  });
  await expect(appears).toContainText("Appears in could not be refreshed.");
  await expect(entries).toHaveCount(1);
  await expect(appears).not.toContainText("could not be loaded");
  api.fail = null;
  api.items = [
    appearance(class1a, "Class 1A", you, 1),
    appearance(enrollment, "Mid-Year Enrollment list", bernard, 7),
  ];
  await appears.getByRole("button", { name: "Retry" }).click();
  await expect(entries).toHaveCount(2);
  await expect(appears).not.toContainText("could not be refreshed");
});

test("a record that is gone or unreadable hides Appears in", async ({
  page,
}) => {
  const read = page.waitForResponse((response) =>
    response.url().includes("/worksheet-rows"),
  );
  const { panel, appears } = await openSheetsTab(
    page,
    [appearance(class1a, "Class 1A", you, 1)],
    { before: (state) => (state.fail = 404) },
  );
  expect((await read).status()).toBe(404);
  await expect(panel.getByRole("tabpanel")).toBeVisible();
  await expect(appears).toHaveCount(0);
});

test("a sheet that went away while listed shows no values, and the list is read again", async ({
  page,
}) => {
  const { api, appears } = await openSheetsTab(
    page,
    [appearance(enrollment, "Mid-Year Enrollment list", bernard, 7)],
    { missingSheets: [enrollment] },
  );
  const entries = appears.getByRole("listitem");
  await expect(entries).toHaveCount(1);
  const reads = api.offsets.length;
  // The sheet is no longer shared with the viewer: route 23 drops it too.
  api.items = [];
  await entries.nth(0).getByRole("button").click();
  await expect(appears).toContainText("No rows link here");
  expect(api.offsets.slice(reads)).toEqual([0]);
  await expect(appears.getByRole("definition")).toHaveCount(0);
});

test("a person cell shows nothing while the name loads, and Unknown person when it cannot", async ({
  page,
}) => {
  const teacher = appearance(class1a, "Class 1A", you, 1);
  const withTeacher = {
    ...teacher,
    columns: [...teacher.columns, { key: "c5", name: "Teacher", type: "user" }],
    cells: { ...teacher.cells, c5: { value: bernard.id } },
  };
  let answer: (() => Promise<void>) | undefined;
  const { appears } = await openSheetsTab(page, [withTeacher], {
    extraColumns: [{ key: "c5", name: "Teacher", type: "user" }],
    before: () =>
      page.route(`**/api/users/${bernard.id}/card`, (route) => {
        answer = () =>
          route.fulfill({
            status: 500,
            json: { detail: { code: "internal_error", message: "Try again" } },
          });
      }),
  });
  await appears.getByRole("button", { name: /Class 1A/ }).click();
  const values = appears.getByRole("definition");
  await expect(values).toHaveText([
    "Ana Cruz",
    "Passed",
    "18",
    "No access",
    "",
  ]);
  await expect.poll(() => answer !== undefined).toBe(true);
  await answer?.();
  await expect(values.last()).toHaveText("Unknown person");
});

test.describe("on a phone", () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test("each row is a 44px target and its values fit the width", async ({
    page,
  }) => {
    const { appears } = await openSheetsTab(page, [
      appearance(class1a, "Class 1A", you, 1),
    ]);
    const open = appears.getByRole("button", { name: /Class 1A/ });
    const box = await open.boundingBox();
    expect(box?.height ?? 0).toBeGreaterThanOrEqual(44);
    await open.click();
    await expect(appears.getByRole("definition")).toHaveText([
      "Ana Cruz",
      "Passed",
      "18",
      "No access",
    ]);
    const width = await page.evaluate(
      () => document.documentElement.scrollWidth,
    );
    expect(width).toBeLessThanOrEqual(390);
  });
});
