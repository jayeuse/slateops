import { expect, test, type Page } from "@playwright/test";
import { sendOpenViewEvent } from "./helpers/openview-event-source";
import {
  at,
  checksTable,
  dashboardWire,
  definition,
  equipmentBar,
  equipmentNumber,
  homeUrl,
  ids,
  installDashboardApi,
  invoicesNumber,
  manager,
  reader,
  card,
  editLayout,
  groupQuery,
  timestamp,
  widget,
} from "./helpers/openview-dashboard-api";
import { keysetPageOf, pageOf } from "../helpers/pagination";
import { wireBucket, wireField, wireRecord } from "../helpers/wire";

// docs/specs/openview-dashboard.md, part B: the department dashboard.

test("each department's Dashboard row opens its home dashboard, read once per module", async ({
  page,
}) => {
  const api = await installDashboardApi(page, { identity: manager });
  await page.goto("/openview?section=dashboards");
  // The address names the first department, so the sidebar and the
  // breadcrumb follow it (BD1).
  await expect(page).toHaveURL(homeUrl);
  const group = page.getByRole("list", { name: "Field service pages" });
  // The group reads Dashboard, Announcements, then its modules (Boards BR1).
  await expect(group.getByRole("link")).toHaveText([
    "Dashboard",
    "Announcements",
    "Equipment",
    "Quality checks",
  ]);
  await expect(group.getByRole("link", { name: "Dashboard" })).toHaveAttribute(
    "aria-current",
    "page",
  );
  await expect(page.getByRole("navigation", { name: "breadcrumb" })).toHaveText(
    /^Field service\s*Dashboard$/,
  );
  // Reports live on module pages, so the sidebar has no OpenView item
  // (EXIT-B1, DC9).
  await expect(page.getByRole("button", { name: "OpenView" })).toHaveCount(0);
  await expect(
    page
      .getByRole("navigation", { name: "Main navigation" })
      .getByRole("link", { name: /^(Dashboards|Charts|Reports)$/ }),
  ).toHaveCount(0);

  await expect(
    page.getByRole("heading", { level: 1, name: "Field service dashboard" }),
  ).toBeVisible();
  await expect(card(page, "Equipment")).toContainText("12");
  await expect(card(page, "Equipment by Category")).toContainText("Repair");
  await expect(card(page, "Quality checks by Result")).toContainText(
    "1–2 of 2",
  );
  // One read per module (BD6): Equipment's two widgets share one batch.
  expect(
    api.batches.map((batch) => [batch.moduleIds.join(), batch.count]).sort(),
  ).toEqual(
    [
      [ids.equipment, 2],
      [ids.checks, 1],
    ].sort(),
  );
});

test("a widget on a module the viewer cannot read is a locked card while the others load", async ({
  page,
}) => {
  await installDashboardApi(page, {
    identity: reader,
    hidden: [ids.invoices],
    dashboards: [
      dashboardWire({
        widgets: [equipmentNumber(), invoicesNumber(), equipmentBar()],
      }),
    ],
  });
  await page.goto(homeUrl);
  const locked = card(page, "Number");
  await expect(locked).toContainText("No access to these records");
  await expect(locked).toContainText("Ask an administrator for access.");
  await expect(card(page, "Equipment")).toContainText("12");
  await expect(card(page, "Equipment by Category")).toContainText("Repair");
  await expect(page.getByText("OpenView data is unavailable")).toHaveCount(0);
  // A reader sees the dashboard, with no layout controls (BD2).
  await expect(page.getByRole("button", { name: "Edit layout" })).toHaveCount(
    0,
  );
});

test("a source in a linked department names that department on its card", async ({
  page,
}) => {
  await installDashboardApi(page, {
    identity: manager,
    dashboards: [dashboardWire({ widgets: [invoicesNumber()] })],
  });
  await page.goto(homeUrl);
  const linked = card(page, "Invoices");
  await expect(linked).toContainText("Finance");
  await expect(linked).toContainText("12");
});

