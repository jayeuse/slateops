import type { Page } from "@playwright/test";
import { expect, signedInAs, test } from "./helpers/test";
import {
  installOpenViewEventSource,
  sendOpenViewEvent,
} from "./helpers/openview-event-source";
import { openedPanel } from "./helpers/settled";

// docs/specs/openview-department-pages.md, DA1–DA9: the Departments section of
// the sidebar. Module pages themselves are covered in openview-views-api.

const ids = {
  sales: "00000000-0000-4000-8000-0000000d0001",
  finance: "00000000-0000-4000-8000-0000000d0002",
  inventory: "00000000-0000-4000-8000-0000000d0003",
  contacts: "00000000-0000-4000-8000-0000000d0011",
  quotes: "00000000-0000-4000-8000-0000000d0012",
  products: "00000000-0000-4000-8000-0000000d0013",
  invoices: "00000000-0000-4000-8000-0000000d0014",
};
const timestamp = "2026-10-01T00:00:00Z";

function page<T>(items: T[], url: URL) {
  return {
    items,
    pagination: {
      limit: Number(url.searchParams.get("limit") ?? 100),
      offset: 0,
      count: items.length,
      total: items.length,
      has_more: false,
      total_is_capped: false,
    },
  };
}

function department(id: string, name: string) {
  return {
    id,
    department_name: name,
    created_at: timestamp,
    updated_at: timestamp,
    deleted_at: null,
    is_deleted: false,
    performed_by: null,
  };
}

async function installCatalog(
  target: Page,
  modules: { id: string; name: string; department: string }[],
) {
  const state = { modules, refused: false, departmentQueries: [] as string[] };
  await target.route(
    (url) => url.pathname === "/api/departments",
    (route) => {
      const url = new URL(route.request().url());
      state.departmentQueries.push(url.search);
      return route.fulfill({
        // The server answers in Sandbox order when asked for created_at.
        json: page(
          [
            department(ids.sales, "Sales"),
            department(ids.finance, "Finance"),
            department(ids.inventory, "Inventory"),
          ],
          url,
        ),
      });
    },
  );
  await target.route(
    (url) => url.pathname === "/api/views/data-sources",
    (route) =>
      route.fulfill({
        ...(state.refused ? { status: 403 } : {}),
        json: page(
          state.modules.map((module) => ({
            id: module.id,
            name: module.name,
            department_id: module.department,
            title_field_id: null,
          })),
          new URL(route.request().url()),
        ),
      }),
  );
  return state;
}

const sidebar = (target: Page) =>
  target.getByRole("navigation", { name: "Main navigation" });

test("the sidebar lists readable departments in Sandbox order with their module pages, above the tools", async ({
  page: target,
}) => {
  const state = await installCatalog(target, [
    { id: ids.quotes, name: "Quotes", department: ids.sales },
    { id: ids.contacts, name: "Contacts", department: ids.sales },
    { id: ids.products, name: "Products", department: ids.inventory },
  ]);
  await target.goto("/platform?section=search");
  const nav = sidebar(target);
  const departments = nav.getByRole("list", { name: "Departments" });
  await expect(departments).toBeVisible();
  // Finance has no readable module, so it is not listed.
  await expect(
    departments.getByRole("button", { name: /^(Sales|Finance|Inventory)$/ }),
  ).toHaveText(["Sales", "Inventory"]);
  expect(
    state.departmentQueries.some((query) =>
      query.includes("sort_by=created_at"),
    ),
  ).toBe(true);
  await expect(nav.getByText("Tools", { exact: true })).toBeVisible();
  // No module page is open here, so every department starts closed.
  await expect(
    nav.getByRole("link", { name: "Contacts", exact: true }),
  ).toHaveCount(0);
  await departments.getByRole("button", { name: "Sales", exact: true }).click();
  const salesPages = nav.getByRole("list", { name: "Sales pages" });
  // The department's home dashboard comes first, then its Announcements
  // (BR1), then its module pages (BD1).
  await expect(salesPages.getByRole("link")).toHaveText([
    "Dashboard",
    "Announcements",
    "Contacts",
    "Quotes",
  ]);
  await expect(
    salesPages.getByRole("link", { name: "Announcements", exact: true }),
  ).toHaveAttribute("href", `/boards?department=${ids.sales}`);
  await expect(
    salesPages.getByRole("link", { name: "Dashboard", exact: true }),
  ).toHaveAttribute(
    "href",
    `/openview?section=dashboards&department=${ids.sales}`,
  );
  await expect(
    salesPages.getByRole("link", { name: "Quotes", exact: true }),
  ).toHaveAttribute("href", `/openview?section=views&module=${ids.quotes}`);
  // Reports live on module pages, so the sidebar has no OpenView item (DC9).
  await expect(
    nav.getByRole("button", { name: "OpenView", exact: true }),
  ).toHaveCount(0);
  await expect(
    nav.getByRole("link", { name: /^(Views|Dashboards|Charts|Reports)$/ }),
  ).toHaveCount(0);
});

