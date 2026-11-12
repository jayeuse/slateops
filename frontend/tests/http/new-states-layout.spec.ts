import { expect, test, type Page } from "./helpers/test";
import { group, fixtureId, ids, mockAccessApi } from "./helpers/access-api";
import {
  createEntry,
  elementBar,
  liveBinding,
  openAuthenticatedSandbox,
} from "./helpers/sandbox-api";
import { wireWorkspace } from "../helpers/wire";
import type { Design } from "../../src/components/systems/sandbox/domain/model";
import type { SandboxDocumentV4 } from "../../src/components/systems/sandbox/domain/document";

// UX-C32 (docs/specs/sandbox-ux-redesign.md): every state that the Build
// create surface and the setup choices added fits the window. From 1280px
// the page itself never scrolls; at 390 it never scrolls sideways. Each
// test opens one page and walks its states (Build B1, B3, B4, B5, B6, B8,
// B9, the review with Setup; Test E4; Access "no manager" rows; Manage
// "New departments").

const WIDE = [
  { width: 1280, height: 720 },
  { width: 1440, height: 900 },
  { width: 1920, height: 1080 },
] as const;
const PHONE = { width: 390, height: 844 } as const;
const SIZES = [...WIDE, PHONE] as const;

/** The page scroll the state causes: none from 1280; none sideways at 390. */
async function expectFits(page: Page, state: string) {
  const size = page.viewportSize()!;
  const overflow = () =>
    page.evaluate((wide) => {
      const root = document.scrollingElement!;
      const sideways = root.scrollWidth - window.innerWidth;
      return wide
        ? Math.max(root.scrollHeight - window.innerHeight, sideways)
        : sideways;
    }, size.width >= 1280);
  await expect
    .poll(overflow, {
      message: `${state} at ${size.width}x${size.height} scrolls the page`,
    })
    .toBeLessThanOrEqual(0);
}

const FINANCE_LIVE_ID = "00000000-0000-4000-8000-0000000000f1";

/** Sales is new (no live binding) with two modules; Finance is published. */
function salesAndFinance(): Design {
  const text = (id: string, name: string) => ({
    id,
    name,
    type: "Text" as const,
    required: false,
    value: "",
    options: "",
    closed: false,
    config: { kind: "text" as const, defaultValue: "" },
  });
  return {
    departments: [
      { id: "sales", name: "Sales", closed: false },
      { id: "finance", name: "Finance", closed: false },
    ],
    modules: [
      {
        id: "orders",
        department: "sales",
        name: "Orders",
        closed: false,
        fields: [text("orders-customer", "Customer")],
        x: 0,
        y: 48,
      },
      {
        id: "customers",
        department: "sales",
        name: "Customers",
        closed: false,
        fields: [],
        x: 0,
        y: 200,
      },
      {
        id: "invoices",
        department: "finance",
        name: "Invoices",
        closed: false,
        fields: [],
        x: 400,
        y: 48,
      },
    ],
    relationships: [],
    rules: [],
  };
}

/** The review of new Sales: its setup rows, less the items it clears. */
function salesReview(document: SandboxDocumentV4) {
  const setup = document.design.departments.find((item) => item.id === "sales")
    ?.setup ?? {
    groups: true,
    dashboard: true,
    category: true,
    channel: true,
  };
  const row = (kind: string, role: string, label: string) => ({
    kind,
    action: "create",
    sandboxId: `sales#${role}`,
    label,
  });
  return [
    {
      kind: "department",
      action: "create",
      sandboxId: "sales",
      label: "Sales",
    },
    ...(setup.groups
      ? [
          row("group", "managers", "Sales managers · manage"),
          row("group", "members", "Sales members · write"),
          row("group", "viewers", "Sales viewers · read"),
        ]
      : []),
    ...(setup.dashboard
      ? [row("dashboard", "dashboard", "Sales dashboard")]
      : []),
    row("board", "board", "Sales"),
    ...(setup.category ? [row("category", "category", "Sales")] : []),
    ...(setup.channel ? [row("channel", "channel", "Sales")] : []),
  ];
}