test("a department without a dashboard offers its managers the presets and tells readers none exists", async ({
  page,
}) => {
  const api = await installDashboardApi(page, {
    identity: manager,
    dashboards: [],
  });
  await page.goto(homeUrl);
  await expect(
    page.getByRole("heading", { name: "Set up the Field service dashboard" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Overview" }).click();
  // The preset places empty spaces; each asks for its chart.
  await expect(page.getByRole("button", { name: "Add a number" })).toHaveCount(
    4,
  );
  await expect(
    page.getByRole("button", { name: "Add a bar chart" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Add a bar chart" }).click();
  const builder = page.getByRole("dialog", { name: "Add a chart" });
  await expect(builder).toContainText("2 × 2 space");
  await expect(builder.getByRole("radio", { name: "Bar" })).toHaveAttribute(
    "aria-checked",
    "true",
  );
  await builder.getByRole("button", { name: "Add to dashboard" }).click();
  await page.getByRole("button", { name: "Save layout" }).click();
  await expect(
    page.getByRole("heading", { level: 1, name: "Field service dashboard" }),
  ).toBeVisible();
  const created = api.writes.find((write) => write.method === "POST");
  expect(created?.body).toEqual({
    department_id: ids.department,
    name: "Field service dashboard",
    position: 0,
    refresh_cadence: "manual",
    widgets: [
      {
        widget_type: "chart",
        grid_column: 0,
        grid_row: 1,
        column_span: 2,
        row_span: 2,
        chart_id: null,
        config: {
          version: 1,
          chart_type: "bar",
          query: {
            mode: "groups",
            module_id: ids.equipment,
            definition: {
              version: 1,
              logic: "and",
              columns: [],
              filters: [],
              sort: [],
              deleted: "exclude",
              search: null,
              search_fields: [],
            },
            aggregation: "count",
            measure: null,
            dimension: { field_id: ids.category, expected_type: "select" },
          },
        },
      },
    ],
  });
});

test("a reader of a department without a dashboard sees that none exists", async ({
  page,
}) => {
  await installDashboardApi(page, { identity: reader, dashboards: [] });
  await page.goto(homeUrl);
  await expect(
    page.getByRole("heading", { name: "No dashboard yet" }),
  ).toBeVisible();
  await expect(page.getByRole("button", { name: "Overview" })).toHaveCount(0);
});

// QA-1: a new department's home exists from the publish with no widgets, so
// its managers still get the presets, and a preset fills that home.
test("an empty home offers its managers the presets and a preset fills that home", async ({
  page,
}) => {
  const api = await installDashboardApi(page, {
    identity: manager,
    dashboards: [dashboardWire({ widgets: [] })],
  });
  await page.goto(homeUrl);
  await expect(
    page.getByRole("heading", { name: "Set up the Field service dashboard" }),
  ).toBeVisible();
  // The home is already empty, so there is no "Start empty".
  await expect(page.getByRole("button", { name: "Start empty" })).toHaveCount(
    0,
  );
  await page.getByRole("button", { name: "Overview" }).click();
  await page.getByRole("button", { name: "Add a bar chart" }).click();
  await page
    .getByRole("dialog", { name: "Add a chart" })
    .getByRole("button", { name: "Add to dashboard" })
    .click();
  await page.getByRole("button", { name: "Save layout" }).click();
  await expect(page.getByRole("toolbar", { name: "Edit layout" })).toHaveCount(
    0,
  );
  expect(api.writes.filter((write) => write.method === "POST")).toEqual([]);
  const save = api.writes.find((write) => write.method === "PATCH");
  expect(save?.path).toBe(`/api/dashboards/${ids.home}`);
  expect(save?.body?.revision).toBe(3);
  expect(
    (save?.body?.widgets as Record<string, unknown>[]).map((item) => [
      item.widget_type,
      item.grid_column,
      item.grid_row,
      item.column_span,
      item.row_span,
    ]),
  ).toEqual([["chart", 0, 1, 2, 2]]);
});

test("a reader of an empty home sees the dashboard, not the presets", async ({
  page,
}) => {
  await installDashboardApi(page, {
    identity: reader,
    dashboards: [dashboardWire({ widgets: [] })],
  });
  await page.goto(homeUrl);
  await expect(
    page.getByRole("heading", { level: 1, name: "Field service dashboard" }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Set up the Field service dashboard" }),
  ).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Overview" })).toHaveCount(0);
});

test("a manager arranges the layout with the keyboard alone and saves one update with the revision", async ({
  page,
}) => {
  const api = await installDashboardApi(page, {
    identity: manager,
    dashboards: [
      dashboardWire({ widgets: [equipmentNumber(), equipmentBar()] }),
    ],
  });
  await page.goto(homeUrl);
  await editLayout(page);
  const handle = page.getByRole("button", {
    name: "Move or resize Equipment",
    exact: true,
  });
  await handle.focus();
  await page.keyboard.press("ArrowRight");
  await expect(
    page.getByRole("status").filter({ hasText: "Moved" }),
  ).toHaveText("Moved: column 2, row 1, 1 × 1.");
  await page.keyboard.press("Shift+ArrowRight");
  await expect(
    page.getByRole("status").filter({ hasText: "Resized" }),
  ).toHaveText("Resized: column 2, row 1, 2 × 1.");
  // A number is one row high: the size rules stop the change and say why.
  await page.keyboard.press("Shift+ArrowDown");
  await expect(
    page.getByRole("status").filter({ hasText: "Not changed" }),
  ).toHaveText("Not changed: too large for a number.");
  await page.getByRole("button", { name: "Save layout" }).click();
  await expect(page.getByRole("toolbar", { name: "Edit layout" })).toHaveCount(
    0,
  );
  const save = api.writes.find((write) => write.method === "PATCH");
  expect(save?.body?.revision).toBe(3);
  expect(
    (save?.body?.widgets as Record<string, unknown>[]).map((item) => [
      item.widget_type,
      item.grid_column,
      item.grid_row,
      item.column_span,
      item.row_span,
    ]),
  ).toEqual([
    ["summary", 1, 0, 2, 1],
    ["chart", 0, 1, 2, 2],
  ]);
});

test("the widget menu lists every size with the reason it cannot be taken, and moves", async ({
  page,
}) => {
  const api = await installDashboardApi(page, {
    identity: manager,
    dashboards: [dashboardWire({ widgets: [equipmentBar(at(2, 1, 2, 2))] })],
  });
  await page.goto(homeUrl);
  await editLayout(page);
  await card(page, "Equipment by Category")
    .getByRole("button", { name: "Equipment by Category, actions" })
    .click();
  const menu = page.getByRole("menu");
  await expect(
    menu.getByRole("menuitemradio", { name: /^1 × 1/ }),
  ).toContainText("too small for a bar chart");
  await expect(
    menu.getByRole("menuitemradio", { name: /^1 × 1/ }),
  ).toHaveAttribute("aria-disabled", "true");
  await expect(
    menu.getByRole("menuitemradio", { name: /^2 × 2/ }),
  ).toHaveAttribute("aria-checked", "true");
  await expect(
    menu.getByRole("menuitem", { name: /^Move right/ }),
  ).toContainText("at the edge");
  await menu.getByRole("menuitem", { name: "Move left" }).click();
  await card(page, "Equipment by Category")
    .getByRole("button", { name: "Equipment by Category, actions" })
    .click();
  await page.getByRole("menuitemradio", { name: /^3 × 3/ }).click();
  await page.getByRole("button", { name: "Save layout" }).click();
  await expect(page.getByRole("toolbar", { name: "Edit layout" })).toHaveCount(
    0,
  );
  const saved = api.writes.at(-1)?.body?.widgets as Record<string, unknown>[];
  expect(saved[0]).toMatchObject({
    grid_column: 1,
    grid_row: 1,
    column_span: 3,
    row_span: 3,
  });
});

test("dragging a widget by pointer moves it to the cells under it", async ({
  page,
}) => {
  await page.clock.install();
  const api = await installDashboardApi(page, {
    identity: manager,
    dashboards: [dashboardWire({ widgets: [equipmentNumber()] })],
  });
  await page.goto(homeUrl);
  await editLayout(page);
  const handle = page.getByRole("button", {
    name: "Move or resize Equipment",
    exact: true,
  });
  const target = page.getByRole("button", {
    name: "Add a widget at column 3, row 2",
  });
  const from = await handle.boundingBox();
  const to = await target.boundingBox();
  if (!from || !to) throw new Error("The grid is not laid out");
  const cell = await card(page, "Equipment").boundingBox();
  if (!cell) throw new Error("The card is not laid out");
  // Grab the handle and drop the card's corner on column 3, row 2.
  await page.mouse.move(from.x + from.width / 2, from.y + from.height / 2);
  await page.mouse.down();
  await page.mouse.move(from.x + 20, from.y + 20, { steps: 4 });
  await page.mouse.move(
    from.x + from.width / 2 + (to.x - cell.x),
    from.y + from.height / 2 + (to.y - cell.y),
    { steps: 8 },
  );
  await page.mouse.up();
  await expect(
    page.getByRole("button", { name: "Add a widget at column 3, row 2" }),
  ).toHaveCount(0);
  // The drop swallows clicks for 50ms (dnd-kit), as it does for a person.
  await page.clock.runFor(100);
  await page.getByRole("button", { name: "Save layout" }).click();
  await expect(page.getByRole("toolbar", { name: "Edit layout" })).toHaveCount(
    0,
  );
  expect(api.writes.at(-1)?.body?.widgets).toMatchObject([
    { grid_column: 2, grid_row: 1, column_span: 1, row_span: 1 },
  ]);
});

test("a layout refusal marks the widget it names, and a conflict keeps the edit and offers a reload", async ({
  page,
}) => {
  const api = await installDashboardApi(page, {
    identity: manager,
    dashboards: [
      dashboardWire({ widgets: [equipmentNumber(), equipmentBar()] }),
    ],
  });
  await page.goto(homeUrl);
  await editLayout(page);
  await page
    .getByRole("button", { name: "Move or resize Equipment", exact: true })
    .focus();
  await page.keyboard.press("ArrowRight");
  api.nextSaveFailure = {
    status: 422,
    detail: {
      code: "dashboard_layout_invalid",
      message: "The dashboard layout does not fit the grid",
      errors: [
        { index: 1, code: "overlap", message: "This widget overlaps widget 1" },
      ],
    },
  };
  await page.getByRole("button", { name: "Save layout" }).click();
  await expect(
    card(page, "Equipment by Category").getByRole("alert"),
  ).toHaveText("This widget overlaps widget 1.");
  await expect(
    page.getByRole("toolbar", { name: "Edit layout" }),
  ).toBeVisible();

  api.nextSaveFailure = {
    status: 409,
    detail: { code: "stale_revision", current_revision: 4 },
  };
  await page.getByRole("button", { name: "Save layout" }).click();
  await expect(
    page.getByText(
      "Someone changed this dashboard while you were editing. Your layout is still here.",
    ),
  ).toBeVisible();
  await expect(
    page.getByRole("toolbar", { name: "Edit layout" }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Discard my changes and reload" })
    .click();
  await expect(page.getByRole("toolbar", { name: "Edit layout" })).toHaveCount(
    0,
  );
});

test("leaving with unsaved layout changes asks first", async ({ page }) => {
  await installDashboardApi(page, {
    identity: manager,
    dashboards: [dashboardWire({ widgets: [equipmentNumber()] })],
  });
  await page.goto(homeUrl);
  await editLayout(page);
  await page
    .getByRole("button", { name: "Move or resize Equipment", exact: true })
    .focus();
  await page.keyboard.press("ArrowDown");
  await page
    .getByRole("list", { name: "Field service pages" })
    .getByRole("link", { name: "Equipment" })
    .click();
  const confirm = page.getByRole("alertdialog", {
    name: "Leave without saving the layout?",
  });
  await expect(confirm).toBeVisible();
  await confirm.getByRole("button", { name: "Keep editing" }).click();
  await expect(page).toHaveURL(homeUrl);
  await expect(
    page.getByRole("toolbar", { name: "Edit layout" }),
  ).toBeVisible();
});

test("a preset replaces the layout only after a confirmation", async ({
  page,
}) => {
  await installDashboardApi(page, { identity: manager });
  await page.goto(homeUrl);
  await editLayout(page);
  await page.getByRole("button", { name: "Presets" }).click();
  await page.getByRole("menuitem", { name: "Lists first" }).click();
  const confirm = page.getByRole("alertdialog", {
    name: "Replace the layout with Lists first?",
  });
  await confirm.getByRole("button", { name: "Keep this layout" }).click();
  await expect(card(page, "Equipment by Category")).toBeVisible();
  await page.getByRole("button", { name: "Presets" }).click();
  await page.getByRole("menuitem", { name: "Lists first" }).click();
  await confirm.getByRole("button", { name: "Replace the layout" }).click();
  await expect(card(page, "Equipment by Category")).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: "Add a records list" }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Add a pie chart" }),
  ).toBeVisible();
});

test("a widget the grid migration could not place must be placed before the layout saves", async ({
  page,
}) => {
  const lost = equipmentNumber({
    grid_column: null,
    grid_row: null,
    column_span: null,
    row_span: null,
  });
  await installDashboardApi(page, {
    identity: manager,
    dashboards: [dashboardWire({ widgets: [equipmentBar(), lost] })],
  });
  await page.goto(homeUrl);
  await editLayout(page);
  const save = page.getByRole("button", { name: "Save layout" });
  await expect(save).toHaveAttribute("aria-disabled", "true");
  await expect(save).toHaveAccessibleDescription(
    "Place or remove the widgets that are not on the grid",
  );
  await page
    .getByRole("region", { name: "Not on the grid" })
    .getByRole("button", { name: "Place it" })
    .click();
  await expect(
    page.getByRole("region", { name: "Not on the grid" }),
  ).toHaveCount(0);
  await expect(save).not.toHaveAttribute("aria-disabled", "true");
});

test("phones stack the widgets in reading order and keep the layout for larger screens", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await installDashboardApi(page, {
    identity: manager,
    dashboards: [
      dashboardWire({
        widgets: [
          checksTable(at(2, 1, 2, 2)),
          equipmentBar(at(0, 1, 2, 2)),
          equipmentNumber(at(0, 0, 1, 1)),
        ],
      }),
    ],
  });
  await page.goto(homeUrl);
  await expect(page.locator("#main-content article")).toHaveCount(3);
  await expect(
    page
      .locator("#main-content article")
      .evaluateAll((cards) =>
        cards.map((element) => element.getAttribute("aria-label")),
      ),
  ).resolves.toEqual([
    "Equipment",
    "Equipment by Category",
    "Quality checks by Result",
  ]);
  const edit = page.getByRole("button", { name: "Edit layout" });
  await expect(edit).toHaveAttribute("aria-disabled", "true");
  await expect(edit).toHaveAccessibleDescription(
    "Edit the layout on a larger screen.",
  );
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth - window.innerWidth,
    ),
  ).toBe(0);
});

test("settings rename the dashboard and set its refresh with the saved revision", async ({
  page,
}) => {
  const api = await installDashboardApi(page, { identity: manager });
  await page.goto(homeUrl);
  await page.getByRole("button", { name: "More dashboard actions" }).click();
  await page.getByRole("menuitem", { name: "Settings…" }).click();
  const dialog = page.getByRole("dialog", { name: "Dashboard settings" });
  await dialog.getByLabel("Name").fill("Service floor");
  await dialog.getByLabel("Refresh").selectOption("one-minute");
  await dialog.getByRole("button", { name: "Save settings" }).click();
  await expect(
    page.getByRole("heading", { level: 1, name: "Service floor" }),
  ).toBeVisible();
  await expect(page.getByText(/· every minute$/)).toBeVisible();
  expect(api.writes.at(-1)?.body).toEqual({
    revision: 3,
    name: "Service floor",
    refresh_cadence: "one-minute",
  });
});

test("archiving the home dashboard hands the department to the next one, and it restores", async ({
  page,
}) => {
  const api = await installDashboardApi(page, {
    identity: manager,
    dashboards: [
      dashboardWire(),
      dashboardWire({
        id: ids.other,
        name: "Night shift",
        is_home: false,
        position: 1,
        widgets: [equipmentNumber()],
      }),
    ],
  });
  await page.goto(homeUrl);
  await page.getByRole("button", { name: "More dashboard actions" }).click();
  await expect(
    page.getByRole("menuitem", { name: "Night shift" }),
  ).toBeVisible();
  await page.getByRole("menuitem", { name: "Archive this dashboard…" }).click();
  await page
    .getByRole("alertdialog", { name: "Archive Field service dashboard?" })
    .getByRole("button", { name: "Archive" })
    .click();
  await expect(
    page.getByRole("heading", { level: 1, name: "Night shift" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "More dashboard actions" }).click();
  await page.getByRole("menuitem", { name: "Archived dashboards…" }).click();
  await page
    .getByRole("dialog", { name: "Archived dashboards" })
    .getByRole("button", { name: "Restore Field service dashboard" })
    .click();
  await expect
    .poll(() => api.writes.map((write) => write.method))
    .toEqual(["DELETE", "POST"]);
  expect(api.writes[0]?.path).toBe(`/api/dashboards/${ids.home}`);
});

test("a refused OpenView read hides the dashboard and offers Retry", async ({
  page,
}) => {
  await installDashboardApi(page, { identity: manager });
  await page.route("**/api/records/aggregate-snapshots", (route) =>
    route.fulfill({
      status: 403,
      contentType: "application/json",
      body: JSON.stringify({ detail: "Forbidden" }),
    }),
  );
  await page.goto(homeUrl);
  await expect(
    page.getByText(
      "OpenView data is unavailable. Sign in or ask for access, then retry.",
    ),
  ).toBeVisible();
  await expect(page.getByRole("article")).toHaveCount(0);
});

test("record changes refresh only the widgets of their module, once per burst", async ({
  page,
}) => {
  await page.clock.install();
  const api = await installDashboardApi(page, { identity: reader });
  await page.goto(homeUrl);
  await expect(card(page, "Quality checks by Result")).toContainText("Repair");
  const before = api.batches.length;
  for (let count = 0; count < 3; count += 1)
    await sendOpenViewEvent(page, "invalidate", {
      entity: "records",
      module_id: ids.checks,
    });
  await page.clock.runFor(301);
  await expect
    .poll(() => api.batches.slice(before).map((batch) => batch.moduleIds))
    .toEqual([[ids.checks]]);
});

test("the cadence reads again on time and waits while the layout is being edited", async ({
  page,
}) => {
  await page.clock.install();
  const api = await installDashboardApi(page, {
    identity: manager,
    dashboards: [
      dashboardWire({
        refresh_cadence: "one-minute",
        widgets: [equipmentNumber()],
      }),
    ],
  });
  await page.goto(homeUrl);
  await expect(card(page, "Equipment")).toContainText("12");
  expect(api.batches).toHaveLength(1);
  await page.clock.runFor(60_000);
  await expect.poll(() => api.batches.length).toBe(2);
  await editLayout(page);
  await page.clock.runFor(120_000);
  expect(api.batches).toHaveLength(2);
});

test("after archiving the only dashboard a manager restores it from the setup state, and readers see no restore", async ({
  page,
}) => {
  const api = await installDashboardApi(page, { identity: manager });
  await page.goto(homeUrl);
  await page.getByRole("button", { name: "More dashboard actions" }).click();
  await page.getByRole("menuitem", { name: "Archive this dashboard…" }).click();
  await page
    .getByRole("alertdialog", { name: "Archive Field service dashboard?" })
    .getByRole("button", { name: "Archive" })
    .click();
  await expect(
    page.getByRole("heading", { name: "Set up the Field service dashboard" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Archived dashboards…" }).click();
  await page
    .getByRole("dialog", { name: "Archived dashboards" })
    .getByRole("button", { name: "Restore Field service dashboard" })
    .click();
  await expect(
    page.getByRole("heading", { level: 1, name: "Field service dashboard" }),
  ).toBeVisible();
  await expect(card(page, "Equipment")).toContainText("12");
  expect(api.writes.map((write) => [write.method, write.path])).toEqual([
    ["DELETE", `/api/dashboards/${ids.home}`],
    ["POST", `/api/dashboards/${ids.home}/restore`],
  ]);
});

test("a reader of a department whose dashboards are all archived is offered no restore", async ({
  page,
}) => {
  await installDashboardApi(page, {
    identity: reader,
    dashboards: [dashboardWire({ is_deleted: true })],
  });
  await page.goto(homeUrl);
  await expect(
    page.getByRole("heading", { name: "No dashboard yet" }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Archived dashboards…" }),
  ).toHaveCount(0);
});

test("cards, spaces and empty cells follow reading order, so a move changes the Tab order and the saved order", async ({
  page,
}) => {
  const api = await installDashboardApi(page, {
    identity: manager,
    dashboards: [
      dashboardWire({
        widgets: [
          equipmentNumber(at(0, 0, 1, 1)),
          invoicesNumber(at(1, 0, 1, 1)),
        ],
      }),
    ],
  });
  await page.goto(homeUrl);
  await editLayout(page);
  await page
    .getByRole("button", { name: "Move or resize Equipment", exact: true })
    .focus();
  await page.keyboard.press("ArrowDown");
  // Row 1 now reads: an empty cell, Invoices, two empty cells; Equipment
  // has moved to row 2.
  await card(page, "Invoices")
    .getByRole("button", { name: "Invoices, actions" })
    .focus();
  await page.keyboard.press("Tab");
  await expect(
    page.getByRole("button", { name: "Add a widget at column 3, row 1" }),
  ).toBeFocused();
  await page.getByRole("button", { name: "Save layout" }).click();
  await expect(page.getByRole("toolbar", { name: "Edit layout" })).toHaveCount(
    0,
  );
  const saved = api.writes.at(-1)?.body?.widgets as {
    config: { query: { module_id: string } };
    grid_row: number;
  }[];
  expect(
    saved.map((item) => [item.config.query.module_id, item.grid_row]),
  ).toEqual([
    [ids.invoices, 0],
    [ids.equipment, 1],
  ]);
});

test("a widget whose read fails says so and reads again on Retry", async ({
  page,
}) => {
  await installDashboardApi(page, { identity: reader });
  let failChecks = true;
  await page.route("**/api/records/aggregate-snapshots", (route) => {
    const body = route.request().postDataJSON() as {
      queries: { module_id: string }[];
    };
    if (failChecks && body.queries[0]?.module_id === ids.checks) {
      failChecks = false;
      return route.fulfill({
        status: 503,
        contentType: "application/json",
        body: JSON.stringify({ detail: "Unavailable" }),
      });
    }
    return route.fallback();
  });
  await page.goto(homeUrl);
  const failed = card(page, "Quality checks by Result");
  await expect(failed.getByRole("alert")).toBeVisible();
  await expect(card(page, "Equipment by Category")).toContainText("Repair");
  await failed.getByRole("button", { name: "Retry" }).click();
  await expect(failed).toContainText("Repair");
  await expect(failed.getByRole("alert")).toHaveCount(0);
});

// UF-C9.4 (DR-9.4, DR-9.5): widget titles read as plain names from the
// query, and a Number with no single value says so in words.
test("UF-C9.4: widget titles are plain names and an empty Number reads No values yet", async ({
  page,
}) => {
  await installDashboardApi(page, {
    identity: manager,
    dashboards: [
      dashboardWire({
        widgets: [
          equipmentNumber(),
          invoicesNumber(),
          equipmentBar(),
          // A distinct count over two groups has no single value to show.
          widget("summary", at(1, 0, 1, 1), {
            version: 1,
            query: {
              ...groupQuery(ids.equipment, ids.category),
              aggregation: "distinct",
              measure: { field_id: ids.category, expected_type: "select" },
            },
          }),
        ],
      }),
    ],
  });
  await page.goto(homeUrl);

  // The chart reads "Equipment" until its fields load, then gains "by …".
  await expect(card(page, "Equipment by Category")).toContainText("Repair");
  await expect(card(page, "Equipment")).toContainText("12");
  await expect(card(page, "Invoices")).toBeVisible();
  const empty = card(page, "Different category values");
  await expect(empty).toContainText("No values yet");
  await expect(empty).not.toContainText("—");
  await expect(
    page.getByRole("article", { name: /^(Number of|Sum of) / }),
  ).toHaveCount(0);
});

// docs/specs/subtle-interactions.md, candidate 6: a Number figure, a table
// group row and a records row open exactly the records they count.

/** The "Repair" option of the fixture's Choice fields. */
const repairOption = "00000000-0000-4000-8000-000000000901";
const inspectionOption = "00000000-0000-4000-8000-000000000902";
const nameField = "00000000-0000-4000-8000-000000000407";
const loggedAt = "00000000-0000-4000-8000-000000000408";

type ExactRead = {
  moduleId: string;
  logic: "and" | "or";
  /** Each condition as "<field id> <operator> <JSON value>". */
  conditions: string[];
  total: number;
};

/**
 * The module page a dashboard link opens: its views and its records. The
 * records read answers the figure's total only for the exact conditions it
 * names; any other read gets the fixture's 9 records, so a wrong condition
 * shows a different count.
 */
async function installModulePage(page: Page, exact: ExactRead[]) {
  const viewWrites: string[] = [];
  await page.route("**/api/views**", (route) => {
    const request = route.request();
    const url = new URL(request.url());
    // The catalog (`/api/views/data-sources…`) stays with the dashboard mock.
    if (
      url.pathname.startsWith("/api/views/data-sources") ||
      (url.pathname !== "/api/views" &&
        !/^\/api\/views\/[^/]+$/.test(url.pathname))
    )
      return route.fallback();
    if (request.method() !== "GET") {
      viewWrites.push(`${request.method()} ${url.pathname}`);
      return route.fulfill({ status: 405, json: { detail: "Not allowed" } });
    }
    return url.pathname === "/api/views"
      ? route.fulfill({ json: pageOf([], { limit: 100 }) })
      : route.fulfill({ status: 404, json: { detail: "View not found" } });
  });
  await page.route("**/api/relationships**", (route) =>
    route.fulfill({
      json: keysetPageOf([], { limit: 100, offset: 0, total: 0 }),
    }),
  );
  await page.route("**/api/records/query", (route) => {
    const body = route.request().postDataJSON() as {
      module_id: string;
      limit: number;
      offset: number;
      definition: {
        logic: string;
        filters: { field_id: string; operator: string; value?: unknown }[];
      };
    };
    const conditions = body.definition.filters.map(
      (filter) =>
        `${filter.field_id} ${filter.operator} ${JSON.stringify(filter.value ?? null)}`,
    );
    const match = exact.find(
      (item) =>
        item.moduleId === body.module_id &&
        item.logic === body.definition.logic &&
        JSON.stringify(item.conditions) === JSON.stringify(conditions),
    );
    if (!match) return route.fallback();
    const rows = Array.from({ length: match.total }, (_, index) =>
      wireRecord({
        id: `00000000-0000-4000-8000-${String(index + 901).padStart(12, "0")}`,
        module_id: body.module_id,
        data: {},
        created_at: timestamp,
        updated_at: timestamp,
      }),
    );
    return route.fulfill({
      json: pageOf(rows.slice(body.offset, body.offset + body.limit), {
        limit: body.limit,
        offset: body.offset,
        total: rows.length,
      }),
    });
  });
  return { viewWrites };
}

/**
 * Equipment names its records by a Name field, and its records read answers
 * two named records: North pump and South valve, both "Repair".
 */
async function installNamedEquipment(page: Page) {
  // Equipment names its records by the Name field.
  await page.route("**/api/views/data-sources**", (route) => {
    const url = new URL(route.request().url());
    if (url.pathname === "/api/views/data-sources")
      return route.fulfill({
        json: pageOf(
          [
            {
              id: ids.equipment,
              name: "Equipment",
              department_id: ids.department,
              title_field_id: nameField,
            },
            {
              id: ids.checks,
              name: "Quality checks",
              department_id: ids.department,
              title_field_id: null,
            },
          ],
          { limit: 100 },
        ),
      });
    if (url.pathname === `/api/views/data-sources/${ids.equipment}/fields`)
      return route.fulfill({
        json: pageOf(
          [
            wireField({
              id: nameField,
              module_id: ids.equipment,
              name: "Name",
              type: "text",
              position: 0,
            }),
            wireField({
              id: ids.category,
              module_id: ids.equipment,
              name: "Category",
              type: "select",
              position: 1,
              config: {
                options: [{ id: repairOption, label: "Repair" }],
              },
            }),
          ],
          { limit: 100 },
        ),
      });
    return route.fallback();
  });
  const records = ["North pump", "South valve"].map((name, index) =>
    wireRecord({
      id: `00000000-0000-4000-8000-${String(index + 811).padStart(12, "0")}`,
      module_id: ids.equipment,
      data: { [nameField]: name, [ids.category]: repairOption },
      display_values: { [ids.category]: "Repair" },
      created_at: timestamp,
      updated_at: timestamp,
    }),
  );
  await page.route("**/api/records/query", (route) =>
    route.fulfill({ json: pageOf(records, { limit: 5 }) }),
  );
  return records;
}

test("SI-C6.1: a Number figure opens its module page with the widget's conditions and its Date or Date-and-time window, and the page counts the figure", async ({
  page,
}) => {
  await installDashboardApi(page, {
    identity: manager,
    dashboards: [
      dashboardWire({
        widgets: [
          widget("summary", at(0, 0, 1, 1), {
            version: 1,
            query: {
              ...groupQuery(ids.equipment, ids.category),
              definition: {
                ...definition,
                filters: [
                  {
                    field_id: ids.category,
                    expected_type: "select",
                    operator: "eq",
                    value: repairOption,
                  },
                ],
              },
              date_field: { field_id: ids.occurred, expected_type: "date" },
              from_date: "2026-10-01",
              to_date: "2026-10-31",
            },
          }),
          // A Date and time window: midnight in the workspace zone
          // (Asia/Manila in the fixture), with its offset.
          widget("summary", at(1, 0, 1, 1), {
            version: 1,
            query: {
              ...groupQuery(ids.invoices, ids.invoiceStatus),
              date_field: { field_id: loggedAt, expected_type: "datetime" },
              from_date: "2026-10-26",
              to_date: "2026-10-26",
            },
          }),
          // No window: the widget's conditions only.
          widget("summary", at(2, 0, 1, 1), {
            version: 1,
            query: groupQuery(ids.checks, ids.checkStatus),
          }),
          // No single value: words, not a link (DR-9.5).
          // A total is not a count: its name says what the figure is.
          widget("summary", at(0, 1, 1, 1), {
            version: 1,
            query: {
              ...groupQuery(ids.equipment, ids.category),
              aggregation: "sum",
              measure: { field_id: ids.amount, expected_type: "decimal" },
            },
          }),
          widget("summary", at(3, 0, 1, 1), {
            version: 1,
            query: {
              ...groupQuery(ids.equipment, ids.category),
              aggregation: "distinct",
              measure: { field_id: ids.category, expected_type: "select" },
            },
          }),
        ],
      }),
    ],
  });
  await installModulePage(page, [
    {
      moduleId: ids.equipment,
      logic: "and",
      conditions: [
        `${ids.category} eq "${repairOption}"`,
        `${ids.occurred} gte "2026-10-01"`,
        `${ids.occurred} lte "2026-10-31"`,
      ],
      total: 12,
    },
    {
      moduleId: ids.invoices,
      logic: "and",
      conditions: [
        `${loggedAt} gte "2026-10-26T00:00:00+08:00"`,
        `${loggedAt} lt "2026-10-27T00:00:00+08:00"`,
      ],
      total: 12,
    },
    { moduleId: ids.checks, logic: "and", conditions: [], total: 12 },
  ]);
  await page.route(
    `**/api/views/data-sources/${ids.invoices}/fields**`,
    (route) =>
      route.fulfill({
        json: pageOf(
          [
            wireField({
              id: ids.invoiceStatus,
              module_id: ids.invoices,
              name: "Status",
              type: "select",
              position: 0,
              config: { options: [{ id: repairOption, label: "Repair" }] },
            }),
            wireField({
              id: loggedAt,
              module_id: ids.invoices,
              name: "Logged at",
              type: "datetime",
              position: 1,
            }),
          ],
          { limit: 100 },
        ),
      }),
  );
  await page.goto(homeUrl);

  const figure = page.getByRole("link", {
    name: "Open the 12 Equipment",
    exact: true,
  });
  await expect(figure).toHaveText("12");
  await expect(
    card(page, "Different category values").getByRole("link"),
  ).toHaveCount(0);
  await expect(
    page.getByRole("link", {
      name: "Open the Equipment behind Total amount: 12",
      exact: true,
    }),
  ).toHaveText("12");
  // The widget menu's "Open the records" opens the same counted records.
  const href = await figure.getAttribute("href");
  await card(page, "Equipment")
    .getByRole("button", { name: "Equipment, actions" })
    .click();
  await expect(
    page.getByRole("menuitem", { name: "Open the records", exact: true }),
  ).toHaveAttribute("href", href ?? "");
  await page.keyboard.press("Escape");

  await figure.click();
  await expect(page).toHaveURL(
    new RegExp(`module=${ids.equipment}&changes=[A-Za-z0-9_-]+`),
  );
  await expect(
    page.getByText("Field service · 12 records", { exact: true }),
  ).toBeVisible();

  await page.goBack();
  await page
    .getByRole("link", { name: "Open the 12 Invoices", exact: true })
    .click();
  await expect(page).toHaveURL(new RegExp(`module=${ids.invoices}&changes=`));
  await expect(
    page.getByText("Finance · 12 records", { exact: true }),
  ).toBeVisible();

  await page.goBack();
  await page
    .getByRole("link", { name: "Open the 12 Quality checks", exact: true })
    .click();
  // No condition differs from the module's starting view, so the page keeps
  // no temporary changes in its address.
  await expect(page).toHaveURL(`/openview?section=views&module=${ids.checks}`);
  await expect(
    page.getByText("Field service · 12 records", { exact: true }),
  ).toBeVisible();
});

test("SI-C6.2: each table group row opens its group's records, and the empty group uses the stored empty operator", async ({
  page,
}) => {
  await installDashboardApi(page, {
    identity: manager,
    dashboards: [dashboardWire({ widgets: [checksTable(at(0, 0, 2, 2))] })],
  });
  await page.route("**/api/records/aggregate-snapshots", (route) => {
    const body = route.request().postDataJSON() as { queries: unknown[] };
    return route.fulfill({
      json: {
        items: body.queries.map(() =>
          pageOf(
            [
              wireBucket({
                key: repairOption,
                label: "Repair",
                value: 7,
                record_count: 7,
              }),
              wireBucket({
                key: null,
                label: "Unspecified",
                value: 2,
                record_count: 2,
              }),
            ],
            { limit: 100 },
          ),
        ),
      },
    });
  });
  await installModulePage(page, [
    {
      moduleId: ids.checks,
      logic: "and",
      conditions: [`${ids.checkStatus} eq "${repairOption}"`],
      total: 7,
    },
    {
      moduleId: ids.checks,
      logic: "and",
      conditions: [`${ids.checkStatus} empty null`],
      total: 2,
    },
  ]);
  await page.goto(homeUrl);

  const table = card(page, "Quality checks by Result");
  await table
    .getByRole("link", { name: "Open the Repair Result records", exact: true })
    .click();
  await expect(page).toHaveURL(new RegExp(`module=${ids.checks}&changes=`));
  await expect(
    page.getByText("Field service · 7 records", { exact: true }),
  ).toBeVisible();
  // A manager of the module sees the link's conditions as unsaved (UF-1.3).
  await expect(
    page.getByText("Unsaved changes", { exact: true }),
  ).toBeVisible();

  await page.goBack();
  await table
    .getByRole("link", {
      name: "Open the Unspecified Result records",
      exact: true,
    })
    .click();
  await expect(
    page.getByText("Field service · 2 records", { exact: true }),
  ).toBeVisible();
});

test("SI-C6.5: a reader's group-row link opens the counted records as temporary changes, with no Unsaved changes and no view write", async ({
  page,
}) => {
  await installDashboardApi(page, { identity: reader });
  const modulePage = await installModulePage(page, [
    {
      moduleId: ids.checks,
      logic: "and",
      conditions: [`${ids.checkStatus} eq "${repairOption}"`],
      total: 7,
    },
  ]);
  await page.goto(homeUrl);
  await card(page, "Quality checks by Result")
    .getByRole("link", { name: "Open the Repair Result records", exact: true })
    .click();
  await expect(page).toHaveURL(
    new RegExp(`module=${ids.checks}&changes=[A-Za-z0-9_-]+`),
  );
  await expect(
    page.getByText("Field service · 7 records", { exact: true }),
  ).toBeVisible();
  await expect(page.getByText("Unsaved changes", { exact: true })).toHaveCount(
    0,
  );
  expect(modulePage.viewWrites).toEqual([]);
});

test("SI-C6.6: at 390 px a Number figure and a group row are 44 px targets that open with the keyboard and a tap", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await installDashboardApi(page, { identity: manager });
  await installModulePage(page, []);
  await page.goto(homeUrl);

  const figure = page.getByRole("link", {
    name: "Open the 12 Equipment",
    exact: true,
  });
  await expect(figure).toBeVisible();
  expect((await figure.boundingBox())?.height).toBeGreaterThanOrEqual(44);
  await figure.focus();
  await page.keyboard.press("Enter");
  // The figure has no condition, so the address keeps no changes.
  await expect(page).toHaveURL(
    `/openview?section=views&module=${ids.equipment}`,
  );

  await page.goBack();
  const row = card(page, "Quality checks by Result").getByRole("link", {
    name: "Open the Repair Result records",
    exact: true,
  });
  await expect(row).toBeVisible();
  expect((await row.boundingBox())?.height).toBeGreaterThanOrEqual(44);
  await row.click();
  await expect(page).toHaveURL(new RegExp(`module=${ids.checks}&changes=`));
});

test("SI-C6.4: at 390 px each records widget row opens its record with the keyboard and a tap", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await installDashboardApi(page, {
    identity: manager,
    dashboards: [
      dashboardWire({
        widgets: [
          widget("records", at(0, 0, 4, 2), {
            version: 1,
            query: {
              module_id: ids.equipment,
              definition: {
                ...definition,
                columns: [
                  { field_id: nameField, expected_type: "text" },
                  { field_id: ids.category, expected_type: "select" },
                ],
              },
            },
          }),
        ],
      }),
    ],
  });
  const records = await installNamedEquipment(page);
  await page.goto(homeUrl);

  const north = page.getByRole("link", {
    name: "North pump, open record",
    exact: true,
  });
  await expect(north).toBeVisible();
  expect((await north.boundingBox())?.height).toBeGreaterThanOrEqual(44);
  await north.focus();
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(
    `/openview?section=views&module=${ids.equipment}&record=${records[0].id}`,
  );

  await page.goBack();
  const south = page.getByRole("link", {
    name: "South valve, open record",
    exact: true,
  });
  await expect(south).toBeVisible();
  expect((await south.boundingBox())?.height).toBeGreaterThanOrEqual(44);
  await south.click();
  await expect(page).toHaveURL(
    `/openview?section=views&module=${ids.equipment}&record=${records[1].id}`,
  );
});

test("SI-C6.5: when no exact link can be made, the figure stays plain and the menu reads Open <module> with the widget's conditions", async ({
  page,
}) => {
  await installDashboardApi(page, {
    identity: manager,
    dashboards: [
      dashboardWire({
        widgets: [
          // "Any condition" over two conditions cannot take the window.
          widget("summary", at(0, 0, 1, 1), {
            version: 1,
            query: {
              ...groupQuery(ids.equipment, ids.category),
              definition: {
                ...definition,
                logic: "or",
                filters: [repairOption, inspectionOption].map((value) => ({
                  field_id: ids.category,
                  expected_type: "select",
                  operator: "eq",
                  value,
                })),
              },
              date_field: { field_id: ids.occurred, expected_type: "date" },
              from_date: "2026-10-01",
              to_date: "2026-10-31",
            },
          }),
        ],
      }),
    ],
  });
  await page.goto(homeUrl);
  const number = card(page, "Equipment");
  await expect(number).toContainText("12");
  await expect(number.getByRole("link")).toHaveCount(0);
  await number.getByRole("button", { name: "Equipment, actions" }).click();
  await expect(
    page.getByRole("menuitem", { name: "Open the records", exact: true }),
  ).toHaveCount(0);
  await expect(
    page.getByRole("menuitem", { name: "Open Equipment", exact: true }),
  ).toHaveAttribute(
    "href",
    new RegExp(`module=${ids.equipment}&changes=[A-Za-z0-9_-]+$`),
  );
});

test("SI-C6.6: from 768 px group and record rows are 32 px, a record row's name starts with its cell text, and the table pager stays in its card", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1024, height: 768 });
  await installDashboardApi(page, {
    identity: manager,
    dashboards: [
      dashboardWire({
        widgets: [
          // Category first: the row's name starts with "Repair".
          widget("records", at(0, 0, 2, 2), {
            version: 1,
            query: {
              module_id: ids.equipment,
              definition: {
                ...definition,
                columns: [
                  { field_id: ids.category, expected_type: "select" },
                  { field_id: nameField, expected_type: "text" },
                ],
              },
            },
          }),
          checksTable(at(2, 0, 2, 2)),
        ],
      }),
    ],
  });
  await installNamedEquipment(page);
  await page.goto(homeUrl);

  const record = page.getByRole("link", {
    name: "Repair, open record North pump",
    exact: true,
  });
  const group = card(page, "Quality checks by Result").getByRole("link", {
    name: "Open the Repair Result records",
    exact: true,
  });
  await expect(group).toBeVisible();
  expect((await group.boundingBox())?.height).toBe(32);
  await expect(record).toBeVisible();
  expect((await record.boundingBox())?.height).toBe(32);
  const table = await card(page, "Quality checks by Result").boundingBox();
  const pager = await card(page, "Quality checks by Result")
    .getByRole("navigation", { name: "Table pages" })
    .boundingBox();
  expect((pager?.y ?? 0) + (pager?.height ?? 0)).toBeLessThanOrEqual(
    (table?.y ?? 0) + (table?.height ?? 0),
  );
});