test("an opened department stays open while the person moves between pages", async ({
  page: target,
}) => {
  await installCatalog(target, [
    { id: ids.products, name: "Products", department: ids.inventory },
  ]);
  await target.goto("/platform?section=search");
  const nav = sidebar(target);
  const inventory = nav.getByRole("button", {
    name: "Inventory",
    exact: true,
  });
  await inventory.click();
  await expect(
    nav.getByRole("link", { name: "Products", exact: true }),
  ).toBeVisible();
  await openedPanel(inventory);
  // Platform is the current group, so its sections are already listed.
  await nav.getByRole("link", { name: "Files", exact: true }).click();
  await expect(target).toHaveURL(/section=files/);
  await expect(
    nav.getByRole("link", { name: "Products", exact: true }),
  ).toBeVisible();
});

test("a module published in the Sandbox appears without a reload", async ({
  page: target,
}) => {
  await installOpenViewEventSource(target);
  const state = await installCatalog(target, [
    { id: ids.contacts, name: "Contacts", department: ids.sales },
  ]);
  await target.goto("/platform?section=search");
  const nav = sidebar(target);
  await expect(
    nav.getByRole("button", { name: "Sales", exact: true }),
  ).toBeVisible();
  await expect(
    nav.getByRole("button", { name: "Finance", exact: true }),
  ).toHaveCount(0);
  state.modules = [
    ...state.modules,
    { id: ids.invoices, name: "Invoices", department: ids.finance },
  ];
  await sendOpenViewEvent(target, "invalidate", { entity: "modules" });
  await expect(
    nav.getByRole("button", { name: "Finance", exact: true }),
  ).toBeVisible();
});

test("a refused catalog read hides the department and module names it held", async ({
  page: target,
}) => {
  await installOpenViewEventSource(target);
  const state = await installCatalog(target, [
    { id: ids.contacts, name: "Contacts", department: ids.sales },
  ]);
  await target.goto("/platform?section=search");
  const nav = sidebar(target);
  await expect(
    nav.getByRole("button", { name: "Sales", exact: true }),
  ).toBeVisible();
  state.refused = true;
  await sendOpenViewEvent(target, "invalidate", { entity: "modules" });
  await expect(nav.getByRole("list", { name: "Departments" })).toHaveCount(0);
  await expect(
    nav.getByRole("button", { name: "Sales", exact: true }),
  ).toHaveCount(0);
});

test("a person who reads no module sees no Departments section", async ({
  page: target,
}) => {
  await target.goto("/platform?section=search");
  const nav = sidebar(target);
  // The Tools stay: an administrator's Files group (UF-C7.3).
  await expect(
    nav.getByRole("button", { name: "Files", exact: true }),
  ).toBeVisible();
  await expect(nav.getByRole("list", { name: "Departments" })).toHaveCount(0);
  await expect(nav.getByText("Tools", { exact: true })).toHaveCount(0);
});

// docs/specs/ux-friction-pass.md DR-7.6: the Platform group is gone, and
// each /platform address still opens with its current checks.
test("UF-C7.4 a writer opens Import & export only by its address, where the administrator refusal shows, and notifications from the bell's View all", async ({
  page: target,
}) => {
  await signedInAs(target, {
    id: "00000000-0000-4000-8000-0000000000a7",
    role: "member",
    access: [{ department_id: ids.sales, module_id: null, level: "write" }],
  });
  await target.goto("/platform?section=import-export");
  await expect(
    target.getByRole("alert").filter({
      hasText:
        "Administrator permission is required to import and export records.",
    }),
  ).toBeVisible();
  const nav = sidebar(target);
  await expect(
    nav.getByRole("link", { name: "Files", exact: true }),
  ).toBeVisible();
  await expect(
    nav.getByRole("link", {
      name: /^(Import & export|Search|Notifications)$/,
    }),
  ).toHaveCount(0);
  await expect(
    nav.getByRole("button", { name: "Platform", exact: true }),
  ).toHaveCount(0);
  await target
    .getByRole("button", { name: "Notifications, 0 unread", exact: true })
    .click();
  await target.getByRole("link", { name: "View all", exact: true }).click();
  await expect(target).toHaveURL(/\/platform\?section=notifications$/);
  await expect(
    target.getByRole("region", { name: "Notifications", exact: true }),
  ).toBeVisible();
});

test("the collapsed rail shows one Departments button that opens the sidebar", async ({
  page: target,
}) => {
  await installCatalog(target, [
    { id: ids.contacts, name: "Contacts", department: ids.sales },
  ]);
  await target.goto("/platform?section=search");
  await target.getByRole("button", { name: "Collapse sidebar" }).click();
  const nav = sidebar(target);
  await expect(
    nav.getByRole("button", { name: "Sales", exact: true }),
  ).toHaveCount(0);
  await nav.getByRole("button", { name: "Departments", exact: true }).click();
  await expect(
    nav.getByRole("button", { name: "Sales", exact: true }),
  ).toBeVisible();
});