/** Opens Build on a selection; a phone shows the canvas for the bars. */
async function openBuild(page: Page, path: string) {
  await page.goto(path);
  if (page.viewportSize()!.width < 768)
    await page.getByRole("tab", { name: "Canvas" }).click();
}

for (const size of SIZES)
  test(`Build and review states fit the window at ${size.width}x${size.height}`, async ({
    page,
  }) => {
    await page.setViewportSize(size);
    await openAuthenticatedSandbox(page, salesAndFinance(), {
      bindings: [liveBinding("department", "finance", FINANCE_LIVE_ID)],
      previewChangesFor: salesReview,
    });
    await expectFits(page, "B1 nothing selected");

    // B3: a new department's bar with + Module and Setup.
    await openBuild(page, "/sandbox?department=sales");
    const salesBar = elementBar(page, "Sales");
    const setupControl = salesBar.getByRole("button", {
      name: "Setup for Sales",
      exact: true,
    });
    await expect(setupControl).toBeVisible();
    await expectFits(page, "B3 new department");

    // B9: Setup open, with Category off so the SD14 line shows.
    await setupControl.click();
    const setup = page.getByRole("dialog", { name: "Setup for Sales" });
    await setup.getByRole("checkbox", { name: "Category" }).click();
    await expect(
      setup.getByText("The channel goes in no category."),
    ).toBeVisible();
    await expectFits(page, "B9 Setup open");
    await page.keyboard.press("Escape");
    await expect(setup).toBeHidden();

    // B4: a module's bar with + Field and Connect.
    await openBuild(page, "/sandbox?module=orders");
    const ordersBar = elementBar(page, "Orders");
    await expect(
      ordersBar.getByRole("button", { name: "Add field to Orders" }),
    ).toBeVisible();
    await expectFits(page, "B4 module selected");

    // B5: the entry.
    await ordersBar
      .getByRole("button", { name: "Add field to Orders" })
      .click();
    const entry = createEntry(page, "Add field to Orders");
    await expect(
      entry.getByRole("textbox", { name: "Field name" }),
    ).toBeVisible();
    await expectFits(page, "B5 entry open");
    await page.keyboard.press("Escape");
    await expect(entry).toBeHidden();

    // B6: Connect.
    await ordersBar
      .getByRole("button", { name: "Connect Orders to another module" })
      .click();
    const connect = page.getByRole("dialog", { name: "Connect Orders to" });
    await expect(connect.getByRole("option").first()).toBeVisible();
    await expectFits(page, "B6 Connect open");
    await page.keyboard.press("Escape");
    await expect(connect).toBeHidden();

    // B8: Add from a template.
    await page
      .getByRole("toolbar", { name: "Canvas view controls" })
      .getByRole("button", { name: "Add department", exact: true })
      .click();
    await createEntry(page, "Add department")
      .getByRole("button", { name: "From a template" })
      .click();
    const template = page.getByRole("dialog", { name: "Add from a template" });
    await expect(
      template.getByRole("listbox", { name: "Template departments" }),
    ).toBeVisible();
    await expectFits(page, "B8 template dialog");
    await page.keyboard.press("Escape");
    await expect(template).toBeHidden();

    // The review with Sales's Setup control, then its popover.
    await page.getByRole("button", { name: "Review & Publish" }).click();
    const review = page.getByRole("dialog", { name: "Review & Publish" });
    const reviewSetup = review.getByRole("button", {
      name: "Setup for Sales: 1 item cleared",
    });
    await expect(reviewSetup).toBeVisible();
    await expectFits(page, "Review with Setup");
    await reviewSetup.click();
    await expect(
      page
        .getByRole("dialog", { name: "Setup for Sales" })
        .getByRole("checkbox", { name: "Channel" }),
    ).toBeVisible();
    await expectFits(page, "Review with the Setup popover open");
  });