test("a module page with no readable module says why, and only an administrator is offered the Sandbox", async ({
  page: target,
}) => {
  // The fixture's catalog is empty: nothing this person can read.
  await target.goto("/openview?section=views");
  await expect(
    target.getByRole("heading", { level: 2, name: "Nothing published yet" }),
  ).toBeVisible();
  await expect(
    target.getByRole("link", { name: "Open Sandbox", exact: true }),
  ).toBeVisible();
  // With no module to name, the breadcrumb names the records landing.
  await expect(
    target
      .getByRole("navigation", { name: "breadcrumb" })
      .locator('[aria-current="page"]'),
  ).toHaveText("Records");

  await signedInAs(target, {
    id: "00000000-0000-4000-8000-0000000000aa",
    role: "member",
  });
  await target.reload();
  await expect(
    target.getByRole("heading", { level: 2, name: "No records to show yet" }),
  ).toBeVisible();
  await expect(target.getByText(/Access › Groups/)).toBeVisible();
  await expect(
    target.getByRole("link", { name: "Open Sandbox", exact: true }),
  ).toHaveCount(0);
});

// A group's pages hang on a guide line, as a tree line marks children. The
// current page is its blue, bold label, with no fill and no bar (Human
// Owner, 2026-11-13). A closed group shows that label colour on its own row.
async function guide(target: Page) {
  return sidebar(target).evaluate((nav) => {
    const probe = document.createElement("span");
    probe.style.color = "var(--action-text)";
    nav.append(probe);
    const ink = getComputedStyle(probe).color;
    probe.remove();
    const list = nav.querySelector('[aria-label="Sales pages"]');
    const items = list ? [...list.querySelectorAll(":scope > li")] : [];
    const lines = items.map((item) => {
      const line = getComputedStyle(item, "::before");
      return {
        width: line.width,
        edge: line.borderLeftWidth,
        radius: line.borderBottomLeftRadius,
      };
    });
    const current = nav.querySelector<HTMLElement>('[aria-current="page"]');
    const header = [...nav.querySelectorAll("button")].find(
      (button) => button.getAttribute("aria-label") === "Sales",
    );
    const look = (element: HTMLElement | undefined | null) =>
      element
        ? {
            fill: getComputedStyle(element).backgroundColor,
            color: getComputedStyle(element).color,
            weight: getComputedStyle(element).fontWeight,
            mark: getComputedStyle(element, "::before").backgroundColor,
          }
        : null;
    return {
      ink,
      lines,
      bars: nav.querySelectorAll('[data-slot="sidebar-active-indicator"]')
        .length,
      current: current
        ? { text: current.textContent?.trim(), ...look(current) }
        : null,
      header: look(header),
    };
  });
}

test("the current page is its blue label on its group's guide line, with no fill and no bar", async ({
  page: target,
}) => {
  await target.setViewportSize({ width: 1440, height: 900 });
  await installCatalog(target, [
    { id: ids.quotes, name: "Quotes", department: ids.sales },
    { id: ids.contacts, name: "Contacts", department: ids.sales },
  ]);
  await target.goto(`/openview?section=views&module=${ids.contacts}`);
  const nav = sidebar(target);
  await expect(
    nav
      .getByRole("list", { name: "Sales pages" })
      .getByRole("link", { name: "Contacts", exact: true }),
  ).toHaveAttribute("aria-current", "page");
  const shown = await guide(target);
  // A 1 px guide line runs down the group; the last page turns into it.
  expect(shown.lines.length).toBeGreaterThan(1);
  for (const line of shown.lines.slice(0, -1)) expect(line.width).toBe("1px");
  expect(shown.lines.at(-1)?.edge).toBe("1px");
  expect(shown.lines.at(-1)?.radius).not.toBe("0px");
  // The current page: blue and bold, no fill, no bar.
  expect(shown.bars).toBe(0);
  expect(shown.current).toMatchObject({
    text: "Contacts",
    fill: "rgba(0, 0, 0, 0)",
    color: shown.ink,
    weight: "600",
  });
  // Its open group takes no fill and no ink.
  expect(shown.header?.fill).toBe("rgba(0, 0, 0, 0)");
  expect(shown.header?.color).not.toBe(shown.ink);
});

test("a closed group shows the current page's label colour on its own row", async ({
  page: target,
}) => {
  await target.setViewportSize({ width: 1440, height: 900 });
  await installCatalog(target, [
    { id: ids.contacts, name: "Contacts", department: ids.sales },
  ]);
  await target.goto(`/openview?section=views&module=${ids.contacts}`);
  const nav = sidebar(target);
  const header = nav.getByRole("button", { name: "Sales", exact: true });
  await expect(header).toHaveAttribute("aria-expanded", "true");
  await header.click();
  await expect(header).toHaveAttribute("aria-expanded", "false");
  await expect
    .poll(async () => {
      const shown = await guide(target);
      return shown.header?.color === shown.ink;
    })
    .toBe(true);
  const shown = await guide(target);
  expect(shown.header).toMatchObject({
    fill: "rgba(0, 0, 0, 0)",
    weight: "600",
    mark: "rgba(0, 0, 0, 0)",
  });
});