// E4: a field whose settings allow no value; the result card opens in
// Change values and names it.
test("a Test result with a field that allows no value fits the window at every width", async ({
  page,
}) => {
  const design = salesAndFinance();
  design.modules[0]!.fields.push({
    id: "stage",
    name: "Stage",
    type: "Select",
    required: true,
    value: "",
    options: "",
    closed: false,
    config: { kind: "select", defaultValue: null, options: [] },
  });
  await page.setViewportSize(WIDE[0]);
  // One trigger listens to "added", so the reading offers Try it.
  await openAuthenticatedSandbox(page, design, {
    triggers: [
      {
        id: "name-orders",
        name: "Name new orders",
        enabled: true,
        priority: 1,
        trigger: { kind: "record-created", moduleId: "orders" },
        conditionGroup: { operator: "all", conditions: [] },
        actions: [
          {
            id: "name-orders-customer",
            kind: "set-field",
            target: { moduleId: "orders", fieldId: "orders-customer" },
            value: { kind: "literal", value: "Walk-in" },
          },
        ],
      },
    ],
  });
  await page.goto("/sandbox?section=test");
  const reading = page.getByRole("region", { name: "Reading", exact: true });
  await reading
    .getByRole("button", { name: "Try it: When a record is added" })
    .click();
  const stage = reading
    .getByRole("region", { name: "Example record", exact: true })
    .getByLabel("Stage");
  await expect(stage).toHaveAccessibleDescription(
    "Its settings allow no value. Enter one to run.",
  );
  for (const size of SIZES) {
    await page.setViewportSize(size);
    await expectFits(page, "Test E4");
  }
});

// SD-C14 rows (plan 11.1 A2): several departments without a manager, last
// in Needs attention.
test("Access no-manager rows fit the window at every width", async ({
  page,
}) => {
  const api = await mockAccessApi(page);
  const managers = fixtureId(620);
  api.groups.set(
    managers,
    group(
      managers,
      "Finance managers",
      [],
      [{ department_id: ids.finance, module_id: null, level: "manage" }],
    ),
  );
  api.departmentsWithoutManager = [ids.finance, ids.inventory];
  await page.setViewportSize(WIDE[0]);
  await page.goto("/access?view=overview");
  const rows = page.getByRole("listitem").filter({ hasText: "has no manager" });
  await expect(rows).toHaveCount(2);
  for (const size of SIZES) {
    await page.setViewportSize(size);
    await expect(rows.first()).toBeVisible();
    await expectFits(page, "Access no-manager rows");
  }
});

// Plan 11.2 M2: Manage › Organization "New departments" with Category off.
test("Manage New departments fits the window at every width", async ({
  page,
}) => {
  await page.route("**/api/workspace", (route) =>
    route.request().method() === "GET"
      ? route.fulfill({
          json: {
            ...wireWorkspace({
              id: "00000000-0000-4000-8000-000000000102",
              locale: "en-PH",
              timezone: "Asia/Manila",
              currency: "PHP",
              today: "2026-10-06",
              purge_enabled: false,
            }),
            department_setup_defaults: {
              groups: true,
              dashboard: true,
              category: true,
              channel: true,
            },
          },
        })
      : route.fallback(),
  );
  await page.setViewportSize(WIDE[0]);
  await page.goto("/manage?view=organization");
  const group = page
    .getByRole("region", { name: "Organization settings", exact: true })
    .getByRole("group", { name: "New departments", exact: true });
  await group.getByRole("checkbox", { name: "Category" }).click();
  await expect(
    group.getByText("The channel goes in no category."),
  ).toBeVisible();
  for (const size of SIZES) {
    await page.setViewportSize(size);
    await expect(group.getByText("Board · always created")).toBeAttached();
    await expectFits(page, "Manage New departments");
  }
});
